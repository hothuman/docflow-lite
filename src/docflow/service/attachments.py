"""Validated local media. Generated IDs determine paths, never supplied filenames."""
from pathlib import Path, PurePosixPath
from uuid import uuid4
import hashlib, os, shutil, struct
from ..safety import check_archive,read_bounded
from ..templates import parse,W
from .validation import ServiceError,text,now

MAX_ATTACHMENT=250*1024*1024

def copy_bounded(source,target,limit=MAX_ATTACHMENT):
    """An exclusive bounded copy also handles a source growing during the read."""
    created=False
    try:
        with Path(source).open('rb') as src,Path(target).open('xb') as dst:
            created=True;size=0
            for part in iter(lambda:src.read(1024*1024),b''):
                size+=len(part)
                if size>limit:raise ServiceError('Копируемый файл превышает допустимый размер')
                dst.write(part)
    except Exception:
        if created:Path(target).unlink(missing_ok=True)
        raise

def safe_path(root,relative):
    root=Path(root).absolute();r=PurePosixPath(str(relative))
    if r.is_absolute() or not r.parts or any(x in ('..','.') or ':' in x or '\\' in x for x in r.parts):raise ServiceError('Небезопасный путь')
    target=root.joinpath(*r.parts)
    for p in (target,*target.parents):
        if p.is_symlink():raise ServiceError('Символические ссылки не поддерживаются')
        if p==root:break
    if not target.resolve().is_relative_to(root.resolve()):raise ServiceError('Выход из папки проекта')
    return target

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()

def inspect_file(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ServiceError('Выберите обычный локальный файл')
    size=path.stat().st_size;suffix=path.suffix.lower()
    if not 0<size<=MAX_ATTACHMENT:raise ServiceError('Размер вложения: от 1 байта до 250 MiB')
    with path.open('rb') as f:head=f.read(32)
    if suffix in {'.png','.jpg','.jpeg'}:
        from PySide6.QtGui import QImageReader
        reader=QImageReader(str(path));reader.setAllocationLimit(128)
        fmt=bytes(reader.format()).lower();s=reader.size()
        if fmt not in (b'png',b'jpeg',b'jpg') or s.width()<=0 or s.height()<=0 or s.width()*s.height()>32_000_000 or reader.read().isNull():raise ServiceError('Повреждённое или слишком большое изображение')
        if (suffix=='.png')!=(fmt==b'png'):raise ServiceError('Содержимое не совпадает с расширением изображения')
        return 'image','image/png' if suffix=='.png' else 'image/jpeg'
    if suffix=='.mp4':
        # Validate top-level ISO BMFF boxes and required movie/media sections.
        boxes=[];offset=0
        with path.open('rb') as f:
            while offset<size:
                f.seek(offset);b=f.read(8)
                if len(b)<8:raise ServiceError('Повреждённый MP4')
                length,kind=struct.unpack('>I4s',b);header=8
                if length==1:
                    ext=f.read(8)
                    if len(ext)!=8:raise ServiceError('Повреждённый MP4')
                    length=struct.unpack('>Q',ext)[0];header=16
                if length==0:length=size-offset
                if length<header or offset+length>size:raise ServiceError('Повреждённый MP4')
                if kind==b'ftyp' and length<16:raise ServiceError('Повреждённый заголовок MP4')
                if kind==b'mdat' and length<=header:raise ServiceError('Нет видеоданных MP4')
                if kind==b'moov':
                    if length>16*1024*1024:raise ServiceError('Слишком большой индекс MP4')
                    f.seek(offset+header);movie=f.read(length-header);pos=0;children=[]
                    while pos<len(movie):
                        if len(movie)-pos<8:raise ServiceError('Повреждённый индекс MP4')
                        n,tag=struct.unpack_from('>I4s',movie,pos)
                        if n<8 or pos+n>len(movie):raise ServiceError('Повреждённый индекс MP4')
                        children.append(tag);pos+=n
                    if not {b'mvhd',b'trak'}.issubset(children):raise ServiceError('В MP4 нет дорожки')
                boxes.append(kind);offset+=length
                if len(boxes)>10000:raise ServiceError('Слишком много секций MP4')
        if not {b'ftyp',b'moov',b'mdat'}.issubset(boxes):raise ServiceError('Не найдено содержимое MP4')
        return 'video','video/mp4'
    if suffix=='.docx':
        import io,zipfile
        raw=read_bounded(path);check_archive(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if 'word/document.xml' not in z.namelist():raise ServiceError('Не документ Word')
            for n in z.namelist():
                if n.startswith('word/') and n.endswith('.xml'):
                    root=parse(z.read(n))
                    if any(next(root.iter(W+t),None) is not None for t in ('instrText','fldSimple','fldChar','object','altChunk')):raise ServiceError('Активные поля Word не допускаются во вложениях')
        return 'document','application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    raise ServiceError('Разрешены PNG, JPEG, MP4 и безопасные DOCX')

def add_attachment(store,repair_id,source,comment=''):
    source=Path(source);kind,mime=inspect_file(source);key=uuid4().hex
    with store.lock:
        repair=store.get('repair_orders',repair_id)
        relative=f"attachments/{repair['equipment_id']}/{repair_id}/{key}{source.suffix.lower()}"
        target=safe_path(store.root,relative);target.parent.mkdir(parents=True,exist_ok=True)
        created=False
        try:
            with source.open('rb') as src,target.open('xb') as dst:
                created=True;copied=0
                for part in iter(lambda:src.read(1024*1024),b''):
                    copied+=len(part)
                    if copied>MAX_ATTACHMENT:raise ServiceError('Файл изменился или превышен лимит')
                    dst.write(part)
            inspect_file(target)
            with store.db.connection(True) as c:
                c.execute('INSERT INTO attachments(id,repair_id,kind,name,path,size,mime,sha256,comment,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(key,repair_id,kind,text(source.name,limit=255),relative,target.stat().st_size,mime,digest(target),text(comment),now()))
                store.audit(c,'attachment',key,'add')
            return key
        except Exception:
            if created:target.unlink(missing_ok=True)
            raise

def attachment_path(store,key,document=False):
    item=store.get('generated_documents' if document else 'attachments',key)
    path=safe_path(store.root,item['path'])
    if not path.is_file():raise ServiceError('Файл отсутствует. Восстановите проверенную резервную копию')
    if digest(path)!=item['sha256']:raise ServiceError('Контрольная сумма файла изменилась. Открытие отменено')
    return path

def remove_attachment(store,key):
    with store.lock:
        item=store.get('attachments',key);path=safe_path(store.root,item['path'])
        # Keep the referenced file until the metadata commit succeeds.
        with store.db.connection(True) as c:
            c.execute('DELETE FROM attachments WHERE id=?',(key,));store.audit(c,'attachment',key,'remove',item['name'])
        path.unlink(missing_ok=True)
