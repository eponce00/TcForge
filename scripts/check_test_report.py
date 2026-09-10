"""Reject empty, failing, skipped, or incomplete JUnit reports."""
import argparse
from pathlib import Path
import sys
import re
import xml.etree.ElementTree as ET


def source_suites(root):
    """Return exact TcUnit runtime suite/name identities declared by test sources."""
    main = ET.parse(root / 'TwinCAT/Testing/POUs/MAIN.TcPOU').findtext('POU/Declaration', '')
    main = re.sub(r'//[^\n]*|\(\*.*?\*\)', '', main, flags=re.S)
    project = root / 'TwinCAT/Testing.plcproj'
    compiled = {(project.parent / node.get('Include', '').replace('\\', '/')).resolve()
                for node in ET.parse(project).iter() if node.tag.rsplit('}', 1)[-1] == 'Compile'}
    suites = {}
    for path in sorted((root / 'TwinCAT/Testing/Tests').glob('*.TcPOU')):
        pou = ET.parse(path).find('POU')
        if pou is None or path.resolve() not in compiled:
            raise ValueError('Unregistered test suite source: ' + str(path))
        matches = re.findall(r'\b(\w+)\s*:\s*' + re.escape(pou.get('Name')) + r'\s*;', main)
        if len(matches) != 1:
            raise ValueError('Expected exactly one MAIN instance of ' + pou.get('Name'))
        code = '\n'.join(node.text or '' for node in pou.iter('ST'))
        code = re.sub(r'//[^\n]*|\(\*.*?\*\)', '', code, flags=re.S)
        names = re.findall(r"\bTEST\s*\(\s*'([^']+)'\s*\)", code, flags=re.I)
        if not names or len(names) != len(set(names)):
            raise ValueError('Empty or duplicate test names in ' + pou.get('Name'))
        suite = 'MAIN.' + matches[0]
        if suite in suites:
            raise ValueError('Duplicate MAIN test suite instance: ' + suite)
        suites[suite] = set(names)
    if not suites:
        raise ValueError('No test suites found')
    return suites


def validate(path, expected_tests, expected_identities=None):
    root = ET.parse(path).getroot()
    if root.tag not in {'testsuite', 'testsuites'}:
        raise ValueError('Expected a JUnit testsuite or testsuites root')
    cases = list(root.iter('testcase'))
    if len(cases) != expected_tests:
        raise ValueError(f'Expected {expected_tests} executed tests, got {len(cases)}')
    identities = [(c.get('classname', ''), c.get('name', '')) for c in cases]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate test results')
    if expected_identities is not None:
        expected = set(expected_identities)
        observed = set(identities)
        if len(expected) != expected_tests:
            raise ValueError('Expected identity count does not match expected test count')
        if observed != expected:
            raise ValueError(f'Test identities differ from source: missing={sorted(expected - observed)}, unexpected={sorted(observed - expected)}')
    for case in cases:
        if any(case.find(tag) is not None for tag in ['failure', 'error', 'skipped']):
            raise ValueError(f'Unsuccessful test: {case.get("name")}')
    for node in root.iter():
        if node.tag in {'testsuite', 'testsuites'}:
            for attr in ['failures', 'errors', 'skipped']:
                if int(node.get(attr, 0)):
                    raise ValueError(f'Report contains {attr}')
    return len(cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--expected-tests', required=True, type=int)
    args = parser.parse_args()
    try:
        if args.expected_tests <= 0:
            raise ValueError('Expected test count must be positive')
        print(f'{validate(args.report, args.expected_tests)} passing tests')
    except (ValueError, OSError, ET.ParseError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
