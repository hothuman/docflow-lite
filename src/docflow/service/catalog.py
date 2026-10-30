"""Exact-key catalog preview/apply. Catalog updates never write repair history."""
from collections import Counter
from dataclasses import dataclass
import hashlib,json,re,unicodedata
from .validation import ServiceError,money,now,text

FIELDS=('external_id','sku','name','group','subgroup','category','unit','kind','description','manufacturer','price','currency','availability','shelf_raw','exported_at')
LABELS=dict(zip(FIELDS,('Внешний код','Внутренний артикул','Название','Группа','Подгруппа','Категория','Единица','Тип (part/work)','Описание','Производитель','Цена','Валюта','Актуальность (как в источнике)','Полка (смысл не подтверждён)','Дата выгрузки (как в источнике)')))
BUSINESS=tuple(x for x in FIELDS if x!='price')+('price_cents',)
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()

def safe_value(value):
    value=str(value or '')
    if len(value)>2000 or any(unicodedata.category(c) in ('Cf','Cs','Cc') and c not in '\n\t' for c in value):raise ServiceError('Управляющие символы или слишком длинная ячейка')
    if value.lstrip().startswith(('=','+','-','@')) or re.search(r'(?i)(https?://|file:|ftp:|\\\\)',value):raise ServiceError('Формула, путь или внешняя ссылка: замените безопасным текстом')
    return value

def normalize(values):
    item={k:safe_value(values.get(k,'')) for k in FIELDS}
    for key in ('external_id','sku'):
        if item[key]!=item[key].strip():raise ServiceError('Пробелы вокруг идентификатора: требуется явное исправление файла')
    if not item['name'].strip():raise ServiceError('Нет названия')
    if len(item['name'])>500 or len(item['sku'])>150 or len(item['external_id'])>150:raise ServiceError('Слишком длинный код или название')
    if item['kind'] not in ('','part','work'):raise ServiceError('Тип должен быть part или work; неизвестный тип не угадывается')
    price=item.pop('price')
    item['price_cents']=money(price) if price.strip() else None
    if item['currency'] and not re.fullmatch('[A-Z]{3}',item['currency']):raise ServiceError('Валюта: явный трёхбуквенный код, например RUB')
    if item['price_cents'] is not None and not item['currency']:raise ServiceError('Для цены нужна явно указанная валюта')
    return item

def _current(c,source):
    rows=list(c.execute('SELECT external_key,sku,payload_json FROM catalog_items WHERE source=? ORDER BY external_key',(source,)))
    return {r[0]:json.loads(r[2]) for r in rows}

@dataclass(frozen=True)
class PreviewRow:
    line:int
    key:str
    payload:str
    state:str
    reason:str=''
    @property
    def item(self):return json.loads(self.payload) if self.payload else {}

@dataclass(frozen=True)
class Preview:
    source:str
    file_sha256:str
    file_name:str
    config_json:str
    base_digest:str
    rows:tuple
    @property
    def counts(self):return dict(Counter(r.state for r in self.rows))

def preview(store,parsed,source,mapping,*,key_field='external_id',update_prices=False,currency=''):
    source=text(safe_value(source),'Источник',True,150)
    if len(parsed['headers'])>32 or len(parsed['rows'])>5000:raise ServiceError('Превышен лимит колонок или строк')
    if key_field not in ('external_id','sku') or not mapping.get(key_field) or not mapping.get('name'):raise ServiceError('Сопоставьте название и выбранный устойчивый код')
    if set(mapping)-set(FIELDS) or any(v not in parsed['headers'] for v in mapping.values() if v):raise ServiceError('Неверное сопоставление колонок')
    config={'mapping':mapping,'key_field':key_field,'update_prices':bool(update_prices),'currency':currency,'sheet':parsed.get('sheet',''),'encoding':parsed.get('encoding','auto'),'source':source}
    with store.db.connection() as c:current=_current(c,source)
    prepared=[]
    for line,raw in parsed['rows']:
        try:
            for value in raw.values():safe_value(value)
            values={k:raw.get(v,'') for k,v in mapping.items() if v}
            if not values.get('currency') and currency:values['currency']=currency
            item=normalize(values);key=item[key_field]
            if not key:raise ServiceError('Нет устойчивого ключа')
            prepared.append(PreviewRow(line,key,canonical(item),'pending'))
        except ServiceError as exc:prepared.append(PreviewRow(line,'','','error',str(exc)))
    keys=Counter(r.key for r in prepared if r.key);skus=Counter(r.item.get('sku') for r in prepared if r.payload and r.item.get('sku'))
    existing_skus={v['sku']:k for k,v in current.items() if v.get('sku')}
    rows=[]
    for row in prepared:
        if row.state=='error':rows.append(row);continue
        item=row.item;sku=item.get('sku');reason=''
        if keys[row.key]>1 or (sku and skus[sku]>1):state='conflict';reason='Дубли кода или артикула внутри файла'
        elif sku and existing_skus.get(sku,row.key)!=row.key:state='conflict';reason='Артикул уже связан с другим внешним кодом'
        else:
            if row.key in current and not update_prices:
                if (item['price_cents'],item['currency'])!=(current[row.key]['price_cents'],current[row.key]['currency']):reason='Обновление цены отключено; прежняя цена сохранена'
                item['price_cents']=current[row.key]['price_cents'];item['currency']=current[row.key]['currency']
            state='new' if row.key not in current else 'unchanged' if item==current[row.key] else 'update'
        rows.append(PreviewRow(row.line,row.key,canonical(item),state,reason))
    return Preview(source,parsed['file_sha256'],parsed['file_name'],canonical(config),digest(current),tuple(rows))

