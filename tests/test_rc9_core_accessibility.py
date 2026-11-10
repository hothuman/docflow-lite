"""The primary action's public accessibility metadata follows its actual route."""
import hashlib
import zipfile
import time

import pytest
from docx import Document
from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from docflow.batch import prepare, generate
from docflow.gui import MainWindow
from docflow.profile import Profile
from docflow.release_check import wait_idle


def assert_action(window):
    button = window.core_next
    interface = QAccessible.queryAccessibleInterface(button)
    assert interface.text(QAccessible.Text.Name)==button.text()==button.accessibleName()
    assert button.toolTip() and interface.text(QAccessible.Text.Description)==button.toolTip()


def wait_service(window):
    ui=window.service_workspace;deadline=time.monotonic()+30
    while ui and (ui.worker or ui._pending_refresh):
        QApplication.processEvents();time.sleep(.005)
        assert time.monotonic()<deadline


@pytest.mark.parametrize('page', [0, 1, 2])
def test_core_action_metadata_survives_mode_switch(qt_application_lifetime, tmp_path, page):
    window = MainWindow(service_root=tmp_path/'project');window.show()
    try:
        window.load_demo();wait_idle(window);window.navigate(page)
        assert_action(window)
        title, hint = window.core_next.text(), window.core_next.toolTip()
        window.mode_picker.setCurrentIndex(1)
        wait_service(window)
        window.mode_picker.setCurrentIndex(0)
        assert window.pages.currentIndex()==page
        assert_action(window)
        assert (window.core_next.text(), window.core_next.toolTip())==(title, hint)
    finally:
        wait_idle(window);window.close()


def test_keyboard_next_and_busy_description(qt_application_lifetime, tmp_path):
    window = MainWindow(service_root=tmp_path/'project');window.show()
    try:
        window.load_demo();wait_idle(window);window.navigate(0)
        window.activateWindow();window.core_next.setFocus()
        QTest.keyClick(window.core_next, Qt.Key.Key_Space)
        assert window.pages.currentIndex()==1
        assert_action(window)
        window.set_busy(True)
        assert not window.core_next.isEnabled()
        assert 'Дождитесь' in window.core_next.toolTip()
        assert_action(window)
        window.set_busy(False)
        assert 'Дождитесь' not in window.core_next.toolTip()
        assert_action(window)
    finally:
        window.set_busy(False);wait_idle(window);window.close()


def test_metadata_after_check_error_repeat_and_mode_switch(qt_application_lifetime, tmp_path):
    window = MainWindow(service_root=tmp_path/'project');window.show()
    try:
        window.load_demo();wait_idle(window);window.navigate(2)
        QTest.keyClick(window.core_next, Qt.Key.Key_Space);wait_idle(window)
        assert_action(window)
        assert 'К созданию' in window.core_next.text()
        QTest.keyClick(window.core_next, Qt.Key.Key_Space)
        assert window.pages.currentIndex()==3
        blocked = tmp_path/'regular-file';blocked.write_bytes(b'QA preserve')
        window.output_path.setText(str(blocked));window.start_generation();wait_idle(window)
        assert window.last_result is None
        window.output_path.setText(str(tmp_path/'output'));window.start_generation();wait_idle(window)
        assert window.last_result.documents==4
        window.navigate(5);wait_service(window);window.navigate(2)
        assert_action(window)
        assert blocked.read_bytes()==b'QA preserve'
    finally:
        wait_idle(window);window.close()


def test_core_reused_template_keeps_each_record_and_previous_runs(tmp_path):
    source = tmp_path/'Таблица.csv';source.write_text('name\nQA Первый\nQA Второй\n', encoding='utf-8')
    template = tmp_path/'Шаблон.docx';document = Document()
    document.add_paragraph('{{name}}');document.save(template)
    before = hashlib.sha256(template.read_bytes()).hexdigest()
    prepared = prepare(Profile(source, [template], {'name': 'name'}))
    old = {}
    for run in range(2):
        result = generate(prepared, tmp_path/'output')
        documents = sorted(result.directory.rglob('*.docx'))
        assert result.documents==2 and len(documents)==2
        for path, expected in zip(documents, ('QA Первый', 'QA Второй')):
            with zipfile.ZipFile(path) as archive:assert archive.testzip() is None
            assert '\n'.join(p.text for p in Document(path).paragraphs)==expected
            old[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path, digest in old.items())
        assert hashlib.sha256(template.read_bytes()).hexdigest()==before
