"""Localized display only; persisted dates and integer money stay unchanged."""
from datetime import datetime
from decimal import Decimal,InvalidOperation
from pathlib import Path
from ...service.validation import rub
from ...service.statuses import STATUSES
from ...service.documents import KINDS
STATES={'prepared':'Подготовлена','sent':'Передача отмечена вручную','approved':'Согласована (ручная отметка)','rejected':'Отклонена','withdrawn':'Отозвана'}
KINDS_DISPLAY={**KINDS,'work':'Работа','part':'Запчасть','delivery':'Доставка','other':'Прочие расходы','preliminary':'Предварительная','final':'Окончательная','payment':'Оплата','refund':'Возврат','image':'Фото','video':'Видео','document':'DOCX','organization':'Организация','entrepreneur':'ИП','individual':'Физическое лицо'}
IMPORT_STATES={'ready':'Готово','already_imported':'Уже импортировано','deferred':'Отложено','error':'Ошибка','conflict':'Конфликт','needs_confirmation':'Нужно подтверждение','blocked':'Нужна проверка','new':'Создать новую запись','defer':'Отложить'}
MONEY={'total','paid','balance','debt','price','amount','difference','preliminary_total','final_total'}
def date_text(value):
 if not value:return '—'
 try:
  parsed=datetime.fromisoformat(str(value));return parsed.strftime('%d.%m.%Y %H:%M') if len(str(value))>10 else parsed.strftime('%d.%m.%Y')
 except ValueError:return str(value)
def display(key,row):
 value=row.get(key,'')
 if key in MONEY:
  cents=row.get(key+'_cents',value);return rub(cents) if type(cents) is int else str(value or '—')
 if key in ('status','old_status','new_status'):return row.get('status_display',STATUSES.get(value,(IMPORT_STATES.get(value,value),''))[0]) if key=='status' else STATUSES.get(value,(value,''))[0] or '—'
 if key=='kind':return KINDS_DISPLAY.get(value,value)
 if key in ('state','state_label'):return STATES.get(value,value)
 if key in ('equipment_decision','client_decision'):return IMPORT_STATES.get(value,'Связать с существующей записью' if value and value!='не выбрано' else 'Не выбрано')
 if key=='voided':return 'Исправлена' if value else 'Действует'
 if key=='archived':return 'В архиве' if value else 'Действует'
 if key.endswith('_at'):return date_text(value).split(' ')[0]
 if key in ('path','logo_path'):return Path(str(value)).name if value else '—'
 if key=='quantity':return str(value).replace('.',',')
 return str(value) if value not in ('',None) else '—'
def sort_value(key,row):
 value=row.get(key,'')
 if key in MONEY:return row.get(key+'_cents',value)
 if key=='quantity':
  try:return float(Decimal(str(value)))
  except (InvalidOperation,ValueError):return 0.0
 if key in ('number','equipment_number') and str(value).isdigit():return int(value)
 return value
def audit_text(row,numbers):
 entity,action=row['entity'],row['action'];number=numbers.get(row['entity_id'],'');suffix=(' №'+number) if number else ''
 known={('clients','save'):'Сохранён клиент',('clients','archive'):'Изменён архивный статус клиента',('equipment','save'):'Сохранено оборудование',('equipment','archive'):'Изменён архивный статус оборудования',('repair','create'):'Создан ремонт'+suffix,('repair','save'):'Сохранён ремонт'+suffix,('repair','discount_change'):'Изменена скидка ремонта'+suffix,('item','save'):'Сохранена позиция расходов',('item','remove'):'Удалена позиция расходов',('payment','record'):'Добавлена внутренняя запись расчётов',('payment','void'):'Исправлена внутренняя запись расчётов',('estimate_draft','save'):'Сохранён предварительный черновик'+suffix,('attachment','add'):'Добавлено вложение',('attachment','remove'):'Удалено вложение',('profile','save'):'Сохранён профиль организации',('profile','activate'):'Изменён активный профиль'}
 if entity=='estimate' and action=='freeze':
  parts=row['detail'].split(':');return 'Сохранена '+KINDS_DISPLAY.get(parts[0],'смета').lower()+' смета'+(' №'+parts[1] if len(parts)>1 else '')
 if entity=='estimate' and action.startswith('manual_'):return 'Ручная отметка сметы: '+STATES.get(action[7:],'изменение состояния')
 if entity=='document':return 'Создан DOCX' if action in ('generate','create') else 'Операция с документом'
 if entity in ('import','history_import'):return 'Выполнена операция импорта'
 return known.get((entity,action),'Локальная операция (подробности в диагностике)')
