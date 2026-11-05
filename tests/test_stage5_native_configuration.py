"""The demo must create its own package, never accept a preceding run's result."""
import json
from docflow.gui import MainWindow
from docflow.release_check import wait_idle
from docflow.ui.configuration import exercise

def test_configuration_demo_proves_fresh_generation(qt_application_lifetime,tmp_path):
    app=qt_application_lifetime;w=MainWindow(service_root=tmp_path/'project');w.show()
    try:
        w.load_demo();wait_idle(w);w.navigate(3);w.output_path.setText(str(tmp_path/'previous'));w.start_generation();wait_idle(w)
        previous=w.last_result
        exercise(w,app,tmp_path,lambda ui:None)
        assert w.last_result is not previous
        assert w.last_result.directory.parent==tmp_path/'Self-service DOCX'
        proof=json.loads((tmp_path/'STAGE5-CONFIGURATION.json').read_text(encoding='utf-8'))
        assert proof['generated']==4 and len(proof['mapping'])==6
    finally:
        wait_idle(w);w.close()
