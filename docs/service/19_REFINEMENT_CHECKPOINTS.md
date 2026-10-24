> Исторический срез предыдущей итерации. Текущее состояние и приёмка изменений a4: [единый трекер](27_PRODUCT_TRACKER.md) и [краткое руководство](28_QUICK_START.md). Результаты прошлых сборок не переносятся автоматически на a4.

# Core + Service: CP1–CP10, 24.10.2026

Исходный HEAD: `71e65eea031b9c3757e89da9b6ca65bfe1aacad5`; существующая ветка `feature/docflow-lite-service`, Draft PR №5. Оба прикреплённых задания прочитаны полностью и приняты как одно задание. Main `12db5cc1f28ac580b7250fe002e8b3cd80e1f66b`, юридический PR №4 `589069508ff9eaf9709c1a294abe29e1080f7846` не меняются. Только синтетические данные.

| CP | Статус и доказательство |
|---|---|
| CP1 Synchronize + Audit | DONE: HEAD/PR сверены; чистая отдельная копия существующей ветки, без перезаписи прежних файлов. Локально 216 passed +16 subtests, 32,26 с; `pytest tests site/tests --junitxml=...`. Три настоящих Qt-снимка до изменений, обзор и карточка просмотрены. Матрица — `20_REFINEMENT_AUDIT.md`. |
| CP2 Core | DONE: `test_engine`, `test_gui`, `test_modernization`, `test_refinement_core`, `test_windows_compat`: 106 passed, 10,71 с. Кнопка сохранения профиля использует worker; синхронный API сохранён. Новый неудачный запуск не показывает прежний успех. Реальные XLSX/CSV по одной записи → 2 DOCX, heartbeat при записи профиля. |
| CP3 Service | DONE: 91 passed, 22,37 с. Регрессия 0/7500/9670/2170, обе DOCX/CSV, долг/переплата/возврат, повторное открытие. Исправлена идентичность повторной внутренней оплаты: изменённые способ/основание/дата отклоняются без мутации. Мастер истории, профили, сохранённая принадлежность старых ремонтов остаются зелёными. |
| CP4 Reliability | DONE: 54 passed, 12,00 с. Экспорт exclusive/bounded/SHA, очистка недописанной копии; restore atomic no-replace (Windows rename, Linux renameat2). Негативные проверки malformed/изменённого архива, конкурентной новой папки и disk-full; прежние миграции/FK/commit-failure зелёные. |
| CP5 UI/UX | DONE в автоматизированной среде: 450 Service +150 Core при1/1,25/1,5/1,75/2;90 native EXE cases. Windows Aero-footer исправлен ClassicStyle, все5 native footer#0d0f13. Реальные снимки просмотрены;12 open-close-destroy сgc passed. Физический DPI NOT VERIFIED. |
| CP6 DOCX | DONE в доступной среде: новая подборка29 DOCX/63 страницы,14 native Service и4 Core;56 PNG совпали с ранее открытыми,7 открыты заново;5 captions same-page. Нагрузка100/1000 аппаратов,624/6024 ремонтов,103 позиции. Word NOT VERIFIED. |
| CP7 Website | DONE подготовка: Service a3 и два настоящих Qt-снимка, Core v0.1.1 и цены сохранены. 20 offline tests passed; production-сайт 49 реальных HTTPS/headers/404/PDF/demo SHA проверок passed, production не изменён. Новая браузерная приёмка CP8. |
| CP8 CI | DONE: application40131835602 /Chromium40131835607 completed/success наf2c0754. Windows иLinux245+16 каждый,0 failed/skipped; логи иXML сохранены. Chromium8widths, demo browser-downloadSHA,0external/writes/errors. |
| CP9 Portable | DONE для технической приёмки: новая a3 изf2c0754, exactEXE запущен безPython вPATH, Core24DOCX, Service9+5+3,90nativecases. SHA/CRC скачанных архивов сверены; ручной Windows10/11 NOT VERIFIED. |
| CP10 Handoff | DONE локальная подготовка: реальный упаковщик завершился успешно, 80 runtime-файлов побайтово совпали с exact-CI Source; Portable/все ZIP/SHA проверены. Финальная демобаза действительно backup→restore→reopen, quick_check/FK и ссылочные SHA passed. Source/Website/Demo/DOCX/QA/19PNG/отчёт/инструкция подготовлены для передачи; не Release/deploy. |

Предыдущий CI повторно прочитан: application `40039598809`, Chromium `40039598815` — success. Это исходное состояние a2, за новый результат не засчитывается. Владелец сообщил об открытии a2 на Windows и ручном сценарии 0/7500/9670/2170; остальные сценарии не считаются пройденными вручную.

Клиентская адаптация BLOCKED: нет настоящего Excel-журнала, утверждённой гарантии и правил связей номеров/рабочих мест/доступа. Ручная приёмка новой сборки Windows/Word остаётся NOT VERIFIED до владельца. Merge, Release, production, формы, индексация, аналитика и платежи запрещены этим заданием.
