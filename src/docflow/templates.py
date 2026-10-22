"""Literal OOXML text substitution. No Jinja engine, eval or code execution."""

import bisect
import copy
import io
import re
import zipfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from lxml import etree as ET
from docx import Document

from .errors import DocFlowError
from .safety import BAD_XML_CHARS, check_archive, read_bounded

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SPACE = "{http://www.w3.org/XML/1998/namespace}space"
TOKEN = re.compile(r"\{\{\s*([^\W\d]\w*)\s*\}\}", re.UNICODE)
STORY = re.compile(r"word/(document|header\d+|footer\d+)\.xml$")


def parse(data: bytes):
    return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False))


def paragraph_nodes(p):
    return [t for t in p.iter(W + "t") if t.text and next(t.iterancestors(W + "p"), None) is p]


def _fields(text: str) -> set[str]:
    rest = TOKEN.sub("", text)
    if any(mark in rest for mark in ("{{", "}}", "{%", "%}", "{#", "#}")):
        raise DocFlowError("Разрешены только переменные {{поле}}. Выражения, циклы и незакрытые скобки запрещены")
    return {m.group(1) for m in TOKEN.finditer(text)}


@dataclass(frozen=True)
class Template:
    path: Path
    raw: bytes
    fields: frozenset[str]

    @classmethod
    def load(cls, path: Path | str):
        path = Path(path)
        if path.suffix.lower() != ".docx":
            raise DocFlowError("Шаблон должен иметь расширение .docx")
        raw = read_bounded(path)
        check_archive(raw)
        fields = set()
        try:
            document = Document(io.BytesIO(raw))
            if document.element.tag != W + "document":
                raise DocFlowError("Неверная структура основного документа Word")
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if "word/document.xml" not in z.namelist():
                    raise DocFlowError("В архиве нет документа Word")
                for name in z.namelist():
                    if not name.startswith("word/") or not name.endswith(".xml"):
                        continue
                    root = parse(z.read(name))
                    if any(next(root.iter(W + tag), None) is not None for tag in ("instrText", "fldSimple", "fldChar", "object", "altChunk")):
                        raise DocFlowError("Поля Word, OLE и altChunk не поддерживаются; используйте обычный текст")
                    all_text = "".join(t.text or "" for t in root.iter(W + "t"))
                    if not STORY.fullmatch(name):
                        if any(m in all_text for m in ("{{", "}}", "{%", "{#")):
                            raise DocFlowError("Переменные поддерживаются в тексте, таблицах и колонтитулах; обнаружена другая часть DOCX")
                        continue
                    part_fields = set()
                    for p in root.iter(W + "p"):
                        text = "".join(t.text for t in paragraph_nodes(p))
                        current = _fields(text)
                        if current and (next(p.iterancestors(W + "txbxContent"), None) is not None or any(next(p.iter(W + tag), None) is not None for tag in ("ins", "del", "br", "tab"))):
                            raise DocFlowError("Переменные в надписях, правках и абзацах с табуляцией/разрывами не поддерживаются")
                        fields.update(current)
                        part_fields.update(current)
                    if _fields(all_text) - part_fields:
                        raise DocFlowError("Переменная находится вне поддерживаемого абзаца")
            if not fields:
                raise DocFlowError("В шаблоне нет переменных вида {{поле}}")
            return cls(path.resolve(), raw, frozenset(fields))
        except DocFlowError:
            raise
        except Exception as exc:
            raise DocFlowError(f"Не удалось прочитать DOCX {path.name}: {exc}") from exc

    def render(self, values: dict[str, str]) -> bytes:
        if self.fields - values.keys():
            raise DocFlowError("Не переданы все переменные шаблона")
        if any(not isinstance(v, str) or BAD_XML_CHARS.search(v) for v in values.values()):
            raise DocFlowError("Подстановка содержит недопустимый текст XML")
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.raw)) as src, zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                data = src.read(info)
                if STORY.fullmatch(info.filename):
                    root = parse(data)
                    for p in root.iter(W + "p"):
                        nodes = paragraph_nodes(p)
                        text = "".join(t.text for t in nodes)
                        offsets, offset = [], 0
                        for node in nodes:
                            offsets.append(offset)
                            offset += len(node.text)
                        for m in reversed(list(TOKEN.finditer(text))):
                            first = bisect.bisect_right(offsets, m.start()) - 1
                            last = bisect.bisect_right(offsets, m.end() - 1) - 1
                            left = nodes[first].text[:m.start() - offsets[first]]
                            right = nodes[last].text[m.end() - offsets[last]:]
                            if first == last:
                                nodes[first].text = left + values[m.group(1)] + right
                            else:
                                nodes[first].text = left + values[m.group(1)]
                                for n in nodes[first + 1:last]:
                                    n.text = ""
                                nodes[last].text = right
                        for node in nodes:
                            self._line_breaks(node)
                    data = ET.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                dst.writestr(info, data)
        return out.getvalue()

    @staticmethod
    def _line_breaks(node):
        text = (node.text or "").replace("\r\n", "\n").replace("\r", "\n")
        chunks = re.split(r"([\n\t])", text)
        node.text = chunks[0]
        node.set(SPACE, "preserve")
        current = node
        for chunk in chunks[1:]:
            if chunk in {"\n", "\t"}:
                added = ET.Element(W + ("br" if chunk == "\n" else "tab"))
            else:
                added = copy.copy(node)
                added.text = chunk
            current.addnext(added)
            current = added

    @cached_property
    def _preview_lines(self) -> tuple[str, ...]:
        """Immutable text plan: preview does not recompress an entire DOCX."""
        lines = []
        with zipfile.ZipFile(io.BytesIO(self.raw)) as z:
            for name in z.namelist():
                if STORY.fullmatch(name):
                    if name != "word/document.xml":
                        lines.append("\n[Колонтитул]")
                    root = parse(z.read(name))
                    for p in root.iter(W + "p"):
                        parts = []
                        for node in p.iter():
                            if node.tag == W + "t":
                                parts.append(node.text or "")
                            elif node.tag in {W + "br", W + "tab"}:
                                parts.append("\n" if node.tag == W + "br" else "\t")
                        lines.append("".join(parts))
        return tuple(lines)

    def preview(self, values: dict[str, str]) -> str:
        if self.fields - values.keys():
            raise DocFlowError("Не переданы все переменные шаблона")
        if any(not isinstance(v, str) or BAD_XML_CHARS.search(v) for v in values.values()):
            raise DocFlowError("Подстановка содержит недопустимый текст XML")
        # Literal callback replacement preserves values containing braces/backslashes.
        return "\n".join(TOKEN.sub(lambda m: values[m.group(1)].replace("\r\n", "\n").replace("\r", "\n"), line)
                         for line in self._preview_lines)

