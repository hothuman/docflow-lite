# Сайт DocFlow

Новая версия сайта использует утверждённую концепцию «Ночной инструмент». Основной адрес: https://docflow-lite.pages.dev/. Хостинг — существующий Cloudflare Pages docflow-lite, Direct Upload. Обычный push не развёртывает production.

Исходники — dist, локальная сборка — build. Команда: python site/scripts/build_site.py. Для переключения загрузки на 1.0.1 подготовьте манифест окончательной сборки. После публикации immutable Release запустите `python site/scripts/build_release_site.py --manifest <manifest.json> --output <folder>`. Скрипт сверяет тег, коммит и SHA256 загружаемых файлов. Черновик и несовпадение SHA256 блокируют сборку.

Проверки: python -m pytest -q site/tests; node --check site/dist/app.js. Браузер: npm ci в site, npx playwright install chromium, npm run test:browser.

Core и Service бесплатны по условиям программы. Настройка — отдельная услуга, Service оценивается по задаче. Контакты: https://t.me/de1grace и docflow.lite@gmail.com.

Условия оригинального продукта утверждены владельцем; software.html не заменяет проекты условий услуг и политики. Форма, аналитика, платежи и индексация выключены. Нет backend заявок и локального сохранения формы.

PDF услуг обновлён для Core/Service и рабочего email. Его генератор build_offer_pdf.py требует reportlab и Carlito; для обычной статической сборки эти зависимости не нужны. Веб-сборка использует уже проверенный PDF и его хеш.

Публикация и откат: ../docs/OFFICIAL_RELEASE.md и docs/CLOUDFLARE_PAGES.md. Исторические отчёты Website 2.0 не являются проверкой нового deployment.

До публикации 1.0.1 действующая ссылка ведёт на [v1.0.0](https://github.com/hothuman/docflow-lite/releases/tag/v1.0.0). Синтетический браузерный макет `prepare_browser_release_fixture.py --version 1.0.1` проверяет будущую страницу. Он использует тестовые метаданные и предназначен только для QA.
