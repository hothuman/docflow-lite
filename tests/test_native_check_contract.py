import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('native_bundle_verifier',Path(__file__).parents[1]/'scripts/verify_windows_bundle.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)


def test_all_required_native_scenarios_are_accepted():
    checks=[{'name':name,'passed':True} for name in verifier.REQUIRED_COMPLETION_CHECKS]
    verifier.assert_completion_checks(checks)


@pytest.mark.parametrize('change',['missing','duplicate','failed','unexpected','old_suite'])
def test_missing_duplicate_failed_or_obsolete_native_evidence_is_rejected(change):
    checks=[{'name':name,'passed':True} for name in sorted(verifier.REQUIRED_COMPLETION_CHECKS)]
    if change=='missing':checks.pop()
    elif change=='duplicate':checks[-1]=dict(checks[0])
    elif change=='failed':checks[0]['passed']=False
    elif change=='unexpected':checks[-1]['name']='unrelated'
    else:checks=checks[:5]
    with pytest.raises(AssertionError):verifier.assert_completion_checks(checks)


@pytest.mark.parametrize('change',['none','source_only','stubbed_dialog','missing','failed'])
def test_project_opening_evidence_requires_real_frozen_native_cancellation(change):
    report={'status':'passed','frozen':True,'qt_platform':'windows',
            'native_folder_dialog_seen':True,'native_folder_dialog_close_sent':True,
            'checks':[{'name':name,'passed':True} for name in verifier.REQUIRED_PROJECT_CHECKS]}
    if change=='none':verifier.assert_project_loading_checks(report);return
    if change=='source_only':report['frozen']=False
    elif change=='stubbed_dialog':report['native_folder_dialog_seen']=False
    elif change=='missing':report['checks'].pop()
    else:report['checks'][0]['passed']=False
    with pytest.raises(AssertionError):verifier.assert_project_loading_checks(report)
