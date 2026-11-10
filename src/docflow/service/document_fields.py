"""Optional scalar aliases and required fields on existing local DOCX profiles."""
from ..matching import suggestions
from .validation import ServiceError

FIELDS={
 'repair_number':'Номер обращения','received_date':'Дата приёмки','completed_date':'Дата завершения','issued_date':'Дата выдачи',
 'equipment_number':'Постоянный номер аппарата','equipment_model':'Модель','equipment_serial':'Серийный номер',
 'equipment_manufacturer':'Производитель','client_name':'Заказчик этого ремонта','client_contact':'Контактное лицо заказчика',
 'client_phone':'Телефон заказчика','client_email':'Email заказчика',
 'owner_name':'Собственник оборудования','owner_contact':'Контактное лицо собственника','owner_phone':'Телефон собственника','owner_email':'Email собственника',
 'organization_name':'Название исполнителя','organization_details':'Реквизиты исполнителя','organization_contact':'Контакты исполнителя',
 'warranty_terms':'Условия гарантии из профиля','complaint':'Жалоба','defects':'Диагностика','plan':'План работ','notes':'Примечания',
 'total':'Итоговая стоимость','paid':'Учтённая оплата','balance':'Остаток','discount':'Скидка',
 'work_total':'Стоимость работ','parts_total':'Стоимость запчастей','delivery_total':'Доставка','other_total':'Другие расходы',
 'received_at':'Дата приёмки (исходный формат)','started_at':'Дата начала (исходный формат)',
 'completed_at':'Дата завершения (исходный формат)','issued_at':'Дата выдачи (исходный формат)','started_date':'Дата начала',
 'accessories':'Комплектация при приёмке','condition':'Внешнее состояние','approval':'Ручное согласование',
 'approval_note':'Основание согласования','issued_accessories':'Комплектация при выдаче','handover':'Сведения о выдаче',
 'source_works':'Работы из исторического источника','client_legal_name':'ФИО / наименование заказчика',
 'equipment_kind':'Тип оборудования','equipment_identifiers':'Другие идентификаторы аппарата','status':'Статус ремонта',
 'expenses_total':'Запчасти и другие расходы','approved_preliminary_total':'Согласованный предварительный итог',
 'estimate_difference':'Разница с согласованной сметой','estimate_version':'Версия сметы','estimate_date':'Дата и время сметы',
 'estimate_day':'Дата сметы','estimate_prepared_by':'Смету подготовил','estimate_state':'Ручная отметка сметы',
 'estimate_reason':'Причина новой версии сметы','estimate_comment':'Комментарий сметы',
 'executor_display':'Исполнитель или отметка нейтральной формы','organization_block':'Блок исполнителя',
}


def validate_options(data):
    from .documents import KINDS,ITEM_FIELDS,HISTORY_FIELDS
    aliases=data.get('template_field_mapping',{});required=data.get('template_required_fields',{})
    if not isinstance(aliases,dict) or not isinstance(required,dict) or (set(aliases)|set(required))-KINDS.keys():
        raise ServiceError('Неверная настройка полей документов')
    def name(value):return isinstance(value,str) and len(value)<=100 and value.isidentifier() and value not in ITEM_FIELDS|HISTORY_FIELDS
    for kind,mapping in aliases.items():
        if not isinstance(mapping,dict) or len(mapping)>100:raise ServiceError('Неверный список соответствий шаблона')
        for variable,target in mapping.items():
            if not name(variable) or not isinstance(target,str) or (target and target not in FIELDS):raise ServiceError('Неизвестное поле документа: '+str(variable))
            if variable in FIELDS and variable!=target:raise ServiceError('Стандартное поле нельзя переопределять: '+variable)
    for kind,fields in required.items():
        if not isinstance(fields,list) or len(fields)>100 or any(not name(f) for f in fields) or len(set(fields))!=len(fields):
            raise ServiceError('Неверные обязательные поля шаблона')
        if any(f not in FIELDS and f not in aliases.get(kind,{}) for f in fields):raise ServiceError('Обязательное поле не сопоставлено')
    return {k:dict(v) for k,v in aliases.items()},{k:list(v) for k,v in required.items()}


def propose_fields(variables):
    groups=tuple((key,label) for key,label in FIELDS.items())+(
        ('client_name','Клиент','Заказчик'),('owner_name','Собственник','Владелец'),
        ('repair_number','Номер ремонта','Номер обращения'),('equipment_model','Модель'),
        ('received_date','Дата приёма','Дата приема','Дата приёмки'),
    )
    choices,_=suggestions(FIELDS,variables,alias_groups=groups);result={}
    for field,variable in choices.items():
        matches=[f for f,v in choices.items() if v==variable]
        if len(matches)==1:result[variable]=field
    return result


def configured_values(values,organization,kind):
    result=dict(values)
    for variable,target in organization.get('template_field_mapping',{}).get(kind,{}).items():
        if target and target not in FIELDS:raise ServiceError('Неизвестное поле настройки шаблона: '+str(target))
        if variable in FIELDS and variable!=target:raise ServiceError('Стандартное поле нельзя переопределять: '+variable)
        result[variable]=values.get(target,'')
    missing=[]
    for field in organization.get('template_required_fields',{}).get(kind,[]):
        value=str(result.get(field,'')).strip()
        if not value or not value.strip('_ -') or value.casefold() in ('неизвестно','не определена','не зафиксирован'):
            missing.append(field)
    return result,missing


def readiness_context(snapshot,kind):
    quote=None
    if kind.startswith('estimate_'):
        quote=next((q for q in snapshot['estimates'] if q['kind']==kind.removeprefix('estimate_')),None)
    from .documents import document_values
    organization=(quote['payload'] if quote else snapshot)['profile']
    return organization,quote,document_values(snapshot,quote)
