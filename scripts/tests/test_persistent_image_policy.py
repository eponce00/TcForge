import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from persistent_image_policy import validate_image
from verify_persistent_images import validate_config

class ImagePolicyTests(unittest.TestCase):
    def snapshot(self, backup=False):
        return dict(completedSequence=0,defaultOutput=False,defaultInhibited=True,
                    restoreOutput=False,restoreInhibited=True,analogInhibited=True,analogRaw=17,
                    bootDataLoadedAtInitialization=backup,oldBootDataAtInitialization=backup,
                    applicationMarker=49374 if backup else 0,markerAtInitialization=49374 if backup else 0,
                    alarmLatched=backup,diagnosticLastFault=10 if backup else 0)
    def test_rejects_unapproved_target_and_path_escape(self):
        config=dict(dedicated_unmapped_bench=True,port=854,target="1.2.3.4.1.1",corrupt_recovery="reinitialize",
                    boot_directory='C:/TwinCAT/Boot/Plc',ssh_sha256='a'*64)
        validate_config(config)
        for key,value in [('port',851),('dedicated_unmapped_bench',False),
                          ('boot_directory','C:/TwinCAT/../Boot/Plc'),
                          ('boot_directory','Boot/Plc'),('boot_directory','//server/share/Boot/Plc'),
                          ('target',"1.2.3.4.1.1'; injected"),('ssh_sha256','untrusted')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_config(dict(config,**{key:value}))

    def test_accepts_untrusted_images_only_with_inhibited_outputs(self):
        for case in ('missing','backup_only','corrupt_current_with_backup'):
            with self.subTest(case=case):
                self.assertTrue(validate_image(self.snapshot(case!='missing'),case,'backup')['passed'])
    def test_rejects_stale_marker_and_wrong_image_flags(self):
        for field,value in [('applicationMarker',49374),('oldBootDataAtInitialization',True),('completedSequence',1)]:
            snapshot=self.snapshot();snapshot[field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):validate_image(snapshot,'missing')
    def test_rejects_energized_saved_output(self):
        snapshot=self.snapshot(True);snapshot['restoreOutput']=True
        with self.assertRaises(AssertionError):validate_image(snapshot,'backup_only')
    def test_corrupt_case_must_prove_backup_was_loaded(self):
        snapshot=self.snapshot(True);snapshot['oldBootDataAtInitialization']=False
        with self.assertRaises(AssertionError):validate_image(snapshot,'corrupt_current_with_backup','backup')

    def test_corrupt_reinitialization_requires_default_state(self):
        snapshot=self.snapshot()
        self.assertEqual(validate_image(snapshot,'corrupt_current_with_backup','reinitialize')['recovery'],'reinitialize')
        for field,value in [('bootDataLoadedAtInitialization',True),('alarmLatched',True),('diagnosticLastFault',10)]:
            with self.subTest(field=field),self.assertRaises(AssertionError):
                validate_image(dict(snapshot,**{field:value}),'corrupt_current_with_backup','reinitialize')

    def test_corrupt_recovery_cannot_be_unspecified(self):
        with self.assertRaises(ValueError):validate_image(self.snapshot(),'corrupt_current_with_backup')

if __name__=='__main__':unittest.main()
