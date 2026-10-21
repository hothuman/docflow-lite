# Компоненты Windows portable и лицензии

Приложение использует python-docx 1.2.0, openpyxl 3.1.5, lxml 6.1.3,
defusedxml 0.7.1, PySide6-Essentials/shiboken6 6.10.2, et_xmlfile 2.0.0
и typing_extensions 4.16.0. Windows-рецепт закрепляет CPython 3.13.16 x64,
PyInstaller 6.22.3 и все build/test-зависимости в requirements/windows-x64.lock.
Для каждого выбранного Windows wheel указан SHA256 фактически полученного файла.

## Состав поставки

- python-docx, openpyxl и et_xmlfile: MIT; lxml: BSD и notices включённых
  libxml2/libxslt; defusedxml: PSFL; typing_extensions: PSF-2.0.
- CPython: PSFL и дополнительные notices из LICENSE.txt установленного Python.
- PyInstaller: GPL с исключением для созданных приложений; исходная лицензия
  включается вместе с остальными notices. Само исключение не отменяет лицензий
  библиотек приложения.
- Qt/PySide6/Shiboken: используется вариант LGPLv3, а не платная лицензия Qt.
  Файлы DLL остаются отдельно в `_internal/`; их совместимая замена допускается.
  Обратное исследование для отладки изменений LGPL-библиотек не ограничивается.

scripts/collect_release_licenses.py копирует имеющиеся тексты из реально
установленных пакетов. В Windows wheels PySide6/shiboken6 найден только
коммерческий notice, поэтому полный текст LGPL/GPL и notices Qt дополнительно
получаются из оригинальных исходных архивов Qt 6.10.2 и pyside-setup 6.10.2.
Их официальные URL и SHA256 закреплены в packaging/third-party-sources.json.
Сборка прекращается при несовпадении хеша, отсутствии обязательного текста
лицензии или обнаружении Qt DLL без предусмотренного соответствующего исходника.

В portable находятся licenses/, QT-LGPL-NOTICE.txt, THIRD-PARTY-LICENSES.json
и THIRD-PARTY-SOURCES.json. Полные соответствующие исходники библиотек,
включая их build-файлы, прикладываются отдельным ThirdParty-Sources ZIP к тому же
публичному релизу. Компоненты Qt/PySide6 проектом не изменялись. При дальнейшей
передаче комплекта сохраняйте лицензии и равнодоступные исходники библиотек.

Это техническое описание фактической упаковки, а не юридическое заключение.
Собственная открытая лицензия DocFlow Lite не вводится.

## Проверка и первичные источники

Фактическая среда и версии записываются в BUILD-INFO.json. Результаты запуска
готового EXE — в WINDOWS-CI-RESULTS.json. Полный исходный архив не содержит
Python/Qt DLL: они находятся только в portable-сборке. Исторический аудит
зависимостей до этапа 03 сохранён в docs/AUDIT.md и docs/dependency-metadata.json.
Его результаты не выдаются за свежую проверку нового Windows-комплекта.

- https://pyinstaller.org/en/stable/license.html
- https://doc.qt.io/qtforpython-6/licenses.html
- https://www.qt.io/development/open-source-lgpl-obligations
- https://download.qt.io/official_releases/qt/6.10/6.10.2/submodules/
- https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.2-src/
