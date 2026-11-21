# Сайт DocFlow

Текущая редакция **Industrial Contrast** переносит утверждённый владельцем вариант A из [01-industrial-contrast.html](../docs/brand/reference/01-industrial-contrast.html). Графит, насыщенный лайм, тяжёлая типографика, прямоугольные элементы и контрастные бумажные разделы следуют этому референсу. [Дизайн-система и решения](../docs/brand/WEBSITE_REDESIGN.md) сохраняют происхождение графики и сравнение с прежней Industrial Atelier. Приложение эта работа не меняет.

Основной адрес — https://docflow-lite.pages.dev/. Хостинг — существующий Cloudflare Pages docflow-lite, Direct Upload. Обычный push не развёртывает production.

После коммерческого аудита добавлен путь «демо → пакет → результат настройки → обращение». Выбор `#request-one`, `#request-bundle` или `#request-service` сохраняется в обычном URL без формы и хранилища. Каждый пакет имеет подготовленное email-письмо и текст для ручного/явного копирования в Telegram. Сообщения сайт не отправляет. Без JavaScript доступны все три описания, письма и контакты. [Исправления и проверки](../docs/brand/COMMERCIAL_FIXES.md) · [Открытые решения до платного запуска](../docs/brand/COMMERCIAL_OWNER_DECISIONS.md).

Исходники — dist, локальная сборка — build. Команда: python site/scripts/build_site.py. Для переключения загрузки на 1.0.1 подготовьте манифест окончательной сборки. После публикации immutable Release запустите `python site/scripts/build_release_site.py --manifest <manifest.json> --output <folder>`. Скрипт сверяет тег, коммит и SHA256 загружаемых файлов. Черновик и несовпадение SHA256 блокируют сборку.

Проверки — `python -m pytest -q site/tests tests/test_v1_release.py tests/test_release_preparation.py`, `node --check site/dist/app.js`. Браузер — `npm ci --prefix site --ignore-scripts`, установка Chromium через Playwright и `node site/tests/browser_check.cjs`. Локальный Edge можно выбрать через `DOCFLOW_BROWSER_CHANNEL=msedge`. Папку доказательств задаёт `DOCFLOW_SITE_QA_OUTPUT`. Первый экран также сверяется с утверждённым HTML A по цветам, типографике, ширине и форме компонентов. Проверяются восемь страниц, 15 ширин, Axe desktop/mobile, клавиатура, диалог изображения, демо, отсутствие JS, reduced motion и рефлоу 2x. CI запускает текущий публичный вариант и отдельную синтетическую fixture будущего 1.0.1.

Core и Service бесплатны по условиям программы. Настройка — отдельная услуга, Service оценивается по задаче. Контакты: https://t.me/de1grace и docflow.lite@gmail.com.

Условия оригинального продукта утверждены владельцем; software.html не заменяет проекты условий услуг и политики. Форма, аналитика, платежи и индексация выключены. Нет backend заявок и локального сохранения формы.

PDF услуг обновлён для Core/Service и рабочего email. Его генератор build_offer_pdf.py требует reportlab и Carlito; для обычной статической сборки эти зависимости не нужны. Веб-сборка использует уже проверенный PDF и его хеш.

Публикация и откат описаны в [ATELIER_DIRECT_UPLOAD.md](docs/ATELIER_DIRECT_UPLOAD.md). Исторические отчёты Website 2.0 не являются проверкой нового deployment. В сборке сохраняются _headers, _redirects и noindex. Ни приложение, ни сайт этим заданием не публикуются.

До публикации 1.0.1 действующая ссылка ведёт на [v1.0.0](https://github.com/hothuman/docflow-lite/releases/tag/v1.0.0). Синтетический браузерный макет `prepare_browser_release_fixture.py --version 1.0.1` проверяет будущую страницу. Он использует тестовые метаданные и предназначен только для QA.
