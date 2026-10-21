import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .data import Record, Table
from .errors import DocFlowError


@dataclass(frozen=True)
class Rule:
    required: bool = True
    kind: str = "text"

    def __post_init__(self):
        if type(self.required) is not bool or self.kind not in {"text", "number", "email", "date"}:
            raise DocFlowError("Неизвестный тип проверки или некорректное required")


@dataclass(frozen=True)
class Issue:
    row: int
    field: str
    message: str

    def to_dict(self):
        return asdict(self)


def validate_mapping(table: Table, fields: set[str], mapping: dict[str, str], rules: dict[str, Rule]) -> None:
    missing = fields - mapping.keys()
    if missing:
        raise DocFlowError("Не сопоставлены переменные: " + ", ".join(sorted(missing)))
    for field, column in mapping.items():
        if column not in table.headers:
            raise DocFlowError(f"Для {field} не найден столбец {column}")
    unknown = rules.keys() - mapping.keys()
    if unknown:
        raise DocFlowError("Проверки заданы для неизвестных переменных: " + ", ".join(sorted(unknown)))


def values_for(record: Record, mapping: dict[str, str], rules: dict[str, Rule]) -> tuple[dict[str, str], list[Issue]]:
    context, issues = {}, []
    for field, column in mapping.items():
        value = record.values[column].strip()
        context[field] = value
        rule = rules.get(field, Rule())
        if not value:
            if rule.required:
                issues.append(Issue(record.row_number, field, "Обязательное поле пусто"))
            continue
        if rule.kind == "number":
            try:
                number = Decimal(value.replace("\u00a0", "").replace(" ", "").replace(",", "."))
                if not number.is_finite() or number < 0:
                    raise InvalidOperation
            except InvalidOperation:
                issues.append(Issue(record.row_number, field, "Нужно конечное число не меньше нуля"))
        elif rule.kind == "email":
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
                issues.append(Issue(record.row_number, field, "Проверьте формат email"))
        elif rule.kind == "date":
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError
                date.fromisoformat(value)
            except ValueError:
                issues.append(Issue(record.row_number, field, "Нужна дата ГГГГ-ММ-ДД"))
    return context, issues

