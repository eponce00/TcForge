"""Canonicalize XAE's effective direct/transitive resolutions and enforce a reviewed lock."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

PROJECTS = ('TcForge.Library', 'TcForge.Tests', 'TcForge', 'TcForge.Simulation')


def parse_resolution_xml(path):
    root = ET.parse(path).getroot()
    # Accept namespaced captures without depending on a particular XML prefix.
    for node in root.iter():
        node.tag = node.tag.rsplit('}', 1)[-1]
    references = root.findall('.//IECProjectDef/References')
    if len(references) != 1 or not len(references[0]):
        raise ValueError('Expected exactly one nonempty IECProjectDef/References section')
    libraries, edges, bindings = {}, set(), {}
    signature_versions, signature_ids = {}, set()

    def required(node, field):
        value = (node.findtext(field) or '').strip()
        if not value:
            raise ValueError(f'Missing effective library {field}')
        return value

    for item in root.findall('./LibrarySignatures/Library'):
        name, version, distributor = (required(item, field) for field in ('LibraryName', 'Version', 'Distributor'))
        if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', version):
            raise ValueError(f'Nonexact library signature version for {name}: {version}')
        identity = f'{name}, {version} ({distributor})'
        libraries[identity] = dict(id=identity, name=name, version=version, distributor=distributor)
        signature_ids.add(identity)
        signature_versions.setdefault((name, distributor), set()).add(version)

    def resolution(node):
        name, version, distributor = (required(node, field) for field in ('LibraryName', 'Version', 'Distributor'))
        if version == '*':
            observed = signature_versions.get((name, distributor), set())
            if len(observed) != 1:
                raise ValueError(f'Unresolved/ambiguous effective version for {name}: actual library signatures required')
            version = next(iter(observed))
        if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', version):
            raise ValueError(f'Unresolved/nonexact effective version for {name}: {version}')
        identity = f'{name}, {version} ({distributor})'
        if signature_ids and identity not in signature_ids:
            raise ValueError(f'Reference resolution absent from actual library signatures: {identity}')
        value = dict(id=identity, name=name, version=version, distributor=distributor)
        if identity in libraries and libraries[identity] != value:
            raise ValueError(f'Ambiguous library identity: {identity}')
        libraries[identity] = value
        for dep in node.findall('Dependencies/Dependency'):
            effective = dep.find('EffectiveResolution')
            placeholder = (dep.findtext('PlaceholderName') or '').strip()
            if effective is None:
                if dep.get('isPlaceholder') == 'true' or placeholder:
                    raise ValueError(f'Unresolved transitive placeholder {placeholder} in {identity}')
                effective = dep
            child = resolution(effective)
            edges.add((identity, child, placeholder))
        return identity

    for ref in references[0]:
        if ref.tag not in ('PlaceholderReference', 'LibraryReference'):
            raise ValueError(f'Unsupported reference element: {ref.tag}')
        binding = (ref.findtext('PlaceholderName') or ref.findtext('LibItemName') or ref.findtext('LibraryName') or '').strip()
        if not binding or binding in bindings:
            raise ValueError(f'Missing/duplicate reference binding: {binding}')
        effective = ref.find('EffectiveResolution')
        if effective is None:
            if ref.tag == 'PlaceholderReference':
                raise ValueError(f'Unresolved direct placeholder: {binding}')
            effective = ref
        bindings[binding] = dict(binding=binding, namespace=(ref.findtext('Namespace') or '').strip(),
                                 systemLibrary=ref.get('systemLibrary', 'false') == 'true', library=resolution(effective))
    return dict(references=[bindings[key] for key in sorted(bindings)],
                libraries=[libraries[key] for key in sorted(libraries)],
                signatureLibraries=sorted(signature_ids),
                dependencies=[dict(library=a, dependency=b, placeholder=c) for a, b, c in sorted(edges)])


def combine_capture(xml_path, signatures_path, output):
    project = ET.parse(xml_path).getroot()
    if project.tag != 'TreeItem':
        raise ValueError('Combine expects an unwrapped IEC project TreeItem capture')
    # ProduceAllLibrarySignatures returns an XML fragment with sibling Library nodes.
    signatures = ET.fromstring('<LibrarySignatures>' + Path(signatures_path).read_text(encoding='utf-8-sig') + '</LibrarySignatures>')
    if not signatures.findall('Library'):
        raise ValueError('Actual library signatures are empty')
    wrapper = ET.Element('TcForgeDependencyCapture')
    wrapper.append(project)
    wrapper.append(signatures)
    ET.ElementTree(wrapper).write(output, encoding='utf-8', xml_declaration=True)


def load_lock(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schemaVersion') != 1 or set(data.get('projects', {})) != set(PROJECTS):
        raise ValueError('Dependency lock must have schemaVersion 1 and exactly the four build projects')
    return data


def check_project(lock_path, project, xml_path):
    lock = load_lock(lock_path)
    if project not in PROJECTS:
        raise ValueError(f'Unknown build project: {project}')
    actual = parse_resolution_xml(xml_path)
    expected = lock['projects'][project]
    if actual != expected:
        old = {item['id'] for item in expected.get('libraries', [])}
        new = {item['id'] for item in actual['libraries']}
        detail = f' added={sorted(new-old)} removed={sorted(old-new)}'
        raise ValueError(f'{project}: effective dependencies differ from reviewed lock;{detail}; bindings/edges also compared')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check')
    check.add_argument('--lock', type=Path, default=Path('dependencies.lock.json'))
    check.add_argument('--project', choices=PROJECTS, required=True)
    check.add_argument('--xml', type=Path, required=True)
    candidate = sub.add_parser('candidate', help='Explicitly produce a candidate from four captures for review; never used by normal builds')
    candidate.add_argument('--captures', type=Path, required=True)
    candidate.add_argument('--output', type=Path, required=True)
    combine = sub.add_parser('combine', help='Combine project XML and actual library signatures into one evidence capture')
    combine.add_argument('--xml', type=Path, required=True)
    combine.add_argument('--signatures', type=Path, required=True)
    combine.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'check':
            result = check_project(args.lock, args.project, args.xml)
            print(f'{args.project}: {len(result["references"])} direct references, {len(result["libraries"])} effective libraries, {len(result["dependencies"])} dependency edges match lock')
        elif args.command == 'combine':
            combine_capture(args.xml, args.signatures, args.output)
            print(f'Combined actual dependency evidence written to {args.output}')
        else:
            result = dict(schemaVersion=1, projects={project: parse_resolution_xml(args.captures / (project + '.xml')) for project in PROJECTS})
            if any(not project['signatureLibraries'] for project in result['projects'].values()):
                raise ValueError('Candidate lock requires actual library signatures for all four projects')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            print(f'Candidate dependency lock written to {args.output}; review before adoption')
    except (ValueError, OSError, ET.ParseError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
