"""CP4: no partial exports and no replacement of another restore destination."""
from pathlib import Path
import json,zipfile
import pytest
from docflow.service.repository import ServiceStore
from docflow.service.demo import seed_demo
from docflow.service.documents import generate_document
from docflow.service.attachments import export_file,copy_bounded
from docflow.service.backup import create_backup,restore_backup
from docflow.service.validation import ServiceError

@pytest.fixture
def project(tmp_path):
 s=ServiceStore(tmp_path/'source');ids=seed_demo(s.root)
 generate_document(s,ids['repair'],'completion')
 return s,ids,s.documents()[0]

def test_export_is_exclusive_complete_and_failed_write_cleans_own_file(project,tmp_path,monkeypatch):
 s,ids,doc=project;target=tmp_path/'Копия.docx'
 p=export_file(s,doc['id'],target,True);before=p.read_bytes()
 with pytest.raises(FileExistsError):export_file(s,doc['id'],target,True)
 assert target.read_bytes()==before
 original=Path.open
 class Full:
  def __init__(self,stream):self.stream=stream
  def __enter__(self):return self
  def __exit__(self,*args):self.stream.close()
  def write(self,data):self.stream.write(data[:10]);raise OSError('No space left on device')
 failed=tmp_path/'partial.docx'
 def opened(path,*a,**kw):
  stream=original(path,*a,**kw)
  return Full(stream) if path==failed and a and a[0]=='xb' else stream
 monkeypatch.setattr(Path,'open',opened)
 with pytest.raises(OSError):export_file(s,doc['id'],failed,True)
 assert not failed.exists() and s.documents()[0]['id']==doc['id']

def test_export_detects_copy_race_and_removes_result(project,tmp_path,monkeypatch):
 import docflow.service.attachments as files
 s,ids,doc=project;original=files.copy_bounded;target=tmp_path/'race.docx'
 def changed(source,destination,*a,**kw):
  original(source,destination,*a,**kw);Path(destination).write_bytes(b'changed during copy')
 monkeypatch.setattr(files,'copy_bounded',changed)
 with pytest.raises(ServiceError,match='копирования'):export_file(s,doc['id'],target,True)
 assert not target.exists() and (s.root/doc['path']).is_file()

def test_restore_does_not_replace_concurrently_created_empty_directory(project,tmp_path,monkeypatch):
 import docflow.service.backup as backups
 s,ids,doc=project;archive=create_backup(s,tmp_path/'snapshot.zip');destination=tmp_path/'new'
 original=backups._check_tree;identity=[]
 def checked(stage):
  original(stage);destination.mkdir();identity.append(destination.stat().st_ino)
 monkeypatch.setattr(backups,'_check_tree',checked)
 with pytest.raises(ServiceError):restore_backup(archive,destination)
 assert destination.is_dir() and list(destination.iterdir())==[]
 assert destination.stat().st_ino==identity[0]
 assert not list(tmp_path.glob('.docflow-restore-*'))

@pytest.mark.parametrize('manifest',[{}, {'format':'docflow-service-backup-1','schema':'4','files':{}}, {'format':'docflow-service-backup-1','schema':4,'files':[]}])
def test_malformed_manifest_does_not_create_destination(project,tmp_path,manifest):
 archive=tmp_path/'malformed.zip'
 with zipfile.ZipFile(archive,'w') as z:z.writestr('manifest.json',json.dumps(manifest))
 with pytest.raises(ServiceError):restore_backup(archive,tmp_path/'new')
 assert not (tmp_path/'new').exists()

def test_restore_crc_or_manifest_hash_failure_keeps_source(project,tmp_path):
 s,ids,doc=project;archive=create_backup(s,tmp_path/'good.zip');bad=tmp_path/'bad.zip'
 with zipfile.ZipFile(archive) as a,zipfile.ZipFile(bad,'w') as b:
  for name in a.namelist():b.writestr(name,b'corrupt' if name==doc['path'] else a.read(name))
 with pytest.raises(ServiceError):restore_backup(bad,tmp_path/'new')
 assert not (tmp_path/'new').exists() and (s.root/doc['path']).is_file()
