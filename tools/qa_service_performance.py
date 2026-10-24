"""Reproducible synthetic scale probes; timings are measurements, not an SLA."""
import argparse,json,platform,sqlite3,time
from pathlib import Path
from docflow.service.repository import ServiceStore
from docflow.service.documents import generate_document


def measure(fn):
 start=time.perf_counter();value=fn();return value,round(time.perf_counter()-start,4)

def dataset(root,count):
 s=ServiceStore(root)
 with s.db.connection(True) as c:
  stamp='2026-10-24T00:00:00+03:00'
  c.execute('INSERT INTO clients(id,kind,name,created_at,updated_at) VALUES(?,?,?,?,?)',('client','organization','Синтетическое нагрузочное предприятие',stamp,stamp))
  c.executemany('INSERT INTO equipment(id,number,manufacturer,model,owner_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',[(f'e{i}',f'SYNTH-{i}','Учебный производитель','Учебная модель','client',stamp,stamp) for i in range(count)])
  repairs=[];items=[]
  for i in range(count):
   for j in range(30 if i==0 else 6):
    key=f'r{i}-{j}';repairs.append((key,f'TEST-{i}-{j}',f'e{i}','client',f'{2023+j%4}-01-{j%28+1:02d}','Учебная жалоба','Учебный дефект','closed',stamp,stamp))
    for k in range(3):items.append((f'i{i}-{j}-{k}',key,('work','part','delivery')[k],f'Учебная позиция {k}','Учебное описание','1','шт.',10000,10000,k))
  c.executemany('INSERT INTO repair_orders(id,number,equipment_id,client_id,received_at,complaint,defects,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',repairs)
  c.executemany('INSERT INTO repair_items(id,repair_id,kind,name,description,quantity,unit,price_cents,total_cents,position) VALUES(?,?,?,?,?,?,?,?,?,?)',items)
  for j in range(100):c.execute('INSERT INTO repair_items(id,repair_id,kind,name,description,quantity,unit,price_cents,total_cents,position) VALUES(?,?,?,?,?,?,?,?,?,?)',(f'large-{j}','r0-0','work',f'Длинная учебная работа {j}','Подробное синтетическое описание без клиентских данных. '*6,'1.125','ч',10025,11278,j+3))
 return s,len(repairs),len(items)+100

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 report={'platform':platform.platform(),'python':platform.python_version(),'synthetic_only':True,'runs':[],'status':'passed'}
 for count in (100,1000):
  s,repairs,items=dataset(args.output/f'data-{count}',count)
  rows,all_time=measure(s.repairs);history,hist_time=measure(lambda:s.repairs(equipment_id='e0'));search,search_time=measure(lambda:s.repairs(query='Учебная позиция 2'));_,dash_time=measure(s.dashboard)
  doc,doc_time=measure(lambda:generate_document(s,'r0-0','combined'))
  assert len(rows)==repairs and len(history)==30 and len(search)==repairs
  assert max(all_time,hist_time,search_time,dash_time,doc_time)<30,'Operation exceeded 30 seconds on this runner'
  from qa_service_gui_performance import probe
  gui=probe(s,repairs,args.output)
  report['runs'].append({'gui':gui,'equipment':count,'repairs':repairs,'items':items,'history_repairs_one_device':30,'journal_seconds':all_time,'history_seconds':hist_time,'search_seconds':search_time,'dashboard_seconds':dash_time,'large_docx_seconds':doc_time,'large_docx_bytes':doc.stat().st_size,'large_docx_rows':103,'docx_path':str(doc)})
 (args.output/'performance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
