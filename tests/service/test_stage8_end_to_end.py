from docflow.service.stage8_check import run_domain


def test_stage8_synthetic_business_cycle(tmp_path):
    proof=run_domain(tmp_path/'Stage8')
    assert proof['status']=='passed' and len(proof['scenarios'])==10
    assert proof['scenarios']['A_new']['balance_cents']==150057
