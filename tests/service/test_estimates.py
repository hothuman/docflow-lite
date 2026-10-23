import csv
import json
from pathlib import Path

import pytest

from docflow.service.repository import ServiceStore
from docflow.service.demo import seed_demo
from docflow.service.estimates import (save_draft, freeze_estimate, record_event,
    get_estimate, export_specification)
from docflow.service.profiles import save_profile, activate_profile, profile
from docflow.service.backup import create_backup, restore_backup
from docflow.service.validation import ServiceError


@pytest.fixture
def project(tmp_path):
    s = ServiceStore(tmp_path/'project'); ids = seed_demo(s.root)
    r = s.create_repair(ids['equipment'], 'QUOTE-TEST')
    return s, ids, r


def preliminary():
    return [
        {'kind':'work','name':'Учебная работа','quantity':'1.5','price':'1000.25'},
        {'kind':'part','name':'Учебная деталь','quantity':'2','price':'200.10'},
        {'kind':'delivery','name':'Доставка в сервис','quantity':'2','price':'150'},
        {'kind':'delivery','name':'Доставка обратно','quantity':'1','price':'50'},
        {'kind':'other','name':'Согласованный учебный расход','price':'25'},
    ]


def test_preliminary_final_delivery_approval_snapshot_and_restore(project, tmp_path):
    s, ids, r = project
    assert save_draft(s, r, preliminary(), '100', 'Учебный расчёт', 0) == 1
    assert s.snapshot(r)['totals']['total'] == s.snapshot(r)['totals']['balance'] == 0
    key = freeze_estimate(s, r, 'preliminary', 'Тестовый оператор', request_id='freeze-once')
    assert freeze_estimate(s, r, 'preliminary', 'Тестовый оператор', request_id='freeze-once') == key
    record_event(s, key, 'approved', 'Тестовый оператор', 'Учебная ручная отметка, не реальное согласие')
    with s.db.connection() as c:
        before = get_estimate(c, key)
    assert before['total'] == 217558
    assert 'balance' not in before['payload']['totals']
    with pytest.raises(ServiceError): s.save_item(r, {'kind':'work','name':'Новая работа','price':'1200'})
    s.save_item(r, {'kind':'work','name':'Фактическая работа','price':'1200','change_reason':'Уточнение объёма после дефектовки'})
    s.save_item(r, {'kind':'delivery','name':'Фактическая доставка','price':'200','change_reason':'Фактический маршрут'})
    s.save_repair(r, {'discount':'25','change_reason':'Утверждённая тестовая скидка'})
    s.add_payment(r, '500')
    assert s.snapshot(r)['totals']['balance'] == 87500
    diff = s.snapshot(r)['estimate_comparison']
    assert diff['preliminary_total'] == 217558 and diff['final_total'] == 137500
    assert diff['difference'] == -80058 and diff['changed_from_approved']
    with pytest.raises(ServiceError): freeze_estimate(s, r, 'final', 'Тестовый оператор')
    final = freeze_estimate(s, r, 'final', 'Тестовый оператор', 'Уточнены фактические работы и маршрут')
    save_draft(s, r, [{'kind':'work','name':'Другой черновик','price':'1'}], expected_revision=1)
    with s.db.connection() as c:
        assert get_estimate(c, key) == before
        assert get_estimate(c, final)['total'] == 137500
    b = create_backup(s, tmp_path/'quotes.zip'); restored = restore_backup(b, tmp_path/'restored')
    again = ServiceStore(restored)
    with again.db.connection() as c:
        assert get_estimate(c, key) == before
        assert get_estimate(c, final)['payload']['totals']['paid'] == 50000


def test_sql_cannot_rewrite_estimate_or_manual_history(project):
    s, _, r = project
    key = freeze_estimate(s, r, 'preliminary', 'Оператор')
    for query in ('UPDATE estimate_versions SET prepared_by=\'Changed\' WHERE id=?',
                  'DELETE FROM estimate_versions WHERE id=?',
                  'UPDATE estimate_events SET actor=\'Changed\' WHERE estimate_id=?',
                  'DELETE FROM estimate_events WHERE estimate_id=?'):
        with pytest.raises(ServiceError), s.db.connection(True) as c: c.execute(query, (key,))
    with s.db.connection() as c: assert get_estimate(c, key)['prepared_by'] == 'Оператор'


def test_draft_revision_and_invalid_discount_preserve_previous_data(project):
    s, _, r = project
    save_draft(s, r, preliminary(), expected_revision=0)
    before = s.snapshot(r)['preliminary_draft']
    with pytest.raises(ServiceError): save_draft(s, r, [], '1', expected_revision=1)
    with pytest.raises(ServiceError): save_draft(s, r, [], expected_revision=0)
    assert s.snapshot(r)['preliminary_draft'] == before


