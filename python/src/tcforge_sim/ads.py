"""Read-only target probe. Live simulation writes require the future PLC IO bridge."""
import argparse
import json
import os
from pathlib import Path


def probe(target: str, port: int) -> dict:
    dll_handle = None
    if os.name == 'nt':
        common = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Beckhoff/TwinCAT/Common64'
        if common.is_dir():
            dll_handle = os.add_dll_directory(str(common))
    try:
        import pyads
        with pyads.Connection(target, port) as connection:
            connection.set_timeout(2000)
            state, device_state = connection.read_state()
            name, version = connection.read_device_info()
            return {'target': target, 'port': port, 'ads_state': state,
                    'device_state': device_state, 'device': name,
                    'version': f'{version.version}.{version.revision}.{version.build}'}
    finally:
        if dll_handle is not None:
            dll_handle.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, help='Explicit AMS Net ID')
    parser.add_argument('--port', required=True, type=int)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be within 1..65535')
    try:
        print(json.dumps(probe(args.target, args.port), indent=2))
    except Exception as exc:
        parser.exit(1, f'ADS probe failed: {exc}\n')


if __name__ == '__main__':
    main()
