"""File exchange only: preview, explicit commit and independent quote snapshots."""
import json
from threading import Event
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLabel,QLineEdit,QComboBox,QCheckBox,QTabWidget,QWidget,QScrollArea,QFileDialog,QProgressDialog,QInputDialog,QMessageBox,QPlainTextEdit)
from ...service import catalog as api
from ...service.catalog_loader import parse_file
from ...service.validation import ServiceError,rub
from .forms import fit_dialog,FieldsDialog
from .widgets import Grid,button
from ..flow import FlowLayout

STATES={'new':'Новая','update':'Обновление','unchanged':'Без изменений','conflict':'Конфликт','error':'Ошибка'}

def catalog_rows(store,query=''):
    return [{**x,'id':str(i),'price_text':rub(x['price_cents']) if x['price_cents'] is not None and x['currency']=='RUB' else (f"{x['price_cents']//100}.{x['price_cents']%100:02d} "+x['currency'] if x['price_cents'] is not None else 'Не указана')} for i,x in enumerate(api.search(store,query))]

class CatalogDialog(QDialog):
    def __init__(self,workspace):
        super().__init__(workspace);self.workspace=workspace;self.store=workspace.store;self.parsed=None;self.plan=None;self.path='';self.setWindowTitle('Каталог — файловая выгрузка');fit_dialog(self,1000,720)
        outer=QVBoxLayout(self);note=QLabel('Локальный XLSX / CSV, без подключения к 1С. Каталог не ведёт склад и не меняет прежние сметы. Для старого проекта используйте отдельную обновлённую копию.');note.setWordWrap(True);outer.addWidget(note)
        tabs=QTabWidget();self.tabs=tabs;outer.addWidget(tabs,1);browse=QWidget();view=QVBoxLayout(browse);self.query=QLineEdit();self.query.setPlaceholderText('Поиск по названию, артикулу, группе');self.query.setAccessibleName('Поиск в каталоге');view.addWidget(self.query)
        self.grid=Grid([('sku','Артикул'),('name','Название'),('group','Группа'),('unit','Ед.'),('price_text','Цена источника'),('source','Источник')]);view.addWidget(self.grid);self.query.textChanged.connect(self.refresh);tabs.addTab(browse,'Каталог')
        page=QWidget();layout=QVBoxLayout(page);body=QWidget();form=QFormLayout(body);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);layout.addWidget(body)
        self.file_label=QLabel('Файл не выбран');self.file_label.setWordWrap(True);form.addRow(self.file_label);button(form,'Выбрать XLSX / CSV',self.choose)
        self.source=QLineEdit();self.source.setPlaceholderText('Постоянное имя источника, например Учебный каталог');form.addRow('Источник *',self.source)
        self.sheet=QComboBox();form.addRow('Лист',self.sheet);self.encoding=QComboBox();self.encoding.addItems(['auto','utf-8-sig','cp1251']);form.addRow('Кодировка CSV',self.encoding)
        self.key=QComboBox();self.key.addItem('Внешний код (точное совпадение)','external_id');self.key.addItem('Внутренний артикул (точное совпадение)','sku');form.addRow('Устойчивый ключ',self.key)
        self.key.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.key.setMinimumContentsLength(12)
        self.currency=QLineEdit();self.currency.setMaxLength(3);self.currency.setPlaceholderText('Пусто, если валюта в файле');form.addRow('Явная валюта по умолчанию',self.currency)
        self.prices=QCheckBox('Обновлять цены каталога');form.addRow(self.prices)
        price_note=QLabel('Прежние сметы и документы сохранят свои цены.');price_note.setWordWrap(True);form.addRow(price_note)
        self.profile=QComboBox();form.addRow('Профиль',self.profile);bar=FlowLayout();form.addRow(bar);button(bar,'Загрузить профиль',self.load_profile);button(bar,'Сохранить профиль',self.save_profile);button(bar,'Перечитать файл / лист',self.read)
        self.mapping={}
        for key,label in api.LABELS.items():
            combo=QComboBox();combo.addItem('Не переносить','');combo.setAccessibleName(label);form.addRow(label,combo);self.mapping[key]=combo;combo.currentIndexChanged.connect(self.invalidate)
        self.preview_grid=Grid([('line','Строка'),('state_label','Решение'),('key','Код'),('name','Название'),('reason','Причина')]);self.preview_grid.setMinimumHeight(180);self.preview_grid.setMaximumHeight(350);self.preview_grid.openRequested.connect(self.details);self.preview_grid.doubleClicked.connect(self.details);layout.addWidget(self.preview_grid,1)
        self.summary=QLabel('Выберите файл, сопоставьте колонки и проверьте изменения.');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.only_problems=QCheckBox('Показать только ошибки и конфликты');self.only_problems.toggled.connect(self.install_preview);layout.addWidget(self.only_problems)
        self.skip=QCheckBox('Пропустить ошибки и конфликты');layout.addWidget(self.skip)
        skip_note=QLabel('Будут применены только допустимые строки. Ошибки и конфликты останутся в отчёте.');skip_note.setWordWrap(True);layout.addWidget(skip_note)
        bar=FlowLayout();layout.addLayout(bar);self.preview_button=button(bar,'Проверить изменения',self.preview);self.apply_button=button(bar,'Применить проверенные изменения',self.apply,primary=True);self.apply_button.setEnabled(False)
        self.import_scroll=QScrollArea();self.import_scroll.setWidgetResizable(True);self.import_scroll.setWidget(page);tabs.addTab(self.import_scroll,'Импорт и сопоставление');self.report=QPlainTextEdit();self.report.setReadOnly(True);tabs.addTab(self.report,'Отчёт');button(outer,'Закрыть',self.reject)
        for w in (self.source,self.currency):w.textChanged.connect(self.invalidate)
        for w in (self.key,self.sheet,self.encoding):w.currentIndexChanged.connect(self.invalidate)
        self.prices.toggled.connect(self.invalidate);self.reload_profiles();self.refresh()
        for label in self.findChildren(QLabel):label.setTextFormat(Qt.TextFormat.PlainText)
    def refresh(self,*args):
        self.grid.install(catalog_rows(self.store,self.query.text()))
        if hasattr(self,'report'):self.report.setPlainText('\n\n'.join(self.report_text(x) for x in api.import_history(self.store)) or 'Импортов пока нет. Здесь появятся последние 20 отчётов.')
    @staticmethod
    def report_text(entry):
        report=entry['report'];return f"Импорт №{entry['id']} · {entry['created_at']}\nИсточник: {entry['source']}\nФайл: {report['file_name']}\nSHA256: {entry['file_sha256']}\n"+'\n'.join(f'{STATES[k]}: {v}' for k,v in report['counts'].items())+'\nЯвно пропущено: '+str(report['skipped'])
    def invalidate(self,*args):
        self.plan=None
        if hasattr(self,'apply_button'):self.apply_button.setEnabled(False);self.summary.setText('Настройки изменились. Выполните проверку заново.')
    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,'Локальная выгрузка','','XLSX / CSV (*.xlsx *.csv)')
        if path:self.path=path;self.file_label.setText(path);self.sheet.clear();self.read()
    def work(self,fn,callback,title):
        cancel=Event();progress=QProgressDialog(title,'Отменить',0,0,self.workspace);progress.setMinimumDuration(0);progress.setWindowModality(Qt.WindowModality.NonModal);progress.canceled.connect(cancel.set);progress.show()
        def done(value):progress.close();callback(value)
        if not self.workspace.run(lambda:fn(cancel),done,title,on_error=lambda _:progress.close()):progress.close()
    def read(self):
        if not self.path:return
        self.invalidate();path=self.path;sheet=self.sheet.currentText();encoding=self.encoding.currentText()
        def loaded(value):
            self.parsed=value;selected=self.sheet.currentText();self.sheet.blockSignals(True);self.sheet.clear();self.sheet.addItems(value['sheets']);self.sheet.setCurrentText(selected or (value['sheets'][0] if value['sheets'] else ''));self.sheet.blockSignals(False)
            for key,combo in self.mapping.items():
                old=getattr(self,'saved_mapping',{}).get(key) or combo.currentData();combo.clear();combo.addItem('Не переносить','')
                for header in value['headers']:combo.addItem(header,header)
                combo.setCurrentIndex(max(0,combo.findData(old or (key if key in value['headers'] else ''))))
            self.summary.setText(f"Прочитано строк: {len(value['rows'])}. Проверьте сопоставление и устойчивый код. Показаны только безопасно прочитанные значения.")
        self.work(lambda cancel:parse_file(path,sheet=sheet or getattr(self,'saved_sheet',''),encoding=encoding,cancel=cancel),loaded,'Читаю локальный файл…')
    def config(self):return dict(source=self.source.text(),mapping={k:v.currentData() for k,v in self.mapping.items() if v.currentData()},key_field=self.key.currentData(),update_prices=self.prices.isChecked(),currency=self.currency.text(),sheet=self.sheet.currentText(),encoding=self.encoding.currentText())
    def preview(self):
        try:
            if not self.parsed:raise ServiceError('Сначала прочитайте файл')
            if self.parsed['encoding']!=self.encoding.currentText() or self.parsed.get('sheet','')!=self.sheet.currentText():raise ServiceError('Перечитайте файл после смены листа или кодировки')
            config=self.config();config.pop('sheet');config.pop('encoding');self.plan=api.preview(self.store,self.parsed,**config);self.install_preview();self.apply_button.setEnabled(True)
        except ServiceError as exc:QMessageBox.warning(self,'Каталог',str(exc))
    def install_preview(self,*args):
        if not self.plan:return
        rows=[{'id':str(i),'line':r.line,'state_label':STATES[r.state],'key':r.key,'name':r.item.get('name',''),'reason':r.reason} for i,r in enumerate(self.plan.rows) if not self.only_problems.isChecked() or r.state in ('error','conflict')];self.preview_grid.install(rows);self.summary.setText(' · '.join(f'{STATES[k]}: {v}' for k,v in self.plan.counts.items())+'\nДвойной щелчок / Enter по строке — все переносимые значения.')
    def details(self,*args):
        selected=self.preview_grid.selected()
        if not selected or not self.plan:return
        row=self.plan.rows[int(selected['id'])];item=row.item;lines=[f'Строка {row.line} · {STATES[row.state]}',row.reason]
        for key,label in api.LABELS.items():
            value=item.get(key,'')
            if key=='price':
                cents=item.get('price_cents');value='Не указана' if cents is None else f'{cents//100}.{cents%100:02d}'
            lines.append(label+': '+str(value))
        dialog=QDialog(self);dialog.setWindowTitle('Проверить переносимые значения');fit_dialog(dialog,650,550);layout=QVBoxLayout(dialog);area=QPlainTextEdit();area.setReadOnly(True);area.setPlainText('\n'.join(lines));layout.addWidget(area);button(layout,'Закрыть',dialog.accept);dialog.exec()
    def apply(self):
        if not self.plan:return
        if QMessageBox.question(self,'Подтвердить импорт',self.summary.text()+'\nПрименить эти изменения? Проблемные строки пропускаются только при явном выборе.')!=QMessageBox.StandardButton.Yes:return
        plan=self.plan;skip=self.skip.isChecked()
        def done(report):self.report.setPlainText('Импорт: '+plan.file_name+'\nИсточник: '+plan.source+'\nSHA256: '+plan.file_sha256+'\n'+'\n'.join(f'{STATES[k]}: {v}' for k,v in report['counts'].items())+'\nЯвно пропущено: '+str(report['skipped']));self.invalidate();self.summary.setText('Импорт завершён. Отчёт сохранён в проекте, сметы не изменены.');self.refresh()
        self.work(lambda cancel:api.apply(self.store,plan,confirmed=True,skip_problems=skip,cancel=cancel),done,'Применяю каталог…')
    def reload_profiles(self):self.profile.clear();self.profile.addItems(api.profiles(self.store))
    def save_profile(self):
        name,ok=QInputDialog.getText(self,'Профиль','Название профиля (без пути к файлу)')
        if ok:
            try:api.save_profile(self.store,name,self.config());self.reload_profiles()
            except ServiceError as exc:QMessageBox.warning(self,'Профиль',str(exc))
    def load_profile(self):
        config=api.profiles(self.store).get(self.profile.currentText())
        if not config:return
        self.saved_mapping=config['mapping'];self.saved_sheet=config['sheet'];self.source.setText(config['source']);self.currency.setText(config['currency']);self.key.setCurrentIndex(max(0,self.key.findData(config['key_field'])));self.prices.setChecked(config['update_prices']);self.encoding.setCurrentText(config['encoding']);self.sheet.setCurrentText(config['sheet'])
        for key,combo in self.mapping.items():combo.setCurrentIndex(max(0,combo.findData(config['mapping'].get(key,''))))
        self.invalidate()
    def reject(self):
        if not self.workspace.worker:super().reject()
    def closeEvent(self,event):
        if self.workspace.worker:event.ignore()
        else:event.accept()

