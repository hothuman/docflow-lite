import pytest

from PySide6.QtWidgets import QApplication

from docflow.gui import configure_app
from docflow.service.workspace_check import exercise


@pytest.mark.parametrize('stage10',[False,True])
def test_one_window_keeps_status_finance_document_and_repeat_context(tmp_path,stage10):
    app=QApplication.instance()
    configure_app(app)
    result=exercise(app,tmp_path/'unified-workshop',stage10=stage10)
    assert result['status']=='passed'
    assert result['operational_top_level_windows']==1
    assert 'status_changes_only_on_explicit_confirmed_action' in result['checks']
    assert 'backup_restores_two_repairs_statuses_and_exact_document' in result['checks']
    if stage10:
        assert 'estimate_csv_and_localized_csv_match_frozen_quote' in result['checks']
        assert 'cancelled_issued_cost_change_preserves_data_and_docx' in result['checks']
