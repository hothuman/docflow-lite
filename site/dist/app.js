'use strict';
const rows = window.DOCFLOW_DEMO || [];
const records = document.querySelector('#demo-records');
const preview = document.querySelector('#demo-preview');
const status = document.querySelector('#demo-status');
const selector = document.querySelector('#demo-template');
let selected = 0;
function render() {
  if (!rows.length) { status.textContent = 'Демопример недоступен. Скачайте приложение из раздела ниже.'; return; }
  const row = rows[selected];
  records.querySelectorAll('button').forEach((button, i) => {
    button.classList.toggle('selected', i === selected);
    button.setAttribute('aria-pressed', String(i === selected));
  });
  const failed = row.errors.length > 0;
  status.textContent = failed ? 'Запись пропущена. Документы не созданы.' : 'Проверка пройдена. Создано документов: ' + row.documents;
  status.classList.toggle('error', failed);
  selector.disabled = failed;
  preview.textContent = failed ? row.errors.join('\n\n') : row.previews[Number(selector.value)];
}
rows.forEach((row, i) => {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'record';
  const number = document.createElement('span'); number.textContent = row.number;
  const text = document.createElement('span');
  const title = document.createElement('strong'); title.textContent = row.client;
  const subtitle = document.createElement('small'); subtitle.textContent = row.service || 'Услуга не указана';
  text.append(title, subtitle);
  const state = document.createElement('span'); state.className = row.errors.length ? 'invalid' : 'valid'; state.textContent = row.errors.length ? '!' : '✓';
  button.append(number, text, state); button.addEventListener('click', () => { selected = i; render(); }); records.append(button);
});
selector.addEventListener('change', render); render();

