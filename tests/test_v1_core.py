"""Stable Core gates: cancellation is atomic, retryable and keeps old results."""
import errno
from pathlib import Path
from threading import Event
import time

import pytest
from docx import Document
from docflow.batch import prepare, generate
from docflow.errors import DocFlowError
from docflow.profile import Profile


def prepared(tmp_path, rows=3):
    source=tmp_path/'Таблица.csv'
    source.write_text('name\n'+'\n'.join('Запись '+str(i) for i in range(rows)),encoding='utf-8')
    doc=Document();doc.add_paragraph('{{name}}');template=tmp_path/'Шаблон.docx';doc.save(template)
    return prepare(Profile(source,[template],{'name':'name'}))


@pytest.mark.parametrize('stop_at',[0,1,3])
def test_cancellation_never_publishes_partial_run_and_retry_works(tmp_path, stop_at):
    job=prepared(tmp_path)
    out=tmp_path/'results';out.mkdir();sentinel=out/'previous.docx';sentinel.write_bytes(b'previous')
    current=0
    def progress(n,total):
        nonlocal current
        current=n
    with pytest.raises(DocFlowError,match='отмен'):
        generate(job,out,progress,cancelled=lambda: current>=stop_at)
    assert list(out.iterdir())==[sentinel]
    assert sentinel.read_bytes()==b'previous'
    result=generate(job,out)
    assert result.documents==3 and result.accepted==3
    assert not list(out.glob('.docflow-*'))


def test_full_disk_invalidates_whole_run_and_keeps_old_files(tmp_path,monkeypatch):
    job=prepared(tmp_path);out=tmp_path/'results';out.mkdir();old=out/'old';old.write_bytes(b'old')
    original=Path.open
    def full(path,*args,**kwargs):
        if path.suffix=='.docx' and args and args[0]=='xb':
            raise OSError(errno.ENOSPC,'synthetic disk full')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',full)
    with pytest.raises(DocFlowError):generate(job,out)
    assert list(out.iterdir())==[old] and old.read_bytes()==b'old'


def test_gui_cancel_then_repeat_is_not_an_error(qt_application_lifetime,tmp_path,monkeypatch):
    from docflow.gui import MainWindow
    from docflow.release_check import wait_idle
    from docflow.templates import Template
    job=prepared(tmp_path);entered=Event();release=Event();original=Template.render
    def paused(template,values):
        entered.set()
        assert release.wait(5)
        return original(template,values)
    monkeypatch.setattr(Template,'render',paused)
    window=MainWindow();window.show();window._install_prepared(job);wait_idle(window)
    window.output_path.setText(str(tmp_path/'output'));window.start_generation()
    try:
        assert entered.wait(5)
        assert window.cancel_btn.isVisible() and window.cancel_btn.isEnabled()
        window.cancel_btn.click();release.set();window.worker.wait(5000);wait_idle(window)
        assert window.last_result is None
        assert 'отмен' in window.status.text().lower()
        assert window.generate_btn.isEnabled() and not window.cancel_btn.isVisible()
        assert not list((tmp_path/'output').iterdir())
        window.start_generation();window.worker.wait(5000);wait_idle(window)
        assert window.last_result.documents==3
    finally:
        release.set()
        if window.worker:window.worker.wait(5000)
        wait_idle(window);window.close()
