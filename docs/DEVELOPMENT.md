# Разработка и проверки

Прочитайте [AGENTS.md](../AGENTS.md). Используйте синтетические данные и отдельную среду. Исходники требуют Python 3.11–3.14; Windows-рецепт закрепляет CPython 3.14.10 x64.

Установите проект: python -m pip install -e ".[gui,dev]". Запуск: python -m docflow.gui.

Основной набор: python -m pytest -q tests site/tests. Сайт: python site/scripts/build_site.py; синтаксис: node --check site/dist/app.js.

На headless Linux задайте QT_QPA_PLATFORM=offscreen и установите библиотеки Qt. Windows CI использует PYTHONUTF8=1. Браузер: в site выполните npm ci, npx playwright install chromium и npm run test:browser.

После изменений обновляйте FILE_HASHES.json: SHA256 исходных файлов без самого манифеста, сред, артефактов и клиентских данных.

scripts/build_windows.ps1 проверяет Python, устанавливает lock с хешами, запускает тесты, собирает PyInstaller onedir, лицензии/исходники зависимостей и выполняет распакованный EXE вне checkout.

tools/qa_layout.py и tools/qa_refinement_ui.py проверяют геометрию и не заменяют визуальный просмотр. Выпуск: [OFFICIAL_RELEASE.md](OFFICIAL_RELEASE.md).

Для изолированной Windows-среды используйте scripts/install_build_python.ps1: официальный NuGet CPython, SHA256 и подпись PSF проверяются, реестр/PATH системы не меняются. Историческая a6 собиралась на 3.13.16/Qt 6.10.2; новый кандидат использует исправления безопасности 3.14.10/Qt 6.12.0.
