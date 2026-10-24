"""Repair editor with explicit saves, immutable payment corrections and versioned documents."""
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import QUrl,Qt
from PySide6.QtGui import QImageReader,QPixmap,QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QTabWidget,QLineEdit,QPlainTextEdit,QComboBox,QScrollArea,QWidget,QFileDialog,QInputDialog,QMessageBox,QCheckBox)
from ...service.validation import rub
from ...service.statuses import STATUSES,APPROVALS
from ...service.documents import KINDS,generate_document
from ...service.attachments import add_attachment,attachment_path,remove_attachment,export_file
from .forms import FieldsDialog
from .widgets import Grid,button,confirm

def amount(c):return f'{c//100}.{c%100:02d}'

class RepairDialog(QDialog):
    def __init__(self,workspace,snapshot):
        super().__init__(workspace);self.workspace=workspace;self.store=workspace.store;self.snapshot=snapshot;self.key=snapshot['repair']['id'];self.dirty=False;self.fields={};self.grids={}
        self.setWindowTitle('Ремонт '+snapshot['repair']['number']);self.resize(960,740);self.setMinimumSize(420,360)
        outer=QVBoxLayout(self);self.identity=QLabel();self.identity.setWordWrap(True);outer.addWidget(self.identity)
        self.summary=QLabel();self.summary.setWordWrap(True);outer.addWidget(self.summary)
        self.tabs=QTabWidget();self.tabs.setUsesScrollButtons(True);outer.addWidget(self.tabs,1)
        sections=[('Приёмка',[('received_at','Дата ГГГГ-ММ-ДД','text'),('complaint','Жалоба','long'),('accessories','Комплектация','long'),('condition','Внешнее состояние','long'),('notes','Примечания','long')]),('Дефектовка',[('defects','Неисправности','long'),('plan','План работ','long'),('approval','Согласование',[(v,v) for v in APPROVALS]),('approval_note','Комментарий к согласованию','long')])]
        for title,fields in sections:
            scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();form=QFormLayout(body);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);scroll.setWidget(body);self.tabs.addTab(scroll,title)
            for key,label,kind in fields:self.add_field(form,key,label,kind)
        for group,title in [('work','Работы'),('part','Запчасти'),('delivery','Доставка'),('other','Прочие расходы')]:
            p=QWidget();layout=QVBoxLayout(p);bar=QHBoxLayout();layout.addLayout(bar)
            grid=Grid([('name','Наименование'),('description','Описание'),('quantity','Количество'),('unit','Ед.'),('price','Цена'),('total','Сумма')]);self.grids[group]=grid;layout.addWidget(grid);self.tabs.addTab(p,title)
            button(bar,'Добавить',lambda _,g=group:self.with_saved(lambda:self.item(g)));button(bar,'Изменить',lambda _,g=group:self.with_saved(lambda:self.item(g,True)));button(bar,'Удалить',lambda _,g=group:self.with_saved(lambda:self.delete_item(g)))
        p=QWidget();layout=QVBoxLayout(p);form=QFormLayout();layout.addLayout(form);self.add_field(form,'discount','Скидка, ₽','text')
        label=QLabel('Только внутренние записи. Программа не проводит платежи и не выдаёт чеки. Ошибочная запись исправляется аннулированием с причиной и новой корректной записью.');label.setWordWrap(True);layout.addWidget(label)
        bar=QHBoxLayout();layout.addLayout(bar);button(bar,'Учесть оплату / возврат',lambda:self.with_saved(self.payment));button(bar,'Исправить ошибочную запись',lambda:self.with_saved(self.void_payment))
        self.grids['payments']=Grid([('occurred_at','Дата'),('kind','Вид'),('amount','Сумма'),('method','Способ'),('voided','Состояние'),('void_reason','Причина'),('comment','Комментарий')]);layout.addWidget(self.grids['payments']);self.tabs.addTab(p,'Финансы')
        from .estimates import EstimatesPanel
        self.estimates=EstimatesPanel(self);self.tabs.addTab(self.estimates,'Сметы')
        p=QWidget();layout=QVBoxLayout(p);bar=QHBoxLayout();layout.addLayout(bar)
        button(bar,'Прикрепить',lambda:self.with_saved(self.add_file));button(bar,'Открыть',self.open_attachment);button(bar,'Просмотр фото',self.preview_image);button(bar,'Удалить',self.delete_attachment)
        self.grids['attachments']=Grid([('name','Имя'),('kind','Тип'),('size','Байт'),('comment','Подпись')]);layout.addWidget(self.grids['attachments']);self.image=QLabel('PNG / JPEG · MP4 · безопасный DOCX');self.image.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.image);self.tabs.addTab(p,'Вложения')
        p=QWidget();layout=QVBoxLayout(p);bar=QHBoxLayout();layout.addLayout(bar);self.doc_kind=QComboBox()
        for k,title in KINDS.items():self.doc_kind.addItem(title,k)
        bar.addWidget(self.doc_kind);button(bar,'Создать DOCX',lambda:self.with_saved(self.generate));self.images=QCheckBox('Выбрать изображения, порядок и подписи (до 10)');self.image_choices=[];layout.addWidget(self.images)
        custom=QHBoxLayout();layout.addLayout(custom);self.template_path=QLineEdit();self.template_path.setPlaceholderText('Встроенная нейтральная форма');self.template_path.setReadOnly(True);custom.addWidget(self.template_path);button(custom,'Свой DOCX',self.pick_template);button(custom,'Сбросить',self.template_path.clear)
        self.grids['documents']=Grid([('kind','Тип'),('version','Версия'),('created_at','Создано'),('path','Путь')]);layout.addWidget(self.grids['documents']);bar2=QHBoxLayout();layout.addLayout(bar2);button(bar2,'Открыть версию',self.open_document);button(bar2,'Сохранить копию',self.export_document);self.tabs.addTab(p,'Документы')
        scroll=QScrollArea();scroll.setWidgetResizable(True);p=QWidget();form=QFormLayout(p);scroll.setWidget(p)
        for key,label,kind in [('status','Производство',[(k,v[0]) for k,v in STATUSES.items()]),('started_at','Начало ГГГГ-ММ-ДД','text'),('completed_at','Завершение ГГГГ-ММ-ДД','text'),('issued_at','Выдача ГГГГ-ММ-ДД','text'),('issued_accessories','Комплектация при выдаче','long'),('handover','Сведения о передаче (только факты)','long'),('status_note','Причина изменения статуса','text')]:self.add_field(form,key,label,kind)
        self.grids['history']=Grid([('changed_at','Когда'),('old_status','Было'),('new_status','Стало'),('note','Примечание'),('source','Источник')]);form.addRow(self.grids['history']);self.tabs.addTab(scroll,'Статус и история')
        bar=QHBoxLayout();outer.addLayout(bar);self.dirty_label=QLabel();bar.addWidget(self.dirty_label,1);self.save_button=button(bar,'Сохранить черновик',self.save);button(bar,'Закрыть',self.close)
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
        self.install(snapshot)
    def add_field(self,form,key,label,kind):
        if isinstance(kind,list):
            w=QComboBox()
            for value,name in kind:w.addItem(name,value)
            w.currentIndexChanged.connect(self.changed)
        elif kind=='long':w=QPlainTextEdit();w.setMinimumHeight(85);w.textChanged.connect(self.changed)
        else:w=QLineEdit();w.textChanged.connect(self.changed)
        w.setAccessibleName(label);w.setMinimumWidth(0);form.addRow(label,w);self.fields[key]=w
    def changed(self,*args):
        self.dirty=True
        if hasattr(self,'dirty_label'):self.dirty_label.setText('Есть несохранённые изменения')
    def install(self,s):
        self.snapshot=s;r=s['repair'];self.revision=r['revision']
        for k,w in self.fields.items():
            value=amount(r['discount_cents']) if k=='discount' else r.get(k,'')
            w.blockSignals(True)
            if isinstance(w,QComboBox):w.setCurrentIndex(max(0,w.findData(value)))
            elif isinstance(w,QPlainTextEdit):w.setPlainText(str(value))
            else:w.setText(str(value))
            w.blockSignals(False)
        self.identity.setText(f"{s['equipment']['number']} · {s['equipment']['model']} · Клиент: {s['client']['name']}")
        t=s['totals'];self.summary.setText(f"Производство: {s['profile']['status_labels'].get(r['status'],STATUSES[r['status']][0])}   |   Фактически {rub(t['total'])} · Учтено {rub(t['paid'])} · Остаток {rub(t['balance'])} · {t['financial_status']}")
        self.estimates.install(s)
        for group in ('work','part','delivery','other'):
            rows=[{**x,'price':rub(x['price_cents']),'total':x['total_cents']} for x in s['repair_items'] if x['kind']==group];self.grids[group].install(rows)
        self.grids['payments'].install([{**x,'amount':rub(x['amount_cents'])} for x in s['payments']]);self.grids['attachments'].install(s['attachments']);self.grids['documents'].install(s['generated_documents']);self.grids['history'].install(s['repair_status_history']);self.dirty=False;self.dirty_label.setText('Черновик сохранён')
    def values(self):return {k:(w.currentData() if isinstance(w,QComboBox) else w.toPlainText() if isinstance(w,QPlainTextEdit) else w.text()) for k,w in self.fields.items()}
    def save(self,after=None):
        # clicked(bool) is not a callback.
        if not callable(after):after=None
        v=self.values();revision=self.revision;s=self.store;key=self.key
        if v['discount']!=amount(self.snapshot['repair']['discount_cents']) and self.snapshot['estimate_comparison']['approved_estimate_id']:
            reason,ok=QInputDialog.getText(self,'Изменение согласованной стоимости','Причина изменения скидки *')
            if not ok:return
            v['change_reason']=reason
        def work():s.save_repair(key,v,revision);return s.snapshot(key)
        def done(snapshot):
            self.install(snapshot)
            if after:after()
        self.workspace.run(work,done,'Сохраняю ремонт…')
    def with_saved(self,fn):
        if self.dirty:self.save(fn)
        else:fn()
    def mutate(self,fn):
        s=self.store;key=self.key
        self.workspace.run(lambda:(fn(),s.snapshot(key))[1],self.install)
    def selected(self,key):
        r=self.grids[key].selected()
        if not r:QMessageBox.information(self,'Service','Выберите строку')
        return r
    def item(self,kind,edit=False):
        row=self.selected(kind) if edit else None
        if edit and not row:return
        fields=[('name','Наименование *','text'),('description','Описание','long'),('quantity','Количество (до 4 знаков)','text'),('unit','Единица','text'),('price','Цена за единицу, ₽','text'),('notes','Примечание','long')]
        if self.snapshot['estimate_comparison']['approved_estimate_id']:fields.append(('change_reason','Причина изменения согласованного объёма *','long'))
        values={**row,'price':amount(row['price_cents'])} if row else {'quantity':'1','unit':'шт.','price':'0'}
        from ...service.finance import ITEM_KINDS
        d=FieldsDialog(ITEM_KINDS[kind],fields,values,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v={**d.values(),'kind':kind};key=row['id'] if row else None;s=self.store;r=self.key;self.mutate(lambda:s.save_item(r,v,key))
    def delete_item(self,kind):
        row=self.selected(kind)
        if row and confirm(self,'Удалить позицию?'):
            reason=''
            if self.snapshot['estimate_comparison']['approved_estimate_id']:
                reason,ok=QInputDialog.getText(self,'Изменение согласованного объёма','Причина удаления *')
                if not ok:return
            s=self.store;self.mutate(lambda:s.remove_item(row['id'],reason))
    def payment(self):
        fields=[('kind','Операция',[('payment','Оплата'),('refund','Возврат')]),('amount','Сумма, ₽','text'),('occurred_at','Дата ГГГГ-ММ-ДД (пусто — сегодня)','text'),('method','Способ (внутренняя запись)','text'),('comment','Примечание','long')]
        d=FieldsDialog('Учёт расчётов — не проведение платежа',fields,{'method':'Перевод — запись вручную'},self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();s=self.store;r=self.key;request=uuid4().hex
            self.mutate(lambda:s.add_payment(r,v['amount'],v['kind'],v['method'],v['occurred_at'],v['comment'],request))
    def void_payment(self):
        row=self.selected('payments')
        if not row or row['voided']:return
        reason,ok=QInputDialog.getText(self,'Исправление','Причина аннулирования (реальная банковская операция не отменяется):')
        if ok and confirm(self,'Исключить эту запись из внутреннего расчёта? История сохранится.'):
            s=self.store;self.mutate(lambda:s.void_payment(row['id'],reason))
    def add_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Локальное вложение','','Вложения (*.png *.jpg *.jpeg *.mp4 *.docx)')
        if not path:return
        caption,ok=QInputDialog.getText(self,'Подпись','Подпись / примечание (необязательно):')
        if ok:
            s=self.store;r=self.key;self.mutate(lambda:add_attachment(s,r,path,caption))
    def delete_attachment(self):
        row=self.selected('attachments')
        if row and confirm(self,'Удалить вложение этого ремонта? Ранее созданные DOCX и резервные копии не меняются.'):
            s=self.store;self.mutate(lambda:remove_attachment(s,row['id']))
    def open_attachment(self):
        row=self.selected('attachments')
        if row:
            s=self.store;self.workspace.run(lambda:attachment_path(s,row['id']),lambda p:QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
    def preview_image(self):
        row=self.selected('attachments')
        if not row or row['kind']!='image':return
        s=self.store
        def read():
            path=attachment_path(s,row['id']);reader=QImageReader(str(path));reader.setAllocationLimit(128);return reader.read()
        self.workspace.run(read,lambda img:self.image.setPixmap(QPixmap.fromImage(img).scaled(540,220,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)),'Загружаю изображение…')
    def pick_template(self):
        p,_=QFileDialog.getOpenFileName(self,'Свой шаблон Service','','Word (*.docx)')
        if p:self.template_path.setText(p)
    def generate(self):
        s=self.store;key=self.key;kind=self.doc_kind.currentData();path=self.template_path.text() or None
        choices=[]
        if self.images.isChecked():
            from .images import ImagesDialog
            dialog=ImagesDialog(self.snapshot['attachments'],self,self.image_choices)
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            choices=dialog.values();self.image_choices=choices
        self.mutate(lambda:generate_document(s,key,kind,path,image_choices=choices))
    def open_document(self):
        row=self.selected('documents')
        if row:
            s=self.store;self.workspace.run(lambda:attachment_path(s,row['id'],True),lambda p:QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
    def export_document(self):
        row=self.selected('documents')
        if not row:return
        path,_=QFileDialog.getSaveFileName(self,'Копия документа',Path(row['path']).name,'Word (*.docx)')
        if not path:return
        s=self.store
        self.workspace.run(lambda:export_file(s,row['id'],path,True),lambda _:QMessageBox.information(self,'Документ','Копия сохранена'))
    def reject(self):self.close()
    def closeEvent(self,event):
        if self.workspace.worker:event.ignore();return
        if self.dirty:
            choice=QMessageBox.question(self,'Черновик','Сохранить изменения перед закрытием?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
            if choice==QMessageBox.StandardButton.Cancel:event.ignore();return
            if choice==QMessageBox.StandardButton.Save:event.ignore();self.save(self.accept);return
        event.accept()
