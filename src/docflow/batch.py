import csv
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import __version__
from .data import Table, load_table
from .errors import DocFlowError
from .profile import Profile
from .safety import csv_safe, safe_name
from .templates import Template
from .validation import Issue, validate_mapping, values_for


@dataclass(frozen=True)
class Prepared:
    profile: Profile
    table: Table
    templates: tuple[Template, ...]


@dataclass(frozen=True)
class BatchResult:
    directory: Path
    total: int
    accepted: int
    rejected: int
    documents: int
    issues: tuple[Issue, ...]


def prepare(profile: Profile) -> Prepared:
    if not 1 <= len(profile.templates) <= 20:
        raise DocFlowError("Выберите от 1 до 20 шаблонов")
    table = load_table(profile.data_file, encoding=profile.encoding, sheet=profile.sheet)
    templates = tuple(Template.load(x) for x in profile.templates)
    fields = set().union(*(t.fields for t in templates))
    validate_mapping(table, fields, profile.mapping, profile.rules)
    if profile.name_column and profile.name_column not in table.headers:
        raise DocFlowError("Не найден столбец для имени папки")
    return Prepared(profile, table, templates)


def generate(prepared: Prepared, output: Path | str, progress: Callable[[int, int], None] | None = None) -> BatchResult:
    """Publish one completed directory. A failed record never leaves partial DOCX."""
    output = Path(output).resolve()
    staging = None
    try:
        output.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".docflow-", dir=output))
        accepted, documents = 0, 0
        issues, records_report = [], []
        for index, record in enumerate(prepared.table.records, 1):
            values, row_issues = values_for(record, prepared.profile.mapping, prepared.profile.rules)
            label = record.values.get(prepared.profile.name_column, "")
            row_name = f"row_{record.row_number:04d}_{safe_name(label)}"
            row_dir = staging / row_name
            row_files = []
            if not row_issues:
                row_dir.mkdir()
                try:
                    for n, template in enumerate(prepared.templates, 1):
                        filename = f"{n:02d}_{safe_name(template.path.stem)}.docx"
                        target = row_dir / filename
                        with target.open("xb") as f:
                            f.write(template.render(values))
                            f.flush()
                            os.fsync(f.fileno())
                        row_files.append(f"{row_name}/{filename}")
                except OSError:
                    # A storage failure invalidates the entire run, not just a row.
                    raise
                except Exception:
                    shutil.rmtree(row_dir)
                    row_files = []
                    row_issues.append(Issue(record.row_number, "", "Не удалось создать комплект DOCX. Проверьте шаблоны; исходные значения в отчёт не записаны"))
            if row_issues:
                issues.extend(row_issues)
            else:
                accepted += 1
                documents += len(row_files)
            records_report.append({"row": record.row_number, "status": "error" if row_issues else "ok", "files": row_files, "issues": [x.to_dict() for x in row_issues]})
            if progress:
                progress(index, len(prepared.table.records))
        total = len(prepared.table.records)
        report = {"version": __version__, "created_at": datetime.now(timezone.utc).isoformat(), "source": prepared.table.source.name, "templates": [x.path.name for x in prepared.templates], "total": total, "accepted": accepted, "rejected": total - accepted, "documents": documents, "records": records_report}
        (staging / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        with (staging / "report.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["row", "status", "field", "message"])
            for item in records_report:
                if item["issues"]:
                    for issue in item["issues"]:
                        writer.writerow([item["row"], "error", csv_safe(issue["field"]), csv_safe(issue["message"])])
                else:
                    writer.writerow([item["row"], "ok", "", ""])
        final = output / ("DocFlow_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:10])
        os.rename(staging, final)
        staging = None
        return BatchResult(final, total, accepted, total - accepted, documents, tuple(issues))
    except OSError as exc:
        raise DocFlowError(f"Не удалось безопасно сохранить пакет: {exc}") from exc
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)

