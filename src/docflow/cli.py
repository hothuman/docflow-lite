import argparse
import json
from pathlib import Path

from . import __version__
from .batch import generate, prepare
from .errors import DocFlowError
from .profile import Profile
from .validation import values_for


def demo_profile() -> Path:
    return Path(__file__).parent / "examples" / "profile.json"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DocFlow Lite — локальная пакетная генерация DOCX")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "check", "preview", "demo"):
        p = sub.add_parser(command)
        if command != "demo":
            p.add_argument("profile", type=Path)
        if command in {"run", "demo"}:
            p.add_argument("--out", type=Path, default=Path.cwd() / "docflow-output")
        if command == "preview":
            p.add_argument("--row", type=int, default=1, help="Номер записи с 1, без заголовка")
            p.add_argument("--template", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        prepared = prepare(Profile.load(demo_profile() if args.command == "demo" else args.profile))
        if args.command == "check":
            issues = [x.to_dict() for record in prepared.table.records for x in values_for(record, prepared.profile.mapping, prepared.profile.rules)[1]]
            print(json.dumps({"rows": len(prepared.table.records), "templates": len(prepared.templates), "issues": issues}, ensure_ascii=False, indent=2))
            return 2 if issues else 0
        if args.command == "preview":
            if not 1 <= args.row <= len(prepared.table.records) or not 1 <= args.template <= len(prepared.templates):
                raise DocFlowError("Номер записи или шаблона вне диапазона")
            values, issues = values_for(prepared.table.records[args.row - 1], prepared.profile.mapping, prepared.profile.rules)
            if issues:
                raise DocFlowError("; ".join(f"{x.field}: {x.message}" for x in issues))
            print(prepared.templates[args.template - 1].preview(values))
            return 0
        result = generate(prepared, args.out)
        print(json.dumps({"directory": str(result.directory), "total": result.total, "accepted": result.accepted, "rejected": result.rejected, "documents": result.documents}, ensure_ascii=False, indent=2))
        return 2 if result.rejected else 0
    except (DocFlowError, OSError) as exc:
        parser.exit(1, f"Ошибка: {exc}\n")

