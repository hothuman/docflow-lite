"""Explicit synthetic fixture. Never populates the ordinary user's database."""
from .repository import ServiceStore
from .validation import ServiceError

def seed_demo(root):
    s=ServiceStore(root)
    if s.clients() or s.equipment():raise ServiceError('Демо можно создавать только в пустой отдельной папке')
    c=s.save_client({'name':'Демонстрационная мастерская','kind':'organization','notes':'Вымышленные данные, не реальный заказчик'})
    e=s.save_equipment({'number':'DEMO-001','model':'Тестовая мойка A','manufacturer':'Демо','owner_id':c,'serial':'SYNTH-001'})
    first=s.create_repair(e,'DEMO-R-001','Не включается — вымышленный пример')
    s.save_item(first,{'kind':'work','name':'Диагностика','quantity':'1','price':'1500'})
    s.save_repair(first,{'status':'closed','defects':'Вымышленный дефект для демонстрации'})
    r=s.create_repair(e,'DEMO-R-002','Повторное обращение — вымышленный пример')
    s.save_item(r,{'kind':'work','name':'Настройка узла','quantity':'1.5','price':'1200'})
    s.save_item(r,{'kind':'part','name':'Демонстрационная деталь','quantity':'2','price':'450.25'})
    s.add_payment(r,'1000',comment='Только синтетическая запись. Реальная оплата не проводилась')
    s.save_repair(r,{'status':'parts','defects':'Тестовая неисправность','plan':'Заменить демонстрационную деталь','approval':'Ожидает ответа'})
    # All eight document forms can be tried immediately. These are synthetic
    # prepared versions, never an invented customer approval or real debt.
    from .estimates import save_draft,freeze_estimate
    save_draft(s,r,s.snapshot(r)['repair_items'],comment='Синтетический пример предварительного расчёта')
    freeze_estimate(s,r,'preliminary',prepared_by='Демонстрационный оператор')
    freeze_estimate(s,r,'final',prepared_by='Демонстрационный оператор')
    return {'client':c,'equipment':e,'first_repair':first,'repair':r}
