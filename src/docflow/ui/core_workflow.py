"""Four document steps, with source/preview hidden until data exists."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame,QVBoxLayout,QHBoxLayout,QTabWidget,QWidget,QComboBox,QTextBrowser,QLineEdit,QCheckBox,QProgressBar)
from .widgets import card,text,DataView,DataModel,RecordModel

def build_create(w):
    page,layout=w.page()
    w.empty_card,empty=card('Первый комплект документов','Выберите таблицу Excel или CSV. Затем добавьте Word-шаблон — программа подставит значения из каждой строки.')
    empty.addWidget(text('Можно начать с вымышленного примера: в нём уже есть таблица и два шаблона.','muted'));empty.addWidget(w.demo_btn);layout.addWidget(w.empty_card)
    w.source_card,source=card('1. Таблица с данными','Одна строка — один комплект документов. Исходная таблица остаётся без изменений.');layout.addWidget(w.source_card)
    w.data_path=QLineEdit();w.data_path.setReadOnly(True);w.data_path.setAccessibleName('Выбранная таблица');source.addWidget(w.data_path)
    w.load_btn=w.button('Выбрать другую таблицу',w.select_data,'folder');source.addWidget(w.load_btn)
    w.stats=text('Таблица ещё не выбрана','muted');source.addWidget(w.stats)
    w.tabs=QTabWidget();w.tabs.setMinimumHeight(180);source.addWidget(w.tabs)
    w.source_table=DataView();w.data_model=DataModel(w);w.source_table.setModel(w.data_model);w.source_table.setAlternatingRowColors(True);w.source_table.setSelectionBehavior(DataView.SelectionBehavior.SelectRows);w.source_table.setSelectionMode(DataView.SelectionMode.SingleSelection);w.source_table.setWordWrap(False);w.source_table.horizontalHeader().setDefaultSectionSize(155);w.source_table.horizontalHeader().setMinimumSectionSize(75);w.source_table.horizontalHeader().setStretchLastSection(True);w.source_table.selectionModel().currentRowChanged.connect(w._table_row_changed);w.tabs.addTab(w.source_table,'Строки таблицы')
    preview=QWidget();pv=QVBoxLayout(preview);w.row_selector=QComboBox();w.record_model=RecordModel(w);w.row_selector.setModel(w.record_model);w.row_selector.setAccessibleName('Запись для предпросмотра');w.template_selector=QComboBox();w.template_selector.setAccessibleName('Шаблон для предпросмотра')
    for selector in (w.row_selector,w.template_selector):selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);selector.setMinimumContentsLength(12);pv.addWidget(selector)
    w.row_selector.currentIndexChanged.connect(w.update_preview);w.template_selector.currentIndexChanged.connect(w.update_preview);pv.addWidget(text('Текст документа. Оформление проверьте в Word или другом редакторе.','muted'));w.preview_text=QTextBrowser();w.preview_text.setOpenExternalLinks(False);w.preview_text.setAccessibleName('Текстовый предпросмотр документа');pv.addWidget(w.preview_text);w.tabs.addTab(preview,'Пример документа');w.report_text=QTextBrowser();w.report_text.setOpenExternalLinks(False);w.tabs.addTab(w.report_text,'Подробности проверки');layout.addStretch()
    w.template_summary=text('Шаблон ещё не выбран','muted')
    w.options_card,options=card('4. Создание документов','Проверьте папку сохранения. Каждый запуск создаёт новый пакет.');w.options_layout=options
    w.name_selector=QComboBox();w.name_selector.setAccessibleName('Столбец для названий папок');options.addWidget(text('Назвать папки по столбцу (необязательно)','muted'));options.addWidget(w.name_selector)
    w.output_path=QLineEdit(str(Path.home()/'Documents'/'DocFlow Lite'));w.output_path.setAccessibleName('Папка результатов');options.addWidget(text('Куда сохранить','section'));options.addWidget(w.output_path);w.output_btn=w.button('Выбрать папку',w.select_output,'folder');options.addWidget(w.output_btn);w.open_after=QCheckBox('Открыть папку после завершения');options.addWidget(w.open_after)
    w.check_btn=w.button('Проверить все строки ещё раз',w.check_all,'check');options.addWidget(w.check_btn)
    w.progress=QProgressBar();w.progress.setRange(0,100);w.progress.setValue(0);w.progress.setTextVisible(False);options.addWidget(w.progress);w.progress_label=text('Документы ещё не созданы','muted');options.addWidget(w.progress_label)
    w.generate_btn=w.button('Создать документы',w.start_generation,primary=True)
    w.ready_card=QFrame();w.readiness=text('','muted');w.ready_details=text('','muted');w.ready_details.hide()

def build_result(w):
    page,layout=w.page();layout.addWidget(w.options_card)
    w.result_card,body=card('Готовые документы','Результаты предыдущих запусков остаются в своих папках.');layout.addWidget(w.result_card);w.result_summary=text('Документы ещё не созданы','section');body.addWidget(w.result_summary);w.result_path=text('','muted');w.result_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);body.addWidget(w.result_path);w.result_open_btn=w.button('Открыть папку с документами',w.open_result,'folder');w.result_open_btn.setEnabled(False);body.addWidget(w.result_open_btn);w.report_btn=w.button('Открыть технический отчёт',w.open_report);w.report_btn.setEnabled(False);body.addWidget(w.report_btn);w.result_report=QTextBrowser();w.result_report.setMinimumHeight(160);w.result_report.setOpenExternalLinks(False);body.addWidget(w.result_report);layout.addStretch()

def readiness(w,valid,message):
    loaded=bool(w.table);w.empty_card.setVisible(not loaded);w.source_card.setVisible(loaded);w.result_card.setVisible(bool(w.last_result))
    checked=w._full_check is not None and w._full_check[0]==w.validation_signature()
    states=[loaded,bool(w.active_templates()),checked,bool(w.last_result)]
    for i,(b,complete) in enumerate(zip(w.route_buttons,states)):
        b.setProperty('complete',complete);b.setChecked(w.pages.currentIndex()==i);b.setEnabled(not w._busy);b.style().unpolish(b);b.style().polish(b);b.setToolTip('Готово' if complete else 'Ещё не завершено')
    page=w.pages.currentIndex();w.core_next.setVisible(page<3);w.generate_btn.setVisible(page==3 and w.cancel_btn.isHidden())
    title=('Выбрать таблицу' if not loaded else 'К шаблонам →','Добавить шаблон Word' if not w.active_templates() else 'К проверке полей →','Проверить все строки' if not checked else 'К созданию документов →')[min(page,2)]
    w.core_next.setText(title);w.core_next.setEnabled(not w._busy and (page!=2 or valid));w.generate_btn.setEnabled(valid and not w._busy)
    state=('Таблица не выбрана' if not loaded else f'Таблица: {len(w.table.records)} строк')+' · '+('Шаблон не выбран' if not w.active_templates() else f'Шаблонов: {len(w.active_templates())}')
    w.core_state.setText(state)
    feedback=(f'Все {w._full_check[2]} строк проверены. С ошибками: {w._full_check[1]}.' if checked else 'Поля связаны. Все строки ещё не проверены.' if valid else message)
    w.mapping_feedback.setText(feedback);w.readiness.setText(feedback)

def next_step(w):
    page=w.pages.currentIndex()
    if page==0:
        if w.table:w.navigate(1)
        else:w.select_data()
    elif page==1:
        if w.active_templates():w.navigate(2)
        else:w.select_templates()
    elif page==2:
        if w._full_check and w._full_check[0]==w.validation_signature():w.navigate(3)
        else:w.check_all()
