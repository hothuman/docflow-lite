"""Repair editor with explicit saves, immutable payment corrections and versioned documents."""
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import QUrl,Qt
from PySide6.QtGui import QImageReader,QPixmap,QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QTabWidget,QLineEdit,QPlainTextEdit,QComboBox,QScrollArea,QWidget,QFileDialog,QInputDialog,QMessageBox,QCheckBox,QFrame,QSizePolicy)
from ...service.validation import rub
from ...service.statuses import STATUSES,APPROVALS
from ...service.documents import KINDS,generate_document
from ...service.attachments import add_attachment,attachment_path,remove_attachment,export_file
from .forms import FieldsDialog,fit_dialog,DateField
from ..flow import FlowLayout
from ..widgets import text
from .navigation import RepairNavigation
from .widgets import Grid,button,confirm
from .document_actions import open_for_printing

BUSINESS_TEXT_FIELDS = ('complaint','accessories','condition','defects','plan','notes','approval_note','issued_accessories','handover')

def amount(c):return f'{c//100}.{c%100:02d}'

class RepairDialog(QDialog):
    def __init__(self,workspace,snapshot):
        super().__init__(workspace);self.workspace=workspace;self.store=workspace.store;self.snapshot=snapshot;self.key=snapshot['repair']['id'];self.dirty=False;self.fields={};self.grids={}
        self.setWindowTitle('Ремонт '+snapshot['repair']['number']);fit_dialog(self,1060,740)
        root_layout=QVBoxLayout(self);scroller=QScrollArea();self.body_scroll=scroller;scroller.setWidgetResizable(True);content=QWidget();scroller.setWidget(content);root_layout.addWidget(scroller,1);outer=QVBoxLayout(content);outer.setContentsMargins(0,0,0,0);outer.setSpacing(10)
        passport=QFrame();passport.setObjectName('card');passport_layout=QVBoxLayout(passport);passport_layout.setContentsMargins(12,8,12,8)
        self.identity=QLabel();self.identity.setWordWrap(True);self.heading=text('','section');passport_layout.addWidget(self.heading);passport_layout.addWidget(self.identity)
        number_bar=FlowLayout();passport_layout.addLayout(number_bar)

        self.repair_number=QLineEdit();self.repair_number.setReadOnly(True);self.repair_number.setAccessibleName('№ ремонта');self.repair_number.setMaximumWidth(160);self.repair_number.hide()
        button(number_bar,'Документы',lambda:self.tabs.show_section('Документы'))
        button(number_bar,'Фото / файлы',lambda:self.tabs.show_section('Вложения'))
        button(number_bar,'Оплаты',lambda:self.tabs.show_section('Финансы'))
        button(number_bar,'История аппарата',self.equipment_history)
        from PySide6.QtWidgets import QMenu,QPushButton
        more=QPushButton('Дополнительно');menu=QMenu(more);menu.addAction('Изменить статус',self.open_status);menu.addAction('Изменить № ремонта',lambda:self.with_saved(self.change_number));menu.addAction('Первоисточник',self.show_source);more.setMenu(menu);number_bar.addWidget(more)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setObjectName('muted');passport_layout.addWidget(self.summary);outer.addWidget(passport)
        self.finance_strip=QWidget();finance=QHBoxLayout(self.finance_strip);finance.setContentsMargins(0,0,0,0);finance.setSpacing(12);self.finance_values={}
        for key,title in [('total','Стоимость ремонта'),('paid','Учтено оплат'),('balance','Остаток')]:
            panel=QFrame();panel.setObjectName('metricCard');box=QVBoxLayout(panel);box.setContentsMargins(14,8,14,8);box.addWidget(text(title,'muted'));value=text('—','metricValue');box.addWidget(value);finance.addWidget(panel,1);self.finance_values[key]=value
        outer.addWidget(self.finance_strip)
        self.state_frame=QFrame();self.state_frame.setObjectName('repairState');state_layout=QHBoxLayout(self.state_frame);state_layout.setContentsMargins(12,8,12,8)
        self.state_hint=text('','muted');self.state_hint.setAccessibleName('Текущий этап и следующий шаг');state_layout.addWidget(self.state_hint,1)
        self.status_action=button(state_layout,'Статус и история',self.open_status);outer.addWidget(self.state_frame)
        self.tabs=RepairNavigation(self);self.tabs.setUsesScrollButtons(False);self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);self.tabs.setMinimumHeight(0);root_layout.insertWidget(0,self.tabs.stage_bar);outer.addWidget(self.tabs,1)
        sections=[('Приёмка',[('received_at','Дата приёмки','date'),('complaint','Что сломалось?','long'),('accessories','Что принесли вместе с аппаратом?','long'),('condition','Внешнее состояние','long'),('notes','Примечания','long')]),('Дефектовка',[('defects','Что нашли при проверке?','long'),('plan','Что нужно сделать?','long')]),('Согласование',[('approval','Ручная отметка согласования',[(v,v) for v in APPROVALS]),('approval_note','На каком основании согласовано?','long')])]
        for title,fields in sections:
            scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();body_layout=QVBoxLayout(body);body_layout.setContentsMargins(0,0,0,0);form=QFormLayout();body_layout.addLayout(form);body_layout.addStretch(1);form.setFormAlignment(Qt.AlignmentFlag.AlignTop);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);scroll.setWidget(body);self.tabs.addTab(scroll,title)
            for key,label,kind in fields:self.add_field(form,key,label,kind)
            if title=='Дефектовка':
                self.source_works=QPlainTextEdit();self.source_works.setReadOnly(True);self.source_works.setMaximumHeight(110);self.source_works.setAccessibleName('Работы из источника')
                form.addRow('Работы из источника',self.source_works);self._source_works_form=form
        for group,title in [('work','Работы'),('part','Запчасти'),('delivery','Доставка'),('other','Прочие расходы')]:
            p=QWidget();layout=QVBoxLayout(p);bar=FlowLayout();layout.addLayout(bar)
            grid=Grid([('name','Наименование'),('description','Описание'),('quantity','Количество'),('unit','Ед.'),('price','Цена'),('total','Сумма')]);grid.setMaximumHeight(230);self.grids[group]=grid;layout.addWidget(grid);self.tabs.addTab(p,title)
            button(bar,'Добавить',lambda _,g=group:self.with_saved(lambda:self.item(g)));button(bar,'Изменить',lambda _,g=group:self.with_saved(lambda:self.item(g,True)));button(bar,'Удалить',lambda _,g=group:self.with_saved(lambda:self.delete_item(g)),danger=True)
        p=QWidget();layout=QVBoxLayout(p);form=QFormLayout();layout.addLayout(form);self.add_field(form,'discount','Скидка, ₽','text')
        label=QLabel('Только внутренние записи. Программа не проводит платежи и не выдаёт чеки. Ошибочная запись исправляется аннулированием с причиной и новой корректной записью.');label.setWordWrap(True);layout.addWidget(label)
        bar=FlowLayout();layout.addLayout(bar);button(bar,'Учесть оплату / возврат',lambda:self.with_saved(self.payment));button(bar,'Исправить ошибочную запись',lambda:self.with_saved(self.void_payment));button(bar,'Сверить полноту истории',lambda:self.with_saved(self.financial_evidence))
        self.grids['payments']=Grid([('occurred_at','Дата'),('kind','Вид'),('amount','Сумма'),('method','Способ'),('voided','Состояние'),('void_reason','Причина'),('comment','Комментарий')]);layout.addWidget(self.grids['payments']);self.tabs.addTab(p,'Финансы')
        from .estimates import EstimatesPanel
        self.estimates=EstimatesPanel(self);self.tabs.addTab(self.estimates,'Сметы')
        p=QWidget();layout=QVBoxLayout(p);bar=FlowLayout();layout.addLayout(bar)
        button(bar,'Прикрепить',lambda:self.with_saved(self.add_file));button(bar,'Открыть',self.open_attachment);button(bar,'Просмотр фото',self.preview_image);button(bar,'Удалить',self.delete_attachment,danger=True)
        self.grids['attachments']=Grid([('name','Имя'),('kind','Тип'),('size','Байт'),('comment','Подпись')]);layout.addWidget(self.grids['attachments']);self.image=QLabel('PNG / JPEG · MP4 · безопасный DOCX');self.image.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.image);self.tabs.addTab(p,'Вложения')
        p=QWidget();layout=QVBoxLayout(p);bar=FlowLayout();layout.addLayout(bar);self.doc_kind=QComboBox()
        for k,title in KINDS.items():self.doc_kind.addItem(title,k)
        self.doc_kind.setAccessibleName('Форма документа');bar.addWidget(self.doc_kind);self.generate_button=button(bar,'Создать документ',lambda:self.with_saved(self.generate));self.images=QCheckBox('Добавить выбранные фотографии (до 10)');self.image_choices=[];layout.addWidget(self.images)
        self.profile_banner=QLabel();self.profile_banner.setWordWrap(True);self.profile_banner.setTextFormat(Qt.TextFormat.PlainText);self.profile_banner.setAccessibleName('Проверка исполнителя перед документом');layout.insertWidget(0,self.profile_banner);button(bar,'Настроить организацию',lambda:self.with_saved(self.setup_organization))
        self.document_status=QLabel('Выберите форму. Данные берутся из этого ремонта; Excel не нужен.');self.document_status.setWordWrap(True);self.document_status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.document_status)
        custom=QHBoxLayout();layout.addLayout(custom);self.template_path=QLineEdit();self.template_path.setPlaceholderText('Без своего DOCX: форма профиля или встроенная');self.template_path.setReadOnly(True);custom.addWidget(self.template_path);button(custom,'Свой DOCX',self.pick_template);button(custom,'Сбросить',self.template_path.clear)
        self.doc_kind.currentIndexChanged.connect(self.refresh_document_profile);self.template_path.textChanged.connect(self.refresh_document_profile)
        self.grids['documents']=Grid([('kind','Тип'),('version','Версия'),('created_at','Создано'),('path','Путь')]);layout.addWidget(self.grids['documents']);bar2=FlowLayout();layout.addLayout(bar2);button(bar2,'Открыть в редакторе',self.open_document);button(bar2,'Папка файла',self.show_document_folder);button(bar2,'Сохранить копию',self.export_document);self.tabs.addTab(p,'Документы')
        scroll=QScrollArea();scroll.setWidgetResizable(True);p=QWidget();form=QFormLayout(p);form.setFormAlignment(Qt.AlignmentFlag.AlignTop);scroll.setWidget(p)
        self.add_field(form,'status','Фактический статус ремонта',[(k,v[0]) for k,v in STATUSES.items()])
        for key,label,kind in [('started_at','Начало ДД.ММ.ГГГГ','date'),('completed_at','Завершение ДД.ММ.ГГГГ','date'),('issued_at','Выдача ДД.ММ.ГГГГ','date'),('issued_accessories','Комплектация при выдаче','long'),('handover','Сведения о передаче (только факты)','long'),('status_note','Причина изменения статуса','text')]:self.add_field(form,key,label,kind)
        self.grids['history']=Grid([('changed_at','Когда'),('old_status','Было'),('new_status','Стало'),('note','Примечание'),('source','Источник')]);form.addRow(self.grids['history']);self.issue_button=button(form,'Выдать оборудование',self.issue);self.tabs.addTab(scroll,'Статус и история')
        self.dirty_label=text('','muted');root_layout.addWidget(self.dirty_label);bar=FlowLayout();root_layout.addLayout(bar);self.next_button=button(bar,'Далее',self.next_step,primary=True);self.quick_document_button=button(bar,'Сформировать акт',lambda:self.with_saved(self.quick_document));self.save_button=button(bar,'Сохранить',self.save);button(bar,'Закрыть',self.close);self.tabs.currentChanged.connect(self.update_step_actions)
        for label in self.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)
            if label.wordWrap():
                # Paths and long organization names must wrap to the viewport.
                # QLabel's minimumSizeHint otherwise widens even inactive pages
                # through QStackedWidget (reproduced in the extracted EXE).
                label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        from PySide6.QtGui import QShortcut,QKeySequence
        self.save_shortcut=QShortcut(QKeySequence.StandardKey.Save,self);self.save_shortcut.activated.connect(lambda:self.save() if self.dirty else None)
        self.install(snapshot)
    def next_step(self):
        stage=self.tabs.currentIndex()
        if stage==4:
            if self.snapshot['repair']['status'] in ('issued','closed','cancelled','historical'):self.tabs.show_section('Документы')
            else:self.issue()
        else:self.tabs.show_section(('Дефектовка','Сметы','Работы','Документы')[stage])
    def update_step_actions(self,*args):
        if not hasattr(self,'next_button'):return
        stage=self.tabs.currentIndex();terminal=self.snapshot['repair']['status'] in ('issued','closed','cancelled','historical')
        self.next_button.setText(('Диагностика →','Смета →','Работы →','К выдаче →','Документы' if terminal else 'Выдать аппарат')[stage]);self.next_button.setProperty('stage',stage);self.next_button.setEnabled(True)
    def equipment_history(self):
        equipment=dict(self.snapshot['equipment']);store=self.store
        def show(owner):
            from .history import HistoryDialog
            self.workspace.modal(HistoryDialog(self.workspace,{**equipment,'owner':owner['name']}))
        self.workspace.run(lambda:store.get('clients',equipment['owner_id']),show,'Открываю историю аппарата…')
    def issue(self):
        from datetime import date
        if not confirm(self,'Отметить фактическую выдачу оборудования? Оплата учитывается отдельно. Остаток: '+rub(self.snapshot['totals']['balance'])):return
        self.tabs.show_section('Статус и история')
        self.fields['status'].setCurrentIndex(self.fields['status'].findData('issued'))
        if not self.fields['issued_at'].text():self.fields['issued_at'].set_date(date.today().isoformat())
        self.save()
    def open_status(self):
        self.tabs.show_section('Статус и история');self.fields['status'].setFocus();self.body_scroll.ensureWidgetVisible(self.fields['status'])
    def add_field(self,form,key,label,kind):
        if isinstance(kind,list):
            w=QComboBox()
            for value,name in kind:w.addItem(name,value)
            w.currentIndexChanged.connect(self.changed)
        elif kind=='long':w=QPlainTextEdit();w.setMinimumHeight(64);w.setMaximumHeight(110);w.textChanged.connect(self.changed)
        elif kind=='date':w=DateField();w.textChanged.connect(self.changed)
        else:w=QLineEdit();w.textChanged.connect(self.changed)
        w.setAccessibleName(label);w.setMinimumWidth(0);form.addRow(label,w);self.fields[key]=w
    def changed(self,*args):
        self.dirty=True
        if hasattr(self,'dirty_label'):self.dirty_label.setText('Есть несохранённые изменения')
        if hasattr(self,'save_button'):self.save_button.setEnabled(True)
    def install(self,s):
        self.snapshot=s;r=s['repair'];self.revision=r['revision']
        from ...service.record_text import repair_display
        presented=repair_display(r);self._display_values={}
        for k,w in self.fields.items():
            value=amount(r['discount_cents']) if k=='discount' else presented.get(k,r.get(k,''))
            if k in BUSINESS_TEXT_FIELDS:self._display_values[k]=str(value)
            w.blockSignals(True)
            if isinstance(w,DateField):w.set_date(value)
            elif isinstance(w,QComboBox):w.setCurrentIndex(max(0,w.findData(value)))
            elif isinstance(w,QPlainTextEdit):w.setPlainText(str(value))
            else:w.setText(str(value))
            w.blockSignals(False)
        self.heading.setText('Ремонт №'+r['number']);self.identity.setText(f"Аппарат №{s['equipment']['number']} · {s['equipment']['model']}\nЗаказчик ремонта: {s['client']['name']} · Собственник: {s.get('owner',s['client'])['name']}")
        self.identity.setMinimumHeight(self.identity.fontMetrics().lineSpacing()*2+4)
        self.repair_number.setText(r['number']);self.setWindowTitle('Ремонт '+r['number'])
        source_works=presented.get('source_works','');self.source_works.setPlainText(source_works);self._source_works_form.setRowVisible(self.source_works,bool(source_works))
        t=s['totals']
        for key,label in self.finance_values.items():label.setText(rub(t[key]))
        self.finance_strip.hide()
        self.summary.setText('Статус: '+s['profile']['status_labels'].get(r['status'],STATUSES[r['status']][0])+f"\nРасчёты: {t['financial_status']} · Стоимость {rub(t['total'])} · Учтено {rub(t['paid'])} · Остаток {rub(t['balance'])}")
        hints={'accepted':'Зафиксируйте жалобу и комплектацию в разделе «Приёмка».','diagnostics':'Опишите неисправности и план работ в разделе «Диагностика».','approval':'Откройте «Сметы» и внесите только фактическую отметку согласования.','parts':'Уточните запчасти и план работ. Этап меняется вручную.','repair':'Запишите выполненные работы и фактическую стоимость.','ready':'Проверьте документы, комплектацию и внутренние расчёты перед выдачей.','issued':'Сведения о выдаче и история доступны в разделе «Статус и история».','closed':'Обращение закрыто. История и документы сохранены.','cancelled':'Отказ или отмена: причина сохраняется в истории.'}
        self.state_hint.setText(s['profile']['status_labels'].get(r['status'],STATUSES[r['status']][0])+' · '+hints.get(r['status'],''))
        self.state_frame.hide()
        stage={'accepted':0,'diagnostics':1,'approval':2,'parts':3,'repair':3,'ready':4,'issued':4,'closed':4}.get(r['status'],0)
        self.update_step_actions()
        self.issue_button.setEnabled(r['status'] not in ('issued','closed','cancelled'))
        facts=[bool(presented.get('complaint')),bool(presented.get('defects')),bool(s['estimates']),bool(s['repair_items']),bool(r.get('issued_at'))]
        for i,present in enumerate(facts):
            note='Есть данные' if present else 'Ещё не заполнено — можно перейти в любом порядке'
            self.tabs.setTabToolTip(i,note);self.tabs.status_labels[i].setText(note)
        self.estimates.install(s)
        from ...service.record_text import readable_field
        for group in ('work','part','delivery','other'):
            rows=[{**x,**{field:readable_field(x.get(field,''),field).text for field in ('name','description','notes')},'price':rub(x['price_cents'] if x.get('price_known',True) else None),'total':x['total_cents'] if x.get('price_known',True) else None} for x in s['repair_items'] if x['kind']==group];self.grids[group].install(rows);self.grids[group].setFixedHeight(min(230,max(100,self.grids[group].horizontalHeader().height()+len(rows)*self.grids[group].verticalHeader().defaultSectionSize()+8)))
        self.grids['payments'].install([{**x,'amount':rub(x['amount_cents'])} for x in s['payments']]);self.grids['attachments'].install(s['attachments']);self.grids['documents'].install(s['generated_documents']);self.grids['history'].install(s['repair_status_history']);self.dirty=False;self.dirty_label.setText('Сохранено');self.save_button.setEnabled(False);self.refresh_document_profile()
    def refresh_document_profile(self,*args):
        from ...service.document_readiness import assess
        check=assess(self.snapshot,self.doc_kind.currentData(),self.template_path.text());profile=check['profile']
        message='Исполнитель: '+(profile['organization_name'] or 'не указан — нейтральная форма')
        if check['missing']:message+='\nПроверьте данные: '+', '.join(check['missing'])+'. Для фирменной формы настройте организацию.'
        if check['quote_snapshot']:message+='\nРеквизиты взяты из сохранённой версии сметы. Изменения профиля её не переписывают.'
        message+='\nЛоготип: '+('выбран; проверяется при формировании' if profile.get('logo_path') else 'не выбран (можно без него)')
        if check['blocked']:message+='\nФирменный шаблон не будет сформирован с неполными данными исполнителя.'
        self.profile_banner.setText(message);self.generate_button.setText('Создать нейтральную форму' if check['neutral'] else 'Создать документ')
    def setup_organization(self):
        from .organization_setup import OrganizationWizard
        self.workspace.modal(OrganizationWizard(self.workspace,self))
    def values(self):
        from ...service.record_text import preserve_field_edit
        values={k:(w.storage_text() if isinstance(w,DateField) else w.currentData() if isinstance(w,QComboBox) else w.toPlainText() if isinstance(w,QPlainTextEdit) else w.text()) for k,w in self.fields.items()}
        for key in BUSINESS_TEXT_FIELDS:
            if key in values:values[key]=preserve_field_edit(self.snapshot['repair'].get(key,''),self._display_values.get(key,''),values[key],key)
        return values

    def show_source(self):
        from ...service.record_text import readable_field
        dialog=QDialog(self);dialog.setWindowTitle('Первоисточник записи');fit_dialog(dialog,800,620)
        box=QVBoxLayout(dialog);hint=QLabel('Исходные значения сохранены без преобразований. Это окно только для чтения; служебные сведения импорта находятся здесь, а не в деловых полях.');hint.setWordWrap(True);box.addWidget(hint)
        viewer=QPlainTextEdit();viewer.setReadOnly(True);viewer.setAccessibleName('Исходные значения и происхождение')
        labels={'complaint':'Жалоба','accessories':'Комплектация','condition':'Внешнее состояние','defects':'Диагностика','plan':'План работ','notes':'Примечания','approval_note':'Согласование','issued_accessories':'Комплектация при выдаче','handover':'Передача'}
        chunks=[]
        for key in BUSINESS_TEXT_FIELDS:
            raw=self.snapshot['repair'].get(key,'');shown=readable_field(raw,key)
            if raw:
                chunks.append(labels[key]+'\n'+str(raw))
                if shown.warning:chunks.append('Пояснение: '+shown.warning)
        for item in self.snapshot['repair_items']:
            chunks.append('Позиция '+str(item.get('position',0)+1)+'\n'+'\n'.join(str(item.get(key,'')) for key in ('name','description','notes') if item.get(key)))
        viewer.setPlainText('\n\n'.join(chunks) or 'В этой записи исходные текстовые поля пусты.');box.addWidget(viewer);button(box,'Закрыть',dialog.accept);dialog.exec()

    def change_number(self):
        old=self.snapshot['repair']['number']
        number,ok=QInputDialog.getText(self,'№ ремонта','Новый деловой номер ремонта:',text=old)
        if not ok or number.strip()==old:return
        if not confirm(self,f'Изменить № ремонта «{old}» на «{number.strip()}»? Номер аппарата и ранее выданные документы останутся прежними.'):return
        key=self.key;revision=self.revision;store=self.store
        self.mutate(lambda:store.rename_repair(key,number,reason='Изменение номера оператором',expected_revision=revision))
    def save(self,after=None):
        # clicked(bool) is not a callback.
        if not callable(after):after=None
        v=self.values();revision=self.revision;s=self.store;key=self.key
        if v['discount']!=amount(self.snapshot['repair']['discount_cents']) and self.snapshot['estimate_comparison']['approved_estimate_id']:
            reason,ok=QInputDialog.getText(self,'Изменение согласованной стоимости','Причина изменения скидки *')
            if not ok:return
            v['change_reason']=reason
        # Historical source fragments are preserved exactly on unrelated edits.
        original=self.snapshot['repair']
        v={k:value for k,value in v.items() if value!=(amount(original['discount_cents']) if k=='discount' else original.get(k,''))}
        def work():s.save_repair(key,v,revision);return s.snapshot(key)
        def done(snapshot):
            self.install(snapshot)
            if after:after()
        self.dirty_label.setText('Сохранение…')
        self.workspace.run(work,done,'Сохраняю ремонт…',on_error=lambda _:self.dirty_label.setText('Не сохранено. Исправьте ошибку и повторите.'))
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
        values={**row,'price':amount(row['price_cents']) if row.get('price_known',True) else ''} if row else {'quantity':'1','unit':'шт.','price':'0'}
        original=next((item for item in self.snapshot['repair_items'] if row and item['id']==row['id']),None)
        from ...service.finance import ITEM_KINDS
        d=FieldsDialog(ITEM_KINDS[kind],fields,values,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v={**d.values(),'kind':kind}
            if original:
                from ...service.record_text import preserve_field_edit
                for field in ('name','description','notes'):v[field]=preserve_field_edit(original.get(field,''),values.get(field,''),v[field],field)
            key=row['id'] if row else None;s=self.store;r=self.key;self.mutate(lambda:s.save_item(r,v,key))
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
    def financial_evidence(self):
        t=self.snapshot['totals']
        d=FieldsDialog('Полнота исторических расчётов',[
            ('cost','Стоимость',[('unknown','Неизвестна / неполная'),('known','Проверена полностью')]),
            ('paid','История оплат',[('unknown','Неизвестна / неполная'),('known','Проверена полностью')]),
            ('reason','Кто сверил и на каком основании *','long')],
            {'cost':'known' if t.get('cost_known',True) else 'unknown',
             'paid':'known' if t.get('payments_known',True) else 'unknown'},self)
        if d.exec()==QDialog.DialogCode.Accepted:
            v=d.values();revision=self.revision
            self.mutate(lambda:self.store.set_financial_evidence(self.key,v['cost']=='known',v['paid']=='known',v['reason'],expected_revision=revision))

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
            s=self.store;self.workspace.run(lambda:attachment_path(s,row['id']),self.workspace.open_local)
    def preview_image(self):
        row=self.selected('attachments')
        if not row or row['kind']!='image':return
        s=self.store
        def read():
            path=attachment_path(s,row['id']);reader=QImageReader(str(path));reader.setAllocationLimit(128);image=reader.read()
            if image.isNull():
                from ...service.validation import ServiceError
                raise ServiceError('Не удалось прочитать изображение. Проверьте файл или восстановите резервную копию.')
            return image
        self.workspace.run(read,lambda img:self.image.setPixmap(QPixmap.fromImage(img).scaled(540,220,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)),'Загружаю изображение…')
    def pick_template(self):
        p,_=QFileDialog.getOpenFileName(self,'Свой шаблон Service','','Word (*.docx)')
        if p:self.template_path.setText(p)
    def quick_document(self):
        choices=[KINDS[key] for key in ('intake','completion','handover')]
        from ...service.document_readiness import assess
        check=assess(self.snapshot,'intake');prompt='Какой документ сформировать из этого ремонта?'
        if check['missing']:prompt='Выберите акт. Реквизиты неполны — форма будет нейтральной.'
        selected,ok=QInputDialog.getItem(self,'Документы и печать',prompt,choices,0,False)
        if not ok:return
        kind=next(key for key,value in KINDS.items() if value==selected)
        self.doc_kind.setCurrentIndex(self.doc_kind.findData(kind));self.tabs.show_section('Документы')
        self.generate(open_after=True)

    def generate(self,open_after=False):
        s=self.store;key=self.key;kind=self.doc_kind.currentData();path=self.template_path.text() or None
        from ...service.document_readiness import assess
        check=assess(self.snapshot,kind,path or '');self.refresh_document_profile()
        if check['blocked']:self.document_status.setText('Документ не создан: заполните данные исполнителя для фирменного шаблона или выберите встроенную нейтральную форму.');return
        choices=[]
        if self.images.isChecked():
            from .images import ImagesDialog
            dialog=ImagesDialog(self.snapshot['attachments'],self,self.image_choices)
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            choices=dialog.values();self.image_choices=choices
        def work():
            result=generate_document(s,key,kind,path,image_choices=choices)
            return s.snapshot(key),result
        def done(result):
            snapshot,generated=result;self.install(snapshot)
            self._last_document=Path(generated)
            grid=self.grids['documents']
            for index,row in enumerate(grid.records.rows):
                if Path(row['path']).name==self._last_document.name:
                    proxy=grid.proxy.mapFromSource(grid.records.index(index,0))
                    if proxy.isValid():grid.selectRow(proxy.row())
                    break
            self.document_status.setText('DOCX сохранён. Нажмите «Открыть для печати»; в Word или LibreOffice выберите «Печать» / Ctrl+P. Файл: '+str(generated))
            if open_after:self.open_print_path(generated)
        def failed(error):
            self.document_status.setText('Документ не создан. Проверьте поля и форму профиля / «Свой DOCX», доступ к папке проекта. '+error)
        self.document_status.setText('Формирую новую версию DOCX…')
        self.workspace.run(work,done,'Формирую документ из карточки ремонта…',on_error=failed)

    def open_print_path(self,path):
        if open_for_printing(self,path):
            self.document_status.setText('Файл передан системной программе. Проверьте документ и выберите «Печать» / Ctrl+P. Отправка на принтер приложением не выполнялась. Файл: '+str(path))
        else:
            self.document_status.setText('Документ сохранён. Не удалось открыть редактор; воспользуйтесь «Показать папку документа». Файл: '+str(path))

    def open_document(self):
        row=self.selected('documents')
        if row:
            s=self.store;self.workspace.run(lambda:attachment_path(s,row['id'],True),self.open_print_path)

    def show_document_folder(self):
        row=self.selected('documents')
        if row:
            store=self.store
            self.workspace.run(lambda:attachment_path(store,row['id'],True),lambda path:self.workspace.open_local(Path(path).parent))
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

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'identity'):self.identity.setMinimumHeight(self.identity.fontMetrics().lineSpacing()*2+4)
        if hasattr(self,'finance_strip'):self.finance_strip.hide()
        if hasattr(self,'state_frame'):self.state_frame.hide()
