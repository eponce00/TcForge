"""Controlled boot-image tests on an explicitly authorized, unmapped Simulation bench.

Requires an existing Secure ADS route, pinned SSH host key and password supplied
through the named environment variable. Does not provision trust or credentials.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import uuid

from lifecycle_fixture import capture, clear_outputs, validate_restored
from persistent_image_policy import validate_image

NAMES = ('Port_854.bootdata', 'Port_854.bootdata-old')


def validate_config(config):
    if config.get('dedicated_unmapped_bench') is not True or config.get('port') != 854:
        raise ValueError('An explicitly authorized unmapped Simulation/854 bench is required')
    if config.get('corrupt_recovery') not in ('reinitialize', 'backup'):
        raise ValueError('Configure the expected corrupt-image recovery mode')
    path = PureWindowsPath(config['boot_directory'])
    if not path.is_absolute() or len(path.drive) != 2 or path.drive[1] != ':' or '..' in path.parts or tuple(p.lower() for p in path.parts[-2:]) != ('boot', 'plc'):
        raise ValueError('Expected an absolute Windows Boot/Plc directory')
    parts = config['target'].split('.')
    if len(parts) != 6 or any(not p.isdigit() or not 0 <= int(p) <= 255 for p in parts):
        raise ValueError('Invalid target AMS Net ID')
    fingerprint = config['ssh_sha256']
    if len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
        raise ValueError('Expected SHA256 hex fingerprint of the SSH public host key')


def ssh(config):
    import paramiko
    class Pin(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            if hashlib.sha256(key.asbytes()).hexdigest() != config['ssh_sha256']:
                raise RuntimeError('SSH host key mismatch')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(Pin())
    try:
        client.connect(config['host'], username=config['ssh_user'],
                       password=os.environ[config['ssh_password_env']],
                       look_for_keys=False, allow_agent=False, timeout=10,
                       banner_timeout=10, auth_timeout=10)
        return client
    except BaseException:
        client.close()
        raise


def remote_config(client, target):
    parts = target.split('.')
    if len(parts) != 6 or any(not p.isascii() or not p.isdigit() or not 0 <= int(p) <= 255 for p in parts):
        raise ValueError('Invalid AMS Net ID')
    # Avoid Windows SSH command-line length limits; the temporary file contains
    # only this repository helper, never credentials. Delete it after execution.
    path = 'C:/Windows/Temp/TcForge-config-' + uuid.uuid4().hex + '.ps1'
    with client.open_sftp() as sftp:
        with sftp.open(path, 'wb') as stream:
            stream.write(Path(__file__).with_name('set_local_runtime_config.ps1').read_bytes())
    try:
        command = f'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{path}" -ExpectedNetId "{target}"'
        _, stdout, stderr = client.exec_command(command, timeout=330)
        data = stdout.read()
        error = stderr.read()
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError('Bench-local CONFIG operation failed: ' + error.decode(errors='replace')[:1500])
        transition = json.loads(data.decode('utf-8-sig'))
        if transition.get('verified') is not True or transition.get('after') != 15 or transition.get('netId') != target:
            raise RuntimeError('Bench-local CONFIG receipt is invalid')
        return transition
    finally:
        with client.open_sftp() as sftp:
            sftp.remove(path)


def run(config, output, selected_cases):
    validate_config(config)
    report = {'passed': False, 'target': config['target'], 'port': 854, 'cases': [],
              'requested_cases': selected_cases, 'corrupt_recovery': config['corrupt_recovery'],
              'scope': 'Controlled persistent images with XAE restart; no power-loss claim'}
    baseline = None
    client = ssh(config)
    remote = str(PureWindowsPath(config['boot_directory'])).replace('\\', '/') + '/'
    counter = 0
    stopped = False
    root = Path(__file__).resolve().parent

    def read_files():
        files = {}
        with client.open_sftp() as sftp:
            for name in NAMES:
                try:
                    with sftp.open(remote + name, 'rb') as stream: files[name] = stream.read()
                except FileNotFoundError:
                    files[name] = None
        return files

    def stop():
        nonlocal stopped
        stopped = True  # A failed reply may follow an applied state transition.
        transition = remote_config(client, config['target'])
        report.setdefault('config_transitions', []).append(transition)

    def write_files(files):
        # Every mutation must be preceded by independently observed CONFIG.
        stop()
        if set(files) != set(NAMES): raise ValueError('Unexpected image names')
        with client.open_sftp() as sftp:
            for name, data in files.items():
                if data is None:
                    try: sftp.remove(remote + name)
                    except FileNotFoundError: pass
                else:
                    with sftp.open(remote + name, 'wb') as stream: stream.write(data)
        if read_files() != files: raise AssertionError('Image write/readback mismatch')

    def start():
        nonlocal counter, stopped
        counter += 1
        with (output / f'restart-{counter}.log').open('w') as log:
            subprocess.run(['powershell.exe', '-NoProfile', '-File', str(root / 'restart_runtime.ps1'),
                            '-Target', config['target'], '-Solution', str(Path(config['solution']).resolve()),
                            '-Output', str(output / f'restart-{counter}.json')],
                           check=True, timeout=360, stdout=log, stderr=subprocess.STDOUT)
        with (output / f'ready-{counter}.log').open('w') as log:
            subprocess.run([sys.executable, str(root / 'wait_runtime_ready.py'),
                            '--config', str(output / 'runtime-config.json'),
                            '--output', str(output / f'ready-{counter}.json'), '--timeout', '300'],
                           check=True, timeout=315, stdout=log, stderr=subprocess.STDOUT)
        stopped = False

    runtime = {'target': config['target'], 'port': 854, 'fixture': 'Simulation',
               'ads_dll_directory': config['ads_dll_directory']}
    (output / 'runtime-config.json').write_text(json.dumps(runtime))
    try:
        report['preflight'] = capture(config['target'], 854, 'seed')
        stop()
        baseline = read_files()
        valid = baseline[NAMES[0]]
        if not valid or len(valid) <= 32: raise AssertionError('No current image after stop')
        report['baseline'] = {}
        for name, data in baseline.items():
            if data is not None:
                (output / name).write_bytes(data)
                report['baseline'][name] = {'length': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        cases = [('missing', {NAMES[0]: None, NAMES[1]: None}),
                 ('backup_only', {NAMES[0]: None, NAMES[1]: valid}),
                 ('corrupt_current_with_backup', {NAMES[0]: b'TcForge invalid test image', NAMES[1]: valid})]
        for name, files in cases:
            if name not in selected_cases:
                continue
            item = {'name': name, 'passed': False}
            report['cases'].append(item)
            write_files(files)
            start()
            item['snapshot'] = capture(config['target'], 854)
            item['validation'] = validate_image(item['snapshot'], name, config['corrupt_recovery'])
            clear_outputs(config['target'], 854)
            item['passed'] = True
            print('Passed '+name, flush=True)
        report['passed'] = True
    except Exception as exc:
        report['failure'] = type(exc).__name__
        if isinstance(exc, subprocess.CalledProcessError):
            report['control_exit_code'] = exc.returncode
            (output / 'control-error.log').write_bytes(exc.stderr or b'')
    finally:
        try:
            if baseline is not None:
                write_files(baseline)
                start()
                report['restored'] = capture(config['target'], 854)
                validate_restored(report['preflight'], report['restored'], 'seed')
                report['baseline_restored'] = True
            elif stopped:
                start()
            report['cleanup'] = clear_outputs(config['target'], 854)
        except Exception as exc:
            report['passed'] = False
            report['cleanup_failure'] = type(exc).__name__
        client.close()
        (output / 'evidence.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--cases', nargs='+', choices=['missing', 'backup_only', 'corrupt_current_with_backup'],
                        default=['missing', 'backup_only', 'corrupt_current_with_backup'])
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Run this XAE-based qualification on a Windows engineering PC')
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    if args.output is None: parser.error('--output is required')
    validate_config(config)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = run(config, output, args.cases)
    print(json.dumps({'passed': report['passed'], 'cases': report['cases'],
                      'cleanup_failure': report.get('cleanup_failure')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__': sys.exit(main())
