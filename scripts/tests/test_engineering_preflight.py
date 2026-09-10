"""Exercise the PowerShell engineering boundary without launching XAE."""
import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell engineering helpers')
class EngineeringPreflightTests(unittest.TestCase):
    def run_ps(self, script):
        scripts = Path(__file__).resolve().parents[1]
        script = "$ErrorActionPreference='Stop'\n$helpers='" + str(scripts).replace("'", "''") + "'\n" + script
        # Windows PowerShell -Command inherits a false $? from a deliberately
        # caught rejection. Uncaught terminating assertions still exit earlier.
        script += '\nexit 0\n'
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand',
                                 base64.b64encode(script.encode('utf-16le')).decode()],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dispatch_is_not_runtime_success_and_cannot_fallback(self):
        self.run_ps(r"""
. (Join-Path $helpers 'online_change_commands.ps1')
$plc=[pscustomobject]@{LoggedIn=$true}
$plc | Add-Member ScriptMethod ProduceXml { param($recursive) '<TreeItem><IECProjectDef><OnlineSettings><LoggedIn>'+ $this.LoggedIn.ToString().ToLower() +'</LoggedIn></OnlineSettings></IECProjectDef></TreeItem>' }
$commands=[pscustomobject]@{Available=$true}
$commands | Add-Member ScriptMethod Item { param($name) [pscustomobject]@{IsAvailable=$this.Available} }
$dte=[pscustomobject]@{Commands=$commands;Calls=0}
$dte | Add-Member ScriptMethod ExecuteCommand { param($name,$args) $this.Calls++ }
$name=Get-TcForgeOnlineChangeCommand -Dte $dte -Plc $plc
$result=Invoke-TcForgeOnlineChange -Dte $dte -Plc $plc -ExpectedCommand $name
if ($dte.Calls -ne 1 -or $result.RuntimeVerified -ne $false) {throw 'Incorrect dispatch evidence'}
$commands.Available=$false
try {Invoke-TcForgeOnlineChange -Dte $dte -Plc $plc -ExpectedCommand $name; throw 'Unexpected dispatch'} catch {if ($_.Exception.Message -eq 'Unexpected dispatch') {throw}}
$commands.Available=$true; $plc.LoggedIn=$false
try {Get-TcForgeOnlineChangeCommand -Dte $dte -Plc $plc; throw 'Unexpected login'} catch {if ($_.Exception.Message -eq 'Unexpected login') {throw}}
if ($dte.Calls -ne 1) {throw 'Fallback executed'}
""")

    def test_generated_symbols_preserve_login_info_and_reject_other_files(self):
        with tempfile.TemporaryDirectory(prefix='tcforge-preflight-') as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '--quiet', directory], check=True)
            (root / 'artifacts').mkdir()
            (root / '.gitignore').write_text('*.tmc\n')
            (root / 'app.tsproj').write_text('<Root><Project TmcFilePath="app.tmc"/></Root>')
            original = b'<TcModuleClass GeneratedBy="TwinCAT XAE Plc"/>'
            (root / 'app.tmc').write_bytes(original)
            (root / 'app.compileinfo').write_bytes(b'preserve exact compiler baseline')
            self.run_ps("$fixture='" + directory.replace("'", "''") + "'\n" + r"""
. (Join-Path $helpers 'prepare_generated_tmc.ps1')
Move-TcForgeGeneratedTmc -Repo $fixture -ProjectFile (Join-Path $fixture 'app.tsproj')
[IO.File]::WriteAllText((Join-Path $fixture 'app.tmc'),'<TcModuleClass GeneratedBy="Other"/>')
try {Move-TcForgeGeneratedTmc -Repo $fixture -ProjectFile (Join-Path $fixture 'app.tsproj'); throw 'Unexpected move'} catch {if ($_.Exception.Message -eq 'Unexpected move') {throw}}
[IO.File]::WriteAllText((Join-Path $fixture 'app.tsproj'),'<Root><Project TmcFilePath="../outside.tmc"/></Root>')
try {Move-TcForgeGeneratedTmc -Repo $fixture -ProjectFile (Join-Path $fixture 'app.tsproj'); throw 'Unexpected escape'} catch {if ($_.Exception.Message -eq 'Unexpected escape') {throw}}
""")
            self.assertEqual((root / 'app.compileinfo').read_bytes(), b'preserve exact compiler baseline')
            backups = list((root / 'artifacts').iterdir())
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
