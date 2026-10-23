# Фактические проверки — 23 октября 2026

Исходный main 12db5cc1f28ac580b7250fe002e8b3cd80e1f66b: 129 tests + 16 subtests на Linux до изменений. Итоговая локальная проверка Python 3.12.14: 176 tests + 16 subtests passed.

## Windows и Linux

[CI 39947489151](https://github.com/hothuman/docflow-lite/actions/runs/39947489151) завершён success для обеих jobs, Python 3.13.16. На каждой платформе JUnit 192 cases (176 тестов + 16 subtests), 0 failures/errors/skipped. Code SHA b9c5377edcde6cbee979062e6e87f97ed74a6505; CI merge checkout 86164b56901dab80435d77022ad8008105baab3f имеет точно то же дерево e151747f41124e32f112576dce36f61f15cca37c. Это не merge в main.

Настоящий Portable извлечён и запущен на Windows Server 2022: обычное видимое окно/закрытие, два frozen Core-прогона с 24 DOCX, XLSX/CSV/профилями; девять frozen Service-проверок. Реальные Qt-диалоги создали клиента, оборудование и ремонт. Дальнейший harness использовал настоящий домен для расчётов/возврата, 5 видов/6 версий DOCX, повторного ремонта, PNG/MP4, backup/restore, перезапуска и возврата в Core. Нативные OS file-dialogs и ручной обход всех кнопок этим не проверены.

Portable SHA256: 2d3507c648da1f1fda76d7763d07ff7e7fe1b552b54d1f5a2347ed0617618e1f.
EXE SHA256: 737f8e820d493fee638bdcd04b761d0dc8314adb43838138058c135ca4c07ecb.
Полученный EXE — AMD64 PE, архив имеет _internal; CRC и все суммы исходного SHA256SUMS проверены.

Повторный [application CI 39949024550](https://github.com/hothuman/docflow-lite/actions/runs/39949024550) после изменения browser-теста также завершил обе jobs success. Runtime-код не менялся.

## Браузер и DOCX

[Chromium CI 39949024477](https://github.com/hothuman/docflow-lite/actions/runs/39949024477) — success: две страницы на 320/360/390/620/768/860/1024/1280 px, без общего overflow, все изображения, FAQ, меню/Escape, keyboard/history, no-JS, выключенная форма и контакты. Демо реально скачано через браузер и побайтно совпало с исходным ZIP. Скрипт проверил отсутствие JS errors, сторонних запросов и POST/другой записи. Четыре снимка и JSON сохраняются в website-service-qa и комплекте QA. Это изолированный HTTP-вывод, не production.

Linux Qt/offscreen: девять сквозных Service-проверок и шесть размеров окна. До отключения рабочей среды отрисованы LibreOffice 12 DOCX, просмотрены все 18 страниц; после исправления таблиц/ширин/заголовков не найдено перекрытий и обрезаний. Это не Microsoft Word. Локальный расширенный демонабор с длинным актом не выдаётся за передаваемый Windows CI проект. В передаваемом CI-проекте количества, SQLite quick_check/FK и SHA файлов проверяются упаковщиком, результат — Service-Verification.json. Два синтетических аппарата из CSV отдельно действительно импортированы во временную базу.

## Публичные загрузки

23.10.2026 около 14:41 МСК получены:
- v0.1.1 Windows ZIP: HTTP 200, 48 776 852 байт, SHA256 c0cac130ec4b39d7d42f0ea6ea1d5f128ff6402c89cc4cb8518bc60403f2a034, CRC OK.
- Демо: HTTP 200, 314 068 байт, SHA256 d93b7b48be7f63dfb5d8d3bc39ea2579d1997ae79c9317ed3e80b4afe77ffd0a, CRC OK, совпадает с файлом репозитория.
- Главная https://docflow-lite.pages.dev/: HTTP 200, прежняя публикация без Service; CSP form-action/connect-src none и noindex сохранены.

Сайт не развёртывался; новые ссылки/скриншоты не объявляются опубликованными. Сообщения/письма не отправлялись; доставляемость email не подтверждалась.

## Исправления и ограничения

Исправлены: перенос строки у переменной в Service-шаблоне, порядок одинаковых дат истории, таблицы/ширины/заголовки DOCX; Windows WinError 32 из-за незакрытого sqlite3.Connection. Добавлен contextlib.closing и проверка настоящего close. Прежняя защита Core сохранена.

Первый browser CI остановился на неверной семантике fieldset.isDisabled; второй — на select после ошибочной демозаписи. Теперь тест проверяет disabled-атрибут и дочерние controls, возвращается к корректной записи перед select. Поведение сайта и защита формы не ослаблялись. Неуспешные прогоны не засчитывались.

Нет физической приёмки Windows 10/11, SmartScreen/подписи, Microsoft Word, точного исходного сложного акта, реального импорта клиентской истории, production, Release, договора/оплаты/приёмки. Итог — alpha для ручной проверки.
