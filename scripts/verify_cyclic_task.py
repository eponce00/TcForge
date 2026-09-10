"""Read-only Example activation check: RUN alone does not prove cyclic execution."""
import argparse
import json
import os
import time


def verify(connection, pause=time.sleep):
    import pyads
    if connection.read_state()[0] != 5:
        raise AssertionError('PLC is not in RUN')
    owner = connection.read_by_name('MAIN.machine.taskIndex', pyads.PLCTYPE_DINT)
    if owner <= 0:
        raise AssertionError('Example cyclic owner is uninitialized')
    symbol = f'TwinCAT_SystemInfoVarList._TaskInfo[{owner}].CycleCount'
    before = connection.read_by_name(symbol, pyads.PLCTYPE_UDINT)
    pause(.15)
    after = connection.read_by_name(symbol, pyads.PLCTYPE_UDINT)
    if after == before:
        raise AssertionError('Cyclic task counter did not advance')
    return {'owner': owner, 'cycle_before': before, 'cycle_after': after, 'passed': True}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target', required=True)
    p.add_argument('--port', type=int, choices=[851], required=True)
    args = p.parse_args()
    if os.name == 'nt':
        dll_directory = os.add_dll_directory(r'C:\Program Files (x86)\Beckhoff\TwinCAT\Common64')
    import pyads
    with pyads.Connection(args.target, args.port) as connection:
        print(json.dumps(verify(connection)))
