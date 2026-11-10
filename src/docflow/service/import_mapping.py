"""Journal vocabulary for the same conservative matching used by Core."""
from ..matching import suggestions
from .history_import import HISTORY_FIELDS

ALIASES=(
 ('repair_number','Номер обращения','Номер ремонта','Repair No','Repair number','Order number'),
 ('repair_key','Внешний ID ремонта','Repair ID'),
 ('received_at','Дата приёма','Дата приёмки','Дата приема','Дата','Received date','Intake date'),
 ('equipment_number','Постоянный номер','Постоянный № аппарата','Номер оборудования','Equipment No','Asset number'),
 ('model','Модель','Equipment model'),('serial','Серийный номер','Серийный №','Serial number'),
 ('manufacturer','Производитель','Manufacturer'),
 ('client_key','ID клиента','Код клиента','Customer ID','Client ID'),
 ('client_name','Клиент','Заказчик','Заказчик ремонта','Customer','Client','Requester'),
 ('client_contact','Контактное лицо','Контакт заказчика','Contact person'),
 ('client_phone','Телефон','Телефон заказчика','Phone'),('client_email','Email','Почта заказчика'),
 ('owner_key','ID собственника','Код владельца','Owner ID'),
 ('owner_name','Собственник','Владелец','Собственник оборудования','Owner'),
 ('owner_contact','Контакт собственника','Owner contact'),
 ('owner_phone','Телефон собственника','Телефон владельца','Owner phone'),
 ('owner_email','Email собственника','Owner email'),
 ('complaint','Неисправность','Жалоба','Жалобы','Complaint'),('defects','Дефектовка','Диагностика','Diagnosis'),
 ('plan','План работ','Work plan'),('works','Выполненные работы','Работы','Completed work'),
 ('parts','Запчасти','Детали','Parts'),('work_cost','Стоимость работ','Стоимость услуг','Labour cost'),
 ('parts_cost','Стоимость запчастей','Стоимость деталей','Parts cost'),
 ('final_total','Окончательный итог','Итого','Общая стоимость','Final total'),
 ('paid_amount','Оплачено','Оплата','Paid amount'),('payment_date','Дата оплаты','Payment date'),
 ('status','Статус','Состояние ремонта','Repair status'),('notes','Примечание','Примечания','Notes'),
)


def propose_history(headers):
    labels=tuple((key,label.rstrip(' *')) for key,label in HISTORY_FIELDS.items())
    return suggestions(HISTORY_FIELDS,headers,alias_groups=(*ALIASES,*labels))
