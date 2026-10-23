"""Domain repository; all SQL, exact calculations and validation stay out of Qt."""
from pathlib import Path
import os
import threading
import json
from uuid import uuid4
from .database import Database
from .validation import text,day,now,money,quantity,line_total,ServiceError
from .statuses import STATUSES,APPROVALS,TERMINAL
from .finance import totals,calculate,ITEM_KINDS

def default_root():
    if os.name=='nt': return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'DocFlowLite'/'Service'
    return Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'DocFlowLite'/'Service'

class ServiceStore:
    def __init__(self,root=None):
        self.root=Path(root or default_root()).absolute()
        if self.root.is_symlink():raise ServiceError('Каталог проекта не должен быть ссылкой')
        self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock(); self.db=Database(self.root/'service.db')
    @staticmethod
    def audit(c,entity,key,action,detail=''):
        c.execute('INSERT INTO operations(entity,entity_id,action,detail,created_at) VALUES(?,?,?,?,?)',(entity,key,action,detail,now()))
    @staticmethod
    def require(c,table,key):
        if table not in {'clients','equipment','repair_orders','repair_items','payments','attachments','generated_documents'}:raise ServiceError('Неизвестный тип записи')
        row=c.execute(f'SELECT * FROM {table} WHERE id=?',(key,)).fetchone()
        if row is None:raise ServiceError('Запись не найдена')
        return dict(row)
    def get(self,table,key):
        with self.db.connection() as c:return self.require(c,table,key)
    def save_client(self,data,key=None):
        values={k:text(data.get(k),k,k=='name',300 if k!='notes' else 20000) for k in ('name','legal_name','contact','phone','email','notes')}
        values['kind']=data.get('kind','organization')
        if values['kind'] not in {'organization','individual','entrepreneur'}:raise ServiceError('Неизвестный тип клиента')
        if values['email'] and ('@' not in values['email'] or any(x.isspace() for x in values['email'])):raise ServiceError('Проверьте email')
        return self._save('clients',values,key)
    def save_equipment(self,data,key=None):
        values={k:text(data.get(k),k,k in ('number','model','owner_id'),300 if k!='notes' else 20000) for k in ('number','manufacturer','model','kind','serial','owner_id','identifiers','notes')}
        with self.db.connection() as c:
            owner=self.require(c,'clients',values['owner_id'])
            if owner['archived']:raise ServiceError('Выберите действующего клиента')
        return self._save('equipment',values,key)
    def _save(self,table,values,key):
        if table not in {'clients','equipment'}:raise ServiceError('Недопустимая запись')
        with self.lock,self.db.connection(True) as c:
            stamp=now()
            if table=='equipment' and any(r['id']!=key and r['number'].casefold()==values['number'].casefold() for r in c.execute('SELECT id,number FROM equipment')):raise ServiceError('Постоянный номер уже существует')
            if key:
                self.require(c,table,key)
                c.execute(f'UPDATE {table} SET '+','.join(k+'=?' for k in values)+',updated_at=? WHERE id=?',(*values.values(),stamp,key))
            else:
                key=uuid4().hex;values={**values,'created_at':stamp,'updated_at':stamp,'id':key}
                c.execute(f'INSERT INTO {table}('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))
            self.audit(c,table,key,'save')
        return key
    def archive(self,table,key,archived=True):
        if table not in {'clients','equipment'}:raise ServiceError('История ремонтов не удаляется')
        with self.lock,self.db.connection(True) as c:
            self.require(c,table,key)
            if archived:
                if table=='clients' and c.execute('SELECT 1 FROM equipment WHERE owner_id=? AND archived=0',(key,)).fetchone():raise ServiceError('Сначала перенесите или архивируйте оборудование клиента')
                if table=='equipment' and c.execute("SELECT 1 FROM repair_orders WHERE equipment_id=? AND status NOT IN('issued','closed','cancelled')",(key,)).fetchone():raise ServiceError('Есть незавершённый ремонт; сначала закройте его')
            c.execute(f'UPDATE {table} SET archived=?,updated_at=? WHERE id=?',(int(archived),now(),key));self.audit(c,table,key,'archive',str(archived))
    def clients(self,query='',archived=False):
        with self.db.connection() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM clients WHERE archived=? ORDER BY name',(int(archived),))]
        q=query.casefold();return [r for r in rows if not q or q in ' '.join(str(v) for v in r.values()).casefold()]
    def equipment(self,query='',archived=False,active=False):
        with self.db.connection() as c:
            rows=[dict(r) for r in c.execute('SELECT e.*,c.name AS owner FROM equipment e JOIN clients c ON c.id=e.owner_id WHERE e.archived=? ORDER BY e.updated_at DESC',(int(archived),))]
            if active:
                ids={r[0] for r in c.execute("SELECT equipment_id FROM repair_orders WHERE status NOT IN('issued','closed','cancelled')")};rows=[r for r in rows if r['id'] in ids]
        q=query.casefold();return [r for r in rows if not q or q in ' '.join(str(v) for v in r.values()).casefold()]
    def create_repair(self,equipment_id,number='',complaint='',request_id=None,client_id=None):
        key=request_id or uuid4().hex
        number=text(number,'Номер ремонта',limit=100);complaint=text(complaint)
        with self.lock,self.db.connection(True) as c:
            existing=c.execute('SELECT * FROM repair_orders WHERE id=?',(key,)).fetchone()
            if existing:
                if (existing['equipment_id']!=equipment_id or (number and number!=existing['number'])
                    or complaint!=existing['complaint'] or (client_id and client_id!=existing['client_id'])):
                    raise ServiceError('Повторный идентификатор другой операции')
                return key
            eq=self.require(c,'equipment',equipment_id)
            if eq['archived']:raise ServiceError('Оборудование архивировано')
            from .profiles import next_number
            suggested,profile_id=next_number(c)
            if not number:
                number=suggested
            client_id=client_id or eq['owner_id']
            if self.require(c,'clients',client_id)['archived']:raise ServiceError('Клиент архивирован')
            if any(x[0].casefold()==number.casefold() for x in c.execute('SELECT number FROM repair_orders')):raise ServiceError('Номер ремонта уже существует')
            stamp=now()
            c.execute('INSERT INTO repair_orders(id,number,equipment_id,client_id,received_at,complaint,created_at,updated_at,profile_id) VALUES(?,?,?,?,?,?,?,?,?)',(key,number,equipment_id,client_id,stamp[:10],complaint,stamp,stamp,profile_id))
            c.execute('INSERT INTO repair_status_history(repair_id,old_status,new_status,changed_at,source) VALUES(?,?,?,?,?)',(key,'','accepted',stamp,'create'))
            self.audit(c,'repair',key,'create')
        return key
    def save_repair(self,key,data,expected_revision=None):
        fields=('complaint','accessories','condition','defects','plan','approval_note','issued_accessories','handover','notes')
        values={f:text(data[f],f) for f in fields if f in data}
        for f in ('received_at','started_at','completed_at','issued_at'):
            if f in data:
                values[f]=day(data[f])
                if f=='received_at' and not values[f]:raise ServiceError('Дата приёмки обязательна')
        if 'status' in data:
            if data['status'] not in STATUSES:raise ServiceError('Неизвестный статус')
            values['status']=data['status']
        if 'approval' in data:
            if data['approval'] not in APPROVALS:raise ServiceError('Неизвестное согласование')
            values['approval']=data['approval']
        if 'discount' in data:values['discount_cents']=money(data['discount'])
        with self.lock,self.db.connection(True) as c:
            old=self.require(c,'repair_orders',key)
            if expected_revision is not None and old['revision']!=expected_revision:raise ServiceError('Запись уже изменена. Откройте свежую версию, чтобы не потерять изменения')
            if not values:return old['revision']
            gross=c.execute('SELECT COALESCE(SUM(total_cents),0) FROM repair_items WHERE repair_id=?',(key,)).fetchone()[0]
            if values.get('discount_cents',old['discount_cents'])>gross:raise ServiceError('Скидка не может превышать стоимость позиций')
            if values.get('discount_cents',old['discount_cents'])!=old['discount_cents']:
                from .estimates import require_change_reason
                reason=require_change_reason(c,key,data.get('change_reason',''))
                self.audit(c,'repair',key,'discount_change',json.dumps({'before':old['discount_cents'],'after':values['discount_cents'],'reason':reason},ensure_ascii=False))
            c.execute('UPDATE repair_orders SET '+','.join(f+'=?' for f in values)+',revision=revision+1,updated_at=? WHERE id=?',(*values.values(),now(),key))
            if values.get('status',old['status'])!=old['status']:
                c.execute('INSERT INTO repair_status_history(repair_id,old_status,new_status,changed_at,note,source) VALUES(?,?,?,?,?,?)',(key,old['status'],values['status'],now(),text(data.get('status_note')),'manual'))
            self.audit(c,'repair',key,'save')
            return old['revision']+1
    def repairs(self,query='',status='',equipment_id=None,active=False,date_from='',date_to='',ascending=False):
        lower=day(date_from);upper=day(date_to)
        if lower and upper and lower>upper:raise ServiceError('Начало диапазона позже окончания')
        order='ASC' if ascending else 'DESC'
        with self.db.connection() as c:
            sql='''SELECT r.*,e.number AS equipment_number,e.model,e.serial,e.manufacturer,c.name AS client,
                COALESCE(i.work_cents,0) AS work_cents,COALESCE(i.parts_cents,0) AS parts_cents,
                COALESCE(i.delivery_cents,0) AS delivery_cents,COALESCE(i.other_cents,0) AS other_cents,
                COALESCE(i.item_text,'') AS item_text,COALESCE(p.paid_cents,0) AS paid_cents
                FROM repair_orders r JOIN equipment e ON r.equipment_id=e.id JOIN clients c ON c.id=r.client_id
                LEFT JOIN (SELECT repair_id,
                    SUM(CASE kind WHEN 'work' THEN total_cents ELSE 0 END) AS work_cents,
                    SUM(CASE kind WHEN 'part' THEN total_cents ELSE 0 END) AS parts_cents,
                    SUM(CASE kind WHEN 'delivery' THEN total_cents ELSE 0 END) AS delivery_cents,
                    SUM(CASE kind WHEN 'other' THEN total_cents ELSE 0 END) AS other_cents,
                    GROUP_CONCAT(name||' '||description,' ') AS item_text FROM repair_items GROUP BY repair_id) i ON i.repair_id=r.id
                LEFT JOIN (SELECT repair_id,SUM(CASE kind WHEN 'payment' THEN amount_cents ELSE -amount_cents END) AS paid_cents
                    FROM payments WHERE voided=0 GROUP BY repair_id) p ON p.repair_id=r.id WHERE 1=1'''
            params=[]
            for clause,value in (('r.equipment_id=?',equipment_id),('r.status=?',status),('r.received_at>=?',lower),('r.received_at<=?',upper)):
                if value:sql+=' AND '+clause;params.append(value)
            if active:sql+=" AND r.status NOT IN ('issued','closed','cancelled')"
            sql+=f' ORDER BY r.received_at {order},r.created_at {order},r.rowid {order}'
            rows=[dict(r) for r in c.execute(sql,params)]
            labels={r['id']:json.loads(r['data_json']).get('status_labels',{}) for r in c.execute('SELECT id,data_json FROM organization_profiles')}
            for r in rows:
                r.update(calculate([{'kind':kind,'total_cents':r[column]} for kind,column in (('work','work_cents'),('part','parts_cents'),('delivery','delivery_cents'),('other','other_cents'))],r['discount_cents'],r['paid_cents']))
                r['status_display']=labels.get(r['profile_id'],{}).get(r['status'],STATUSES[r['status']][0])
        q=query.casefold()
        return [r for r in rows if not q or q in ' '.join(str(v) for v in r.values()).casefold()]
    def snapshot(self,key):
        with self.db.connection() as c:
            r=self.require(c,'repair_orders',key)
            result={'repair':r,'equipment':self.require(c,'equipment',r['equipment_id']),'client':self.require(c,'clients',r['client_id']),'totals':totals(c,key)}
            for table in ('repair_items','payments','attachments','generated_documents','repair_status_history'):
                result[table]=[dict(x) for x in c.execute(f'SELECT * FROM {table} WHERE repair_id=? ORDER BY '+('position,rowid' if table=='repair_items' else 'rowid'),(key,))]
            from .estimates import draft,list_estimates,comparison
            from .profiles import profile
            result.update(preliminary_draft=draft(c,key),estimates=list_estimates(c,key),estimate_comparison=comparison(c,key),profile=profile(c,r['profile_id']))
            return result
    def save_item(self,repair_id,data,key=None):
        kind=data.get('kind')
        if kind not in ITEM_KINDS:raise ServiceError('Выберите работу, запчасть, доставку или другой расход')
        q=quantity(data.get('quantity','1'));price=money(data.get('price','0'))
        values={'kind':kind,'name':text(data.get('name'),'Название',True,500),'description':text(data.get('description')),'quantity':q,'unit':text(data.get('unit','шт.'),'Единица',True,30),'price_cents':price,'total_cents':line_total(q,price),'position':int(data.get('position',0)),'notes':text(data.get('notes'))}
        with self.lock,self.db.connection(True) as c:
            self.require(c,'repair_orders',repair_id)
            from .estimates import require_change_reason
            reason=require_change_reason(c,repair_id,data.get('change_reason',''))
            if key:
                old=self.require(c,'repair_items',key)
                if old['repair_id']!=repair_id:raise ServiceError('Позиция другого ремонта')
                c.execute('UPDATE repair_items SET '+','.join(f+'=?' for f in values)+' WHERE id=?',(*values.values(),key))
            else:
                key=uuid4().hex
                c.execute('INSERT INTO repair_items(id,repair_id,'+','.join(values)+') VALUES('+','.join('?' for _ in range(len(values)+2))+')',(key,repair_id,*values.values()))
            self._check_items(c,repair_id);self._touch(c,repair_id);self.audit(c,'item',key,'save',json.dumps({'values':values,'reason':reason},ensure_ascii=False))
        return key
    def remove_item(self,key,reason=''):
        with self.lock,self.db.connection(True) as c:
            r=self.require(c,'repair_items',key)
            from .estimates import require_change_reason
            reason=require_change_reason(c,r['repair_id'],reason)
            c.execute('DELETE FROM repair_items WHERE id=?',(key,))
            self._check_items(c,r['repair_id']);self._touch(c,r['repair_id']);self.audit(c,'item',key,'remove',json.dumps({'values':r,'reason':reason},ensure_ascii=False))
    @staticmethod
    def _check_items(c,key):
        rows=c.execute('SELECT total_cents FROM repair_items WHERE repair_id=?',(key,)).fetchall()
        if len(rows)>2000 or sum(r[0] for r in rows)>9000000000000000:raise ServiceError('Превышен лимит позиций или суммы ремонта')
        if c.execute('SELECT discount_cents FROM repair_orders WHERE id=?',(key,)).fetchone()[0]>sum(r[0] for r in rows):raise ServiceError('Сначала уменьшите скидку; позиция не изменена')
    def documents(self):
        with self.db.connection() as c:return [dict(x) for x in c.execute('SELECT d.*,r.number FROM generated_documents d JOIN repair_orders r ON d.repair_id=r.id ORDER BY d.created_at DESC,d.version DESC')]
    def compare_repairs(self,keys):
        if not 2<=len(set(keys))<=6:raise ServiceError('Выберите от двух до шести разных ремонтов')
        rows=[self.snapshot(key) for key in keys]
        if len({r['repair']['equipment_id'] for r in rows})!=1:raise ServiceError('Сравниваются ремонты одного оборудования')
        return sorted(rows,key=lambda s:(s['repair']['received_at'],s['repair']['created_at'],s['repair']['number']))
    @staticmethod
    def _touch(c,key):c.execute('UPDATE repair_orders SET revision=revision+1,updated_at=? WHERE id=?',(now(),key))
    def add_payment(self,repair_id,amount,kind='payment',method='Перевод (внутренняя запись)',occurred_at='',comment='',request_id=None):
        cents=money(amount)
        if cents<=0 or kind not in {'payment','refund'}:raise ServiceError('Введите положительную сумму и вид операции')
        key=request_id or uuid4().hex
        with self.lock,self.db.connection(True) as c:
            self.require(c,'repair_orders',repair_id)
            existing=c.execute('SELECT * FROM payments WHERE id=?',(key,)).fetchone()
            if existing:
                if existing['repair_id']!=repair_id or existing['amount_cents']!=cents or existing['kind']!=kind:raise ServiceError('Идентификатор платежа относится к другой записи')
                return key
            if kind=='payment' and totals(c,repair_id)['paid']+cents>9000000000000000:raise ServiceError('Превышен лимит учтённых оплат')
            if kind=='refund' and cents>totals(c,repair_id)['paid']:raise ServiceError('Возврат превышает учтённую оплату')
            c.execute('INSERT INTO payments(id,repair_id,amount_cents,occurred_at,method,kind,comment,created_at) VALUES(?,?,?,?,?,?,?,?)',(key,repair_id,cents,day(occurred_at) or now()[:10],text(method,'Способ',True,100),kind,text(comment),now()))
            self._touch(c,repair_id);self.audit(c,'payment',key,'record',kind)
        return key
    def void_payment(self,key,reason):
        reason=text(reason,'Причина исправления',True)
        with self.lock,self.db.connection(True) as c:
            r=self.require(c,'payments',key)
            if r['voided']:return
            c.execute('UPDATE payments SET voided=1,void_reason=? WHERE id=?',(reason,key))
            if totals(c,r['repair_id'])['paid']<0:raise ServiceError('Сначала исправьте связанный возврат')
            self._touch(c,r['repair_id']);self.audit(c,'payment',key,'void',reason)
    def dashboard(self):
        rows=self.repairs()
        with self.db.connection() as c:
            eq=c.execute('SELECT COUNT(*) FROM equipment WHERE archived=0').fetchone()[0]
            recent=[dict(r) for r in c.execute('SELECT * FROM operations ORDER BY id DESC LIMIT 20')]
        return {'equipment':eq,'active':sum(r['status'] not in TERMINAL for r in rows),'approval':sum(r['status']=='approval' for r in rows),'parts':sum(r['status']=='parts' for r in rows),'ready':sum(r['status']=='ready' for r in rows),'debt':sum(max(0,r['balance']) for r in rows),'recent':recent}
