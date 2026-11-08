
from docx import Document
import pytest

from docflow.service.backup import create_backup, inspect_backup, restore_backup
from docflow.service.documents import generate_document
from docflow.service.repository import ServiceStore
from docflow.service.validation import ServiceError


def test_verified_backup_cannot_silently_be_replaced_before_restore(tmp_path):
    first = ServiceStore(tmp_path/'source')
    first.save_client({'name':'Учебный заказчик'})
    archive = create_backup(first,tmp_path/'source.zip')
    expected = inspect_backup(archive)
    assert expected['schema'] == 6 and expected['files'] >= 1
    original = archive.read_bytes()

    second = ServiceStore(tmp_path/'other')
    second.save_client({'name':'Другой учебный заказчик'})
    alternative = create_backup(second,tmp_path/'other.zip')
    archive.write_bytes(alternative.read_bytes())
    destination = tmp_path/'restored'
    with pytest.raises(ServiceError,match='Архив изменился'):
        restore_backup(archive,destination,expected_sha256=expected['sha256'])
    assert not destination.exists()
    assert first.clients()[0]['name']=='Учебный заказчик'

    archive.write_bytes(original)
    restored = ServiceStore(restore_backup(archive,destination,expected_sha256=expected['sha256']))
    assert restored.clients()[0]['name']=='Учебный заказчик'
    assert archive.read_bytes()==original
    with restored.db.connection() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


@pytest.mark.parametrize('serial',['','QA-SN-007'])
def test_stock_document_does_not_print_empty_serial_label(tmp_path,serial):
    store = ServiceStore(tmp_path/'project')
    key = store.intake(client={'name':'Учебный клиент'},
                       equipment={'number':'0007','model':'Насос','serial':serial})
    path = generate_document(store,key,'intake')
    equipment = next(p.text for p in Document(path).paragraphs if p.text.startswith('Оборудование:'))
    assert 'Насос' in equipment and '0007' in equipment
    assert ('серийный №' in equipment) == bool(serial)
    if serial:
        assert serial in equipment
