"""Shipping terms must be available in package resources and reachable from About."""
from importlib import resources
from pathlib import Path
from PySide6.QtWidgets import QLabel,QPushButton
from PySide6.QtGui import QDesktopServices
from docflow.gui import MainWindow,configure_app

ROOT=Path(__file__).resolve().parents[1]

def test_original_terms_are_present_as_package_data():
    assert resources.files('docflow').joinpath('resources/LICENSE.txt').read_bytes()==(ROOT/'LICENSE.txt').read_bytes()

def test_about_explains_lgpl_and_opens_actual_terms(tmp_path,monkeypatch,qt_application_lifetime):
    configure_app(qt_application_lifetime)
    window=MainWindow(service_root=tmp_path/'project')
    try:
        window.navigate(4)
        text=' '.join(label.text() for label in window.pages.widget(4).findChildren(QLabel))
        assert 'LGPLv3' in text and 'Гапоненко Ростислав Дмитриевич' in text
        urls=[];monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:urls.append(url) or True)
        button=next(b for b in window.pages.widget(4).findChildren(QPushButton) if b.text()=='Условия использования')
        button.click();assert len(urls)==1 and urls[0].isLocalFile()
        assert Path(urls[0].toLocalFile()).read_bytes()==(ROOT/'LICENSE.txt').read_bytes()
    finally:window.close()
