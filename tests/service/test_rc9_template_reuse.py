"""Reusing a supplied template must preserve source bytes and per-repair context."""
import hashlib
import json
import zipfile

import pytest
from docx import Document

from docflow.service.documents import KINDS, create_templates, generate_document
from docflow.service.estimates import freeze_estimate, save_draft
from docflow.service.profiles import save_profile
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
    document = Document(path)
    return '\n'.join([p.text for p in document.paragraphs] + [
        c.text for t in document.tables for r in t.rows for c in r.cells])


@pytest.mark.parametrize('modern', [False, True], ids=['v5', 'v6'])
@pytest.mark.parametrize('mode', ['explicit', 'profile'])
@pytest.mark.parametrize('organization', ['', 'QA Исполнитель'])
def test_reuse_completion_for_two_repairs_and_repeat(tmp_path, modern, mode, organization):
    store = ServiceStore(tmp_path/'project')
    template = create_templates(tmp_path/'templates', modern=modern)['completion']
    original = sha(template)
    repairs = [store.intake(client={'name': name}, equipment={
        'number': number, 'model': 'QA Модель'}) for name, number in (
            ('QA Заказчик Первый', 'QA-001'), ('QA Заказчик Второй', 'QA-002'))]
    paths = {}
    for repair in repairs:
        save_profile(store, {'name': 'QA Профиль', 'organization_name': organization,
                            'details': 'QA реквизиты', 'contact': 'QA контакт'},
                     assets={'templates': {'completion': template}} if mode=='profile' else None,
                     repair_id=repair)
    for run in range(2):
        for index, repair in enumerate(repairs):
            path = generate_document(store, repair, 'completion',
                                     template=template if mode=='explicit' else None)
            text = content(path)
            own, other = ('Первый', 'Второй') if index==0 else ('Второй', 'Первый')
            assert own in text and other not in text
            assert ('QA-001' if index==0 else 'QA-002') in text
            # Classic v5 displays the explicit (possibly blank) executor field;
            # modern v6 adds the neutral-form explanation for an empty profile.
            assert (organization or ('Исполнитель не указан — нейтральная форма' if modern else 'Исполнитель:')) in text
            assert 'QA реквизиты' in text and 'QA контакт' in text
            assert '{{' not in text
            paths[path] = sha(path)
        assert sha(template)==original
        assert all(sha(path)==digest for path, digest in paths.items())
    with store.db.connection() as connection:
        for repair in repairs:
            rows = connection.execute('SELECT version,sha256 FROM generated_documents '
                                      'WHERE repair_id=? ORDER BY version', (repair,)).fetchall()
            assert [row['version'] for row in rows]==[1, 2]
    assert len(paths)==4


@pytest.mark.parametrize('modern', [False, True], ids=['v5', 'v6'])
@pytest.mark.parametrize('kind', [k for k in KINDS if k!='completion'])
def test_profile_template_supports_other_document_kinds(tmp_path, modern, kind):
    store = ServiceStore(tmp_path/'project')
    repair = store.intake(client={'name': 'QA Заказчик'},
                         equipment={'number': 'QA-ALL', 'model': 'QA Модель'})
    template = create_templates(tmp_path/'templates', modern=modern)[kind]
    original = sha(template)
    save_profile(store, {'name': 'QA Профиль', 'organization_name': 'QA Организация'},
                 assets={'templates': {kind: template}}, repair_id=repair)
    estimate = None
    if kind.startswith('estimate_'):
        save_draft(store, repair, [{'kind': 'work', 'name': 'QA Работа', 'price': '1.01'}])
        estimate = freeze_estimate(store, repair, kind.removeprefix('estimate_'), 'QA Оператор')
    path = generate_document(store, repair, kind, estimate_id=estimate)
    text = content(path)
    assert 'QA Организация' in text and 'QA Заказчик' in text
    assert '{{' not in text and sha(template)==original


def test_reused_estimate_template_uses_immutable_organization(tmp_path):
    store = ServiceStore(tmp_path/'project')
    repair = store.intake(client={'name': 'QA Заказчик'},
                         equipment={'number': 'QA-FROZEN', 'model': 'QA Модель'})
    template = create_templates(tmp_path/'templates', modern=True)['estimate_preliminary']
    key = save_profile(store, {'name': 'QA Профиль', 'organization_name': 'QA Старая организация'},
                       assets={'templates': {'estimate_preliminary': template}}, repair_id=repair)
    quote = freeze_estimate(store, repair, 'preliminary', 'QA Оператор')
    first = generate_document(store, repair, 'estimate_preliminary', estimate_id=quote)
    original = sha(first)
    with store.db.connection() as connection:
        before = connection.execute('SELECT payload_json FROM estimate_versions WHERE id=?', (quote,)).fetchone()[0]
    save_profile(store, {'name': 'QA Профиль', 'organization_name': 'QA Новая организация'},
                 key=key, repair_id=repair)
    second = generate_document(store, repair, 'estimate_preliminary', estimate_id=quote)
    assert 'QA Старая организация' in content(second) and 'QA Новая организация' not in content(second)
    assert sha(first)==original
    with store.db.connection() as connection:
        assert connection.execute('SELECT payload_json FROM estimate_versions WHERE id=?', (quote,)).fetchone()[0]==before


def test_unknown_template_field_rejected_without_partial_document_then_retry(tmp_path):
    store = ServiceStore(tmp_path/'project')
    repair = store.intake(client={'name': 'QA Заказчик'},
                         equipment={'number': 'QA-BAD', 'model': 'QA Модель'})
    first = generate_document(store, repair, 'completion')
    original = sha(first)
    template = tmp_path/'unknown.docx'
    document = Document();document.add_paragraph('{{unknown_qa_field}}');document.save(template)
    with pytest.raises(ServiceError, match='unknown_qa_field'):
        generate_document(store, repair, 'completion', template=template)
    assert len(store.documents())==1 and sha(first)==original
    valid = create_templates(tmp_path/'valid', modern=True)['completion']
    content(generate_document(store, repair, 'completion', template=valid))
    assert len(store.documents())==2 and sha(first)==original
