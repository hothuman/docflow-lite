# Сайт DocFlow

Новая версия сайта использует утверждённую концепцию «Ночной инструмент». Основной адрес: https://docflow-lite.pages.dev/. Хостинг — существующий Cloudflare Pages docflow-lite, Direct Upload. Обычный push не развёртывает production.

Исходники — dist, локальная сборка — build. Команда: python site/scripts/build_site.py. Сборка с подтверждённой загрузкой prerelease выполняется build_release_site.py после проверки реальных GitHub файлов, target и SHA256. До этого preview сохраняет прежнюю действующую загрузку.

Проверки: python -m pytest -q site/tests; node --check site/dist/app.js. Браузер: npm ci в site, npx playwright install chromium, npm run test:browser.

Core и Service бесплатны по условиям программы. Настройка — отдельная услуга, Service оценивается по задаче. Контакты: https://t.me/de1grace и docflow.lite@gmail.com.

Условия оригинального продукта утверждены владельцем; software.html не заменяет проекты условий услуг и политики. Форма, аналитика, платежи и индексация выключены. Нет backend заявок и локального сохранения формы.

PDF услуг обновлён для Core/Service и рабочего email. Его генератор build_offer_pdf.py требует reportlab и Carlito; для обычной статической сборки эти зависимости не нужны. Веб-сборка использует уже проверенный PDF и его хеш.

Публикация и откат: ../docs/OFFICIAL_RELEASE.md и docs/CLOUDFLARE_PAGES.md. Исторические отчёты Website 2.0 не являются проверкой нового deployment.
