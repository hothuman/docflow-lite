"""Explicit upgrade into a new project; never migrate the selected original."""
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile

from .attachments import digest
from .backup import MAX_BACKUP, _check_tree, _publish_new_tree
from .database import Database, validate_schema
from .validation import ServiceError


def copy_project_for_upgrade(source, destination):
    source = Path(source).absolute()
    destination = Path(destination).absolute()
    if source.is_symlink() or str(source).startswith('\\\\'):
        raise ServiceError('Выберите обычную локальную папку проекта')
    if destination.exists() or destination.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(destination.resolve()):
        raise ServiceError('Для обновления нужна отдельная новая папка вне исходного проекта')
    if Database.migration_required(source/'service.db') is None:
        raise ServiceError('Обновление этого проекта не требуется')
    wal = source/'service.db-wal'
    if wal.exists() and wal.stat().st_size:
        raise ServiceError('Сначала закройте старую программу: в проекте есть незавершённый журнал SQLite. Исходные данные не изменены')
    files = []
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ServiceError('Ссылка среди файлов проекта: обновление копии отменено')
        if path.is_file() and path.name not in ('.docflow-service.lock', 'service.db-wal', 'service.db-shm'):
            files.append(path)
    if len(files) > 20000 or sum(path.stat().st_size for path in files) > MAX_BACKUP:
        raise ServiceError('Превышен безопасный размер копии проекта')
    original = {path.relative_to(source).as_posix(): digest(path) for path in files}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.docflow-upgrade-', dir=destination.parent) as temp:
        stage = Path(temp)
        for path in files:
            relative = path.relative_to(source)
            if relative.as_posix() == 'service.db':
                # No WAL is ignored: a nonempty WAL is rejected above. Immutable
                # read avoids creating bookkeeping files in the old project.
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)) as src, closing(sqlite3.connect(stage/'service.db')) as dst:
                    validate_schema(src, src.execute('PRAGMA user_version').fetchone()[0])
                    src.backup(dst)
            else:
                target = stage/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        if any(not (source/name).is_file() or digest(source/name) != expected for name, expected in original.items()):
            raise ServiceError('Исходные файлы изменились во время копирования; обновление отменено')
        if wal.exists() and wal.stat().st_size:
            raise ServiceError('Исходный журнал SQLite изменился во время копирования; обновление отменено')
        _check_tree(stage)
        Database(stage/'service.db', allow_upgrade=True)
        _check_tree(stage)
        _publish_new_tree(stage, destination)
    return destination
