"""Consistent SQLite online backup plus integrity-checked local file manifest.

No encryption or signatures are claimed. Restore only into a new empty folder.
"""
from pathlib import Path
from contextlib import closing
import hashlib, json, os, sqlite3, tempfile, zipfile, shutil
import sys
from uuid import uuid4
from .attachments import safe_path,digest,MAX_ATTACHMENT
from .database import Database,SCHEMA_VERSION
from .validation import ServiceError,now

MAX_BACKUP=5*1024**3

def _publish_new_tree(stage,destination):
    """Atomic directory publication without replacing a concurrently created target.

    Windows rename refuses existing targets. Linux renameat2(NOREPLACE) supplies
    the same guarantee; ordinary POSIX rename could replace an empty directory.
    Unsupported platforms fail safely before touching the target.
    """
    if os.name=='nt':
        os.rename(stage,destination)
    elif sys.platform.startswith('linux'):
        import ctypes
        libc=ctypes.CDLL(None,use_errno=True)
        rename=getattr(libc,'renameat2',None)
        if rename is None:raise ServiceError('Система не поддерживает безопасное восстановление в новую папку')
        rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        rename.restype=ctypes.c_int
        if rename(-100,os.fsencode(stage),-100,os.fsencode(destination),1)!=0:
            code=ctypes.get_errno();raise OSError(code,os.strerror(code),str(destination))
    else:raise ServiceError('Система не поддерживает безопасное восстановление в новую папку')

def _check_tree(folder):
    db=Database(folder/'service.db')
    with db.connection() as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchall():raise ServiceError('Нарушена целостность резервной базы')
        for table in ('attachments','generated_documents','managed_files'):
            for r in c.execute(f'SELECT path,sha256 FROM {table}'):
                f=safe_path(folder,r['path'])
                if not f.is_file() or digest(f)!=r['sha256']:raise ServiceError('Файл резервной копии отсутствует или изменён')

def create_backup(store,destination):
    destination=Path(destination)
    if destination.exists():raise ServiceError('Резервную копию нельзя перезаписать; выберите новое имя')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name('.'+destination.name+'.'+uuid4().hex+'.tmp')
    with store.lock,tempfile.TemporaryDirectory(prefix='docflow-backup-') as temp:
        stage=Path(temp)
        with store.db.connection() as src,closing(sqlite3.connect(stage/'service.db')) as dst:src.backup(dst)
        files={'service.db':stage/'service.db'}
        with closing(sqlite3.connect(stage/'service.db')) as c:
            c.row_factory=sqlite3.Row
            for table in ('attachments','generated_documents','managed_files'):
                for r in c.execute(f'SELECT path,sha256 FROM {table}'):
                    f=safe_path(store.root,r['path'])
                    if not f.is_file() or digest(f)!=r['sha256']:raise ServiceError('Не удалось включить изменённое или пропавшее вложение')
                    files[r['path']]=f
        # User-edited templates are data too, even if not installed via a profile.
        templates=safe_path(store.root,'templates')
        if templates.exists():
            for f in templates.rglob('*'):
                if f.is_symlink():raise ServiceError('Ссылка среди шаблонов запрещена')
                if f.is_file():files[f.relative_to(store.root).as_posix()]=f
        if len(files)>19999:raise ServiceError('Слишком много файлов для резервной копии')
        if sum(f.stat().st_size for f in files.values())>MAX_BACKUP:raise ServiceError('Резервная копия превышает 5 GiB')
        manifest={'format':'docflow-service-backup-1','schema':SCHEMA_VERSION,'created_at':now(),'files':{n:{'sha256':digest(p),'size':p.stat().st_size} for n,p in files.items()}}
        created=False
        try:
            with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,allowZip64=True) as z:
                for name,path in files.items():z.write(path,name)
                z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            # Check the written bytes too; a concurrent external edit must not produce a false success.
            with zipfile.ZipFile(temporary) as verified:
                for name,meta in manifest['files'].items():
                    h=hashlib.sha256()
                    with verified.open(name) as member:
                        for part in iter(lambda:member.read(1024*1024),b''):h.update(part)
                    if h.hexdigest()!=meta['sha256']:raise ServiceError('Файл изменился во время резервирования')
            # An exclusive destination prevents accidental replacement.
            with temporary.open('rb') as src,destination.open('xb') as dst:
                created=True;shutil.copyfileobj(src,dst)
            return destination
        except Exception:
            if created:destination.unlink(missing_ok=True)
            raise
        finally:temporary.unlink(missing_ok=True)

def restore_backup(archive,destination):
    archive=Path(archive);destination=Path(destination).absolute()
    if destination.exists():raise ServiceError('Восстановление разрешено только в новую папку; текущую базу не заменяем')
    if archive.is_symlink() or archive.stat().st_size>MAX_BACKUP:raise ServiceError('Недопустимый размер резервной копии')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.docflow-restore-',dir=destination.parent) as temp:
        stage=Path(temp)
        try:
            with zipfile.ZipFile(archive) as z:
                infos=z.infolist();names=[x.filename for x in infos]
                if len(infos)>20000 or len(names)!=len(set(names)) or sum(x.file_size for x in infos)>MAX_BACKUP:raise ServiceError('Превышены лимиты или повторяются имена резервной копии')
                if 'manifest.json' not in names or z.getinfo('manifest.json').file_size>5*1024*1024:raise ServiceError('Нет допустимого манифеста')
                manifest=json.loads(z.read('manifest.json'))
                if manifest.get('format')!='docflow-service-backup-1' or manifest.get('schema')>SCHEMA_VERSION:raise ServiceError('Неизвестный формат или новая версия базы')
                files=manifest['files']
                if set(names)!=(set(files)|{'manifest.json'}) or 'service.db' not in files:raise ServiceError('Состав архива не совпадает с манифестом')
                for info in infos:
                    safe_path(stage,info.filename)
                    if info.filename=='manifest.json':continue
                    if (info.external_attr>>16)&0o170000==0o120000:raise ServiceError('Ссылка в архиве запрещена')
                    name=info.filename
                    if name!='service.db' and not name.startswith(('attachments/','generated/','templates/','profiles/')):raise ServiceError('Непредусмотренный файл в архиве')
                    target=safe_path(stage,name);target.parent.mkdir(parents=True,exist_ok=True)
                    h=hashlib.sha256();size=0
                    with z.open(info) as src,target.open('xb') as dst:
                        for part in iter(lambda:src.read(1024*1024),b''):
                            size+=len(part)
                            if size>info.file_size:raise ServiceError('Повреждённое вложение')
                            h.update(part);dst.write(part)
                    if size!=files[name]['size'] or h.hexdigest()!=files[name]['sha256']:raise ServiceError('Контрольная сумма резервной копии не совпала')
            _check_tree(stage)
            # Materialize only after all files and references have passed.
            _publish_new_tree(stage,destination)
            # TemporaryDirectory may clean a now absent directory; this is supported.
            return destination
        except ServiceError:raise
        except (OSError,ValueError,KeyError,zipfile.BadZipFile,RuntimeError,TypeError) as exc:raise ServiceError('Восстановление отменено: повреждённая или недоступная копия') from exc
