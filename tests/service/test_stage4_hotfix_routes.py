import json
from test_stage1_upgrade_copy import app
from docflow.service.hotfix_check import run,CHECKS

def test_rc8_actual_widget_routes_sql_and_versions(app,tmp_path):
    output=tmp_path/'qa'
    assert run(output)==0
    report=json.loads((output/'HOTFIX-SELF-TEST.json').read_text(encoding='utf-8'))
    assert set(report['checks'])==CHECKS and len(report['checks'])==len(CHECKS)
    assert report['old_document_unchanged'] and not report['word_checked']
