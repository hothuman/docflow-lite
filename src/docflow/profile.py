import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import DocFlowError
from .safety import read_bounded
from .validation import Rule


@dataclass
class Profile:
    data_file: Path
    templates: list[Path]
    mapping: dict[str, str]
    rules: dict[str, Rule] = field(default_factory=dict)
    name_column: str = ""
    encoding: str = "auto"
    sheet: str | None = None

    @classmethod
    def load(cls, path: Path | str):
        path = Path(path).resolve()
        try:
            obj = json.loads(read_bounded(path, 1024 * 1024).decode("utf-8-sig"))
            if obj.get("version") != 1:
                raise DocFlowError("Неизвестная версия настроек")
            allowed = {"version", "data_file", "templates", "mapping", "rules", "name_column", "encoding", "sheet"}
            if set(obj) - allowed or not isinstance(obj["data_file"], str):
                raise DocFlowError("Некорректные поля настроек")
            if not isinstance(obj["templates"], list) or not 1 <= len(obj["templates"]) <= 20 or not all(isinstance(x, str) and x for x in obj["templates"]):
                raise DocFlowError("Укажите от 1 до 20 DOCX-шаблонов")
            mapping = obj["mapping"]
            if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
                raise DocFlowError("Некорректное сопоставление полей")
            rules = {key: Rule(**value) for key, value in obj.get("rules", {}).items()}
            if not isinstance(obj.get("name_column", ""), str) or obj.get("encoding", "auto") not in {"auto", "utf-8-sig", "cp1251"}:
                raise DocFlowError("Некорректный столбец имени или кодировка")
            if obj.get("sheet") is not None and not isinstance(obj["sheet"], str):
                raise DocFlowError("Имя листа должно быть текстом")
            return cls((path.parent / obj["data_file"]).resolve(), [(path.parent / x).resolve() for x in obj["templates"]], mapping, rules, obj.get("name_column", ""), obj.get("encoding", "auto"), obj.get("sheet"))
        except DocFlowError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise DocFlowError(f"Не удалось прочитать настройки: {exc}") from exc

    def save(self, path: Path | str) -> None:
        path = Path(path).resolve()
        if path.suffix.lower() != ".json" or path in {self.data_file.resolve(), *(p.resolve() for p in self.templates)}:
            raise DocFlowError("Настройки сохраняются в отдельный файл .json; исходные документы защищены")
        def relative(p):
            try:
                return os.path.relpath(p, path.parent).replace("\\", "/")
            except ValueError:
                return str(p)
        obj = {"version": 1, "data_file": relative(self.data_file), "templates": [relative(x) for x in self.templates], "mapping": self.mapping, "rules": {k: {"required": v.required, "kind": v.kind} for k, v in self.rules.items()}, "name_column": self.name_column, "encoding": self.encoding, "sheet": self.sheet}
        # Explicitly selected profile may be replaced. Write a sibling temp first.
        import tempfile
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".docflow-profile-", delete=False) as f:
                temp_name = f.name
                json.dump(obj, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, path)
        finally:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink()

