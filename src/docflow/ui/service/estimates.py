"""Explicit local quote editing and manual approval; no messages are sent."""
import json
from uuid import uuid4
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QWidget,QFileDialog,QMessageBox,QScrollArea
from ...service.estimates import save_draft,freeze_estimate,record_event,export_specification
from ...service.finance import ITEM_KINDS
from ...service.validation import rub
from .forms import FieldsDialog,fit_dialog
from ..flow import FlowLayout
from .presentation import STATES,KINDS_DISPLAY,date_text
from ...service.finance import calculate
from ...service.validation import money,ServiceError
from .widgets import Grid,button

def amount(c):return f'{c//100}.{c%100:02d}'

class DraftDialog(QDialog):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;self.workspace=editor.workspace;fit_dialog(self,960,640);self.dirty=False;self.setWindowTitle('Предварительный расчёт — отдельный черновик')
        source=editor.snapshot['preliminary_draft'];self.revision=source['revision'];self.lines=[dict(x) for x in source['lines']]
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);scroll.setWidget(body);outer.addWidget(scroll,1);note=QLabel('Черновик не меняет фактические работы и задолженность. После сохранения создайте неизменяемую версию сметы.');note.setWordWrap(True);layout.addWidget(note)
        bar=FlowLayout();layout.addLayout(bar)
        for title,fn in [('Добавить',self.add),('Из каталога',self.from_catalog),('Изменить',self.edit),('Удалить',self.remove),('Выше',lambda:self.move(-1)),('Ниже',lambda:self.move(1))]:button(bar,title,fn)
        self.grid=Grid([('kind','Тип'),('name','Наименование'),('description','Описание'),('quantity','Количество'),('unit','Ед.'),('price','Цена'),('total','Сумма')]);layout.addWidget(self.grid,1)
        self.total_label=QLabel();self.total_label.setObjectName('section');self.total_label.setWordWrap(True);self.total_label.setAccessibleName('Итог предварительного черновика');layout.addWidget(self.total_label)
        self.discount=QLineEdit(amount(source['discount_cents']) if source['revision'] else editor.snapshot['profile']['default_discount']);self.discount.setAccessibleName('Скидка предварительной сметы');layout.addWidget(QLabel('Скидка, ₽'));layout.addWidget(self.discount)
        self.comment=QPlainTextEdit(source['comment']);self.comment.setAccessibleName('Комментарий предварительной сметы');self.comment.setMaximumHeight(100);layout.addWidget(self.comment)
        bottom=FlowLayout();outer.addLayout(bottom);self.dirty_label=QLabel('Черновик: можно редактировать');self.dirty_label.setWordWrap(True);outer.addWidget(self.dirty_label)
        self.save_button=button(bottom,'Сохранить расчёт',self.save,primary=True);button(bottom,'Отмена',self.reject)
        self.discount.textChanged.connect(self.changed);self.comment.textChanged.connect(self.changed);self.install()
    def install(self):
        self.grid.install([{**x,'id':str(i),'price':x['price_cents'],'total':x['total_cents']} for i,x in enumerate(self.lines)]);self.grid.sortByColumn(-1,Qt.SortOrder.AscendingOrder);self.update_total()
    def change(self,index=None):
        row=self.lines[index] if index is not None else {'kind':'work','quantity':'1','unit':'шт.','price_cents':0}
        d=FieldsDialog('Позиция предварительного расчёта',[('kind','Тип',list(ITEM_KINDS.items())),('name','Наименование *','text'),('description','Описание','long'),('quantity','Количество','text'),('unit','Ед.','text'),('price','Цена, ₽','text')],{**row,'price':amount(row['price_cents'])},self)
        if d.exec()==QDialog.DialogCode.Accepted:
            from ...service.estimates import normalize_lines
            try:value=normalize_lines([{**row,**d.values()}])[0]
            except Exception as exc:QMessageBox.warning(self,'Расчёт',str(exc));return
            if index is None:self.lines.append(value)
            else:self.lines[index]=value
            self.changed();self.install()
    def add(self):self.change()
    def from_catalog(self):
        from .catalog import CatalogPicker
        d=CatalogPicker(self.editor.store,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            if len(self.lines)>=2000:QMessageBox.warning(self,'Расчёт','Допускается до 2000 позиций');return
            self.lines.append(d.value);self.changed();self.install()
    def edit(self):
        row=self.grid.selected()
        if row:self.change(int(row['id']))
    def remove(self):
        row=self.grid.selected()
        if row:self.lines.pop(int(row['id']));self.changed();self.install()
    def move(self,direction):
        row=self.grid.selected()
        if row:
            i=int(row['id']);j=i+direction
            if 0<=j<len(self.lines):self.lines[i],self.lines[j]=self.lines[j],self.lines[i];self.changed();self.install();self.grid.selectRow(j)
    def changed(self,*args):
        self.dirty=True;self.dirty_label.setText('Есть несохранённые изменения черновика');self.update_total()
    def update_total(self):
        try:
            totals=calculate(self.lines,money(self.discount.text()));self.total_label.setText('Позиции: '+str(len(self.lines))+' · Скидка: '+rub(totals['discount'])+' · Итог: '+rub(totals['total']));self.save_button.setEnabled(True)
        except ServiceError as exc:self.total_label.setText(str(exc));self.save_button.setEnabled(False)
    def save(self):
        rows=[dict(x) for x in self.lines];discount=self.discount.text();comment=self.comment.toPlainText();editor=self.editor
        def work():save_draft(editor.store,editor.key,rows,discount,comment,self.revision);return editor.store.snapshot(editor.key)
        def saved(snapshot):self.dirty=False;editor.install(snapshot);self.accept()
        self.dirty_label.setText('Сохранение…');self.workspace.run(work,saved,'Сохраняю отдельный черновик сметы…',on_error=lambda _:self.dirty_label.setText('Не сохранено. Исправьте ошибку и повторите.'))
    def may_close(self):
        if self.workspace.worker:return False
        if not self.dirty:return True
        choice=QMessageBox.question(self,'Предварительный черновик','Сохранить изменения расчёта перед закрытием?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if choice==QMessageBox.StandardButton.Save:self.save();return False
        if choice==QMessageBox.StandardButton.Discard:self.dirty=False;return True
        return False
    def reject(self):
        if self.may_close():super().reject()
    def closeEvent(self,event):
        if self.may_close():event.accept()
        else:event.ignore()

class EstimatesPanel(QWidget):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;layout=QVBoxLayout(self)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.summary)
        bar=FlowLayout();layout.addLayout(bar)
        button(bar,'Редактировать предварительный расчёт',lambda:editor.with_saved(self.edit_draft))
        bar=FlowLayout();layout.addLayout(bar)
        button(bar,'Сохранить предварительную версию',lambda:editor.with_saved(lambda:self.freeze('preliminary')))
        button(bar,'Сохранить окончательную версию',lambda:editor.with_saved(lambda:self.freeze('final')))
        version_note=QLabel('Сохранённые версии — не изменяются. Для исправления создайте новую версию.');version_note.setWordWrap(True);layout.addWidget(version_note)
        self.grid=Grid([('kind','Смета'),('version','Версия'),('created_at','Подготовлена'),('prepared_by','Автор'),('state_label','Ручная отметка'),('total','Итог')]);layout.addWidget(self.grid)
        bar=FlowLayout();layout.addLayout(bar);button(bar,'Состав и журнал',self.details);button(bar,'Ручная отметка',self.manual_event);button(bar,'DOCX выбранной версии',self.document);button(bar,'CSV для ручного переноса',self.export)
        note=QLabel('CSV — спецификация для ручного переноса, не интеграция с 1С. Кнопки не отправляют сообщения клиенту и не подтверждают банковскую оплату.');note.setWordWrap(True);layout.addWidget(note)
    def install(self,s):
        c=s['estimate_comparison'];p=c['preliminary_total'];d=c['difference']
        t=s['totals']
        self.summary.setText('Предварительная стоимость: '+(rub(p) if p is not None else 'нет версии')+' · Фактическая: '+rub(c['final_total'])+' · Разница: '+(rub(d) if d is not None else 'не определена')+'\nУчтённые оплаты: '+rub(t['paid'])+' · Остаток: '+rub(t['balance'])+'\nРедактируемый черновик №'+str(s['preliminary_draft']['revision'])+' · Согласование отмечено вручную: '+('да' if c['approved_estimate_id'] else 'нет'))
        self.grid.install([{**q,'state_label':STATES[q['state']]} for q in s['estimates']])
    def modal(self,d):
        w=self.editor.workspace;w.dialogs.append(d)
        try:return d.exec()
        finally:w.dialogs.remove(d)
    def edit_draft(self):self.modal(DraftDialog(self.editor))
    def freeze(self,kind):
        editor=self.editor;d=FieldsDialog('Неизменяемая версия сметы',[('actor','Кто подготовил *','text'),('reason','Причина изменения / комментарий','long')],parent=self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();request=uuid4().hex;revision=editor.revision
            editor.mutate(lambda:freeze_estimate(editor.store,editor.key,kind,v['actor'],v['reason'],request,revision))
    def selected(self):
        q=self.grid.selected()
        if not q:QMessageBox.information(self,'Сметы','Выберите версию сметы')
        return q
    def manual_event(self):
        q=self.selected()
        if not q:return
        d=FieldsDialog('Ручная отметка — без отправки клиенту',[('action','Событие',[(k,v) for k,v in STATES.items() if k!='prepared']),('actor','Кто внёс *','text'),('comment','Основание и способ подтверждения *','long')],parent=self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();e=self.editor;e.mutate(lambda:record_event(e.store,q['id'],v['action'],v['actor'],v['comment']))
    def details(self):
        q=self.selected()
        if not q:return
        d=QDialog(self);d.setWindowTitle('Неизменяемый состав и журнал ручных событий');d.resize(800,600);layout=QVBoxLayout(d);area=QPlainTextEdit();area.setReadOnly(True)
        lines=[f"{KINDS_DISPLAY[q['kind']]} · версия {q['version']} — не изменяется · {q['prepared_by']}",f"Причина: {q['reason']}",f"SHA256: {q['payload_sha256']}"]
        for x in q['payload']['lines']:lines.append(f"{ITEM_KINDS[x['kind']]}: {x['name']} · {x['quantity']} {x['unit']} × {rub(x['price_cents'])} = {rub(x['total_cents'])}\n{x['description']}")
        lines.append('Скидка '+rub(q['payload']['totals']['discount'])+' · Итог '+rub(q['total']))
        lines += [f"{date_text(x['occurred_at'])} · {STATES[x['action']]} · {x['actor']} · {x['comment']}" for x in q['events']]
        area.setPlainText('\n'.join(lines));layout.addWidget(area);button(layout,'Закрыть',d.accept);d.exec()
    def document(self):
        q=self.selected()
        if q:
            from ...service.documents import generate_document
            e=self.editor;e.with_saved(lambda:e.mutate(lambda:generate_document(e.store,e.key,'estimate_'+q['kind'],estimate_id=q['id'])))
    def export(self):
        q=self.selected()
        if not q:return
        path,_=QFileDialog.getSaveFileName(self,'Новый CSV спецификации',f"specification-v{q['version']}.csv",'CSV (*.csv)')
        if path:self.editor.workspace.run(lambda:export_specification(self.editor.store,q['id'],path),lambda _:QMessageBox.information(self,'Спецификация','CSV сохранён. Перенос и проверка в учётной системе выполняются вручную.'))
