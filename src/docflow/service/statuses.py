"""Production state never implies payment, acceptance or a customer's signature."""
STATUSES={
 'historical':('Архив · статус не установлен','#a6b7ad'),
 'accepted':('Принято','#e0bc63'), 'diagnostics':('На дефектовке','#e0bc63'),
 'approval':('Ожидает согласования','#df965a'), 'repair':('В ремонте','#e0bc63'),
 'parts':('Ожидает запчастей','#df965a'), 'ready':('Готово к выдаче','#8ab59c'),
 'issued':('Выдано','#8daed2'), 'closed':('Закрыто','#a69fa6'),
 'cancelled':('Отказ / отменено','#a69fa6')}
TERMINAL={'closed','cancelled','issued','historical'}
APPROVALS=('Не согласовано','Ожидает ответа','Согласовано','Отказ')
