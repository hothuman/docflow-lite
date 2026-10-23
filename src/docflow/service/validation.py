"""Bounded domain inputs; prices are integer kopecks, quantities decimal strings."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from ..safety import BAD_XML_CHARS
from ..errors import DocFlowError

class ServiceError(DocFlowError):
    pass

def text(value, name='Поле', required=False, limit=20000):
    value=str(value or '').strip()
    if required and not value: raise ServiceError(f'{name}: заполните значение')
    if len(value)>limit or BAD_XML_CHARS.search(value): raise ServiceError(f'{name}: недопустимый или слишком длинный текст')
    return value

def decimal(value, name, maximum='1000000000000', scale=2):
    try:
        result=Decimal(str(value).replace(',','.'))
        if not result.is_finite() or result<0 or result>Decimal(maximum): raise ValueError()
        if result != result.quantize(Decimal(10) ** -scale): raise ValueError()
        return result
    except (InvalidOperation,ValueError,TypeError):
        raise ServiceError(f'{name}: требуется неотрицательное число, до {scale} знаков после запятой') from None

def money(value): return int(decimal(value,'Сумма')*100)
def quantity(value):
    q=decimal(value,'Количество','1000000000',4)
    if q<=0: raise ServiceError('Количество должно быть больше нуля')
    return str(q)
def line_total(qty, price_cents):
    result=(Decimal(qty)*price_cents).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
    if result>9000000000000000: raise ServiceError('Слишком большая сумма позиции')
    return int(result)
def rub(cents):
    sign='−' if cents<0 else ''
    return sign+f'{abs(cents)//100:,}'.replace(',',' ')+f',{abs(cents)%100:02d} ₽'
def day(value):
    if not value:return ''
    try: return date.fromisoformat(str(value)).isoformat()
    except ValueError: raise ServiceError('Дата должна иметь формат ГГГГ-ММ-ДД') from None

def now(): return datetime.now().astimezone().isoformat(timespec='seconds')
