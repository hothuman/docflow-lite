'use strict';
document.documentElement.classList.add('js');
const menuToggle = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#main-nav');
function closeMenu(returnFocus = false) {
  if (!menuToggle || !navigation) return;
  menuToggle.setAttribute('aria-expanded', 'false');
  navigation.classList.remove('is-open');
  if (returnFocus) menuToggle.focus();
}
if (menuToggle && navigation) {
  menuToggle.addEventListener('click', () => {
    const open = menuToggle.getAttribute('aria-expanded') !== 'true';
    menuToggle.setAttribute('aria-expanded', String(open));
    navigation.classList.toggle('is-open', open);
  });
  navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', () => closeMenu()));
  document.addEventListener('click', event => {
    if (!navigation.contains(event.target) && !menuToggle.contains(event.target)) closeMenu();
  });
  matchMedia('(min-width: 861px)').addEventListener('change', () => closeMenu());
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menuToggle.getAttribute('aria-expanded') === 'true') closeMenu(true);
  });
}
// Intake is disabled: no endpoint, persistence, SDK or transmission.
const rows = window.DOCFLOW_DEMO || [];
const records = document.querySelector('#demo-records');
const preview = document.querySelector('#demo-preview');
const status = document.querySelector('#demo-status');
const selector = document.querySelector('#demo-template');
if (records && preview && status && selector) {
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
}

// Genuine product screenshots. The image description follows the selected view.
const screenDialog = document.querySelector('.screen-dialog');
document.querySelectorAll('.showcase-section').forEach(section => {
  const image = section.querySelector('.showcase-image');
  const caption = section.querySelector('.screen-caption');
  if (!image || !caption) return;
  section.querySelectorAll('[data-screen-src]').forEach(button => {
    button.addEventListener('click', () => {
      image.src = button.dataset.screenSrc;
      const stage = document.body.dataset.publicVersion === '1.0.1' ? 'версии' : 'кандидата';
      image.alt = button.dataset.screenLabel + ' · реальный экран ' + stage + ' 1.0.1 на учебных данных';
      caption.textContent = button.dataset.screenLabel;
      section.querySelectorAll('[data-screen-src]').forEach(tab => {
        tab.setAttribute('aria-pressed', String(tab === button));
      });
    });
  });
  const expand = section.querySelector('[data-open-screen]');
  if (expand && screenDialog) expand.addEventListener('click', () => {
    screenDialog.querySelector('img').src = image.src;
    screenDialog.querySelector('img').alt = image.alt;
    screenDialog.querySelector('h2').textContent = caption.textContent;
    screenDialog.showModal();
  });
});
if (screenDialog) {
  screenDialog.querySelector('[data-close-screen]').addEventListener('click', () => screenDialog.close());
  screenDialog.addEventListener('click', event => {
    if (event.target === screenDialog) {
      const bounds = screenDialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) screenDialog.close();
    }
  });
}
// Presentation only: route diagrams never read or transmit user data.
document.querySelectorAll('[data-route]').forEach(panel => {
  const routes = {
    core: [['Таблица XLSX / CSV','Исходные данные','ВХОД'],['Проверка полей','Шаблоны и сопоставление','ПРОЦЕСС'],['Комплект DOCX','Документы в выбранной папке','РЕЗУЛЬТАТ']],
    service: [['Аппарат','Постоянный номер оборудования','ОБЪЕКТ'],['Обращение','Работы, сметы и ручные отметки','РЕМОНТ'],['История и документы','Каждое обращение сохраняется отдельно','СВЯЗИ']]
  };
  panel.querySelectorAll('[data-route-mode]').forEach(button => button.addEventListener('click', () => {
    const mode = button.dataset.routeMode;
    panel.dataset.route = mode;
    panel.querySelectorAll('[data-route-mode]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    panel.querySelectorAll('.route-stops li').forEach((row,i) => {
      row.querySelector('strong').textContent = routes[mode][i][0];
      row.querySelector('small').textContent = routes[mode][i][1];
      row.querySelector('.route-role').textContent = routes[mode][i][2];
    });
  }));
});
