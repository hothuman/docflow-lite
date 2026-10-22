# DocFlow Lite Website 2.0 — Cloudflare Pages

## Реальный статус — 22 октября 2026

- **Основной адрес: https://docflow-lite.pages.dev/**. Владелец успешно создал проект `docflow-lite` и дважды опубликовал Website 2.0 через **Direct Upload**. Повторный deploy использовал архив с действительным публичным адресом.
- По скриншотам владельца проверены главная, демо, FAQ, цены и контакты; скачивание Windows ZIP с нового сайта он подтвердил отдельно.
- PR #1 (`feature/website-v2` → `main`) объединён. Исходники программы, EXE и Release v0.1.1 не затронуты.
- GitHub-интеграция Cloudflare при авторизации выдала ошибку, поэтому текущий проект **не связан с GitHub** и не публикует новые коммиты автоматически.
- Предыдущий Sites-хостинг отдельно не отключён. Форма заявок намеренно заблокирована, индексация отключена, юридические страницы — проекты.

## Повторная публикация Website 2.0

В корне репозитория (Python 3.10+; Node для JS-проверки):

```bash
python3 -m unittest discover -s site/tests -v
PUBLIC_SITE_URL=https://docflow-lite.pages.dev/ ENABLE_INDEXING=0 python3 site/scripts/build_site.py
node --check site/dist/app.js
```

На Windows используйте синтаксис переменных среды PowerShell/cmd. Загрузите содержимое `site/build/` или ZIP **с файлами из корня каталога сборки** в **Workers & Pages → docflow-lite → Create deployment → Production → Save and deploy**. Не создавайте второй Pages-проект, не загружайте ZIP Windows-программы или полный исходный репозиторий.

`PUBLIC_SITE_URL` обновляет canonical, og:url и og:image. `ENABLE_INDEXING=0` сохраняет noindex и запрет индексации в robots. Форма остаётся отключённой независимо от индексации. Не активируйте сбор данных, аналитику, платные интеграции или индексацию без отдельного решения владельца. После Direct Upload переход на Git integration внутри того же Pages-проекта напрямую не поддерживается.

## Проверка после размещения

- Главная, `/privacy.html`, `/terms.html` открываются по HTTPS; случайный неизвестный путь возвращает 404, а не главную с кодом 200.
- CSS, JS, favicon, скриншот, субтитры и видео загружаются. Проверены реальные 320/390 px и десктоп; дополнительно проверьте свой телефон.
- Получены защитные заголовки из `_headers`, включая `form-action 'none'` и `connect-src 'none'`.
- Все три поля формы и submit остаются отключёнными. Нет сохранения и сообщения об отправленной заявке.
- Windows-кнопка открывает существующий GitHub Release ZIP. Реально скачайте его и сравните SHA256: `c0cac130ec4b39d7d42f0ea6ea1d5f128ff6402c89cc4cb8518bc60403f2a034`.
- Демо ZIP скачивается и имеет SHA256 `f7a5153455b2383bf9b6394b66bb053bef9cca398726b32633b2bb7698f4f860`.
- Telegram ведёт на @de1grace, текст заготовки читается; email — rostg2007@gmail.com. Контрольное обращение можно отправить самостоятельно с другого аккаунта; агент от имени владельца его не отправлял.
- Canonical, og:url, og:image и robots/sitemap соответствуют фактически выданному адресу и текущему режиму индексации.
- Старый сайт продолжает работать. Его отключение и смена ссылок обсуждаются отдельно после успешной проверки v2.

Windows ZIP размером около 49 МБ не переносится в Pages: лимит одного статического файла Pages — 25 MiB. Он остаётся в GitHub Release, поэтому ни R2, ни платный хостинг файлов не нужен.

## До включения формы

Нужно подтвердить оператора и его реквизиты, утвердить политику и нужные согласия, проверить основания обработки, локализацию/трансграничную передачу и применимость уведомления РКН, выбрать и проверить место хранения, доступ и сроки удаления. Затем отдельно реализовать обработчик и проверить маршрут тестовой заявки. В текущем проекте обработчика нет. Снятие HTML-блокировки и CSP само по себе не является законным запуском формы.

## Официальные источники

- [Git integration и авторизация GitHub](https://developers.cloudflare.com/pages/get-started/git-integration/)
- [Root directory, build/output, переменные среды](https://developers.cloudflare.com/pages/configuration/build-configuration/)
- [Build image и версии Python](https://developers.cloudflare.com/pages/configuration/build-image/)
- [Защитные заголовки](https://developers.cloudflare.com/pages/configuration/headers/)
- [Free limits: файлы, размеры, сборки](https://developers.cloudflare.com/pages/platform/limits/)
