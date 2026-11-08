"""Explicit local quote editing and manual approval; no messages are sent."""
from uuid import uuid4
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QWidget,
                               QFileDialog,QMessageBox,QScrollArea,QTabBar,QFrame)
from ...service.estimates import save_draft,freeze_estimate,record_event,export_specification,normalize_lines
from ...service.finance import ITEM_KINDS, calculate
from ...service.validation import money,rub,ServiceError
from .forms import FieldsDialog,fit_dialog
from ..flow import FlowLayout
from ..widgets import text
from .presentation import STATES,KINDS_DISPLAY,date_text
from .widgets import Grid,button

def amount(c):return f'{c//100}.{c%100:02d}'

ITEM_LABELS={**ITEM_KINDS,'other':'Прочие расходы'}
LINE_COLUMNS=[('kind','Тип'),('name','Позиция'),('description','Описание'),('quantity','Кол-во'),
              ('unit','Ед.'),('price','Цена'),('total','Сумма')]


def line_rows(lines):
    return [{**row,'price':row['price_cents'] if row.get('price_known',True) else None,
             'total':row['total_cents'] if row.get('price_known',True) else None} for row in lines]


def inline_validation(form, normalize):
    """Keep a typed row in its form if the estimate rejects its values."""
    result=[]

    def check(values):
        try:result[:]=[normalize(values)]
        except ServiceError as exc:
            message=str(exc)
            if message.startswith('Сумма:'):message='Цена, ₽:'+message.removeprefix('Сумма:')
            form.show_error(message)
            return False
        return True

    form.check_values=check
    return result


