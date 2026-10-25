"""Rebuild the public one-page service brief; requires reportlab and Carlito fonts."""
from pathlib import Path
import argparse
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

SITE=Path(__file__).resolve().parents[1]

def build(font_dir):
    pdfmetrics.registerFont(TTFont('Body',str(font_dir/'Carlito_Regular.ttf')))
    pdfmetrics.registerFont(TTFont('BodyBold',str(font_dir/'Carlito_Bold.ttf')))
    pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold')
    out=SITE/'dist/assets/DocFlow-Lite-Offer.pdf'
    c=canvas.Canvas(str(out),pagesize=(595.28,841.89),pageCompression=0,invariant=1)
    c.setTitle('DocFlow Core + Service — программа и индивидуальная настройка')
    c.setAuthor('Гапоненко Ростислав Дмитриевич')
    c.setFillColor(HexColor('#081C20'));c.rect(0,777,596,65,fill=1,stroke=0)
    c.setFillColor(HexColor('#C2EF92'));c.setFont('BodyBold',13);c.drawString(42,804,'DOCFLOW / CORE + SERVICE')
    def para(text,x,y,width=511,size=11,bold=False,color='#12241A'):
        style=ParagraphStyle('p',fontName='BodyBold' if bold else 'Body',fontSize=size,leading=size*1.3,textColor=HexColor(color))
        p=Paragraph(text,style);_,height=p.wrap(width,800);p.drawOn(c,x,y-height);return y-height
    y=para('Документы и история ремонта',42,749,size=28,bold=True)
    y=para('Core создаёт DOCX из XLSX/CSV и ваших шаблонов. Service ведёт оборудование, обращения, сметы и документы в локальном проекте.',42,y-14,size=12)
    y=para('Программа бесплатна',42,y-20,size=15,bold=True)
    y=para('Core + Service alpha 0.3.0a6 для Windows x64. Без установки Python, регистрации и платы за каждый документ. Условия использования входят в поставку; индивидуальная настройка оплачивается отдельно.',42,y-7)
    top=y-24
    bottoms=[]
    for x,title,price,body in [(42,'Один простой DOCX','от 5 000 руб.','Одна таблица, согласованный шаблон, сопоставление и проверки. Результат: шаблон, профиль, вымышленный пример, пробные документы и инструкция.'),(310,'До трёх DOCX','от 9 000 руб.','Комплект из общей таблицы, согласованные переменные и проверки. Результат: шаблоны, профиль, проверочные документы и инструкция.')]:
        yy=para(title,x,top,243,size=14,bold=True);yy=para(price,x,yy-6,243,size=23,bold=True);yy=para(body,x,yy-12,243);bottoms.append(yy)
    y=para('Service — оценка по задаче',42,min(bottoms)-25,size=15,bold=True)
    y=para('Профили, документы и перенос согласованного формата. Состав, окончательная сумма и срок определяются после изучения обезличенных материалов.',42,y-7)
    y=para('Сначала описание процесса и проверочный пример',42,y-21,size=15,bold=True)
    y=para('Укажите нужные документы, источник данных и ожидаемый результат. До начала заказа согласуются версии файлов, объём, сроки и приёмка. Исправление обязательных недостатков не ограничивается раундом дополнительных пожеланий.',42,y-7)
    y=para('Границы предварительной версии',42,y-20,size=14,bold=True)
    y=para('Один локальный оператор. Нет банка, кассы, склада и общей сетевой базы. DOCX проверяются в редакторе заказчика; содержание и реквизиты форм утверждаются отдельно. EXE не подписан. Перед обновлением нужна копия проекта.',42,y-7,size=10)
    assert y>140, 'Content overlaps contact block'
    c.setFillColor(HexColor('#12241A'));c.setFont('Body',11)
    c.drawString(42,111,'Telegram: @de1grace');c.linkURL('https://t.me/de1grace',(42,107,200,125),relative=0)
    c.drawString(270,111,'Email: docflow.lite@gmail.com');c.linkURL('mailto:docflow.lite@gmail.com',(270,107,550,125),relative=0)
    c.drawString(42,88,'https://docflow-lite.pages.dev/');c.linkURL('https://docflow-lite.pages.dev/',(42,84,270,101),relative=0)
    para('Предварительное описание услуг, не счёт и не подтверждение заказа. Реальные клиентские данные для первичной оценки не нужны. Редакция 26.10.2026.',42,65,size=8,color='#455351')
    c.save();return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--font-dir',type=Path,required=True);a=p.parse_args();print(build(a.font_dir))
