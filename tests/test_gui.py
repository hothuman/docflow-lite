import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from docflow.gui import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_gui_demo_preview_validation_and_worker(app, tmp_path):
    window = MainWindow()
    window.show()
    window.load_demo()
    app.processEvents()
    assert window.source_table.rowCount() == 3
    assert window.mapping_table.rowCount() == 6
    assert "Демо Клиент А" in window.preview_text.toPlainText()
    window.row_selector.setCurrentIndex(2)
    assert "будет пропущена" in window.preview_text.toPlainText()
    window.check_all()
    assert "С ошибками: 1" in window.status.text()
    window.output_path.setText(str(tmp_path))
    window.start_generation()
    deadline = time.monotonic() + 20
    while (window.worker.isRunning() or window.last_result is None) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    window.worker.wait(1000)
    app.processEvents()
    assert window.last_result.documents == 4
    assert window.generate_btn.isEnabled()
    assert "4 DOCX" in window.status.text()
    window.close()

