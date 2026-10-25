> Исторический срез предыдущей итерации. Текущее состояние и приёмка изменений a4: [единый трекер](27_PRODUCT_TRACKER.md) и [краткое руководство](28_QUICK_START.md). Результаты прошлых сборок не переносятся автоматически на a4.

# CP8: фактические CI, 24.10.2026

Первый новый запуск: https://github.com/hothuman/docflow-lite/actions/runs/40089019878 , исходный HEAD 3c86b51b64eff2abf00195a5bde1c2b4ee5bbaa8. Linux success. Website: https://github.com/hothuman/docflow-lite/actions/runs/40089019867 — success; Chromium 156.0.8078.4, восемь ширин 320–1280, две страницы, FAQ, меню/клавиатура, no-JS, реальное браузерное скачивание demo ZIP с SHA256, ноль внешних запросов/записей/JS errors. Шесть новых browser PNG просмотрены.

Windows остановлен до сборки: **1 failed, 243 passed +16 subtests**, 101,28 с. Полный traceback сохранён в QA. `test_real_dialog_dark_paint_and_three_groups`: фиксированная координата (8,8) получила RGB 243/244/246 — ровно цвет текста темы. Диагностика Linux показывает, что в этой координате контейнера находится QLabel «Дата ДД.ММ.ГГГГ»; точка не является гарантированным фоном и зависит от Segoe UI/DejaVu.

Исправлено измерение: для контейнера проверяются открытые участки без дочерних элементов; для пустой нижней строки QTextEdit — фон viewport. Порог <70 сохранён и применяется ко всем выбранным точкам, проверки не отключены. Сохраняются реальные PNG и JSON с прежней точкой, её дочерним виджетом и новыми измерениями на обеих ОС. Локально 12 UI tests passed, 3,20 с, 2105 точек фона контейнера и 71 точка поля. На Windows подтверждение нового измерения ещё PENDING; итоговый успешный CI будет записан после выполнения.

Новый Windows Portable до успешного native self-test не объявляется готовым. Release/Cloudflare/main не изменялись.


## Успешное повторное выполнение

[Application run 40089632829](https://github.com/hothuman/docflow-lite/actions/runs/40089632829) и [Chromium run 40089632847](https://github.com/hothuman/docflow-lite/actions/runs/40089632847) — completed/success, один исходный HEAD `31a70cde3a582cce636ded4fdb575527c3ce10a4`. Windows: 244 passed +16 subtests, 91,021 с; Linux: 244 passed +16 subtests, 50,261 с. Нет skipped/failed. JUnit считает 260 случаев вместе с16 subtests; это не260 отдельных pytest-тестов.

Windows JSON прямо подтвердил: старая точка имела #f3f4f6 и находилась внутри QLabel «Дата ДД.ММ.ГГГГ»; 3597 точек открытого фона дали maximum channel19, 59 точек поля —27. Изменение теста устранило попадание на глиф; приложение и порог темноты не подменялись. Source offscreen PNG Windows не годится для оценки шрифта (квадраты вместо глифов), поэтому читаемость русского текста проверяется на настоящих `windows` PNG нового EXE. Они открыты: кириллица читается, сметы показывают 0 /7500 /9670 /2170.

Новый frozen EXE: нативный плагин Qt `windows`, обычное окно действительно найдено через Win32 и закрыто дважды; Core12 DOCX за каждый запуск; Service9 базовых +5 completion +3 refinement. Импорт 900/101/305/900, четвёртое обращение, профили, обе сметы, фото и backup/restore проверены через реальные Qt-формы. 90 virtual native layout cases passed. Linux дополнительно 450 Service +150 Core layouts при пяти масштабах, включая175/200%. Это виртуальные клиентские размеры, не физический монитор владельца.

Portable SHA256 `9a5ff9fb50d283d69ec0fa8e42dafe5c033ab3e2253bd33d65a46a63d0144356`.
EXE SHA256 `e4707efa88a303820831007d45619ceb82368e517f14044ee220ec46ac32a88f`.
Python3.13.16, Windows Server2022 x64; PyInstaller6.22.3 и pinned wheel hashes. Сборочный merge commit `9707a43ad8dfb70273b4b1f894cb6503380f9d03`. Release artifactZIP125700621 байт, его SHA256 проверен против GitHub API. Внутренние SHA256SUMS и ZIP CRC проверены отдельно.

Ручной тест владельца Windows10/11, диалоги выбора файлов ОС, Microsoft Word и клиентская юридическая форма не заявляются. Сравнение запуска с неизменённым v0.1.1: три чередующихся native samples, медиана0,7164с →0,7066с, без обещаний ускорения/SLA. Сборка a3 — alpha для приёмки. Actions artifacts истекают31.10.2026; точные сроки находятся в provenance JSON. Исходный runtime будет дополнительно побайтово сверен при упаковке с exact-CI Source ZIP.


## Дополнительный нативный визуальный дефект и новый gate

При окончательном просмотре native `refined-layout/import-1280.png` из EXE31a70cd обнаружен белый footer мастера импорта. Причина — QWizard по умолчанию выбирает Aero на Windows и рисует native panel вне общей тёмной QSS. В HistoryWizard явно выбран ClassicStyle, совпадающий с существующим Linux-макетом; бизнес-процесс пяти шагов не меняется.

Добавлена регрессия реального Qt-цвета фона, а `layout_check` записывает wizard_footer_rgb и проверяет тёмный footer во всех размерах, в том числе внутри frozen Windows EXE. Локально новый полный набор245 passed +16 subtests, 49,89с, без skip; 90 layout cases при200% также passed. Новая Windows-сборка и повторный native запуск PENDING на момент этого коммита. Предыдущие результаты выше — история первого кандидата a3, не подтверждение устранения этого дополнительного дефекта.

## Финальная сборка после footer-исправления — SUCCESS

[Application40131835602](https://github.com/hothuman/docflow-lite/actions/runs/40131835602) и [Chromium40131835607](https://github.com/hothuman/docflow-lite/actions/runs/40131835607): completed/success, source `f2c0754857cca7758567771cace16c1e69af5088`, CI merge `4d43a67e6fb979a0af2521f70788273fe323a1b2`. Windows245+16,91,712с; Linux245+16,39,003с,0failed/skipped. Новый exact frozen EXE: Core24DOCX, Service9+5+3,90native layout cases; все5 import-footer#0d0f13. Native PNG открыт — фон тёмный, кириллица читается, кнопки доступны.

Новая Portable SHA256 `a32490ecdb351b50b4b189948dd71432b6dad33014ff4a65b235ce9de25ff854`; EXE `6d9cd8209fa51712e9e03b589f16e06643ad143ad389eef0463e489c83a01113`. Все4 внешних Actions ZIP сверены с API digest/size и CRC. Browser156.0.8078.4:8ширин,2страницы, noJS/menu/FAQ/keyboard, реальный demo-downloadSHA,0JS errors/foreign requests/data writes. Предыдущие SHA и PENDING выше — сохранённая история кандидатов, не финальный результат. Полная передача:25_REFINEMENT_HANDOFF.md.