def test_zero_quotes_and_manual_event_rules(project):
    s, _, r = project
    key = freeze_estimate(s, r, 'preliminary', 'Оператор')
    with pytest.raises(ServiceError): record_event(s, key, 'approved', '', 'Причина')
    with pytest.raises(ServiceError): record_event(s, key, 'approved', 'Оператор', '')
    ev = record_event(s, key, 'approved', 'Оператор', 'Вымышленный тест')
    assert record_event(s, key, 'approved', 'Оператор', 'Вымышленный тест') == ev
    with pytest.raises(ServiceError): record_event(s, key, 'sent', 'Оператор', 'Недопустимый переход')
    record_event(s, key, 'withdrawn', 'Оператор', 'Вымышленное исправление отметки')
    assert s.snapshot(r)['estimate_comparison']['approved_estimate_id'] is None
    final = freeze_estimate(s, r, 'final', 'Оператор')
    with s.db.connection() as c: assert get_estimate(c, final)['total'] == 0


@pytest.mark.parametrize('rows,discount', [
    ([{'kind':'delivery','name':'A','quantity':'0','price':'1'}], '0'),
    ([{'kind':'delivery','name':'A','quantity':'1.23456','price':'1'}], '0'),
    ([{'kind':'other','name':'A','quantity':'1000000000','price':'1000000000000'}], '0'),
    ([{'kind':'part','name':'A','price':'-1'}], '0'),
    ([], '0.01'),
])
def test_quote_invalid_bounds_are_atomic(project, rows, discount):
    s, _, r = project
    with pytest.raises(ServiceError): save_draft(s, r, rows, discount)
    assert s.snapshot(r)['preliminary_draft']['revision'] == 0


def test_rounding_overpayment_refund_and_void_use_only_final(project):
    s, _, r = project
    save_draft(s, r, [{'kind':'work','name':'План','price':'500'}])
    s.save_item(r, {'kind':'delivery','name':'Дробная доставка','quantity':'0.5','price':'0.01'})
    assert s.snapshot(r)['totals']['total'] == 1
    p = s.add_payment(r, '2'); refund = s.add_payment(r, '0.50', 'refund')
    t = s.snapshot(r)['totals']; assert t['overpaid'] == 149 and t['financial_status'] == 'Переплата / корректировка'
    s.void_payment(refund, 'Учебная корректировка'); s.void_payment(p, 'Учебная корректировка')
    assert s.snapshot(r)['totals']['financial_status'] == 'Нет учтённой оплаты'


def test_quote_csv_is_real_and_formula_safe(project, tmp_path):
    s, _, r = project
    save_draft(s, r, [{'kind':'other','name':'=HYPERLINK("bad")','price':'12.50'}])
    key = freeze_estimate(s, r, 'preliminary', 'Оператор')
    p = export_specification(s, key, tmp_path/'specification.csv')
    with p.open(encoding='utf-8-sig', newline='') as f: rows = list(csv.reader(f, delimiter=';'))
    assert rows[1][5].startswith("'=") and rows[-1][-1] == '12.50'
    before = p.read_bytes()
    with pytest.raises(FileExistsError): export_specification(s, key, p)
    assert p.read_bytes() == before


def test_local_profiles_numbering_statuses_and_historical_profile_snapshot(project):
    s, ids, _ = project
    key = save_profile(s, {'name':'Учебная мастерская А','organization_name':'Синтетическое предприятие А',
                           'number_prefix':'SYN-', 'number_start':'900', 'status_labels':{'accepted':'Ожидает осмотра'}}, activate=True)
    repair = s.create_repair(ids['equipment'])
    assert s.get('repair_orders', repair)['number'] == 'SYN-000900'
    assert s.repairs(equipment_id=ids['equipment'])[0]['status_display'] == 'Ожидает осмотра'
    quote = freeze_estimate(s, repair, 'preliminary', 'Оператор')
    save_profile(s, {'name':'Учебная мастерская Б','organization_name':'Синтетическое предприятие Б'}, key)
    with s.db.connection() as c:
        assert get_estimate(c, quote)['payload']['profile']['organization_name'] == 'Синтетическое предприятие А'
        assert profile(c, key)['organization_name'] == 'Синтетическое предприятие Б'
    activate_profile(s)
    assert s.create_repair(ids['equipment'])


def test_profile_assets_are_checked_and_restored(project, tmp_path):
    from PySide6.QtGui import QImage, QColor
    s, _, _ = project
    logo = tmp_path/'synthetic.png'; im = QImage(100,100,QImage.Format.Format_RGB32); im.fill(QColor('#873047')); assert im.save(str(logo))
    with pytest.raises(ServiceError): save_profile(s, {'name':'Учебный'}, assets={'logo':logo})
    key = save_profile(s, {'name':'Учебный'}, assets={'logo':logo}, logo_rights_confirmed=True)
    with s.db.connection() as c: relative = profile(c, key)['logo_path']
    assert (s.root/relative).read_bytes() == logo.read_bytes()
    b = create_backup(s, tmp_path/'profile.zip'); root = restore_backup(b, tmp_path/'restored')
    assert (root/relative).read_bytes() == logo.read_bytes()