class DraftDialog(QDialog):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;self.workspace=editor.workspace;fit_dialog(self,960,640);self.dirty=False;self.setWindowTitle('Предварительный расчёт — отдельный черновик')
        source=editor.snapshot['preliminary_draft'];self.revision=source['revision'];self.lines=[dict(x) for x in source['lines']]
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();layout=QVBoxLayout(body);scroll.setWidget(body);outer.addWidget(scroll,1);note=QLabel('Черновик не меняет фактические работы и задолженность. После сохранения создайте неизменяемую версию сметы.');note.setWordWrap(True);layout.addWidget(note)
        bar=FlowLayout();layout.addLayout(bar)
        for title,fn in [('Добавить позицию',self.add),('Из каталога',self.from_catalog),('Изменить',self.edit),('Удалить',self.remove),('Выше',lambda:self.move(-1)),('Ниже',lambda:self.move(1))]:button(bar,title,fn)
        self.grid=Grid(LINE_COLUMNS,settings_key='repair/quote-draft' if editor.embedded else None)
        self.grid.setAccessibleName('Редактируемые позиции предварительной сметы');layout.addWidget(self.grid,1)
        self.total_label=QLabel();self.total_label.setObjectName('section');self.total_label.setWordWrap(True);self.total_label.setAccessibleName('Итог предварительного черновика');layout.addWidget(self.total_label)
        self.discount=QLineEdit(amount(source['discount_cents']) if source['revision'] else editor.snapshot['profile']['default_discount']);self.discount.setAccessibleName('Скидка предварительной сметы');layout.addWidget(QLabel('Скидка, ₽'));layout.addWidget(self.discount)
        self.comment=QPlainTextEdit(source['comment']);self.comment.setAccessibleName('Комментарий предварительной сметы');self.comment.setMaximumHeight(100);layout.addWidget(self.comment)
        bottom=FlowLayout();outer.addLayout(bottom);self.dirty_label=QLabel('Черновик: можно редактировать');self.dirty_label.setWordWrap(True);outer.addWidget(self.dirty_label)
        self.save_button=button(bottom,'Сохранить расчёт',self.save,primary=True)
        button(bottom,'Отмена',self.workspace.back_page if editor.embedded else self.reject)
        self.discount.textChanged.connect(self.changed);self.comment.textChanged.connect(self.changed);self.install()
    def install(self):
        self.grid.install([{**row,'id':str(i)} for i,row in enumerate(line_rows(self.lines))])
        self.grid.sortByColumn(-1,Qt.SortOrder.AscendingOrder);self.update_total()
    def change(self,index=None):
        row=self.lines[index] if index is not None else {'kind':'work','quantity':'1','unit':'шт.','price_cents':0}
        d=FieldsDialog('Позиция предварительного расчёта',[('kind','Тип',list(ITEM_LABELS.items())),('name','Наименование *','text'),('description','Описание','long'),('quantity','Количество','text'),('unit','Единица','text'),('price','Цена, ₽','text')],{**row,'price':amount(row['price_cents'])},self)
        if self.editor.embedded:
            result=inline_validation(d,lambda values:normalize_lines([{**row,**values}])[0])
            return self.workspace.embed_form(d,lambda _:self.set_line(result[0],index))
        if d.exec()==QDialog.DialogCode.Accepted:
            try:value=normalize_lines([{**row,**d.values()}])[0]
            except Exception as exc:QMessageBox.warning(self,'Расчёт',str(exc));return
            self.set_line(value,index)
    def set_line(self,value,index=None):
        if index is None:self.lines.append(value)
        else:self.lines[index]=value
        self.changed();self.install()
    def add(self):
        if len(self.lines)>=2000:
            self.dirty_label.setText('В расчёте допускается до 2000 позиций')
            return
        return self.change()
    def from_catalog(self):
        if len(self.lines)>=2000:
            self.dirty_label.setText('В расчёте допускается до 2000 позиций')
            return
        if self.editor.embedded:
            page=EstimateCatalogPage(self)
            self.workspace.push_page(page,'Выбрать позицию каталога')
            page.refresh()
            return
        from .catalog import CatalogPicker
        d=CatalogPicker(self.editor.store,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            self.set_line(d.value)
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
            totals=calculate(self.lines,money(self.discount.text()))
        except ServiceError as exc:
            self.total_label.setText('Ошибка скидки. '+str(exc))
            self.set_discount_error(True)
            return
        self.total_label.setText('Позиции: '+str(len(self.lines))+' · Скидка: '+rub(totals['discount'])+' · Итог: '+rub(totals['total']))
        self.set_discount_error(False)
    def set_discount_error(self,failed):
        self.save_button.setEnabled(not failed)
        self.total_label.setObjectName('error' if failed else 'section')
        self.discount.setProperty('validationIssue',failed)
        for widget in (self.total_label,self.discount):
            widget.style().unpolish(widget);widget.style().polish(widget)
    def save(self,after=None):
        if not callable(after):after=self.accept
        rows=[dict(x) for x in self.lines];discount=self.discount.text();comment=self.comment.toPlainText();editor=self.editor
        def work():save_draft(editor.store,editor.key,rows,discount,comment,self.revision);return editor.store.snapshot(editor.key)
        def saved(snapshot):self.dirty=False;editor.install(snapshot);after()
        self.dirty_label.setText('Сохранение…')
        self.workspace.run(work,saved,'Сохраняю отдельный черновик сметы…',
                           on_error=lambda error:self.dirty_label.setText('Не сохранено. '+error),
                           inline_error=editor.embedded)
    def request_exit(self,proceed):
        if not self.dirty:
            proceed()
            return
        choices=QMessageBox.StandardButton
        prompt=QMessageBox(QMessageBox.Icon.Question,'Черновик сметы','Сохранить изменения расчёта перед выходом?',
                           choices.Save|choices.Discard|choices.Cancel,self)
        for kind,label in ((choices.Save,'Сохранить'),(choices.Discard,'Уйти без сохранения'),(choices.Cancel,'Остаться')):
            prompt.button(kind).setText(label)
        prompt.setDefaultButton(choices.Cancel);prompt.setEscapeButton(choices.Cancel)
        prompt.button(choices.Save).setEnabled(self.save_button.isEnabled())
        choice=prompt.exec()
        if choice==choices.Save:self.save(proceed)
        elif choice==choices.Discard:proceed()
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


class EstimateCatalogPage(QWidget):
    def __init__(self,draft):
        super().__init__(draft);self.draft=draft;self.workspace=draft.workspace
        layout=QVBoxLayout(self)
        layout.addWidget(text('Выберите позицию, затем подтвердите количество и цену в рублях. Черновик сохранит отдельную копию.','muted'))
        self.query=QLineEdit();self.query.setPlaceholderText('Название или артикул');self.query.setAccessibleName('Поиск позиции каталога');layout.addWidget(self.query)
        self.query.returnPressed.connect(self.refresh)
        actions=FlowLayout();layout.addLayout(actions);button(actions,'Найти',self.refresh,primary=True)
        self.choose_button=button(actions,'Добавить выбранную позицию',self.choose);self.choose_button.setEnabled(False)
        self.grid=Grid([('sku','Артикул'),('name','Название'),('price_text','Цена источника'),('source','Источник')])
        self.grid.setAccessibleName('Позиции каталога');layout.addWidget(self.grid,1)
        self.grid.selectionModel().currentRowChanged.connect(lambda:self.choose_button.setEnabled(self.grid.selected() is not None))
        self.grid.openRequested.connect(self.choose)
        self.status=text('','muted');layout.addWidget(self.status)

    def refresh(self):
        from .catalog import catalog_rows
        query=self.query.text()
        def install(rows):
            self.grid.install(rows)
            if rows:self.grid.selectRow(0)
            self.status.setText(f'Найдено позиций: {len(rows)}' if rows else 'Совпадений нет. Измените запрос.')
        self.workspace.run(lambda:catalog_rows(self.draft.editor.store,query),install,'Ищу в каталоге…',
                           on_error=lambda error:self.status.setText('Ошибка поиска. '+error),inline_error=True)

    def choose(self):
        from .catalog import quote_line
        item=self.grid.selected()
        if not item:return
        price=amount(item['price_cents']) if item['currency']=='RUB' and item['price_cents'] is not None else ''
        form=FieldsDialog('Подтвердить позицию каталога',[
            ('kind','Тип',[('', 'Выберите тип'),('part','Запчасть'),('work','Работа')]),
            ('name','Наименование *','text'),('quantity','Количество','text'),('unit','Единица','text'),
            ('price','Цена, ₽','text')],{**item,'price':price,'quantity':'1'},self)
        result=inline_validation(form,lambda values:quote_line(item,values))

        def selected(_):
            self.draft.set_line(result[0])
            # QDialog emits accepted before finished. Wait until its route closes.
            QTimer.singleShot(0,self,lambda:self.workspace.back_page() if self.workspace.current_page is self else None)
        self.workspace.embed_form(form,selected)


class EstimatesPanel(QWidget):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;layout=QVBoxLayout(self)
        if editor.embedded:
            self.build_workspace(layout)
            return
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
    def build_workspace(self,layout):
        layout.setContentsMargins(0,0,0,0)
        overview=QFrame();overview.setObjectName('card');overview_layout=QVBoxLayout(overview)
        overview_layout.setContentsMargins(12,6,12,6);overview_layout.setSpacing(3)
        self.summary=text('','section');overview_layout.addWidget(self.summary)
        overview_layout.addWidget(text('Предварительная смета описывает план. Долг рассчитывается по фактическим расходам и учтённым оплатам.','muted'))
        layout.addWidget(overview)
        self.mode=QTabBar();self.mode.setExpanding(False);self.mode.setUsesScrollButtons(True)
        self.mode.setAccessibleName('Какой состав сметы показать')
        for title in ('Черновик','Фактические позиции','Версии'):self.mode.addTab(title)
        bar=FlowLayout();layout.addLayout(bar)
        bar.addWidget(self.mode)
        self.edit_button=button(bar,'Редактировать черновик',lambda:self.editor.with_saved(self.edit_draft),primary=True)
        self.freeze_preliminary=button(bar,'Сохранить предварительную версию',lambda:self.editor.with_saved(lambda:self.freeze('preliminary')))
        self.freeze_actual=button(bar,'Сохранить окончательную версию',lambda:self.editor.with_saved(lambda:self.freeze('final')),primary=True)
        self.version_panel=QWidget();versions=QVBoxLayout(self.version_panel);versions.setContentsMargins(0,0,0,0);layout.addWidget(self.version_panel)
        self.version_hint=text('Выберите версию, чтобы увидеть её исходный состав. Версии сохраняются без изменений.','muted')
        self.grid=Grid([('kind','Смета'),('version','№'),('created_at','Дата'),('prepared_by','Автор'),('state_label','Состояние'),('total','Итог')],
                       settings_key='repair/quote-versions')
        self.grid.setAccessibleName('Сохранённые версии сметы');versions.addWidget(self.grid)
        versions.addWidget(self.version_hint)
        self.grid.selectionModel().currentRowChanged.connect(self.show_content)
        version_actions=FlowLayout();versions.addLayout(version_actions)
        self.version_buttons=[
            button(version_actions,'Подготовить DOCX',self.document,primary=True),
            button(version_actions,'Записать ответ заказчика',self.manual_event),
            button(version_actions,'Автор и история',self.details),
            button(version_actions,'Выгрузить CSV',self.export),
        ]
        self.caption=text('','section');layout.addWidget(self.caption)
        self.lines=Grid(LINE_COLUMNS,settings_key='repair/quote-content')
        self.lines.setAccessibleName('Состав сметы');layout.addWidget(self.lines)
        self.empty=text('','empty');layout.addWidget(self.empty)
        self.line_detail=text('','muted');layout.addWidget(self.line_detail)
        self.lines.selectionModel().currentRowChanged.connect(self.show_line)
        self.costs=text('','section');layout.addWidget(self.costs)
        self.mode.currentChanged.connect(self.show_content)
        self.snapshot=None

    def install(self,s):
        c=s['estimate_comparison'];p=c['preliminary_total'];d=c['difference']
        t=s['totals']
        if self.editor.embedded:
            first=self.snapshot is None
            self.snapshot=s
            self.summary.setText(f"Предварительно: {rub(p) if p is not None else 'нет сохранённой версии'}   ·   "
                f"Фактически: {rub(c['final_total'])}   ·   Разница: {rub(d) if d is not None else 'не установлена'}\n"
                f"Учтено: {rub(t['paid'])}   ·   Остаток: {rub(t['balance'])}")
            self.grid.install([{**q,'state_label':STATES[q['state']]} for q in s['estimates']])
            self.grid.setFixedHeight(min(180,max(90,52+38*len(s['estimates']))))
            if s['estimates'] and not self.grid.selected():self.grid.selectRow(0)
            if first and not s['preliminary_draft']['lines']:
                if s['estimates']:self.mode.setCurrentIndex(2)
                elif s['repair_items']:self.mode.setCurrentIndex(1)
            self.show_content()
            return
        self.summary.setText('Предварительная стоимость: '+(rub(p) if p is not None else 'нет версии')+' · Фактическая: '+rub(c['final_total'])+' · Разница: '+(rub(d) if d is not None else 'не определена')+'\nУчтённые оплаты: '+rub(t['paid'])+' · Остаток: '+rub(t['balance'])+'\nРедактируемый черновик №'+str(s['preliminary_draft']['revision'])+' · Согласование отмечено вручную: '+('да' if c['approved_estimate_id'] else 'нет'))
        self.grid.install([{**q,'state_label':STATES[q['state']]} for q in s['estimates']])

    def show_content(self,*_):
        if not self.snapshot:return
        mode=self.mode.currentIndex();version=self.grid.selected() if mode==2 else None
        self.edit_button.setVisible(mode==0)
        self.freeze_preliminary.setVisible(mode==0)
        self.freeze_actual.setVisible(mode==1)
        self.version_panel.setVisible(mode==2)
        self.grid.setVisible(bool(self.snapshot['estimates']))
        for action in self.version_buttons:action.setEnabled(version is not None)
        if mode==0:
            draft=self.snapshot['preliminary_draft']
            rows=draft['lines'];totals=calculate(rows,draft['discount_cents'])
            next_version=max((q['version'] for q in self.snapshot['estimates'] if q['kind']=='preliminary'),default=0)+1
            heading=f'Предварительная смета №{next_version} · Черновик'
            empty='Позиций пока нет. Откройте черновик и добавьте работы или запчасти.'
        elif mode==1:
            rows=self.snapshot['repair_items'];totals=self.snapshot['totals']
            heading='Фактические работы и расходы'
            empty='Фактических расходов пока нет. Добавьте их на этапе «Работы».'
        elif version:
            rows=version['payload']['lines'];totals=version['payload']['totals']
            state='Сохранена' if version['state']=='prepared' else STATES[version['state']]
            heading=f"{KINDS_DISPLAY[version['kind']]} смета №{version['version']} · {state}"
            empty='Сохранённая версия не содержит позиций.'
        else:
            rows=[];totals=None;heading='Сохранённые версии'
            empty='Версий пока нет. Сохраните предварительную или окончательную смету.'
        self.caption.setText(heading)
        self.lines.install(line_rows(rows))
        self.lines.setFixedHeight(min(265,max(90,52+38*len(rows))))
        self.lines.setVisible(bool(rows));self.empty.setText(empty);self.empty.setVisible(not rows)
        if rows and not self.lines.selected():self.lines.selectRow(0)
        self.show_line()
        cost_text='' if totals is None else (
            f"Работы {rub(totals['work'])} · Запчасти {rub(totals['parts'])} · "
            f"Доставка {rub(totals['delivery'])} · Прочие {rub(totals['other'])}\n"
            f"Скидка {rub(totals['discount'])} · Итого {rub(totals['total'])}")
        self.costs.setText(cost_text);self.costs.setVisible(bool(cost_text))
        self.updateGeometry()

    def show_line(self,*_):
        row=self.lines.selected()
        if row is None:
            self.line_detail.clear();self.line_detail.hide()
            return
        self.line_detail.setText(' · '.join(filter(None,(ITEM_LABELS[row['kind']],row.get('description'),row.get('notes')))))
        self.line_detail.show()

    def modal(self,d):
        w=self.editor.workspace;w.dialogs.append(d)
        try:return d.exec()
        finally:w.dialogs.remove(d)
    def edit_draft(self):
        dialog=DraftDialog(self.editor)
        if self.editor.embedded:
            return self.editor.workspace.embed_form(dialog,before_close=dialog.request_exit)
        self.modal(dialog)
    def freeze(self,kind):
        editor=self.editor
        title='Сохранить предварительную смету' if kind=='preliminary' else 'Сохранить окончательную смету'
        reason_required=any(q['kind']==kind for q in editor.snapshot['estimates']) or (
            kind=='final' and editor.snapshot['estimate_comparison']['changed_from_approved'])
        reason_label='Причина изменения *' if editor.embedded and reason_required else 'Причина изменения / комментарий'
        d=FieldsDialog(title if editor.embedded else 'Неизменяемая версия сметы',[('actor','Кто подготовил *','text'),('reason',reason_label,'long')],parent=self)
        request=uuid4().hex;revision=editor.revision
        if editor.embedded:
            new_version=[]
            def freeze(values):
                new_version.append(freeze_estimate(editor.store,editor.key,kind,values['actor'],values['reason'],request,revision))
            editor.persist_form(d,freeze)
            d.accepted.connect(lambda:self.select_version(new_version[0]))
            return d
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values()
            editor.mutate(lambda:freeze_estimate(editor.store,editor.key,kind,v['actor'],v['reason'],request,revision))

    def select_version(self,key):
        self.mode.setCurrentIndex(2)
        for position,estimate in enumerate(self.grid.records.rows):
            if estimate['id']==key:
                proxy=self.grid.proxy.mapFromSource(self.grid.records.index(position,0))
                if proxy.isValid():self.grid.selectRow(proxy.row())
                return
    def selected(self):
        q=self.grid.selected()
        if not q:QMessageBox.information(self,'Сметы','Выберите версию сметы')
        return q
    def manual_event(self):
        q=self.selected()
        if not q:return
        e=self.editor
        d=FieldsDialog('Ответ заказчика и передача сметы' if e.embedded else 'Ручная отметка — без отправки клиенту',[('action','Событие',[(k,v) for k,v in STATES.items() if k!='prepared']),('actor','Кто внёс *','text'),('comment','Основание и способ подтверждения *','long')],parent=self)
        if e.embedded:
            d.layout().insertWidget(0,text('Запишите фактическое событие. DocFlow сохраняет запись в истории сметы.','muted'))
            return e.persist_form(d,lambda v:record_event(e.store,q['id'],v['action'],v['actor'],v['comment']))
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();e.mutate(lambda:record_event(e.store,q['id'],v['action'],v['actor'],v['comment']))
    def details(self):
        q=self.selected()
        if not q:return
        embedded=self.editor.embedded
        d=QWidget(self) if embedded else QDialog(self);d.setWindowTitle('Автор и история сметы' if embedded else 'Неизменяемый состав и журнал ручных событий')
        if not embedded:d.resize(800,600)
        layout=QVBoxLayout(d);area=QPlainTextEdit();area.setReadOnly(True);area.setAccessibleName('История выбранной версии сметы')
        lines=[f"{KINDS_DISPLAY[q['kind']]} смета №{q['version']} · {date_text(q['created_at'])}",f"Подготовил: {q['prepared_by']}"]
        if q['reason']:lines.append(f"Комментарий: {q['reason']}")
        if not embedded:
            for x in line_rows(q['payload']['lines']):
                lines.append(f"{ITEM_LABELS[x['kind']]}: {x['name']} · {x['quantity']} {x['unit']} × {rub(x['price'])} = {rub(x['total'])}\n{x['description']}")
            lines.append('Скидка '+rub(q['payload']['totals']['discount'])+' · Итог '+rub(q['total']))
        lines.append('')
        lines += [f"{date_text(x['occurred_at'])} · {STATES[x['action']]} · {x['actor']} · {x['comment']}" for x in q['events']]
        lines += ['',f"Контрольная сумма сохранённой версии: {q['payload_sha256']}"]
        area.setPlainText('\n'.join(lines));layout.addWidget(area)
        if embedded:return self.editor.workspace.push_page(d,d.windowTitle())
        button(layout,'Закрыть',d.accept);d.exec()
    def document(self):
        q=self.selected()
        if q:
            e=self.editor
            if e.embedded:
                def start():
                    e.tabs.show_section('Документы')
                    e.document_wizard.start('estimate_'+q['kind'],estimate_id=q['id'])
                return e.with_saved(start)
            from ...service.documents import generate_document
            e.with_saved(lambda:e.mutate(lambda:generate_document(e.store,e.key,'estimate_'+q['kind'],estimate_id=q['id'])))
    def export(self):
        q=self.selected()
        if not q:return
        path,_=QFileDialog.getSaveFileName(self,'Новый CSV спецификации',f"specification-v{q['version']}.csv",'CSV (*.csv)')
        if path:
            workspace=self.editor.workspace
            workspace.run(lambda:export_specification(self.editor.store,q['id'],path),
                          lambda _:workspace.message.setText('CSV сохранён. Перенос и проверка в учётной системе выполняются вручную.'),
                          'Сохраняю CSV выбранной версии…',inline_error=self.editor.embedded)
