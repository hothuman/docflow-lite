"""Build an auditable review handoff from verified, synthetic CI artifacts.

No release, tag, Pages deployment, network request or client-data import.
"""
from pathlib import Path
from contextlib import closing
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / ".handoff-input"
OUT = ROOT / "handoff"
VERSION = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive(folder, target, prefix=""):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                assert not p.is_symlink(), str(p)
                z.write(p, prefix + p.relative_to(folder).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist()))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    OUT.mkdir(exist_ok=True)
    assert not any(OUT.iterdir()), 'Refusing to mix deliverables with an existing handoff'
    provenance = read_json(INPUT/'ci-provenance.json')
    application, browser_run = provenance['application_run'], provenance['browser_run']
    assert all(r['status']=='completed' and r['conclusion']=='success' for r in (application,browser_run))
    assert application['head_sha']==browser_run['head_sha']
    BUILD_RUN, BROWSER_RUN, CODE_SHA = application['id'], browser_run['id'], application['head_sha']
    release = INPUT / "release"
    windows = INPUT / "windows"
    linux = INPUT / "linux"
    browser = INPUT / "browser"
    results = read_json(release / "WINDOWS-CI-RESULTS.json")
    assert results["status"] == "passed"
    binary_info=read_json(release/'BUILD-INFO.json')
    assert binary_info['version']==VERSION
    PORTABLE_SHA, EXE_SHA = results['portable_sha256'], results['exe_sha256']
    assert binary_info['exe_sha256']==EXE_SHA
    assert results['service']['refinement']['status']=='passed'
    assert len(results['service']['refinement']['checks'])==3
    assert all(c['passed'] for c in results['service']['refinement']['checks'])
    layout=results['service']['refinement']['layout']
    assert layout['status']=='passed' and len(layout['cases'])==90
    assert all(not c['failures'] for c in layout['cases'])
    assert results["service"]["status"] == "passed"
    assert results["service"]["completion"]["status"] == "passed"
    assert all(x["passed"] for x in results["service"]["completion"]["checks"])
    assert len(results["service"]["checks"]) == 9
    assert all(x["passed"] for x in results["service"]["checks"])
    assert all(r["frozen"] and r["exit_code"] == 0 for r in results["runs"])
    assert results["source_checkout_not_used_for_runtime"]
    assert not results["runtime_path_contains_python"]
    assert read_json(browser / "browser-checks.json")["status"] == "passed"

    portable = release / f"DocFlow-Lite-{VERSION}-Windows-x64-Portable.zip"
    assert digest(portable) == PORTABLE_SHA
    with zipfile.ZipFile(portable) as z:
        assert z.testzip() is None
        exe = z.read("DocFlow-Lite/DocFlow-Lite.exe")
        assert hashlib.sha256(exe).hexdigest() == EXE_SHA
        pe = struct.unpack_from("<I", exe, 0x3c)[0]
        assert exe[:2] == b"MZ" and exe[pe:pe + 4] == b"PE\0\0"
        assert struct.unpack_from("<H", exe, pe + 4)[0] == 0x8664
        assert any(n.startswith("DocFlow-Lite/_internal/") for n in z.namelist())

    hashes = read_json(ROOT / "FILE_HASHES.json")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    assert set(hashes) == set(tracked) - {"", "FILE_HASHES.json"}
    for name, expected in hashes.items():
        assert digest(ROOT / name) == expected, name
        assert not any(p in {"private", "client-work", ".git"} for p in Path(name).parts)
    with zipfile.ZipFile(release / f"DocFlow-Lite-{VERSION}-Source.zip") as z:
        runtime = [n for n in hashes if n.startswith(("src/", "scripts/", "packaging/", "requirements/", "tools/")) or n in {"launch.py", "pyproject.toml"}]
        for name in runtime:
            assert z.read("docflow-lite/" + name) == (ROOT / name).read_bytes(), name

    for name in (portable.name, f"DocFlow-Lite-{VERSION}-ThirdParty-Sources.zip", "BUILD-INFO.json", "README-WINDOWS.txt", "WINDOWS-CI-RESULTS.json", f"DocFlow-Lite-{VERSION}-Source.zip"):
        shutil.copy2(release / name, OUT / name)
    with zipfile.ZipFile(OUT / f"DocFlow-Lite-{VERSION}-ThirdParty-Sources.zip") as z:
        assert z.testzip() is None

    subprocess.check_call(["git", "archive", "--format=zip", "--prefix=docflow-lite/", "--output=" + str(OUT / f"DocFlow-Lite-{VERSION}-Source-Review.zip"), "HEAD"], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="service-review-") as temporary:
        stage = Path(temporary)
        site = stage / "site"
        env = {**os.environ, "PUBLIC_SITE_URL": "https://docflow-lite.pages.dev/", "ENABLE_INDEXING": "0"}
        subprocess.check_call(["python3", "site/scripts/build_site.py", "--output", str(site)], cwd=ROOT, env=env)
        info = read_json(site / "build-info.json")
        assert info["public_url"] == "https://docflow-lite.pages.dev/"
        assert not info["indexing_enabled"] and not info["lead_collection_enabled"]
        assert (site / "service.html").is_file()
        archive(site, OUT / "DocFlow-Lite-Service-Website-Review.zip")

        projects = list(windows.rglob("Рабочий проект с пробелами"))
        assert len(projects) == 1
        source = projects[0]
        demo = stage / "Service-Synthetic-Demo"
        project = demo / "project"
        project.mkdir(parents=True)
        for folder in ("attachments", "generated", "templates", "profiles"):
            if (source / folder).is_dir(): shutil.copytree(source / folder, project / folder)
        with closing(sqlite3.connect(source / "service.db")) as src, closing(sqlite3.connect(project / "service.db")) as dst:
            src.backup(dst)
        with closing(sqlite3.connect(project / "service.db")) as c:
            c.row_factory = sqlite3.Row
            assert c.execute("pragma quick_check").fetchone()[0] == "ok"
            assert not c.execute("pragma foreign_key_check").fetchall()
            counts = {t: c.execute("select count(*) from " + t).fetchone()[0] for t in ("clients", "equipment", "repair_orders", "attachments", "generated_documents", "organization_profiles", "estimate_versions", "import_records")}
            for table in ("attachments", "generated_documents", "managed_files"):
                for row in c.execute("select path,sha256 from " + table):
                    assert digest(project / row["path"]) == row["sha256"]
        for p in (project / "generated").rglob("*.docx"):
            with zipfile.ZipFile(p) as z:
                assert z.testzip() is None
                assert b"{{" not in z.read("word/document.xml")
        with (demo / "Service-Equipment-Import.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Постоянный номер", "Модель"])
            w.writerows([["SYNTH-IMPORT-001", "Учебный аппарат А"], ["SYNTH-IMPORT-002", "Учебный аппарат Б"]])
        for example in (ROOT / "examples/service").glob("History-900.*"):
            shutil.copy2(example, demo / example.name)
        # Back up the final a3 project, not the earlier completion-only snapshot.
        sys.path.insert(0,str(ROOT/'src'))
        from docflow.service.repository import ServiceStore
        from docflow.service.backup import create_backup,restore_backup
        store=ServiceStore(project)
        backup=create_backup(store,demo/'synthetic.service-backup.zip')
        restored=restore_backup(backup,demo/'restored-project')
        with closing(sqlite3.connect(restored/'service.db')) as c:
            assert c.execute('pragma quick_check').fetchone()[0]=='ok'
            assert not c.execute('pragma foreign_key_check').fetchall()
            for table,count in counts.items():assert c.execute('select count(*) from '+table).fetchone()[0]==count
        assert counts['repair_orders']==7 and counts['import_records']==3
        (demo/'verified-counts.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
        (demo / "README.txt").write_text(
            "ТОЛЬКО СИНТЕТИЧЕСКИЕ ДАННЫЕ. Нет реального клиента, заказа или оплаты.\n\n"
            "Распакуйте Windows Portable целиком. Service → Настройки → Открыть другой локальный проект → папка project.\n"
            "Это проект из фактически пройденного Windows CI: " + json.dumps(counts, ensure_ascii=False) + ".\n"
            "Восемь редактируемых форм находятся в project/templates/default-v3, созданные документы — project/generated.\n"
            "Видео показывает встроенный пример Core, а не оборудование реального клиента.\n"
            "CSV содержит два дополнительных учебных аппарата: при импорте явно сопоставьте номер/модель и выберите вымышленного владельца.\n"
            "restored-project — фактически восстановленная и проверенная копия; synthetic.service-backup.zip — полный архив.\n"
            "SYNTH-ACCEPT-7500 показывает 0 /7500 /9670 /2170; аппарат 900 — историю 101/305/900, четвёртое обращение и этот финансовый сценарий.\n"
            "Работайте локально одним пользователем. Проверьте Word и backup/restore перед реальными данными.\n"
            "Формы нейтральные; сложный исходный акт и юридические условия требуют согласования.\n",
            encoding="utf-8",
        )
        archive(demo, OUT / "Service-Synthetic-Demo.zip", "Service-Synthetic-Demo/")

        qa = stage / "QA"
        shutil.copytree(windows, qa / "windows")
        shutil.copytree(linux, qa / "linux")
        shutil.copytree(browser, qa / "website")
        shutil.copytree(ROOT / "docs/service", qa / "docs")
        shutil.copy2(release / f"DocFlow-Lite-{VERSION}-Source.zip", qa / "Exact-CI-Build-Source.zip")
        shutil.copy2(release / "BUILD-INFO.json", qa / "BUILD-INFO.json")
        shutil.copy2(ROOT / "docs/README-WINDOWS-SERVICE.txt", qa / "README-WINDOWS.txt")
        proof = {
            "status": "passed",
            "handoff_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "binary_source_commit": CODE_SHA,
            "binary_ci_merge_commit": binary_info["commit"],
            "binary_ci_run": BUILD_RUN,
            "browser_ci_run": BROWSER_RUN,
            "current_runtime_matches_exact_build_source": True,
            "portable_sha256": PORTABLE_SHA,
            "exe_sha256": EXE_SHA,
            "demo_counts": counts,
            "restored_demo_included": True,
            "refinement_native_checks":3,
            "native_virtual_layout_cases":90,
            "demo_integrity": "quick_check, foreign_key_check and referenced SHA256 passed",
            "production_deployed": False,
            "manual_windows_10_11": False,
            "microsoft_word_visual_acceptance": False,
            "main_merged": False,
            "official_release_created": False,
        }
        (qa / "handoff-verification.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.copy2(qa / "handoff-verification.json", OUT / "Service-Verification.json")
        (qa / "README.txt").write_text(
            "Actual Windows/Linux CI and isolated Chromium reports, screenshots, synthetic projects and documentation.\n"
            "No real customer files. Native Windows runner is not physical Windows 10/11 acceptance.\n"
            "Website screenshot/tests concern an isolated review build, not a new Cloudflare publication.\n"
            "Exact-CI-Build-Source.zip is the source tree used for the supplied binary; Source-Review.zip adds final documentation/support packaging.\n",
            encoding="utf-8",
        )
        if (INPUT/'local').is_dir():shutil.copytree(INPUT/'local',qa/'local')
        if (INPUT/'document-examples').is_dir():archive(INPUT/'document-examples',OUT/'DocFlow-Lite-Document-Examples.zip')
        if (INPUT/'screenshots').is_dir():archive(INPUT/'screenshots',OUT/'DocFlow-Lite-Review-Screenshots.zip')
        shutil.copy2(INPUT/'ci-provenance.json',qa/'ci-provenance.json')
        archive(qa, OUT / "DocFlow-Lite-Service-QA-and-Docs.zip")
        print("HANDOFF_PROOF " + json.dumps(proof, ensure_ascii=False))
    shutil.copy2(ROOT / "docs/service/25_REFINEMENT_HANDOFF.md", OUT / "DocFlow-Lite-Service-Report-2026-10-24.md")
    shutil.copy2(ROOT / "docs/service/26_MANUAL_ACCEPTANCE.md", OUT / "DocFlow-Lite-Manual-Acceptance.md")
    for p in OUT.glob("*.zip"):
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None
            assert len(z.namelist()) == len(set(z.namelist()))
    lines = [digest(p) + "  " + p.name for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "SHA256SUMS-Service.txt"]
    lines.append(EXE_SHA + "  DocFlow-Lite/DocFlow-Lite.exe (inside Portable ZIP)")
    (OUT / "SHA256SUMS-Service.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(OUT.iterdir()) if p.is_file()]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
