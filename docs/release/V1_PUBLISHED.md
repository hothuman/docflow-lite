# DocFlow Lite / Service 1.0.0

**STABLE RELEASED — приложение.** [Release](https://github.com/hothuman/docflow-lite/releases/tag/v1.0.0) опубликован 26.10.2026; draft=false, prerelease=false, immutable=true. [Скачать Portable](https://github.com/hothuman/docflow-lite/releases/download/v1.0.0/DocFlow-Lite-1.0.0-Windows-x64-Portable.zip).

## Точная поставка

Release commit/tag: ea2ed3ad5a515ee32dce611f5bdef177141b5eb8, после merge PR8. [Управляемый выпускной CI 40357372433](https://github.com/hothuman/docflow-lite/actions/runs/40357372433) прошёл Windows/Linux и создал draft. Все 9файлов draft сверены с оригинальными CI assets; после публикации все 9скачаны и побайтово совпали с ними. Тег совпадает с BUILD-INFO, выпуск помечен latest.

Portable SHA256: 7a6aaef4270845f0df3018c9ccc71ff631215cf126c1ab8f04478625fcf18bf1.

EXE SHA256: 6722416d79aa91910734f209be132b9c5d9dd498b8c6b44cdd368ca8edb11c56. Фактическая подпись: NotSigned.

CPython 3.14.10 x64 / Qt-PySide6-Shiboken 6.12.0. Поставка содержит Windows Portable, соответствующие исходники, исходники библиотек, лицензии, SBOM, BUILD-INFO, SHA256SUMS, инструкции и исходный CI-протокол. Опубликованные файлы не меняются последующими коммитами сайта/документации.

## Проверки

По 321 тесту +20 подтестов в Windows/Linux CI, без ошибок/пропусков. Оригинальный main EXE локально на Windows 11 build 26200 вне checkout/системного Python: два обычных запуска/закрытия, 24 Core DOCX, отмена 5000 строк/повтор, Service /90 геометрических случаев, копия/восстановление и upgrade синтетической a6. Исходный a6 backup сохранил SHA; 4 Qt source-архива проверены отдельно. Локальный отчёт не заменяет оригинальный WINDOWS-CI-RESULTS.

Владелец сообщил о приёмке RC1 в Windows и Word без замечаний; версии среды не указаны. Агент ранее просмотрел 12 документов /24 страницы в LibreOffice 26.8.1.1; Word агентом не проверен. В итоговой 1.0 принятый движок/шаблоны не переписаны. Новый main EXE проверен отдельно, приёмка владельцем нового SHA не выдумывается.

## Сайт и хранение

Основной адрес: https://docflow-lite.pages.dev/. Публикационный сайт собирается только после реальной проверки immutable Release/tag/размеров/скачанных SHA. Версия и хеши развёрнутого содержимого доступны в публичном build-info.json. Снимки для новой поставки получены из настоящего итогового EXE; происхождение — site/docs/SCREENSHOT_PROVENANCE.json.

Постоянный комплект владельца: outputs/DocFlow-1.0.0-Release. Там находятся исходные CI ZIP, 9 файлов выпуска, публично скачанные копии, локальные QA, сайт/архив, резервный снимок и фактический протокол production/deployment. Предыдущий Cloudflare deployment 961d9bd8-eae0-4c49-b84c-a04264469b06 сохранён для отката; проект/хостинг не меняется.

## Отдельный остаток

Коммерческий правовой GO остаётся незакрытым: фактический маршрут данных/канал РФ, условия услуг и вопросы РКН. Публичный выпуск бесплатной программы не утверждает эти процессы. Формы, платежи, аналитика и индексация выключены; PR4 не объединён. Клиентская адаптация не выполнялась. Один оператор/локальная SQLite, без шифрования копий, кассы/банка/сервера; произвольные Word-шаблоны не обещаются.

История RC1: V1_FINAL_REPORT.md. Последующее разрешение владельца: V1_PUBLICATION_AUTHORIZATION.md. Актуальные обязательные решения: ../legal/V1_OWNER_DECISIONS.md.

## Выполненное production-размещение

После зелёных application40361424897 и website40361424603 объединён PR9; website main `aa0d19aafe9a4c2338fd6ab0c27eafb6ee32d9b9`. В существующий Cloudflare Pages Direct Upload загружен архив SHA256 `4d6b05bd8bc550607562d8f071a00b86d63e1f11527bd795155b3f7f39f7582f`, 28 файлов. Production deployment: `8153d353-7b61-4e54-90c1-ff91a1687653`, https://8153d353.docflow-lite.pages.dev/.

На основном HTTPS-адресе прошли 66 проверок: страницы, настоящий 404, редирект index.html, заголовки, noindex, отсутствие форм, PDF/demo и опубликованный Release/SHA. Все 26 публично выдаваемых файлов побайтово соответствуют архиву; два служебных файла Cloudflare проверены по применённым заголовкам/редиректу. Chromium156: 19 сценариев на 320/360/390/620/768/860/1024/1280 px, клавиатура/фокус, без JS, reduced motion, демо/скачивание; script_errors, external_requests, data_writes пусты.

Доказательства: PRODUCTION-CHECKS.json, PRODUCTION-FILE-HASHES.json, QA-Website-Public/browser-checks.json и настоящие снимки в постоянном комплекте. Исходный EXE/Source ZIP остаётся выпуском ea2ed3a; отчётные коммиты после него не подменяют происхождение.
