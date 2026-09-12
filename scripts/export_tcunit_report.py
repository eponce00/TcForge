"""Read completed TcUnit 1.3 test identities/results over ADS and write JUnit.

Run after the test runner finishes, against the same isolated runtime. This reads
the pinned TcUnit instance layout; it does not infer passes from summary counts.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from check_test_report import validate, source_suites

ROOT = Path(__file__).resolve().parents[1]


def read_symbols(helper, target, port, symbols):
    result = {}
    for offset in range(0, len(symbols), 80):
        batch = symbols[offset:offset + 80]
        process = subprocess.run(
            [str(helper), 'read-var-list', '--amsnetid', target, '--port', str(port),
             '--symbols', ','.join(batch)], capture_output=True, text=True,
            encoding='utf-8', check=True, timeout=60)
        data = json.loads(process.stdout)
        if data.get('ErrorMessage') or data.get('ErrorCount') or data.get('SuccessCount') != len(batch):
            failures = {name: entry.get('ErrorMessage') for name, entry in data.get('Results', {}).items() if not entry.get('Success')}
            raise ValueError('ADS read failed: ' + str(failures or data.get('ErrorMessage')))
        for name in batch:
            entry = data['Results'][name]
            if not entry.get('Success'):
                raise ValueError('ADS read failed: ' + name)
            value = entry['RawValue']
            if entry['DataType'] == 'Tc2_System.T_MaxString':
                # Bytes beyond the terminator are unused memory, not report content.
                value = bytes.fromhex(value).split(b'\0', 1)[0].decode('utf-8')
            elif entry['DataType'].startswith('UINT ('):
                value = int.from_bytes(bytes.fromhex(value), 'little')
            result[name] = value
    return result


def export(helper, target, port, output, expected_cycle_ms=None, provenance_token=None):
    provenance = {}
    if provenance_token:
        from build_evidence import report_context
        provenance = report_context(provenance_token, helper, target, port, expected_cycle_ms)
    lock = json.loads((ROOT / 'toolchain.json').read_text(encoding='utf-8'))
    if lock['tcunitVersion'] != '1.3.0.0':
        raise ValueError('Revalidate the ADS result layout before changing TcUnit version')
    suites = source_suites(ROOT)
    started = 'GVL_TcUnit.StartedAt'
    counts = read_symbols(helper, target, port, [started, *[s + '.NumberOfTests' for s in suites]])
    cycle_units = None
    if expected_cycle_ms is not None:
        owner = read_symbols(helper, target, port, ['MAIN.rpcContext.ownerTask'])['MAIN.rpcContext.ownerTask']
        if not isinstance(owner, int) or owner <= 0:
            raise ValueError('Test task has not executed')
        symbol = f'TwinCAT_SystemInfoVarList._TaskInfo[{owner}].CycleTime'
        cycle_units = read_symbols(helper, target, port, [symbol])[symbol]
        if cycle_units != expected_cycle_ms * 10000:
            raise ValueError(f'Wrong running task period: {cycle_units} x 100 ns')
    fields = ['TestName', 'TestIsFinished', 'TestIsFailed', 'TestIsSkipped', 'Duration']
    symbols = []
    for suite, names in suites.items():
        if counts[suite + '.NumberOfTests'] != len(names):
            raise ValueError('Incomplete or unexpected test count: ' + suite)
        symbols.extend(f'{suite}.Tests[{i}].{field}' for i in range(1, len(names) + 1) for field in fields)
    values = read_symbols(helper, target, port, symbols)
    if read_symbols(helper, target, port, [started])[started] != counts[started]:
        raise ValueError('Runtime was reinitialized during result capture')
    report = ET.Element('testsuites')
    for suite, names in suites.items():
        group = ET.SubElement(report, 'testsuite', name=suite, tests=str(len(names)))
        properties = ET.SubElement(group, 'properties')
        for key, value in provenance.items():
            ET.SubElement(properties, 'property', name=key, value=value)
        ET.SubElement(properties, 'property', name='target', value=target)
        ET.SubElement(properties, 'property', name='adsPort', value=str(port))
        if cycle_units is not None:
            ET.SubElement(properties, 'property', name='cycleTime100ns', value=str(cycle_units))
        observed = set()
        for index in range(1, len(names) + 1):
            base = f'{suite}.Tests[{index}].'
            name = values[base + 'TestName']
            if name not in names or name in observed:
                raise ValueError('Unexpected/duplicate runtime test identity: ' + suite + '.' + name)
            observed.add(name)
            for field in ['TestIsFinished', 'TestIsFailed', 'TestIsSkipped']:
                if not isinstance(values[base + field], bool):
                    raise ValueError('Unexpected TcUnit Boolean representation')
            if not values[base + 'TestIsFinished']:
                raise ValueError('Test has not finished: ' + suite + '.' + name)
            duration = values[base + 'Duration']
            if not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration < 0:
                raise ValueError('Invalid duration: ' + suite + '.' + name)
            case = ET.SubElement(group, 'testcase', classname=suite, name=name, time=str(duration))
            if values[base + 'TestIsSkipped']:
                ET.SubElement(case, 'skipped')
            if values[base + 'TestIsFailed']:
                ET.SubElement(case, 'failure', message='TcUnit assertion failed; see runner failure details')
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(report)
    ET.ElementTree(report).write(output, encoding='utf-8', xml_declaration=True)
    validate(output, sum(map(len, suites.values())),
             {(suite, name) for suite, names in suites.items() for name in names})
    print(f'{len(suites)} suites, {sum(map(len, suites.values()))} individual results verified: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--port', type=int, default=853)
    parser.add_argument('--helper', type=Path, default=ROOT.parent / 'twincat-mcp/TcAutomation/bin/Release-v2/TcAutomation.exe')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/tcunit.xml')
    parser.add_argument('--expected-cycle-ms', type=int, choices=[1, 10])
    parser.add_argument('--provenance-token', type=Path)
    args = parser.parse_args()
    export(args.helper, args.target, args.port, args.output, args.expected_cycle_ms, args.provenance_token)
