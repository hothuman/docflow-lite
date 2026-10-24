# Архитектура
`service/database.py`: короткие SQLite-соединения на вызывающий поток, транзакции BEGIN IMMEDIATE, внешние ключи, WAL и миграции. `repository.py`: CRUD, ограничения, аудит, оптимистическая revision. `finance.py`/`validation.py`: Decimal, копейки и проверки. `attachments.py`: типы, безопасные пути, копирование, SHA256. `documents.py`: ограниченное расширение строк и адаптер неизменённого Core Template. `backup.py`: SQLite online backup, manifest и восстановление в новую папку. `importers.py`: явный импорт одной транзакцией.

Qt не выполняет SQL или денежные вычисления в обработчиках. `ui/service/workspace.py` сериализует Job/QThread, доставляет результат в GUI после завершения, блокирует повторные действия и закрытие при записи. `repair_editor.py` управляет формами/несохранёнными изменениями; `models.py`/`widgets.py` используют QAbstractTableModel/QSortFilterProxyModel. Изображения, чтение базы, DOCX, хеши, импорт и backup выполняются вне основного потока.

Service загружается лениво при выборе шестого пункта; прежние пять страниц и CLI Core сохраняются. Пользовательский каталог Windows — LOCALAPPDATA/DocFlowLite/Service, не _internal. Выбранный проект можно заменить на другой только после успешной проверки и получения блокировки. У данных нет облачной синхронизации.

Слои допускают замену repository серверным адаптером в отдельной задаче. Это не доказательство уже работающей сети. Официальные инженерные ориентиры: https://www.sqlite.org/backup.html и https://doc.qt.io/qtforpython-6.10/PySide6/QtCore/QThread.html .
