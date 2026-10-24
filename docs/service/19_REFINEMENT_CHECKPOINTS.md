# Core + Service: CP1–CP10, 24.10.2026

Исходный HEAD: `71e65eea031b9c3757e89da9b6ca65bfe1aacad5`; существующая ветка `feature/docflow-lite-service`, Draft PR №5. Оба прикреплённых задания прочитаны полностью и приняты как одно задание. Main `12db5cc1f28ac580b7250fe002e8b3cd80e1f66b`, юридический PR №4 `589069508ff9eaf9709c1a294abe29e1080f7846` не меняются. Только синтетические данные.

| CP | Статус и доказательство |
|---|---|
| CP1 Synchronize + Audit | DONE: HEAD/PR сверены; чистая отдельная копия существующей ветки, без перезаписи прежних файлов. Локально 216 passed +16 subtests, 32,26 с; `pytest tests site/tests --junitxml=...`. Три настоящих Qt-снимка до изменений, обзор и карточка просмотрены. Матрица — `20_REFINEMENT_AUDIT.md`. |
| CP2 Core | NOT DONE |
| CP3 Service | NOT DONE |
| CP4 Reliability | NOT DONE |
| CP5 UI/UX | NOT DONE |
| CP6 DOCX | NOT DONE |
| CP7 Website | NOT DONE |
| CP8 CI | NOT DONE |
| CP9 Portable | NOT DONE |
| CP10 Handoff | NOT DONE |

Предыдущий CI повторно прочитан: application `40039598809`, Chromium `40039598815` — success. Это исходное состояние a2, за новый результат не засчитывается. Владелец сообщил об открытии a2 на Windows и ручном сценарии 0/7500/9670/2170; остальные сценарии не считаются пройденными вручную.

Клиентская адаптация BLOCKED: нет настоящего Excel-журнала, утверждённой гарантии и правил связей номеров/рабочих мест/доступа. Ручная приёмка будущей сборки Windows/Word остаётся NOT VERIFIED до владельца. Merge, Release, production, формы, индексация, аналитика и платежи запрещены этим заданием.
