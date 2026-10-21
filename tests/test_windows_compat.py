"""Filesystem cases run both on Linux and on the real Windows runner."""
import json
import shutil
from pathlib import PureWindowsPath

import pytest
from docx import Document

from docflow.batch import generate, prepare
from docflow.cli import demo_profile
from docflow.profile import Profile
from docflow.safety import safe_name


@pytest.mark.parametrize('name', [
    'CON', 'con.txt', 'CON .txt', 'AUX', 'PRN', 'NUL', 'COM1', 'COM¹',
    'LPT9', 'LPT³', 'CONIN$', 'CONOUT$', 'отчёт: клиент?', 'имя. ',
])
def test_safe_names_create_real_files(tmp_path, name):
    cleaned = safe_name(name)
    assert not PureWindowsPath(cleaned).is_reserved()
    target = tmp_path / cleaned
    target.write_text('проверка', encoding='utf-8')
    assert target.read_text(encoding='utf-8') == 'проверка'


@pytest.mark.parametrize('extension', ['xlsx', 'csv'])
def test_unicode_spaces_profile_and_generation(tmp_path, extension):
    folder = tmp_path / 'Путь с пробелами'
    folder.mkdir()
    demo = Profile.load(demo_profile())
    data = folder / ('Клиенты.' + extension)
    shutil.copy2(demo.data_file.with_suffix('.'+extension), data)
    templates = []
    for i, source in enumerate(demo.templates):
        target = folder / f'{i+1} Шаблон.docx'
        shutil.copy2(source, target)
        templates.append(target)
    p = Profile(data, templates, demo.mapping, demo.rules, demo.name_column)
    saved = folder / 'Настройки.JSON'
    p.save(saved)
    before = {path:path.read_bytes() for path in [data,*templates]}
    restored = Profile.load(saved)
    assert restored.data_file == data.resolve()
    assert restored.templates == [x.resolve() for x in templates]
    result = generate(prepare(restored), folder / 'Результаты Word')
    assert (result.accepted,result.rejected,result.documents) == (2,1,4)
    docs = list(result.directory.rglob('*.docx'))
    assert len(docs) == 4
    assert all('{{' not in '\n'.join(p.text for p in Document(doc).paragraphs) for doc in docs)
    report = json.loads((result.directory/'report.json').read_text(encoding='utf-8'))
    assert report['records'][2]['status'] == 'error'
    assert len(report['records'][2]['issues']) == 2
    assert all(path.read_bytes() == raw for path,raw in before.items())
    assert not list(folder.rglob('.docflow-*'))


def test_cross_drive_profile_paths_fall_back_to_absolute(tmp_path, monkeypatch):
    demo = Profile.load(demo_profile())
    def different_drive(*args):
        raise ValueError('path is on a different drive')
    monkeypatch.setattr('docflow.profile.os.path.relpath', different_drive)
    saved = tmp_path / 'profile.json'
    demo.save(saved)
    obj = json.loads(saved.read_text(encoding='utf-8'))
    assert obj['data_file'] == str(demo.data_file)
    assert Profile.load(saved).data_file == demo.data_file
