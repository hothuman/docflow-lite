# DocFlow Lite v0.1.1 и Website 2.0 — публикация

**Основной публичный сайт:** https://docflow-lite.pages.dev/
**GitHub:** https://github.com/hothuman/docflow-lite
**Windows Release v0.1.1:** https://github.com/hothuman/docflow-lite/releases/tag/v0.1.1

22 октября 2026 года владелец развернул Website 2.0 на **Cloudflare Pages** через **Direct Upload**. Подтверждены первичная и повторная production-публикации, последняя — с действующим `PUBLIC_SITE_URL`. Владелец проверил главную, демо, FAQ, контакты и скачивание Windows ZIP с публичного сайта. Отдельная внешняя машинная проверка HTTP-ответов 404 и заголовков CDN остаётся открытой.

Предыдущая публикация на Sites — историческая, **не отключена автоматически**. Для новых публичных ссылок используйте исключительно https://docflow-lite.pages.dev/.

## Обновление сайта

Исходные статические файлы находятся в `site/dist/`, воспроизводимая сборка — `site/scripts/build_site.py`, результат — `site/build/` (игнорируется Git). При сборке обязательно указывайте подтверждённый основной URL:

```bash
python3 -m unittest discover -s site/tests -v
PUBLIC_SITE_URL=https://docflow-lite.pages.dev/ ENABLE_INDEXING=0 python3 site/scripts/build_site.py
node --check site/dist/app.js
```

На Windows переменные среды задаются соответствующим синтаксисом PowerShell или cmd. Сборщик выставляет canonical, og:url, og:image; индексация остаётся выключенной (`noindex`, `robots.txt: Disallow: /`, пустой sitemap). Форма заявок остаётся заблокированной, backend не существует.

Cloudflare: **Workers & Pages → docflow-lite → Create deployment → Production**. Загрузите `site/build/` либо ZIP с файлами сборки непосредственно в корне, затем **Save and deploy**. **Не загружайте Windows Portable ZIP** или весь репозиторий. Проект **не связан с GitHub**: merge/push не развёртывают сайт автоматически. Подробности: `site/docs/CLOUDFLARE_PAGES.md`.

Подготовленный ранее необязательный workflow GitHub Pages `.github/workflows/pages.yml` не используется для основного хостинга.

## Что не меняли

- Приложение, исходный код движка и GUI, зависимости, Windows ZIP, тег и Release v0.1.1.
- Telegram @de1grace и адрес rostg2007@gmail.com.
- Бесплатную программу; платная настройка требует отдельного согласования стоимости и условий.

## Открытые вопросы

- Утвердить юридические страницы и обработку данных до запуска формы.
- Проверить на публичном домене HTTP 404, CSP/защитные заголовки и работу на физическом мобильном устройстве.
- Исторический PDF-прайс `site/dist/assets/DocFlow-Lite-Offer.pdf` ещё содержит адрес предыдущего сайта: **его нужно отдельно исправить и повторно загрузить в Cloudflare**, не считать заменённым.
- Старый сайт Sites остаётся опубликованным до отдельного решения владельца.

Исторические проверки версии программы: `docs/AUDIT.md` и `docs/VERIFICATION.md`. Они не заменяют тестирование текущего Cloudflare-развёртывания.