class CatalogPicker(QDialog):
    def __init__(self,store,parent=None):
        super().__init__(parent);self.store=store;self.value=None;fit_dialog(self,860,560);self.setWindowTitle('Добавить из каталога в черновик');layout=QVBoxLayout(self);note=QLabel('Найдите позицию, затем явно подтвердите количество и цену в рублях. Смета сохранит отдельную копию значений.');note.setWordWrap(True);layout.addWidget(note);self.query=QLineEdit();self.query.setPlaceholderText('Название или артикул');self.query.setAccessibleName('Поиск позиции');layout.addWidget(self.query);self.grid=Grid([('sku','Артикул'),('name','Название'),('price_text','Цена источника'),('source','Источник')]);layout.addWidget(self.grid,1);bar=FlowLayout();layout.addLayout(bar);button(bar,'Выбрать и подтвердить',self.choose,primary=True);button(bar,'Отмена',self.reject);self.query.textChanged.connect(self.refresh);self.refresh()
    def refresh(self,*args):self.grid.install(catalog_rows(self.store,self.query.text()))
    def choose(self):
        item=self.grid.selected()
        if not item:return
        price='' if item['currency']!='RUB' or item['price_cents'] is None else f"{item['price_cents']//100}.{item['price_cents']%100:02d}"
        d=FieldsDialog('Подтвердить позицию — цена сметы в ₽',[('kind','Тип *',[('', 'Выберите тип'),('part','Запчасть'),('work','Работа')]),('name','Название *','text'),('quantity','Количество *','text'),('unit','Единица *','text'),('price','Цена в ₽ * (без пересчёта валют)','text')],{**item,'price':price,'quantity':'1'},self)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:
                self.value=quote_line(item,d.values());self.accept()
            except ServiceError as exc:QMessageBox.warning(self,'Позиция',str(exc))

def quote_line(item,values):
    from ...service.estimates import normalize_lines
    if not str(values.get('price','')).strip():raise ServiceError('Укажите цену в рублях явно; неизвестная цена не равна нулю')
    return normalize_lines([{**values,'description':item['description'],'notes':f"Каталог: {item['source']}; код: {item['external_key']}; артикул: {item['sku']}; снимок: {api.digest(item)}"}])[0]
