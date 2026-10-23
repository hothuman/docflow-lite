"""Literal Service row expansion. Core syntax/engine stay unchanged; no expressions."""
import bisect,copy,io,re,zipfile
from pathlib import Path
from uuid import uuid4
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from ..templates import Template,TOKEN,paragraph_nodes,W,parse,STORY
from ..safety import check_archive
from .attachments import safe_path,attachment_path,digest
from .validation import ServiceError,rub,now
from .statuses import STATUSES

KINDS={'intake':'Акт приёмки оборудования','completion':'Акт выполненных работ','combined':'Карточка ремонта и выполненные работы','defects':'Приложение с дефектовкой','handover':'Передача оборудования'}
MARKER=re.compile(r'\[\[items:(work|part)\]\]')
ITEM_FIELDS={'item_no','item_name','item_description','item_quantity','item_unit','item_price','item_total'}
ALIASES={'n':'item_no','name':'item_name','qty':'item_quantity','unit':'item_unit','price':'item_price','sum':'item_total'}
ITEM_FIELDS.update(ALIASES)
MAX_ROWS=1000

def create_templates(folder):
    """Create editable neutral forms; no original customer's conditions or signatures."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    for kind,title in KINDS.items():
        path=folder/(kind+'.docx')
        if path.exists():continue
        d=Document();s=d.sections[0];s.page_width=Inches(8.27);s.page_height=Inches(11.69)
        s.top_margin=s.bottom_margin=Inches(.65);s.left_margin=s.right_margin=Inches(.65)
        for style in ('Normal','Title','Heading 1','Heading 2'):
            d.styles[style].font.name='Arial';d.styles[style].font.color.rgb=RGBColor(0,0,0)
        d.styles['Normal'].font.size=Pt(10);d.styles['Normal'].paragraph_format.space_after=Pt(5)
        d.styles['Title'].font.size=Pt(20)
        for style in ('Title','Heading 1','Heading 2'):
            pp=d.styles[style].element.find(qn('w:pPr'))
            if pp is not None:
                for border in list(pp.findall(qn('w:pBdr'))):pp.remove(border)
        d.add_paragraph(title,'Title')
        d.add_paragraph('Ремонт {{repair_number}} · {{received_at}}')
        d.add_paragraph('Заказчик: {{client_name}}')
        d.add_paragraph('Оборудование: {{equipment_model}} · № {{equipment_number}} · серийный № {{equipment_serial}}')
        if kind in ('intake','combined'):
            d.add_paragraph('Жалоба: {{complaint}}');d.add_paragraph('Комплектация: {{accessories}}');d.add_paragraph('Внешнее состояние: {{condition}}')
        if kind in ('defects','completion','combined'):
            d.add_paragraph('Дефектовка','Heading 1');d.add_paragraph('{{defects}}');d.add_paragraph('План: {{plan}}');d.add_paragraph('Согласование: {{approval}}. {{approval_note}}')
        if kind in ('completion','combined'):
            for group,title2 in (('work','Работы'),('part','Запчасти')):
                d.add_paragraph(title2,'Heading 1')
                t=d.add_table(rows=2,cols=6);t.style='Table Grid';t.autofit=False
                labels=['№','Наименование','Кол-во','Ед.','Цена','Сумма']
                for c,label in zip(t.rows[0].cells,labels):c.text=label
                repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
                values=['{{n}}','[[items:'+group+']]{{name}}','{{qty}}','{{unit}}','{{price}}','{{sum}}']
                for c,value in zip(t.rows[1].cells,values):c.text=value
                t.rows[1].cells[1].add_paragraph('{{item_description}}')
                no_split=OxmlElement('w:cantSplit');t.rows[1]._tr.get_or_add_trPr().append(no_split)
                widths=[.55,2.35,.75,.65,.95,1.15]
                for col,width in zip(t.columns,widths):col.width=Inches(width)
                for row in t.rows:
                    for cell,width in zip(row.cells,widths):cell.width=Inches(width)
            d.add_paragraph('Работы: {{work_total}} · Запчасти: {{parts_total}}')
            d.add_paragraph('Скидка: {{discount}} · Всего: {{total}}')
            d.add_paragraph('Внутренний учёт: оплачено {{paid}}, остаток {{balance}}. Не банковский документ и не чек.')
        if kind=='handover':
            d.add_paragraph('Дата выдачи: {{issued_at}}');d.add_paragraph('Комплектация при выдаче: {{issued_accessories}}');d.add_paragraph('Зафиксированные сведения о передаче: {{handover}}')
        d.add_paragraph('Статус: {{status}} · Примечания: {{notes}}')
        d.add_paragraph('Проект формы. Юридические условия и сведения сторон согласуются отдельно. Подписи не проставлены.')
        d.add_paragraph('Передал ____________________     Принял ____________________')
        d.core_properties.author='';d.core_properties.last_modified_by='';d.core_properties.comments=''
        d.save(path)
    return {k:folder/(k+'.docx') for k in KINDS}

def replace_spans(p,pattern,callback):
    nodes=paragraph_nodes(p);text=''.join(t.text for t in nodes);offsets=[];n=0
    for node in nodes:offsets.append(n);n+=len(node.text)
    for m in reversed(list(pattern.finditer(text))):
        first=bisect.bisect_right(offsets,m.start())-1;last=bisect.bisect_right(offsets,m.end()-1)-1
        left=nodes[first].text[:m.start()-offsets[first]];right=nodes[last].text[m.end()-offsets[last]:]
        if first==last:nodes[first].text=left+callback(m)+right
        else:
            nodes[first].text=left+callback(m)
            for x in nodes[first+1:last]:x.text=''
            nodes[last].text=right

def render_service(template_path,values,items,images=()):
    template=Template.load(template_path)  # Existing archive/XML/active-content checks.
    d=Document(io.BytesIO(template.raw));extra={};count=0
    markers=0
    for table in d.tables:
        for row in list(table.rows):
            content=''.join(t.text or '' for t in row._tr.iter(W+'t'))
            matches=list(MARKER.finditer(content))
            if not matches:continue
            markers+=len(matches)
            if len(matches)!=1 or row._tr.find('.//'+W+'vMerge') is not None or row._tr.find('.//'+W+'tbl') is not None:raise ServiceError('Маркер должен находиться в простой строке таблицы без вложенных таблиц/вертикального объединения')
            group=matches[0].group(1);subset=[x for x in items if x['kind']==group]
            if len(subset)>MAX_ROWS:raise ServiceError('Не более 1000 строк каждого типа в одном DOCX')
            for index,item in enumerate(subset,1):
                count+=1;clone=copy.deepcopy(row._tr)
                local={'item_no':str(index),'item_name':item['name'],'item_description':item['description'],'item_quantity':item['quantity'],'item_unit':item['unit'],'item_price':rub(item['price_cents']),'item_total':rub(item['total_cents'])}
                for p in clone.iter(W+'p'):
                    replace_spans(p,MARKER,lambda m:'')
                    def rename(m):
                        field=m.group(1)
                        if field not in ITEM_FIELDS:return m.group(0)
                        new=f'_s{count}_{field}';extra[new]=local[ALIASES.get(field,field)];return '{{'+new+'}}'
                    replace_spans(p,TOKEN,rename)
                row._tr.addprevious(clone)
            table._tbl.remove(row._tr)
    for p in d.element.iter(W+'p'):
        if '[[items:' in ''.join(t.text or '' for t in p.iter(W+'t')):raise ServiceError('Неподдерживаемый или неправильно размещённый маркер строк')
    if len(images)>10:raise ServiceError('В приложение допускается не более десяти изображений')
    if images:
        d.add_page_break();d.add_paragraph('Приложение с изображениями','Heading 1')
        for image_index,(path,caption) in enumerate(images):
            if Path(path).stat().st_size>10*1024*1024:raise ServiceError('Изображение для DOCX превышает 10 MiB')
            extra[f'_image_caption_{image_index}']=caption
            d.add_paragraph('{{'+f'_image_caption_{image_index}'+'}}');d.add_picture(str(path),width=Inches(6))
    raw=io.BytesIO();d.save(raw);raw=raw.getvalue();check_archive(raw)
    fields=set()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for n in z.namelist():
            if STORY.fullmatch(n):
                root=parse(z.read(n))
                for p in root.iter(W+'p'):fields.update(m.group(1) for m in TOKEN.finditer(''.join(t.text for t in paragraph_nodes(p))))
    available={**values,**extra}
    if fields-available.keys():raise ServiceError('Неизвестные поля шаблона: '+', '.join(sorted(fields-available.keys())))
    return Template(Path(template_path),raw,frozenset(fields)).render(available)

def generate_document(store,repair_id,kind,template=None,image_ids=()):
    if kind not in KINDS:raise ServiceError('Неизвестный документ')
    with store.lock:
        s=store.snapshot(repair_id);r=s['repair'];eq=s['equipment'];c=s['client'];t=s['totals']
        values={k:str(v or '') for k,v in r.items()}
        values.update({'repair_number':r['number'],'equipment_number':eq['number'],'equipment_model':eq['model'],'equipment_serial':eq['serial'],'client_name':c['name'],'status':STATUSES[r['status']][0],**{k:rub(t[k]) for k in ('discount','total','paid','balance')},'work_total':rub(t['work']),'parts_total':rub(t['parts'])})
        images=[]
        for key in image_ids:
            item=store.get('attachments',key)
            if item['repair_id']!=repair_id or item['kind']!='image':raise ServiceError('Изображение должно относиться к этому ремонту')
            images.append((attachment_path(store,key),item['comment'] or item['name']))
        path=Path(template) if template else create_templates(safe_path(store.root,'templates'))[kind]
        rendered=render_service(path,values,s['repair_items'],images)
        with store.db.connection(True) as db:
            version=db.execute('SELECT COALESCE(MAX(version),0)+1 FROM generated_documents WHERE repair_id=? AND kind=?',(repair_id,kind)).fetchone()[0]
            relative=f'generated/{repair_id}/{kind}-v{version:03d}-{uuid4().hex[:8]}.docx'
            target=safe_path(store.root,relative);target.parent.mkdir(parents=True,exist_ok=True)
            created=False
            try:
                with target.open('xb') as f:
                    created=True;f.write(rendered)
                db.execute('INSERT INTO generated_documents(id,repair_id,kind,version,created_at,path,sha256,template) VALUES(?,?,?,?,?,?,?,?)',(uuid4().hex,repair_id,kind,version,now(),relative,digest(target),path.name))
                store.audit(db,'document',repair_id,'generate',kind+':'+str(version))
            except Exception:
                if created:target.unlink(missing_ok=True)
                raise
        return target
