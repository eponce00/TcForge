"""Bind fresh build/test evidence to exact source, tooling and library bytes.

Tokens must be created before XAE mutations. Finish only after closing XAE and
restoring the original source profiles. These local records detect stale/mixed
artifacts; they are not signed attestations or proof of power-loss durability.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import re
from pathlib import Path
import time
import uuid
import xml.etree.ElementTree as ET

from check_test_report import source_suites, validate

ROOT = Path(__file__).resolve().parents[1]
SOURCE_EXTENSIONS = {'.tcpou', '.tcdut', '.tcgvl', '.tcio', '.tctto', '.plcproj', '.tsproj',
                     '.sln', '.xti', '.tclibcat', '.tcvis', '.tctxt', '.tcgtlo', '.tcvmo'}
BUILD_RESULTS = ('TcForge-library-check-all.json', 'TcForge.Tests-build.json',
                 'TcForge-build.json', 'TcForge.Simulation-build.json')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def file_record(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': digest(path)}


def verify_file(record):
    require(digest(record['path']) == record['sha256'], 'Changed evidence/library file: ' + record['path'])


def build_toolchain_digest(path):
    # Only these two top-level fields describe workflow rather than compilation.
    # Qualification is still independently enforced by the release gate.
    value = read(path)
    value.pop('notes', None)
    value.pop('qualification', None)
    return canonical_digest(value)


def source_snapshot(root):
    root = Path(root).resolve()
    paths = [p for p in (root / 'TwinCAT').rglob('*') if p.is_file() and p.suffix.lower() in SOURCE_EXTENSIONS]
    paths += [p for p in (root / 'scripts').rglob('*') if p.is_file() and p.suffix.lower() in {'.py', '.ps1'}]
    paths += [root / 'toolchain.json', root / 'dependencies.lock.json']
    workflow = root / '.github/workflows'
    if workflow.exists():
        paths += [p for p in workflow.rglob('*') if p.is_file()]
    files = {p.relative_to(root).as_posix(): digest(p) for p in sorted(paths)}
    toolchain_hash = build_toolchain_digest(root / 'toolchain.json')
    files['toolchain.json'] = toolchain_hash
    require(any(name.endswith('.plcproj') for name in files), 'No PLC project source found')
    return {'files': files, 'sha256': canonical_digest(files), 'toolchainSha256': toolchain_hash}


def helper_snapshot(helper_root):
    helper_root = Path(helper_root).resolve(strict=True)
    source = {}
    binary = {}
    for path in helper_root.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(helper_root)
        parts = set(relative.parts)
        if parts & {'.git', 'obj', 'artifacts', 'node_modules', '.venv'}:
            continue
        if 'bin' not in parts and path.suffix.lower() in {'.cs', '.csproj', '.sln', '.props', '.targets', '.config'}:
            source[relative.as_posix()] = digest(path)
        elif (
            'bin' in parts
            and any(part.startswith('Release') for part in parts)
            and path.suffix.lower() in {'.exe', '.dll', '.config'}
        ):
            binary[relative.as_posix()] = digest(path)
    require(source and binary, 'Helper source and Release binaries are both required')
    files = dict(source=source, binary=binary)
    return {'root': str(helper_root), **files, 'sha256': canonical_digest(files)}


def verify_snapshot(root, snapshot, helper):
    require(source_snapshot(root) == snapshot, 'Source/toolchain changed since evidence snapshot; restore profiles or rebuild')
    require(helper_snapshot(helper['root']) == helper, 'Build helper source/binaries changed since evidence snapshot')


def fresh(path, started):
    require(Path(path).stat().st_mtime_ns >= started, 'Artifact predates this run: ' + str(path))


def git_metadata(root):
    """Record revision context without retaining status paths or requiring a clean tree."""
    root = Path(root).resolve()
    if not (root / '.git').exists():
        return {'commit': None, 'dirty': None}
    try:
        revision = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', 'HEAD'],
                                  check=True, capture_output=True, text=True, timeout=15).stdout.strip()
        status = subprocess.run(['git', '-C', str(root), 'status', '--porcelain=v1', '--untracked-files=normal'],
                                check=True, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('Cannot record Git revision/dirty context for this repository') from exc
    require(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', revision) is not None, 'Invalid Git commit identity')
    return {'commit': revision, 'dirty': bool(status.stdout.strip())}


def verify_git_metadata(root, value):
    metadata = value.get('git')
    require(isinstance(metadata, dict), 'Missing Git revision context')
    commit = metadata.get('commit')
    if commit is None:
        require(metadata.get('dirty') is None and not (Path(root) / '.git').exists(),
                'A real Git repository requires captured commit and dirty context')
    else:
        require(isinstance(commit, str) and re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit) is not None
                and isinstance(metadata.get('dirty'), bool), 'Invalid Git revision context')
    # Commit context is informative; exact source/tooling hashes authorize evidence.
    # A later commit with byte-identical source need not invalidate the build.


def begin_build(root, helper_root, output):
    value = {'schemaVersion': 1, 'kind': 'pending-build', 'buildId': uuid.uuid4().hex,
             'startedNs': time.time_ns(), 'git': git_metadata(root),
             'source': source_snapshot(root), 'helper': helper_snapshot(helper_root)}
    write(output, value)
    return value


def clean_build_result(path, version, started):
    fresh(path, started)
    value = read(path)
    require(value.get('RequestedXaeVersion') == version and value.get('EffectiveXaeVersion') == version,
            'Build XAE identity differs from toolchain: ' + str(path))
    result = value.get('Result', value)
    require(result.get('Success') is True and result.get('ErrorCount') == 0 and result.get('WarningCount') == 0,
            'Build/check did not complete with zero errors and warnings: ' + str(path))
    return file_record(path)


def finish_build(root, token, library, dependencies, output):
    value = read(token)
    require(value.get('kind') == 'pending-build', 'Build token was already consumed or is invalid')
    verify_snapshot(root, value['source'], value['helper'])
    lock = read(Path(root) / 'toolchain.json')
    results = [clean_build_result(Path(root) / 'artifacts' / name, lock['xaeBaseline'], value['startedNs'])
               for name in BUILD_RESULTS]
    fresh(library, value['startedNs'])
    require(Path(dependencies).resolve() == (Path(root) / 'dependencies.lock.json').resolve(),
            'Build must use the snapshotted repository dependency lock')
    captures = {name: file_record(Path(root) / 'artifacts' / (name + '-dependencies.xml'))
                for name in ('TcForge.Library', 'TcForge.Tests', 'TcForge', 'TcForge.Simulation')}
    for record in captures.values():
        fresh(record['path'], value['startedNs'])
    result = dict(value, kind='build', completedNs=time.time_ns(), library=file_record(library),
                  dependencies=file_record(dependencies), dependencyCaptures=captures, results=results, platform=lock['platform'])
    # Dependency capture validation is shared with the dependency capture tool.
    verify_dependencies(result['dependencies'], result['dependencyCaptures'])
    bundle = Path(root).resolve() / 'artifacts' / 'builds' / value['buildId']
    bundle.mkdir(parents=True, exist_ok=False)
    def retain(record, name):
        destination = bundle / name
        shutil.copy2(record['path'], destination)
        retained = file_record(destination)
        require(retained['sha256'] == record['sha256'], 'Evidence changed during bundle capture')
        return retained
    result['library'] = retain(result['library'], 'TcForge.library')
    result['dependencies'] = retain(result['dependencies'], 'dependencies.lock.json')
    result['results'] = [retain(record, Path(record['path']).name) for record in result['results']]
    result['dependencyCaptures'] = {name: retain(record, name + '-dependencies.xml')
                                    for name, record in result['dependencyCaptures'].items()}
    canonical = bundle / 'build-evidence.json'
    result['immutableManifestPath'] = str(canonical)
    verify_snapshot(root, value['source'], value['helper'])
    write(canonical, result)
    if Path(output).resolve() != canonical:
        write(output, result)
    write(token, dict(value, kind='consumed-build'))
    return result


def verify_dependencies(record, captures):
    verify_file(record)
    from dependency_lock import check_project
    expected = {'TcForge.Library', 'TcForge.Tests', 'TcForge', 'TcForge.Simulation'}
    require(set(captures) == expected, 'Missing dependency resolution capture')
    for name, capture in captures.items():
        verify_file(capture)
        check_project(Path(record['path']), name, Path(capture['path']))


def verify_build(root, manifest, library):
    value = read(manifest)
    require(value.get('schemaVersion') == 1 and value.get('kind') == 'build', 'Invalid build evidence')
    verify_git_metadata(root, value)
    require(digest(value['immutableManifestPath']) == digest(manifest),
            'Requested build manifest differs from its immutable bundle')
    verify_snapshot(root, value['source'], value['helper'])
    verify_file(value['library'])
    require(digest(library) == value['library']['sha256'], 'Requested library differs from bound build artifact')
    verify_dependencies(value['dependencies'], value['dependencyCaptures'])
    lock = read(Path(root) / 'toolchain.json')
    require(value['platform'] == lock['platform'], 'Build platform differs from toolchain')
    require(len(value['results']) == len(BUILD_RESULTS) and
            {Path(record['path']).name for record in value['results']} == set(BUILD_RESULTS),
            'Missing consumer/check build evidence')
    for record in value['results']:
        verify_file(record)
        clean_build_result(record['path'], lock['xaeBaseline'], value['startedNs'])
    return value


def begin_test(root, manifest, library, cycle_ms, target, output, installed_library=None):
    require(cycle_ms in (1, 10), 'Only qualified 1 ms and 10 ms periods are supported')
    build = verify_build(root, manifest, library)
    installed = file_record(installed_library) if installed_library else None
    if installed:
        require(installed['sha256'] == build['library']['sha256'], 'Installed TcForge library differs from build artifact')
    value = {'schemaVersion': 1, 'kind': 'pending-test', 'runId': uuid.uuid4().hex,
             'startedNs': time.time_ns(), 'build': file_record(build['immutableManifestPath']), 'buildId': build['buildId'],
             'source': build['source'], 'helper': build['helper'], 'library': build['library'],
             'installedLibrary': installed, 'cycleMs': cycle_ms, 'target': target, 'platform': build['platform'],
             'adsPort': read(Path(root) / 'toolchain.json')['testAdsPort']}
    write(output, value)
    return value


def report_context(token, helper, target, port, cycle_ms):
    value = read(token)
    require(value.get('kind') == 'pending-test', 'Report requires an unconsumed run token')
    require(value['target'] == target and value['cycleMs'] == cycle_ms and value['adsPort'] == port,
            'Exporter target/port/period differs from run token')
    helper = Path(helper).resolve(strict=True)
    try:
        relative = helper.relative_to(Path(value['helper']['root'])).as_posix()
    except ValueError:
        raise ValueError('Exporter helper is outside the bound helper root') from None
    require(value['helper']['binary'].get(relative) == digest(helper), 'Exporter helper binary differs from build provenance')
    return report_properties(token)


def report_properties(token):
    value = read(token)
    require(value.get('kind') == 'pending-test', 'Report requires an unconsumed run token')
    return {'buildId': value['buildId'], 'runId': value['runId'],
            'sourceSha256': value['source']['sha256'], 'librarySha256': value['library']['sha256'],
            'toolchainSha256': value['source']['toolchainSha256'],
            'expectedCycleTime100ns': str(value['cycleMs'] * 10000), 'platform': value['platform']}


def verify_report(root, report, value):
    declared = source_suites(Path(root))
    identities = {(suite, name) for suite, names in declared.items() for name in names}
    validate(report, len(identities), identities)
    expected = {'buildId': value['buildId'], 'runId': value['runId'],
                'sourceSha256': value['source']['sha256'], 'librarySha256': value['library']['sha256'],
                'toolchainSha256': value['source']['toolchainSha256'], 'platform': value['platform'],
                'expectedCycleTime100ns': str(value['cycleMs'] * 10000),
                'cycleTime100ns': str(value['cycleMs'] * 10000), 'target': value['target'],
                'adsPort': str(read(Path(root) / 'toolchain.json')['testAdsPort'])}
    groups = list(ET.parse(report).getroot().iter('testsuite'))
    require(groups, 'Report has no suite properties')
    bound_cases = 0
    for group in groups:
        direct_cases = group.findall('testcase')
        if not direct_cases:
            continue
        bound_cases += len(direct_cases)
        properties = group.findall('properties/property')
        require(len({p.get('name') for p in properties}) == len(properties), 'Duplicate report properties')
        actual = {p.get('name'): p.get('value') for p in properties}
        require(all(actual.get(key) == entry for key, entry in expected.items()),
                'Report identity/period/target differs from the bound run')
    require(bound_cases == len(identities), 'Every report test must belong to a suite with bound properties')


def finish_test(root, token, report, activation_build):
    value = read(token)
    require(value.get('kind') == 'pending-test', 'Test token was already consumed or is invalid')
    verify_file(value['build'])
    verify_build(root, value['build']['path'], value['library']['path'])
    verify_snapshot(root, value['source'], value['helper'])
    if value['installedLibrary']:
        verify_file(value['installedLibrary'])
    fresh(report, value['startedNs'])
    version = read(Path(root) / 'toolchain.json')['xaeBaseline']
    activation = clean_build_result(activation_build, version, value['startedNs'])
    verify_report(root, report, value)
    verify_snapshot(root, value['source'], value['helper'])
    bundle = Path(root).resolve() / 'artifacts' / 'runs' / value['runId']
    bundle.mkdir(parents=True, exist_ok=False)
    retained = bundle / 'activation-build.json'
    shutil.copy2(activation['path'], retained)
    activation_copy = file_record(retained)
    require(activation_copy['sha256'] == activation['sha256'], 'Activation build evidence changed during capture')
    receipt = dict(value, kind='test', completedNs=time.time_ns(), report=file_record(report), activationBuild=activation_copy)
    write(str(report) + '.evidence.json', receipt)
    write(token, dict(value, kind='consumed-test'))
    return receipt


def validate_release(root, manifest, library, reports):
    build = verify_build(root, manifest, library)
    require(len(reports) == 2, 'Release requires exactly one 1 ms and one 10 ms report')
    periods = set()
    runs = set()
    for report in reports:
        value = read(str(report) + '.evidence.json')
        require(value.get('kind') == 'test' and value.get('schemaVersion') == 1, 'Invalid test receipt')
        require(value['buildId'] == build['buildId'] and value['build']['sha256'] == digest(manifest),
                'Test report belongs to a different build')
        require(value['platform'] == build['platform'], 'Test platform differs from build')
        require(value['source'] == build['source'] and value['library'] == build['library'] and value['helper'] == build['helper'],
                'Test receipt source/library/tooling differs from build')
        verify_file(value['report'])
        require(digest(report) == value['report']['sha256'], 'Test report bytes differ from receipt')
        require(value.get('installedLibrary'), 'Release requires verified installed TcForge library identity')
        verify_file(value['installedLibrary'])
        require(value['installedLibrary']['sha256'] == build['library']['sha256'], 'Installed library was not the built artifact')
        verify_file(value['activationBuild'])
        clean_build_result(value['activationBuild']['path'], read(Path(root) / 'toolchain.json')['xaeBaseline'], value['startedNs'])
        verify_report(root, report, value)
        periods.add(value['cycleMs'])
        runs.add(value['runId'])
    require(periods == {1, 10} and len(runs) == 2, 'Release requires distinct complete 1 ms and 10 ms runs')
    return build['buildId']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    begin = sub.add_parser('begin-build')
    begin.add_argument('--helper-root', type=Path, required=True)
    begin.add_argument('--output', type=Path, required=True)
    finish = sub.add_parser('finish-build')
    finish.add_argument('--token', type=Path, required=True)
    finish.add_argument('--library', type=Path, required=True)
    finish.add_argument('--dependencies', type=Path, required=True)
    finish.add_argument('--output', type=Path, required=True)
    start_test = sub.add_parser('begin-test')
    start_test.add_argument('--build', type=Path, required=True)
    start_test.add_argument('--library', type=Path, required=True)
    start_test.add_argument('--cycle-ms', type=int, choices=(1, 10), required=True)
    start_test.add_argument('--target', required=True)
    start_test.add_argument('--installed-library', type=Path)
    start_test.add_argument('--output', type=Path, required=True)
    end_test = sub.add_parser('finish-test')
    end_test.add_argument('--token', type=Path, required=True)
    end_test.add_argument('--report', type=Path, required=True)
    end_test.add_argument('--activation-build', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'begin-build':
        result = begin_build(args.root, args.helper_root, args.output)
    elif args.command == 'finish-build':
        result = finish_build(args.root, args.token, args.library, args.dependencies, args.output)
    elif args.command == 'begin-test':
        result = begin_test(args.root, args.build, args.library, args.cycle_ms, args.target, args.output, args.installed_library)
    else:
        result = finish_test(args.root, args.token, args.report, args.activation_build)
    print(json.dumps({'kind': result['kind'], 'buildId': result['buildId'], 'runId': result.get('runId')}))


if __name__ == '__main__':
    main()
