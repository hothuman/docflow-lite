"""Bounded OOXML reads; no archive extraction, entities or active content."""

import io
import re
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from defusedxml import ElementTree as SafeET

from .errors import DocFlowError

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_MEMBER_BYTES = 30 * 1024 * 1024
MAX_MEMBERS = 2000
BAD_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def read_bounded(path: Path, limit: int = MAX_FILE_BYTES) -> bytes:
    try:
        with path.open("rb") as f:
            data = f.read(limit + 1)
    except OSError as exc:
        raise DocFlowError(f"Не удалось прочитать файл {path.name}: {exc}") from exc
    if len(data) > limit:
        raise DocFlowError(f"Файл {path.name} превышает лимит {limit // 1024 // 1024} МБ")
    return data


def check_archive(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > MAX_MEMBERS or sum(x.file_size for x in infos) > MAX_EXPANDED_BYTES:
                raise DocFlowError("Архив Office превышает допустимый размер после распаковки")
            seen = set()
            for info in infos:
                name = info.filename
                lower = name.lower()
                if name in seen or "\\" in name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                    raise DocFlowError("Некорректные или повторяющиеся пути внутри файла Office")
                seen.add(name)
                if info.flag_bits & 1 or info.file_size > MAX_MEMBER_BYTES:
                    raise DocFlowError("Зашифрованный или слишком большой элемент Office")
                if any(x in lower for x in ("vbaproject", "activex", "/embeddings/", "externallinks/")):
                    raise DocFlowError("Макросы, вложенные объекты и внешние связи не поддерживаются")
                if lower.endswith((".xml", ".rels")):
                    root = SafeET.fromstring(z.read(info), forbid_dtd=True)
                    if lower.endswith(".rels"):
                        for rel in root:
                            if rel.attrib.get("TargetMode", "").lower() == "external":
                                raise DocFlowError("Внешние связи Office запрещены; удалите их из копии шаблона")
    except DocFlowError:
        raise
    except Exception as exc:
        raise DocFlowError("Файл Office повреждён или содержит небезопасный XML") from exc


def safe_name(value: str, fallback: str = "record") -> str:
    value = unicodedata.normalize("NFKC", str(value))
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = "".join(c for c in value if unicodedata.category(c) not in {"Cf", "Cs"})
    value = value.strip(" .")[:64].rstrip(" .") or fallback
    if value.split(".")[0].rstrip(" ").upper() in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = "_" + value
    return value


def csv_safe(value: object) -> str:
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text

