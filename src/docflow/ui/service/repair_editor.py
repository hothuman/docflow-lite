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

class RepairEditor:
    embedded = False

    def __init__(self,workspace,snapshot):
        super().__init__(workspace);self.workspace=workspace;self.store=workspace.store;self.snapshot=snapshot;self.key=snapshot['repair']['id'];self.dirty=False;self.fields={};self.grids={}
        self.setWindowTitle(('Ремонт № ' if self.embedded else 'Ремонт ')+snapshot['repair']['number'])
        if not self.embedded:fit_dialog(self,1060,740)
        root_layout=QVBoxLayout(self);scroller=QScrollArea();self.body_scroll=scroller;scroller.setWidgetResizable(True);content=QWidget();scroller.setWidget(content);root_layout.addWidget(scroller,1);outer=QVBoxLayout(content);outer.setContentsMargins(0,0,0,0);outer.setSpacing(10)
        if self.embedded:root_layout.setContentsMargins(0,0,0,0);root_layout.setSpacing(6)
        self.overview=QWidget();self.overview_layout=QVBoxLayout(self.overview);self.overview_layout.setContentsMargins(0,0,0,0);self.overview_layout.setSpacing(7)
        outer.addWidget(self.overview)
        passport=QFrame();passport.setObjectName('card');passport_layout=QVBoxLayout(passport);passport_layout.setContentsMargins(12,8,12,8)
        self.identity=QLabel();self.identity.setWordWrap(True);self.heading=text('','section');passport_layout.addWidget(self.heading);passport_layout.addWidget(self.identity)
        if self.embedded:
            self.heading.hide()
            self.compact_status=text('','repairStatus')
            passport_layout.addWidget(self.compact_status)
        number_bar=FlowLayout();passport_layout.addLayout(number_bar)

        self.repair_number=QLineEdit();self.repair_number.setReadOnly(True);self.repair_number.setAccessibleName('№ ремонта');self.repair_number.setMaximumWidth(160);self.repair_number.hide()
        button(number_bar,'Документы',lambda:self.tabs.show_section('Документы'))
        if not self.embedded:
            button(number_bar,'Фото / файлы',lambda:self.tabs.show_section('Вложения'))
        button(number_bar,'Оплаты',lambda:self.tabs.show_section('Финансы'))
        button(number_bar,'История аппарата',self.equipment_history)
        from PySide6.QtWidgets import QMenu,QPushButton
        more=QPushButton('Дополнительно');menu=QMenu(more);menu.addAction('Изменить № ремонта',lambda:self.with_saved(self.change_number));menu.addAction('Первоисточник',self.show_source);more.setMenu(menu);number_bar.addWidget(more)
        if self.embedded:
            menu.addAction('Изменить статус',self.open_status)
            menu.addAction('История статусов',self.show_status_history)
            menu.addAction('Что уже заполнено',lambda:self.tabs.show_section('Приёмка'))
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setObjectName('muted');passport_layout.insertWidget(2,self.summary);self.overview_layout.addWidget(passport)
        self.finance_strip=QWidget();finance=QHBoxLayout(self.finance_strip);finance.setContentsMargins(0,0,0,0);finance.setSpacing(12);self.finance_values={}
        for key,title in [('total','Стоимость ремонта'),('paid','Учтено оплат'),('balance','Остаток')]:
            panel=QFrame();panel.setObjectName('metricCard');box=QVBoxLayout(panel);box.setContentsMargins(14,8,14,8);box.addWidget(text(title,'muted'));value=text('—','metricValue');box.addWidget(value);finance.addWidget(panel,1);self.finance_values[key]=value
        self.overview_layout.addWidget(self.finance_strip)
        self.state_frame=QFrame();self.state_frame.setObjectName('repairState');state_layout=QVBoxLayout(self.state_frame);state_layout.setContentsMargins(12,8,12,8)
        self.status_value=text('','section');self.status_value.setObjectName('repairStatus');state_layout.addWidget(self.status_value)
        self.state_hint=text('','muted');self.state_hint.setAccessibleName('Что сделать дальше');state_layout.addWidget(self.state_hint)
        status_actions=FlowLayout();state_layout.addLayout(status_actions)
        self.status_action=button(status_actions,'Изменить статус',self.open_status)
        if self.embedded:button(status_actions,'История статусов',self.show_status_history)
        self.overview_layout.addWidget(self.state_frame)
        self.tabs=RepairNavigation(self,embedded=self.embedded);self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);self.tabs.setMinimumHeight(0);root_layout.insertWidget(0,self.tabs.stage_bar)
        if self.embedded:
            checklist=QFrame();checklist.setObjectName('card');steps=QVBoxLayout(checklist);steps.addWidget(text('Что уже заполнено','section'));choices=FlowLayout();steps.addLayout(choices)
            self.checklist=checklist
            self.checks={}
            for section,name in (('Приёмка','Приёмка'),('Дефектовка','Диагностика'),('Согласование','Согласование'),('Сметы','Смета'),('Работы','Работы'),('Документы','Документы'),('Статус и история','Выдача')):
                self.checks[section]=(name,button(choices,name,lambda _,section=section:self.tabs.show_section(section)))
            outer.addWidget(checklist)
            self.tabs.sectionChanged.connect(self.update_breadcrumb)
        outer.addWidget(self.tabs,1)
        sections=[('Приёмка',[('received_at','Дата приёмки','date'),('complaint','Что сломалось?','long'),('accessories','Что принесли вместе с аппаратом?','long'),('condition','Внешнее состояние','long'),('notes','Примечания','long')]),('Дефектовка',[('defects','Что нашли при проверке?','long'),('plan','Что нужно сделать?','long')]),('Согласование',[('approval','Ответ заказчика',[(v,v) for v in APPROVALS]),('approval_note','На каком основании согласовано?','long')])]
        for title,fields in sections:
            scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();body_layout=QVBoxLayout(body);body_layout.setContentsMargins(0,0,0,0);form=QFormLayout();body_layout.addLayout(form);body_layout.addStretch(1);form.setFormAlignment(Qt.AlignmentFlag.AlignTop);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);scroll.setWidget(body)
            if self.embedded and title=='Согласование':agreement_page=scroll
            else:self.tabs.addTab(scroll,title)
            for key,label,kind in fields:self.add_field(form,key,label,kind)
            if title=='Дефектовка':
                self.source_works=QPlainTextEdit();self.source_works.setReadOnly(True);self.source_works.setMaximumHeight(110);self.source_works.setAccessibleName('Работы из источника')
                form.addRow('Работы из источника',self.source_works);self._source_works_form=form
        if self.embedded:self.build_items_page()
        else:
            for group,title in [('work','Работы'),('part','Запчасти'),('delivery','Доставка'),('other','Прочие расходы')]:
                p=QWidget();layout=QVBoxLayout(p);bar=FlowLayout();layout.addLayout(bar)
                grid=Grid([('name','Наименование'),('description','Описание'),('quantity','Количество'),('unit','Ед.'),('price','Цена'),('total','Сумма')]);grid.setMaximumHeight(230);self.grids[group]=grid;layout.addWidget(grid);self.tabs.addTab(p,title)
                button(bar,'Добавить',lambda _,g=group:self.with_saved(lambda:self.item(g)));button(bar,'Изменить',lambda _,g=group:self.with_saved(lambda:self.item(g,True)));button(bar,'Удалить',lambda _,g=group:self.with_saved(lambda:self.delete_item(g)),danger=True)
        p=QWidget();layout=QVBoxLayout(p);form=QFormLayout();layout.addLayout(form);self.add_field(form,'discount','Скидка, ₽','text')
        label=QLabel('Только внутренние записи. Программа не проводит платежи и не выдаёт чеки. Ошибочная запись исправляется аннулированием с причиной и новой корректной записью.');label.setWordWrap(True);layout.addWidget(label)
        self.payment_summary=text('','section');layout.insertWidget(0,self.payment_summary)
        bar=FlowLayout();layout.addLayout(bar)
        if self.embedded:
            button(bar,'Учесть оплату',lambda:self.with_saved(lambda:self.payment('payment')),primary=True)
            button(bar,'Учесть возврат',lambda:self.with_saved(lambda:self.payment('refund')))
        else:button(bar,'Учесть оплату / возврат',lambda:self.with_saved(self.payment))
        button(bar,'Исправить запись',lambda:self.with_saved(self.void_payment));button(bar,'Сверить полноту истории',lambda:self.with_saved(self.financial_evidence))
        self.grids['payments']=Grid([('occurred_at','Дата'),('kind','Вид'),('amount','Сумма'),('method','Способ'),('voided','Состояние'),('void_reason','Причина'),('comment','Комментарий')],settings_key='repair/payments' if self.embedded else None);layout.addWidget(self.grids['payments']);self.tabs.addTab(p,'Финансы')
        from .estimates import EstimatesPanel
        self.estimates=EstimatesPanel(self);self.tabs.addTab(self.estimates,'Сметы')
        if self.embedded:self.tabs.addTab(agreement_page,'Согласование')
        p=QWidget();layout=QVBoxLayout(p);bar=FlowLayout();layout.addLayout(bar)
        button(bar,'Прикрепить',lambda:self.with_saved(self.add_file));button(bar,'Открыть',self.open_attachment);button(bar,'Просмотр фото',self.preview_image);button(bar,'Удалить',self.delete_attachment,danger=True)
        self.grids['attachments']=Grid([('name','Имя'),('kind','Тип'),('size','Байт'),('comment','Подпись')]);layout.addWidget(self.grids['attachments']);self.image=QLabel('PNG / JPEG · MP4 · безопасный DOCX');self.image.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.image);self.tabs.addTab(p,'Вложения')
        if not self.embedded:self.build_documents_page()
        scroll=QScrollArea();scroll.setWidgetResizable(True);p=QWidget();form=QFormLayout(p);form.setFormAlignment(Qt.AlignmentFlag.AlignTop);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);scroll.setWidget(p)
        if self.embedded:
            self.handover_readiness=text('','section');form.addRow(self.handover_readiness)
            form.addRow(text('Запишите дату и получателя. Проверка формы и создание акта доступны в разделе «Документы».','muted'))
            status_form=QFormLayout(QWidget(self))
        else:status_form=form
        self.add_field(status_form,'status','Фактический статус ремонта',[(k,v[0]) for k,v in STATUSES.items()])
        if self.embedded:status_form.parentWidget().hide()
        for key,label,kind in [('started_at','Начало','date'),('completed_at','Завершение','date'),('issued_at','Дата выдачи','date'),('issued_accessories','Комплектация при выдаче','long'),('handover','Кому передано и на каком основании','long'),('status_note','Причина изменения статуса','text')]:self.add_field(status_form if key=='status_note' else form,key,label,kind)
        self.grids['history']=Grid([('changed_at','Когда'),('old_status','Было'),('new_status','Стало'),('note','Причина'),('source','Источник')])
        if not self.embedded:form.addRow(self.grids['history'])
        self.issue_button=button(form,'Отметить, что оборудование передано' if self.embedded else 'Выдать оборудование',self.issue);self.tabs.addTab(scroll,'Статус и история')
        if self.embedded:
            self.build_documents_page()
            self.tabs.show_section('Приёмка')
        self.dirty_label=text('','muted');bar=FlowLayout()
        if not self.embedded:root_layout.addWidget(self.dirty_label)
        else:
            self.save_error=text('','formError');self.save_error.setAccessibleName('Ошибка сохранения ремонта')
            self.save_error.hide();root_layout.addWidget(self.save_error)
        root_layout.addLayout(bar);self.next_button=button(bar,'Далее',self.next_step,primary=True)
        if not self.embedded:self.quick_document_button=button(bar,'Сформировать акт',lambda:self.with_saved(self.quick_document))
        self.save_button=button(bar,'Сохранить',self.save)
        if self.embedded:
            self.cancel_edits=button(bar,'Отменить правки',lambda:self.install(self.snapshot))
            self.dirty_label.setWordWrap(False)
            bar.addWidget(self.dirty_label)
        else:button(bar,'Закрыть',self.close)
        self.tabs.currentChanged.connect(self.update_step_actions)
        for label in self.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)
            if label.wordWrap():
                # Paths and long organization names must wrap to the viewport.
                label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        from PySide6.QtGui import QShortcut,QKeySequence
        self.save_shortcut=QShortcut(QKeySequence.StandardKey.Save,self);self.save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.save_shortcut.activated.connect(lambda:self.save() if self.dirty else None)
        self.install(snapshot)

    def build_documents_page(self):
        if self.embedded:
            from .document_actions import ServiceDocumentWizard
            wizard=ServiceDocumentWizard(self);self.document_wizard=wizard
            for name in ('doc_kind','template_path','profile_banner','document_status','generate_button','images','image_choices'):
                setattr(self,name,getattr(wizard,name))
            self.grids['documents']=wizard.grid;self.tabs.addTab(wizard,'Документы')
            return
        p=QWidget();layout=QVBoxLayout(p);bar=FlowLayout();layout.addLayout(bar);self.doc_kind=QComboBox()
        for k,title in KINDS.items():self.doc_kind.addItem(title,k)
        self.doc_kind.setAccessibleName('Форма документа');bar.addWidget(self.doc_kind)
        button(bar,'Проверить форму',self.check_document)
        self.generate_button=button(bar,'Создать документ',lambda:self.with_saved(self.generate));self.images=QCheckBox('Добавить выбранные фотографии (до 10)');self.image_choices=[];layout.addWidget(self.images)
        self.profile_banner=QLabel();self.profile_banner.setWordWrap(True);self.profile_banner.setTextFormat(Qt.TextFormat.PlainText);self.profile_banner.setAccessibleName('Проверка исполнителя перед документом');layout.insertWidget(0,self.profile_banner);button(bar,'Настроить организацию',lambda:self.with_saved(self.setup_organization))
        self.document_status=QLabel('Выберите акт, смету, гарантийную форму или другой документ. Данные берутся из текущего ремонта.');self.document_status.setWordWrap(True);self.document_status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.document_status)
        custom=QHBoxLayout();layout.addLayout(custom);self.template_path=QLineEdit();self.template_path.setPlaceholderText('Без своего DOCX: форма профиля или встроенная');self.template_path.setReadOnly(True);custom.addWidget(self.template_path);button(custom,'Свой DOCX',self.pick_template);button(custom,'Сбросить',self.template_path.clear)
        self.doc_kind.currentIndexChanged.connect(self.refresh_document_profile);self.template_path.textChanged.connect(self.refresh_document_profile)
        self.grids['documents']=Grid([('kind','Тип'),('version','Версия'),('created_at','Создано'),('path','Путь')]);layout.addWidget(self.grids['documents']);bar2=FlowLayout();layout.addLayout(bar2);button(bar2,'Открыть в редакторе',self.open_document);button(bar2,'Показать в папке',self.show_document_folder);button(bar2,'Сохранить копию',self.export_document);self.tabs.addTab(p,'Документы')
    def next_step(self):
        stage=self.tabs.currentIndex()
        if self.embedded:
            if stage==4:
                target='Документы' if self.tabs.is_section('Статус и история') else 'Статус и история'
                self.tabs.show_section(target)
            else:self.tabs.show_section(('Дефектовка','Сметы','Работы','Статус и история')[stage])
            return
        if stage==4:
            if self.snapshot['repair']['status'] in ('issued','closed','cancelled','historical'):self.tabs.show_section('Документы')
            else:self.issue()
        else:self.tabs.show_section(('Дефектовка','Сметы','Работы','Документы')[stage])
    def update_step_actions(self,*args):
        if not hasattr(self,'next_button'):return
        stage=self.tabs.currentIndex();terminal=self.snapshot['repair']['status'] in ('issued','closed','cancelled','historical')
        label=('Диагностика →','Смета →','Работы →','К выдаче →','Документы' if terminal else 'Выдать аппарат')[stage]
        if self.embedded:
            overview=stage==0
            self.compact_status.setVisible(not overview)
            self.state_frame.setVisible(overview)
            self.checklist.setVisible(overview)
            label=('Продолжить · Диагностика','Продолжить · Смета','Продолжить · Работы','Продолжить · Выдача',
                   'Документы' if self.tabs.is_section('Статус и история') else 'Подготовка к выдаче')[stage]
        self.next_button.setText(label);self.next_button.setAccessibleName(label)
        self.next_button.setProperty('stage',stage);self.next_button.setEnabled(True)
        help_text='Открывает следующий этап карточки.' if stage<4 else 'Открывает документы или подтверждение фактической выдачи.'
        self.next_button.setToolTip(help_text);self.next_button.setAccessibleDescription(help_text)
    def equipment_history(self):
        if self.embedded:
            equipment=self.snapshot['equipment'];owner=self.snapshot.get('owner',self.snapshot['client'])
            self.workspace.show_history({**equipment,'owner':owner['name']})
            return
        equipment=dict(self.snapshot['equipment']);store=self.store
        def show(owner):
            from .history import HistoryDialog
            self.workspace.modal(HistoryDialog(self.workspace,{**equipment,'owner':owner['name']}))
        self.workspace.run(lambda:store.get('clients',equipment['owner_id']),show,'Открываю историю аппарата…')
    def issue(self):
        from datetime import date
        if self.embedded:
            if self.snapshot['repair']['status'] in ('issued','closed','cancelled','historical'):return
            balance=self.snapshot['totals']['balance']
            money_notice='Остаток не установлен.' if balance is None else f'Осталось {rub(balance)}.'
            if not confirm(self,'Отметить, что оборудование передано? '+money_notice+' Выдача не подтверждает оплату.',
                           'Подтвердить выдачу',cancel='Вернуться'):return
            if not self.fields['issued_at'].text():self.fields['issued_at'].set_date(date.today().isoformat())
            self.save(status_change=('issued','Оператор подтвердил фактическую передачу'))
            return
        if not confirm(self,'Отметить фактическую выдачу оборудования? Оплата учитывается отдельно. Остаток: '+rub(self.snapshot['totals']['balance']),'Подтвердить выдачу'):return
        self.tabs.show_section('Статус и история')
        self.fields['status'].setCurrentIndex(self.fields['status'].findData('issued'))
        if not self.fields['issued_at'].text():self.fields['issued_at'].set_date(date.today().isoformat())
        self.save()
    def open_status(self):
        if self.embedded:
            self.with_saved(self.edit_status)
            return
        self.tabs.show_section('Статус и история');self.fields['status'].setFocus();self.body_scroll.ensureWidgetVisible(self.fields['status'])

    def update_breadcrumb(self,label):
        self.route_detail=label
        if self.workspace.current_page is self:
            self.workspace.pages.update_heading()
        self.update_step_actions()

    def build_items_page(self):
        from ...service.finance import ITEM_KINDS
        page=QWidget();layout=QVBoxLayout(page)
        self.items_totals=text('','section');layout.addWidget(self.items_totals)
        bar=FlowLayout();layout.addLayout(bar)
        button(bar,'Добавить работу',lambda:self.with_saved(lambda:self.item('work')),primary=True)
        button(bar,'Добавить запчасть',lambda:self.with_saved(lambda:self.item('part')))
        button(bar,'Добавить доставку',lambda:self.with_saved(lambda:self.item('delivery')))
        button(bar,'Добавить прочие расходы',lambda:self.with_saved(lambda:self.item('other')))
        self.item_filter=QComboBox();self.item_filter.setAccessibleName('Тип фактических расходов')
        self.item_filter.addItem('Все позиции','')
        for key,label in ITEM_KINDS.items():self.item_filter.addItem(label,key)
        layout.addWidget(self.item_filter)
        columns=[('kind','Тип'),('name','Наименование'),('description','Описание'),('quantity','Кол-во'),('unit','Ед.'),('price','Цена'),('total','Сумма')]
        self.items_grid=Grid(columns,settings_key='repair/items')
        self.items_grid.setAccessibleName('Фактические работы и расходы');layout.addWidget(self.items_grid)
        self.items_empty=text('Пока расходов нет. Добавьте выполненную работу или использованную запчасть.','muted');layout.addWidget(self.items_empty)
        self.item_detail=text('','muted');self.item_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(self.item_detail)
        self.items_grid.selectionModel().currentRowChanged.connect(self.show_item_detail)
        actions=FlowLayout();layout.addLayout(actions)
        button(actions,'Изменить позицию',lambda:self.with_saved(lambda:self.item('',True)))
        button(actions,'Удалить позицию',lambda:self.with_saved(lambda:self.delete_item('')),danger=True)
        self.item_filter.currentIndexChanged.connect(self.install_items)
        self.tabs.addTab(page,'Работы')

    def install_items(self,*_):
        from ...service.record_text import readable_field
        selected=self.item_filter.currentData()
        rows=[{**item,**{field:readable_field(item.get(field,''),field).text for field in ('name','description','notes')},
               'price':item['price_cents'] if item.get('price_known',True) else None,
               'total':item['total_cents'] if item.get('price_known',True) else None}
              for item in self.snapshot['repair_items'] if not selected or selected==item['kind']]
        self.items_grid.install(rows)
        self.items_grid.setVisible(bool(rows))
        self.items_grid.setFixedHeight(min(310,max(90,52+38*len(rows))))
        self.items_empty.setVisible(not rows)
        self.show_item_detail()
        totals=self.snapshot['totals']
        self.items_totals.setText('Работы '+rub(totals['work'])+' · Запчасти '+rub(totals['parts'])+
                                  ' · Доставка '+rub(totals['delivery'])+' · Прочие '+rub(totals['other']))

    def show_item_detail(self,*_):
        row=self.items_grid.selected()
        self.item_detail.setText('\n'.join(value for value in (row['description'],row['notes']) if value) if row else '')

    def edit_status(self):
        old=self.snapshot['repair']['status']
        choices=[(key,value[0]) for key,value in STATUSES.items() if key!='issued' or key==old]
        form=FieldsDialog('Изменить производственный статус',[
            ('status','Новый статус',choices),('reason','Причина или пояснение','long')],{'status':old},self)
        form.save_button.setText('Применить статус')

        def check(data):
            from ...service.statuses import TERMINAL
            status=data['status'];reason=data['reason'].strip()
            if status==old:return True
            risky=old in TERMINAL or status in TERMINAL
            if risky and not reason:
                form.show_error('Укажите причину изменения закрытого, архивного или выданного статуса.','reason')
                return False
            return not risky or confirm(self,f'{STATUSES[old][0]} → {STATUSES[status][0]}\nПричина: {reason}',
                                         'Изменить статус',cancel='Вернуться')

        form.check_values=check
        self.workspace.embed_form(form,lambda data:self.save(status_change=(data['status'],data['reason'])))

    def show_status_history(self):
        from .presentation import date_text
        page=QWidget();layout=QVBoxLayout(page)
        layout.addWidget(text('История статусов','section'))
        viewer=QPlainTextEdit();viewer.setReadOnly(True);viewer.setAccessibleName('Хронология статусов')
        sources={'manual':'Действие сотрудника','create':'Приёмка','import':'Импорт','historical_import':'Импорт журнала'}
        entries=[]
        for row in self.snapshot['repair_status_history']:
            old=STATUSES.get(row['old_status'],('Новая запись',))[0]
            new=STATUSES.get(row['new_status'],('Не установлен',))[0]
            entries.append(f"{date_text(row['changed_at'])} · {sources.get(row['source'],'Запись журнала')}\n"
                           f"{old} → {new}\nПричина: {row['note'] or 'Не указана'}")
        viewer.setPlainText('\n\n'.join(entries) or 'Изменений статуса пока нет.')
        layout.addWidget(viewer,1)
        self.workspace.push_page(page,'История статусов')
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
        if hasattr(self,'cancel_edits'):self.cancel_edits.setEnabled(True)
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
        number_gap=' ' if self.embedded else ''
        self.heading.setText('Ремонт №'+number_gap+r['number']);self.identity.setText(f"Аппарат №{number_gap}{s['equipment']['number']} · {s['equipment']['model']}\nЗаказчик ремонта: {s['client']['name']} · Собственник: {s.get('owner',s['client'])['name']}")
        self.identity.setMinimumHeight(self.identity.fontMetrics().lineSpacing()*2+4)
        self.repair_number.setText(r['number']);self.setWindowTitle(('Ремонт № ' if self.embedded else 'Ремонт ')+r['number'])
        source_works=presented.get('source_works','');self.source_works.setPlainText(source_works);self._source_works_form.setRowVisible(self.source_works,bool(source_works))
        t=s['totals']
        for key,label in self.finance_values.items():
            value=rub(t[key]) if t[key] is not None or not self.embedded else 'Не установлено'
            if self.embedded and key=='balance' and (t[key] or 0)>0:value+=' · Долг'
            label.setText(value)
            label.setProperty('debt',self.embedded and key=='balance' and (t[key] or 0)>0)
            label.style().unpolish(label);label.style().polish(label)
        self.finance_strip.setVisible(self.embedded)
        self.summary.setText('Статус: '+s['profile']['status_labels'].get(r['status'],STATUSES[r['status']][0])+f"\nРасчёты: {t['financial_status']} · Стоимость {rub(t['total'])} · Учтено {rub(t['paid'])} · Остаток {rub(t['balance'])}")
        self.summary.setVisible(not self.embedded)
        hints={'accepted':'Зафиксируйте жалобу и комплектацию в разделе «Приёмка».','diagnostics':'Опишите неисправности и план работ в разделе «Диагностика».','approval':'Откройте «Сметы» и внесите только фактическую отметку согласования.','parts':'Уточните запчасти и план работ. Этап меняется вручную.','repair':'Запишите выполненные работы и фактическую стоимость.','ready':'Проверьте документы, комплектацию и внутренние расчёты перед выдачей.','issued':'Сведения о выдаче и история доступны в разделе «Статус и история».','closed':'Обращение закрыто. История и документы сохранены.','cancelled':'Отказ или отмена: причина сохраняется в истории.'}
        status=s['profile']['status_labels'].get(r['status'],STATUSES[r['status']][0])
        self.status_value.setText('Статус · '+status);self.status_value.setAccessibleName('Производственный статус: '+status)
        if self.embedded:
            self.compact_status.setText(self.status_value.text())
            self.compact_status.setAccessibleName(self.status_value.accessibleName())
        hint=hints.get(r['status'],'')
        self.state_hint.setText(hint if self.embedded else f'{status} · {hint}')
        if not self.embedded:self.state_frame.hide()
        self.payment_summary.setText('Итого '+rub(t['total'])+' · Учтено '+rub(t['paid'])+' · Остаток '+rub(t['balance'])+' · '+t['financial_status'])
        self.update_step_actions()
        self.issue_button.setEnabled(r['status'] not in ('issued','closed','cancelled') and (not self.embedded or r['status']!='historical'))
        facts=[bool(presented.get('complaint')),bool(presented.get('defects')),bool(s['estimates']),bool(s['repair_items']),bool(r.get('issued_at'))]
        for i,present in enumerate(facts):
            note='Есть данные' if present else 'Ещё не заполнено — можно перейти в любом порядке'
            self.tabs.setTabToolTip(i,note);self.tabs.status_labels[i].setText(note)
        self.estimates.install(s)
        from ...service.record_text import readable_field
        if self.embedded:
            self.install_items()
            completed=[facts[0],facts[1],r['approval']=='Согласовано',facts[2],facts[3],bool(s['generated_documents']),r['status']=='issued' and bool(r['issued_at'])]
            for index,((name,action),ready) in enumerate(zip(self.checks.values(),completed)):
                state='Готово' if ready else 'Требует проверки' if index==6 and (bool(r['issued_at']) or t['balance'] is None) else 'Не заполнено'
                action.setText(name+' · '+state);action.setAccessibleName(name+': '+state)
            self.handover_readiness.setText('Подготовка: '+('Работы записаны' if facts[3] else 'Работы не записаны')+' · '+
                ('Документ есть' if s['generated_documents'] else 'Документ ещё не создан')+' · '+
                ('Долг '+rub(t['balance']) if (t['balance'] or 0)>0 else 'Остаток '+rub(t['balance'])))
            self.document_wizard.install(s);self.cancel_edits.setEnabled(False)
            self.save_error.hide()
            for field in self.fields.values():
                if field.property('validationIssue'):self.mark_invalid(field,False)
            self.workspace.pages.update_heading()
        else:
            for group in ('work','part','delivery','other'):
                rows=[{**x,**{field:readable_field(x.get(field,''),field).text for field in ('name','description','notes')},'price':rub(x['price_cents'] if x.get('price_known',True) else None),'total':x['total_cents'] if x.get('price_known',True) else None} for x in s['repair_items'] if x['kind']==group];self.grids[group].install(rows);self.grids[group].setFixedHeight(min(230,max(100,self.grids[group].horizontalHeader().height()+len(rows)*self.grids[group].verticalHeader().defaultSectionSize()+8)))
            self.grids['documents'].install(s['generated_documents']);self.refresh_document_profile()
        self.grids['payments'].install([{**x,'amount':x['amount_cents']} for x in s['payments']]);self.grids['attachments'].install(s['attachments']);self.grids['history'].install(s['repair_status_history']);self.dirty=False;self.dirty_label.setText('Сохранено');self.save_button.setEnabled(False)
    def refresh_document_profile(self,*args):
        from ...service.document_readiness import assess
        check=assess(self.snapshot,self.doc_kind.currentData(),self.template_path.text());profile=check['profile']
        message='Исполнитель: '+(profile['organization_name'] or 'не указан — нейтральная форма')
        if check['missing']:message+='\nПроверьте данные: '+', '.join(check['missing'])+'. Для фирменной формы настройте организацию.'
        if check['required_missing']:message+='\nОбязательные поля шаблона не заполнены: '+', '.join(check['required_missing'])+'. Заполните данные ремонта или настройки формы.'
        if check['quote_snapshot']:message+='\nРеквизиты взяты из сохранённой версии сметы. Изменения профиля её не переписывают.'
        message+='\nЛоготип: '+('выбран; проверяется при формировании' if profile.get('logo_path') else 'не выбран (можно без него)')
        if check['blocked']:message+='\nФирменный шаблон не будет сформирован с неполными данными исполнителя.'
        self.profile_banner.setText(message);self.generate_button.setText('Создать нейтральную форму' if check['neutral'] else 'Создать документ')
    def setup_organization(self):
        from .organization_setup import OrganizationWizard
        wizard=OrganizationWizard(self.workspace,self)
        if self.embedded:self.workspace.embed_form(wizard)
        else:self.workspace.modal(wizard)
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
        viewer.setPlainText('\n\n'.join(chunks) or 'В этой записи исходные текстовые поля пусты.');box.addWidget(viewer)
        if self.embedded:self.workspace.embed_form(dialog)
        else:button(box,'Закрыть',dialog.accept);dialog.exec()

    def change_number(self):
        old=self.snapshot['repair']['number']
        number,ok=QInputDialog.getText(self,'№ ремонта','Новый деловой номер ремонта:',text=old)
        if not ok or number.strip()==old:return
        if not confirm(self,f'Изменить № ремонта «{old}» на «{number.strip()}»? Номер аппарата и ранее выданные документы останутся прежними.'):return
        key=self.key;revision=self.revision;store=self.store
        self.mutate(lambda:store.rename_repair(key,number,reason='Изменение номера оператором',expected_revision=revision))
    def save(self,after=None,*,status_change=None):
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
        if self.embedded:
            v.pop('status',None);v.pop('status_note',None)
            from ...service.validation import day,ServiceError
            for key_name in ('received_at','started_at','completed_at','issued_at'):
                if key_name not in v:continue
                try:day(v[key_name])
                except ServiceError as error:
                    self.show_save_error(str(error),key_name)
                    return
        if status_change and status_change[0]!=original['status']:
            v['status'],v['status_note']=status_change
        def work():s.save_repair(key,v,revision);return s.snapshot(key)
        def done(snapshot):
            self.install(snapshot)
            if after:after()
        self.dirty_label.setText('Сохранение…')
        self.workspace.run(work,done,'Сохраняю ремонт…',on_error=self.show_save_error,inline_error=self.embedded)

    @staticmethod
    def mark_invalid(field, invalid):
        field.setProperty('validationIssue',invalid)
        field.style().unpolish(field);field.style().polish(field)

    def show_save_error(self,error,field_name=None):
        if not self.embedded:
            self.dirty_label.setText('Не сохранено. '+error)
            return
        self.dirty_label.setText('Не сохранено')
        self.save_error.setText('Ошибка · '+error);self.save_error.show()
        normalized=error.casefold()
        if field_name:key,section=field_name,'Приёмка' if field_name=='received_at' else 'Статус и история'
        elif 'скидк' in normalized:key,section='discount','Финансы'
        elif 'дата приёмки' in normalized:key,section='received_at','Приёмка'
        else:return
        self.tabs.show_section(section)
        field=self.fields[key]
        self.mark_invalid(field,True);field.setFocus();self.body_scroll.ensureWidgetVisible(field)
    def with_saved(self,fn):
        if self.dirty:self.save(fn)
        else:fn()
    def mutate(self,fn):
        s=self.store;key=self.key
        self.workspace.run(lambda:(fn(),s.snapshot(key))[1],self.install)
    def selected(self,key):
        r=(self.items_grid if self.embedded and not key else self.grids[key]).selected()
        if not r:QMessageBox.information(self,'Service','Выберите строку')
        return r
    def item(self,kind,edit=False):
        row=self.selected(kind) if edit else None
        if edit and not row:return
        if row and not kind:kind=row['kind']
        fields=[('name','Наименование *','text'),('description','Описание','long'),('quantity','Количество (до 4 знаков)','text'),('unit','Единица','text'),('price','Цена за единицу, ₽','text'),('notes','Примечание','long')]
        if self.snapshot['estimate_comparison']['approved_estimate_id']:fields.append(('change_reason','Причина изменения согласованного объёма *','long'))
        values={**row,'price':amount(row['price_cents']) if row.get('price_known',True) else ''} if row else {'quantity':'1','unit':'шт.','price':'0'}
        original=next((item for item in self.snapshot['repair_items'] if row and item['id']==row['id']),None)
        from ...service.finance import ITEM_KINDS
        d=FieldsDialog(ITEM_KINDS[kind],fields,values,self)
        def persist(data):
            v={**data,'kind':kind}
            if original:
                from ...service.record_text import preserve_field_edit
                for field in ('name','description','notes'):v[field]=preserve_field_edit(original.get(field,''),values.get(field,''),v[field],field)
            key=row['id'] if row else None;s=self.store;r=self.key
            return s.save_item(r,v,key)
        if self.embedded:return self.persist_form(d,persist)
        if d.exec()==QDialog.DialogCode.Accepted:
            values=d.values()
            self.mutate(lambda:persist(values))
    def delete_item(self,kind):
        row=self.selected(kind)
        if row and confirm(self,'Удалить позицию?'):
            reason=''
            if self.snapshot['estimate_comparison']['approved_estimate_id']:
                reason,ok=QInputDialog.getText(self,'Изменение согласованного объёма','Причина удаления *')
                if not ok:return
            s=self.store;self.mutate(lambda:s.remove_item(row['id'],reason))
    def payment(self,kind=None):
        fields=[('kind','Операция',[('payment','Оплата'),('refund','Возврат')]),('amount','Сумма, ₽','text'),('occurred_at','Дата ГГГГ-ММ-ДД (пусто — сегодня)','text'),('method','Способ (внутренняя запись)','text'),('comment','Примечание','long')]
        if kind:fields=fields[1:]
        title='Учесть оплату' if kind=='payment' else 'Учесть возврат' if kind=='refund' else 'Учёт расчётов — не проведение платежа'
        d=FieldsDialog(title,fields,{'method':'Перевод — запись вручную'},self)
        if self.embedded:
            d.layout().insertWidget(0,text('Запись меняет внутренний расчёт. Банковские операции выполняются отдельно.','muted'))
        request=uuid4().hex;s=self.store;r=self.key
        def persist(v):return s.add_payment(r,v['amount'],kind or v['kind'],v['method'],v['occurred_at'],v['comment'],request)
        if self.embedded:return self.persist_form(d,persist)
        if d.exec()==QDialog.DialogCode.Accepted:
            values=d.values()
            self.mutate(lambda:persist(values))
    def financial_evidence(self):
        t=self.snapshot['totals']
        d=FieldsDialog('Полнота исторических расчётов',[
            ('cost','Стоимость',[('unknown','Неизвестна / неполная'),('known','Проверена полностью')]),
            ('paid','История оплат',[('unknown','Неизвестна / неполная'),('known','Проверена полностью')]),
            ('reason','Кто сверил и на каком основании *','long')],
            {'cost':'known' if t.get('cost_known',True) else 'unknown',
             'paid':'known' if t.get('payments_known',True) else 'unknown'},self)
        revision=self.revision
        def persist(v):return self.store.set_financial_evidence(self.key,v['cost']=='known',v['paid']=='known',v['reason'],expected_revision=revision)
        if self.embedded:return self.persist_form(d,persist)
        if d.exec()==QDialog.DialogCode.Accepted:
            values=d.values()
            self.mutate(lambda:persist(values))

    def persist_form(self,form,write):
        result=[]
        def perform(values):
            write(values)
            result.append(self.store.snapshot(self.key))
        form.persist_with(self.workspace,perform)
        return self.workspace.embed_form(form,lambda _:self.install(result[0]))

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
        if not p:return
        from ...templates import Template
        def checked(template):
            self.template_path.setText(p)
            messages=[f'DOCX проверен. Полей: {len(template.fields)}.']
            messages.extend(f.message for f in template.diagnostics)
            messages.append('Сопоставление полей ремонта проверяется при создании. Оформление проверьте в Word.')
            self.document_status.setText('\n'.join(messages))
        self.workspace.run(lambda:Template.load(p),checked,'Проверяю шаблон…',on_error=lambda error:self.document_status.setText(str(error)))
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

    def check_document(self):
        from ...service.document_readiness import assess
        check=assess(self.snapshot,self.doc_kind.currentData(),self.template_path.text())
        self.refresh_document_profile()
        if check['blocked']:
            fields=', '.join(check['required_missing'] or check['missing'])
            message='Нужно заполнить перед созданием: '+fields
        elif check['neutral']:
            message='Будет использована нейтральная форма. Для документа с реквизитами заполните профиль организации.'
        else:
            message='Данные исполнителя заполнены. После формирования проверьте документ в Word.'
        self.document_status.setText(message)
        self.body_scroll.ensureWidgetVisible(self.document_status)

    def generate(self,open_after=False):
        s=self.store;key=self.key;kind=self.doc_kind.currentData();path=self.template_path.text() or None
        from ...service.document_readiness import assess
        check=assess(self.snapshot,kind,path or '');self.refresh_document_profile()
        if check['blocked']:self.document_status.setText('Документ не создан. Проверьте данные исполнителя и обязательные поля: '+', '.join(check['required_missing'] or check['missing']));return
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
        if self.embedded and hasattr(self,'overview'):
            pinned=event.size().height()>=650
            if pinned and self.overview.parentWidget() is not self:
                self.layout().insertWidget(0,self.overview);self.overview.show()
            elif not pinned and self.overview.parentWidget() is self:
                self.body_scroll.widget().layout().insertWidget(0,self.overview);self.overview.show()
        elif hasattr(self,'finance_strip'):
            self.finance_strip.hide();self.state_frame.hide()


class RepairPage(RepairEditor,QWidget):
    embedded = True

    def request_exit(self, proceed):
        if self.workspace.worker:return
        if not self.dirty:
            proceed()
            return
        prompt=QMessageBox(QMessageBox.Icon.Question,'Несохранённые изменения',
                           'Сохранить правки ремонта перед уходом?',
                           QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,self)
        for kind,label in ((QMessageBox.StandardButton.Save,'Сохранить'),(QMessageBox.StandardButton.Discard,'Уйти без сохранения'),(QMessageBox.StandardButton.Cancel,'Остаться')):
            prompt.button(kind).setText(label)
        prompt.setDefaultButton(QMessageBox.StandardButton.Cancel)
        prompt.setEscapeButton(QMessageBox.StandardButton.Cancel)
        result=prompt.exec()
        if result==QMessageBox.StandardButton.Save:self.save(proceed)
        elif result==QMessageBox.StandardButton.Discard:proceed()


class RepairDialog(RepairEditor,QDialog):
    """Compatibility entry for frozen diagnostics and isolated widget tests."""