def apply(store,plan,*,confirmed=False,skip_problems=False,cancel=None):
    if not confirmed:raise ServiceError('Сначала подтвердите предпросмотр')
    if any(r.state in ('conflict','error') for r in plan.rows) and not skip_problems:raise ServiceError('Есть конфликты/ошибки; исправьте файл или явно подтвердите пропуск')
    with store.lock,store.db.connection(True) as c:
        if digest(_current(c,plan.source))!=plan.base_digest:raise ServiceError('Каталог изменился после предпросмотра; выполните проверку заново')
        for row in plan.rows:
            if cancel and cancel.is_set():raise ServiceError('Импорт отменён; изменения откачены')
            if row.state not in ('new','update'):continue
            c.execute('INSERT INTO catalog_items(source,external_key,sku,payload_json,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(source,external_key) DO UPDATE SET sku=excluded.sku,payload_json=excluded.payload_json,updated_at=excluded.updated_at',(plan.source,row.key,row.item.get('sku',''),row.payload,now()))
        if c.execute('SELECT COUNT(*) FROM catalog_items').fetchone()[0]>50000:raise ServiceError('Каталог превышает 50000 позиций')
        if cancel and cancel.is_set():raise ServiceError('Импорт отменён; изменения откачены')
        report={'counts':plan.counts,'skipped':sum(r.state in ('error','conflict') for r in plan.rows),'file_name':plan.file_name,'config':json.loads(plan.config_json)}
        c.execute('INSERT INTO catalog_imports(source,file_sha256,report_json,created_at) VALUES(?,?,?,?)',(plan.source,plan.file_sha256,canonical(report),now()))
        store.audit(c,'catalog',plan.source,'import',canonical(plan.counts))
    return report

def search(store,query='',limit=500):
    query=query.casefold().strip()
    with store.db.connection() as c:
        # Bound iteration as well as returned rows; the catalog itself has a hard cap.
        result=[]
        for r in c.execute('SELECT source,external_key,payload_json FROM catalog_items ORDER BY source,external_key LIMIT 50000'):
            item={**json.loads(r[2]),'source':r[0],'external_key':r[1]}
            if not query or query in ' '.join(str(item.get(k,'')) for k in ('external_id','sku','name','group','subgroup','category','manufacturer')).casefold():result.append(item)
            if len(result)>=limit:break
        return result

def save_profile(store,name,config):
    name=text(name,'Название профиля',True,150)
    if set(config)!={'source','mapping','key_field','update_prices','currency','sheet','encoding'} or not isinstance(config['mapping'],dict) or set(config['mapping'])-set(FIELDS):raise ServiceError('Некорректный профиль')
    if len(canonical(config))>16000:raise ServiceError('Профиль слишком большой')
    with store.lock,store.db.connection(True) as c:c.execute('INSERT INTO catalog_profiles VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET config_json=excluded.config_json,updated_at=excluded.updated_at',(name,canonical(config),now()))

def profiles(store):
    with store.db.connection() as c:return {r[0]:json.loads(r[1]) for r in c.execute('SELECT name,config_json FROM catalog_profiles ORDER BY name')}

def import_history(store):
    with store.db.connection() as c:return [{**dict(r),'report':json.loads(r['report_json'])} for r in c.execute('SELECT * FROM catalog_imports ORDER BY id DESC LIMIT 20')]
