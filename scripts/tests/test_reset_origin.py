import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_reset_origin import validate_initialized, validate_origin_transition
from test_lifecycle_fixture import snapshots


def xml(logged):
    return '<TreeItem><IECProjectDef><OnlineSettings><LoggedIn>'+logged+'</LoggedIn></OnlineSettings></IECProjectDef></TreeItem>'


def initialized():
    before,after=snapshots()
    after.update(applicationMarker=0,markerAtInitialization=0,completedSequence=0,diagnosticLastFault=0,
                 defaultOutput=False,restoreOutput=False,defaultInhibited=True,restoreInhibited=True,
                 analogInhibited=True,analogRaw=17,alarmActive=False,alarmLatched=False,alarmAcked=False,
                 diagnosticFaulted=False,cycles=10)
    return before,after


class ResetOriginEvidenceTests(unittest.TestCase):
    def test_actual_origin_requires_login_logout_and_removal(self):
        result=dict(Success=True,Operation='ResetOriginCmd',TargetNetId='test')
        for code in (6,1808):
            validate_origin_transition(xml('true'),xml('false'),result,
                                       dict(symbol_error_code=code,system_ads_state=5),'test')
        for before,after in (('false','false'),('true','true')):
            with self.assertRaises(AssertionError):
                validate_origin_transition(xml(before),xml(after),result,
                                           dict(symbol_error_code=1808,system_ads_state=5),'test')

    def test_timeout_or_network_loss_is_not_removal(self):
        result=dict(Success=True,Operation='ResetOriginCmd',TargetNetId='test')
        for removal in ({},dict(symbol_error_code=1861,system_ads_state=5),
                        dict(symbol_error_code=1808,system_ads_state=0)):
            with self.assertRaises(AssertionError):
                validate_origin_transition(xml('true'),xml('false'),result,removal,'test')

    def test_wrong_operation_target_or_failed_command_rejected(self):
        result=dict(Success=True,Operation='ResetOriginCmd',TargetNetId='test')
        for field,value in (('Success',False),('Operation','Activate'),('TargetNetId','other')):
            bad=dict(result); bad[field]=value
            with self.assertRaises(AssertionError):
                validate_origin_transition(xml('true'),xml('false'),bad,
                                           dict(symbol_error_code=1808,system_ads_state=5),'test')

    def test_initialized_fixture_passes(self):
        validate_initialized(*initialized())

    def test_each_retained_marker_history_and_command_fails(self):
        for field,value in (('applicationMarker',49374),('markerAtInitialization',49374),
                            ('completedSequence',1),('diagnosticLastFault',1),('defaultOutput',True),
                            ('restoreOutput',True),('defaultInhibited',False),('restoreInhibited',False),
                            ('analogInhibited',False),('analogRaw',42),('alarmActive',True),
                            ('alarmLatched',True),('alarmAcked',True),('diagnosticFaulted',True),('cycles',0)):
            with self.subTest(field=field):
                before,after=initialized(); after[field]=value
                with self.assertRaises(AssertionError): validate_initialized(before,after)

    def test_unseeded_start_cannot_claim_persistence_reset(self):
        before,after=initialized(); before['applicationMarker']=0
        with self.assertRaises(AssertionError): validate_initialized(before,after)

if __name__=='__main__': unittest.main()
