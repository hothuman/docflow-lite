"""Local organization configuration and checked assets, never a tenant/cloud account."""
import copy
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from .attachments import digest, inspect_file, safe_path,copy_bounded
from .statuses import STATUSES
from .validation import ServiceError, money, now, text

NEUTRAL = {'id':None, 'name':'Нейтральный профиль', 'organization_name':'', 'contact':'',
           'details':'', 'number_prefix':'R-', 'number_start':1, 'status_labels':{},
           'default_discount':'0', 'warranty_terms':'', 'template_paths':{}, 'logo_path':''}


def profile(connection, key=None, *, active=False):
    if active and not key:
        row = connection.execute("SELECT value FROM service_settings WHERE key='active_profile'").fetchone()
        key = row[0] if row else None
    if not key:
        return copy.deepcopy(NEUTRAL)
    row = connection.execute('SELECT * FROM organization_profiles WHERE id=?', (key,)).fetchone()
    if row is None:
        raise ServiceError('Профиль предприятия не найден')
    return {**copy.deepcopy(NEUTRAL), **json.loads(row['data_json']), 'id':row['id'], 'name':row['name']}


def profiles(store):
    with store.db.connection() as c:
        return [profile(c, r[0]) for r in c.execute('SELECT id FROM organization_profiles ORDER BY name')]


def validate_profile(data):
    result = {key:text(data.get(key, NEUTRAL[key]), key, key=='name', 20000 if key in ('details','warranty_terms') else 500)
              for key in ('name','organization_name','contact','details','number_prefix','default_discount','warranty_terms')}
    if not re.fullmatch(r'[\w .-]{1,20}', result['number_prefix']):
        raise ServiceError('Префикс номера: от 1 до 20 букв, цифр, пробелов, точек, дефисов')
    try:
        number = int(data.get('number_start', 1))
        if str(number) != str(data.get('number_start', 1)) or not 1 <= number <= 10**12:
            raise ValueError()
    except (ValueError, TypeError):
        raise ServiceError('Начальный номер должен быть целым от 1 до 1000000000000') from None
    result['number_start'] = number
    money(result['default_discount'])
    labels = data.get('status_labels', {})
    if not isinstance(labels, dict) or set(labels)-STATUSES.keys():
        raise ServiceError('Названия статусов должны соответствовать существующим производственным состояниям')
    result['status_labels'] = {k:text(v, 'Название статуса', True, 100) for k,v in labels.items()}
    paths = data.get('template_paths', {})
    if not isinstance(paths, dict):
        raise ServiceError('Неверный список шаблонов профиля')
    from .documents import KINDS
    if set(paths)-KINDS.keys():
        raise ServiceError('Неизвестный вид шаблона')
    result['template_paths'] = {k:text(v, 'Путь шаблона', True, 500) for k,v in paths.items()}
    result['logo_path'] = text(data.get('logo_path', ''), 'Путь логотипа', limit=500)
    return result


def save_profile(store, data, key=None, *, assets=None, logo_rights_confirmed=False, activate=False):
    """Copy explicitly selected files and commit their registry with the profile.

    Old assets remain referenced by historical estimate snapshots and backups.
    Caller must affirm logo rights; no permission is inferred from a filename.
    """
    values = validate_profile(data)
    assets = assets or {}
    created = []
    key = key or uuid4().hex
    try:
        with store.lock, store.db.connection(True) as c:
            existing = c.execute('SELECT 1 FROM organization_profiles WHERE id=?', (key,)).fetchone()
            selected = []
            if assets.get('logo'):
                if not logo_rights_confirmed:
                    raise ServiceError('Для логотипа нужно подтвердить право использования')
                source = Path(assets['logo'])
                kind, _ = inspect_file(source)
                if kind != 'image' or source.stat().st_size > 10*1024**2:
                    raise ServiceError('Логотип: PNG/JPEG не более 10 MiB')
                selected.append(('logo', source))
            for doc_kind, source in assets.get('templates', {}).items():
                from .documents import KINDS
                from ..templates import Template
                if doc_kind not in KINDS:
                    raise ServiceError('Неизвестный документ профиля')
                source = Path(source)
                Template.load(source)
                selected.append((doc_kind, source))
            for asset_kind, source in selected:
                relative = f'profiles/{key}/{uuid4().hex}{source.suffix.lower()}'
                target = safe_path(store.root, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                copy_bounded(source,target,10*1024**2 if asset_kind=='logo' else 20*1024**2)
                created.append(target)
                # Validate the copied bytes, not just the pre-copy source.
                if asset_kind == 'logo':
                    inspect_file(target); values['logo_path'] = relative
                else:
                    from ..templates import Template
                    Template.load(target); values['template_paths'][asset_kind] = relative
                c.execute('INSERT INTO managed_files(path,sha256,size,kind) VALUES(?,?,?,?)',
                          (relative, digest(target), target.stat().st_size, asset_kind))
            for relative in list(values['template_paths'].values()) + ([values['logo_path']] if values['logo_path'] else []):
                path = safe_path(store.root, relative)
                record = c.execute('SELECT * FROM managed_files WHERE path=?', (relative,)).fetchone()
                if record is None or not path.is_file() or digest(path) != record['sha256']:
                    raise ServiceError('Файл профиля отсутствует или изменён; выберите его заново')
            stamp = now(); content = json.dumps(values, ensure_ascii=False, sort_keys=True)
            if existing:
                c.execute('UPDATE organization_profiles SET name=?,data_json=?,updated_at=? WHERE id=?',
                          (values['name'], content, stamp, key))
            else:
                c.execute('INSERT INTO organization_profiles(id,name,data_json,created_at,updated_at) VALUES(?,?,?,?,?)',
                          (key, values['name'], content, stamp, stamp))
            if activate:
                c.execute("INSERT INTO service_settings(key,value) VALUES('active_profile',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key,))
            store.audit(c, 'profile', key, 'save')
    except Exception:
        for path in created: path.unlink(missing_ok=True)
        raise
    return key


def activate_profile(store, key=None):
    with store.lock, store.db.connection(True) as c:
        if key:
            profile(c, key)
            c.execute("INSERT INTO service_settings(key,value) VALUES('active_profile',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key,))
        else:
            c.execute("DELETE FROM service_settings WHERE key='active_profile'")
        store.audit(c, 'profile', key or 'neutral', 'activate')


def next_number(connection):
    p = profile(connection, active=True)
    n = p['number_start']
    used = {r[0].casefold() for r in connection.execute('SELECT number FROM repair_orders')}
    while (number := f"{p['number_prefix']}{n:06d}").casefold() in used:
        n += 1
    return number, p['id']
