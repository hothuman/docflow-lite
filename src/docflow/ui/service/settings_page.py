
"""Grouped entry points for the existing workshop project operations."""
from PySide6.QtWidgets import QComboBox, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from ..flow import ActionBar
from ..widgets import card
from .widgets import button


class SettingsPage(QWidget):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.setAccessibleName('Настройки мастерской')
        layout=QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        self.category=QComboBox()
        self.category.setAccessibleName('Категория настроек')
        layout.addWidget(self.category)
        self.pages=QStackedWidget()
        layout.addWidget(self.pages, 1)

        groups=(
            ('Общие','Быстрые действия на обзоре и справка по приёмке.',[
                ('Настроить стартовые действия',workspace.customize_dashboard),
                ('Быстрый старт: ремонт за 5 минут',workspace.quick_help)]),
            ('Проекты','Открывайте рабочий проект, отдельную копию или учебную базу.',[
                ('Открыть другой проект',workspace.choose_project),('Создать отдельный проект',workspace.new_project),
                ('Открыть папку проекта',workspace.open_folder),('Создать отдельное демо',workspace.demo)]),
            ('Организация','Данные исполнителя и правила нумерации хранятся в профиле организации.',[
                ('Профили организаций',workspace.organization_profiles)]),
            ('Импорт','Используйте локальный Excel или CSV, в том числе экспортированный файл из 1С.',[
                ('Импорт журнала ремонтов из Excel / выгрузки 1С',workspace.import_history),
                ('Импорт оборудования XLSX / CSV',workspace.import_equipment),
                ('Каталог из XLSX / CSV',workspace.open_catalog),
                ('Word → проверочный CSV',workspace.review_docx),('Проверить связи без изменений',workspace.diagnose_links)]),
            ('Документы','Шаблоны и обязательные поля настраиваются в профиле организации. Создание доступно в карточке ремонта.',[
                ('Формы в профиле организации',workspace.organization_profiles),
                ('К документам мастерской',lambda:workspace.tabs.setCurrentIndex(5))]),
            ('Резервные копии','ZIP включает базу и связанные файлы. Восстановление открывает отдельный новый проект.',[
                ('Создать резервную копию',workspace.backup),('Восстановить в новую папку',workspace.restore)]),
            ('О программе','DocFlow Lite обрабатывает данные в локальном проекте. Журнал диагностики хранится на компьютере.',[
                ('История действий / диагностика',workspace.diagnostics)]),
        )
        available_without_project=(workspace.choose_project,workspace.new_project,workspace.demo,workspace.restore)
        for title,description,actions in groups:
            self.category.addItem(title)
            scroll=QScrollArea()
            scroll.setWidgetResizable(True)
            page=QWidget()
            page_layout=QVBoxLayout(page)
            panel,body=card(title,description)
            bar=ActionBar()
            body.addWidget(bar)
            for label,callback in actions:
                control=button(bar,label,callback)
                if callback in available_without_project:
                    workspace._safe_project_buttons.append(control)
            page_layout.addWidget(panel)
            page_layout.addStretch()
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        self.category.currentIndexChanged.connect(self.pages.setCurrentIndex)
        self.category.setCurrentIndex(1)
