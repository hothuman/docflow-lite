import copy
import pytest
from docflow.service.stage4_check import run,CHECKS
from scripts.verify_windows_bundle import assert_stage4_checks

def test_all_stage4_routes_and_fail_closed_verifier(app,tmp_path):
    import json
    path=tmp_path/'Synthetic QA'
    assert run(path)==0
    report=json.loads((path/'STAGE4-SELF-TEST.json').read_text(encoding='utf-8'))
    assert {c['name'] for c in report['checks']}==CHECKS
    report.update(frozen=True,qt_platform='windows');assert_stage4_checks(report)
    for missing in CHECKS:
        bad=copy.deepcopy(report);bad['checks']=[c for c in bad['checks'] if c['name']!=missing]
        with pytest.raises(AssertionError):assert_stage4_checks(bad)
    bad=copy.deepcopy(report);bad['checks'][0]['passed']=False
    with pytest.raises(AssertionError):assert_stage4_checks(bad)

from test_stage1_upgrade_copy import app
