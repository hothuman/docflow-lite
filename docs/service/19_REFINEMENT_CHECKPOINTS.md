# Core + Service: CP1–CP10, 24.10.2026

Исходный HEAD: `71e65eea031b9c3757e89da9b6ca65bfe1aacad5`; существующая ветка `feature/docflow-lite-service`, Draft PR №5. Оба прикреплённых задания прочитаны полностью и приняты как одно задание. Main `12db5cc1f28ac580b7250fe002e8b3cd80e1f66b`, юридический PR №4 `589069508ff9eaf9709c1a294abe29e1080f7846` не меняются. Только синтетические данные.

| CP | Статус и доказательство |
|---|---|
| CP1 Synchronize + Audit | DONE: HEAD/PR сверены; чистая отдельная копия существующей ветки, без перезаписи прежних файлов. Локально 216 passed +16 subtests, 32,26 с; `pytest tests site/tests --junitxml=...`. Три настоящих Qt-снимка до изменений, обзор и карточка просмотрены. Матрица — `20_REFINEMENT_AUDIT.md`. |
| CP2 Core | DONE: `test_engine`, `test_gui`, `test_modernization`, `test_refinement_core`, `test_windows_compat`: 106 passed, 10,71 с. Кнопка сохранения профиля использует worker; синхронный API сохранён. Новый неудачный запуск не показывает прежний успех. Реальные XLSX/CSV по одной записи → 2 DOCX, heartbeat при записи профиля. |
| CP3 Service | DONE: 91 passed, 22,37 с. Регрессия 0/7500/9670/2170, обе DOCX/CSV, долг/переплата/возврат, повторное открытие. Исправлена идентичность повторной внутренней оплаты: изменённые способ/основание/дата отклоняются без мутации. Мастер истории, профили, сохранённая принадлежность старых ремонтов остаются зелёными. |
| CP4 Reliability | DONE: 54 passed, 12,00 с. Экспорт exclusive/bounded/SHA, очистка недописанной копии; restore atomic no-replace (Windows rename, Linux renameat2). Негативные проверки malformed/изменённого архива, конкурентной новой папки и disk-full; прежние миграции/FK/commit-failure зелёные. |
| CP5 UI/UX | DONE локальная реализация: общая тема, Dashboard, таблицы, три группы ремонта, сметы, даты, состояния сохранения и ошибки. 22 Service GUI +29 Core GUI passed; 450 Service/150 Core virtual layout cases, контрольные типы окон просмотрены; после финальных правок 90 Service cases повторены. Отчёт `21_UI_UX_REFINEMENT.md`; Windows/Website gates остаются CP7–9. |
| CP6 DOCX | NOT DONE |
| CP7 Website | NOT DONE |
| CP8 CI | NOT DONE |
| CP9 Portable | NOT DONE |
| CP10 Handoff | NOT DONE |

Предыдущий CI повторно прочитан: application `40039598809`, Chromium `40039598815` — success. Это исходное состояние a2, за новый результат не засчитывается. Владелец сообщил об открытии a2 на Windows и ручном сценарии 0/7500/9670/2170; остальные сценарии не считаются пройденными вручную.

Клиентская адаптация BLOCKED: нет настоящего Excel-журнала, утверждённой гарантии и правил связей номеров/рабочих мест/доступа. Ручная приёмка будущей сборки Windows/Word остаётся NOT VERIFIED до владельца. Merge, Release, production, формы, индексация, аналитика и платежи запрещены этим заданием.
