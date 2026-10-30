from docflow.service.stage3_check import run

def test_real_qt_import_picker_and_prefs_routes(tmp_path,monkeypatch):
    monkeypatch.setenv('DOCFLOW_SETTINGS_DIR',str(tmp_path/'ini'))
    assert run(tmp_path/'routes')==0
