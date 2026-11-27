"""Standard diagnostics only store safe technical metadata."""

from concurrent.futures import ThreadPoolExecutor
import logging
import socket
from urllib import request

import pytest

from docflow.ui import diagnostics


@pytest.fixture
def local_journal(tmp_path, monkeypatch):
    logger = logging.Logger('test-local-journal', logging.INFO)
    monkeypatch.setattr(diagnostics, '_logger', logger)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    yield diagnostics.diagnostic_path()
    for handler in logger.handlers:
        handler.close()


def test_technical_log_excludes_message_paths_nested_errors_and_unknown_context(
        local_journal, monkeypatch):
    private = 'QA Клиент +7 900 111-22-33 user@example.invalid ИНН 123456789012 секрет DOCX'
    legacy = local_journal.with_name('diagnostic.log')
    legacy.parent.mkdir(parents=True)
    legacy.write_text(private, encoding='utf-8')

    def forbidden(*args, **kwargs):
        pytest.fail('Local diagnostics must not send data')

    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(request, 'urlopen', forbidden)
    code = compile(
        'try:\n raise ValueError(private)\nexcept ValueError as cause:\n'
        ' raise PermissionError(13, private, private) from cause',
        'C:/QA-private-project/record.docx', 'exec',
    )
    try:
        exec(code, {'__name__': 'docflow.ui.window', 'private': private})
    except PermissionError as exc:
        diagnostics.record_exception('Core generation', exc)
        diagnostics.record_exception(private, exc)
        diagnostics.record_project_event(private, exc)
    text = diagnostics.read_diagnostics()
    assert 'operation=Core generation error_type=PermissionError frames=docflow.ui.window:4' in text
    assert 'operation=other' in text and 'project result=other' in text
    assert private not in text
    for marker in ('example.invalid', '900 111', '123456789012', 'QA-private-project',
                   'record.docx', 'Traceback', 'ValueError', 'секрет DOCX'):
        assert marker not in text
    assert legacy.read_text(encoding='utf-8') == private


def test_worker_and_project_events_rotate_one_concurrent_writer(local_journal, monkeypatch):
    monkeypatch.setattr(diagnostics, '_MAX_BYTES', 340)

    def emit(index):
        diagnostics.record_exception('Service worker', RuntimeError('QA confidential'))
        diagnostics.record_project_event('worker_error', PermissionError('QA private path'))

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(emit, range(24)))
    paths = sorted(local_journal.parent.glob('technical.log*'))
    assert {path.name for path in paths} == {'technical.log', 'technical.log.1', 'technical.log.2'}
    assert all(0 < path.stat().st_size < 340 for path in paths)
    text = ''.join(path.read_text(encoding='utf-8') for path in paths)
    assert 'project result=worker_error' in text and 'operation=Service worker' in text
    assert 'QA confidential' not in text and 'QA private path' not in text
    assert len(diagnostics._logger.handlers) == 1
