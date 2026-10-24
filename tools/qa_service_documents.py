"""Synthetic deliverable forms, complex template and media for visual acceptance."""
import argparse,json,shutil,sys
from pathlib import Path
from PIL import Image,ImageDraw
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docflow.service.repository import ServiceStore
from docflow.service.demo import seed_demo
from docflow.service.profiles import save_profile
from docflow.service.estimates import save_draft,freeze_estimate,record_event
from docflow.service.attachments import add_attachment
from docflow.service.documents import generate_document,create_templates,KINDS
from docflow.service.backup import create_backup,restore_backup


def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=True)
 media=out/'media';media.mkdir();logo=media/'synthetic-logo.png';im=Image.new('RGB',(420,180),'white');ImageDraw.Draw(im).text((40,65),'DEMO SERVICE',fill='black',font_size=42);im.save(logo)
 s=ServiceStore(out/'project');ids=seed_demo(s.root)
 profile=save_profile(s,{'name':'Синтетический профиль','organization_name':'Учебное предприятие','details':'Демонстрационные данные. Не реальный исполнитель.','number_prefix':'EXAMPLE-'},assets={'logo':logo},logo_rights_confirmed=True,activate=True)
 r=s.create_repair(ids['equipment'],'EXAMPLE-001','Тестовое снижение давления при работе. Синтетический пример.')
 s.save_repair(r,{'defects':'Учебный износ уплотнения и загрязнение контрольного фильтра.','plan':'Проверить узел, заменить учебные детали, выполнить контрольную настройку.','accessories':'Учебный шланг, демонстрационный кабель','condition':'Синтетическое описание внешнего состояния','notes':'Сведения вымышлены и предназначены для проверки программы.','status':'repair'})
 actual=[{'kind':'work','name':'Диагностика учебного аппарата','description':'Проверка комплектности и контрольных параметров без реального оборудования.','quantity':'1.5','unit':'ч','price':'1000.25'}, {'kind':'work','name':'Контрольная настройка','description':'Учебное описание с переносами\nВторая строка описания','quantity':'1','unit':'компл.','price':'800'}, {'kind':'part','name':'Демонстрационное уплотнение','quantity':'2','unit':'шт.','price':'200.10'}, {'kind':'delivery','name':'Доставка в сервис','quantity':'1','unit':'рейс','price':'250'}, {'kind':'delivery','name':'Доставка обратно','quantity':'1','unit':'рейс','price':'250'}, {'kind':'other','name':'Другой согласованный учебный расход','quantity':'1','unit':'компл.','price':'75'}]
 save_draft(s,r,actual[:3],discount='50',comment='Учебный предварительный расчёт без доставки и дополнительного расхода')
 q=freeze_estimate(s,r,'preliminary','Учебный оператор');record_event(s,q,'approved','Учебный оператор','Тестовая ручная отметка для демонстрации. Не согласие реального клиента.')
 for row in actual:s.save_item(r,{**row,'change_reason':'Уточнение учебного состава после предварительного расчёта'})
 s.save_repair(r,{'discount':'50','change_reason':'Учебная согласованная скидка'});s.add_payment(r,'500',comment='Синтетическая запись, не реальная оплата')
 final=freeze_estimate(s,r,'final','Учебный оператор','Добавлены два рейса доставки и согласованный учебный расход')
 choices=[]
 for i,(w,h) in enumerate(((700,340),(260,800))):
  path=media/f'synthetic-equipment-{i}.png';image=Image.new('RGB',(w,h),'#f2f0ed');draw=ImageDraw.Draw(image);draw.rectangle((25,25,w-25,h-25),outline='#873047',width=6);draw.text((35,45),'SYNTHETIC '+str(i+1),fill='black',font_size=25);image.save(path)
  ident=add_attachment(s,r,path,'Учебная схема '+str(i+1));choices.append({'id':ident,'caption':'Вымышленная схема '+str(i+1),'stage':'После осмотра' if i==0 else 'До осмотра'})
 forms=out/'documents';forms.mkdir();templates=create_templates(out/'templates')
 for kind in KINDS:
  path=generate_document(s,r,kind,image_choices=choices if kind=='combined' else None);shutil.copy2(path,forms/(kind+'.docx'))
 # Complex editable form demonstrates merged columns, nested/history table,
 # landscape layout and editable header/footer, without private customer data.
 d=Document();sec=d.sections[0];sec.orientation=WD_ORIENT.LANDSCAPE;sec.page_width=Inches(11.7);sec.page_height=Inches(8.3);sec.left_margin=sec.right_margin=Inches(.55)
 d.styles['Normal'].font.name='Arial'
 for style in ('Title','Heading 1','Heading 2'):
  d.styles[style].font.color.rgb=RGBColor(0,0,0)
  prop=d.styles[style].element.find(qn('w:pPr'))
  if prop is not None:
   for border in list(prop.findall(qn('w:pBdr'))):prop.remove(border)
 d.sections[0].header.paragraphs[0].text='{{organization_name}} · {{organization_contact}}';d.sections[0].footer.paragraphs[0].text='Оборудование {{equipment_number}} · {{repair_number}}'
 d.add_paragraph('Карточка ремонта {{repair_number}}','Title');t=d.add_table(rows=3,cols=6);t.style='Table Grid';t.cell(0,0).merge(t.cell(0,5)).text='{{equipment_model}} · № {{equipment_number}}'
 t.cell(1,0).merge(t.cell(1,2)).text='Заказчик {{client_name}}';t.cell(1,3).merge(t.cell(1,5)).text='Приёмка {{received_at}}'
 t.cell(2,0).merge(t.cell(2,2)).text='Жалоба {{complaint}}';t.cell(2,3).merge(t.cell(2,5)).text='Дефектовка {{defects}}'
 for group,title in [('work','Работы'),('part','Запчасти'),('delivery','Доставка'),('other','Прочие расходы')]:
  d.add_paragraph(title,'Heading 1');table=d.add_table(rows=2,cols=4);table.style='Table Grid'
  for c,v in zip(table.rows[0].cells,['Наименование','Описание','Количество','Стоимость']):c.text=v
  table.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
  table.rows[1]._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
  for cell in table.rows[0].cells:
   shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'ECECF0');cell._tc.get_or_add_tcPr().append(shade)
   for paragraph in cell.paragraphs:paragraph.paragraph_format.keep_with_next=True
  borders=OxmlElement('w:tblBorders')
  for side in ('top','left','bottom','right','insideH','insideV'):
   border=OxmlElement('w:'+side);border.set(qn('w:val'),'single');border.set(qn('w:color'),'D9D9D9');border.set(qn('w:sz'),'4');borders.append(border)
  table._tbl.tblPr.append(borders)
  for c,v in zip(table.rows[1].cells,['[[items:'+group+']]{{name}}','{{item_description}}','{{qty}} {{unit}}','{{sum}}']):c.text=v
 d.add_paragraph('Итого {{total}} · Учтено {{paid}} · Остаток {{balance}}')
 custom=out/'templates/complex-landscape.docx';d.save(custom)
 save_profile(s,{**s.snapshot(r)['profile']},profile,assets={'templates':{'combined':custom}})
 path=generate_document(s,r,'combined',image_choices=[choices[1],choices[0]]);shutil.copy2(path,forms/'complex-landscape-with-images.docx')
 backup=create_backup(s,out/'synthetic.service-backup.zip');restore_backup(backup,out/'restore-verification')
 (out/'examples-info.json').write_text(json.dumps({'synthetic_only':True,'repair':r,'preliminary':q,'final':final,'document_kinds':list(KINDS),'customer_template_acceptance':False,'warranty_period_assigned':False},ensure_ascii=False,indent=2),encoding='utf-8')
 print('Created synthetic documents and verified backup/restore:',len(list(forms.glob('*.docx'))))
if __name__=='__main__':main()
