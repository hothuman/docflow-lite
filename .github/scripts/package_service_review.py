"""Build an auditable review handoff from verified, synthetic CI artifacts.

No release, tag, Pages deployment, network request or client-data import.
"""
from pathlib import Path
from contextlib import closing
import csv
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / ".handoff-input"
OUT = ROOT / "handoff"
VERSION = "0.3.0a1"
BUILD_RUN = 39947489151
BROWSER_RUN = 39949024477
CODE_SHA = "b9c5377edcde6cbee979062e6e87f97ed74a6505"
PORTABLE_SHA = "2d3507c648da1f1fda76d7763d07ff7e7fe1b552b54d1f5a2347ed0617618e1f"
EXE_SHA = "737f8e820d493fee638bdcd04b761d0dc8314adb43838138058c135ca4c07ecb"


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
    release = INPUT / "release"
    windows = INPUT / "windows"
    linux = INPUT / "linux"
    browser = INPUT / "browser"
    results = read_json(release / "WINDOWS-CI-RESULTS.json")
    assert results["status"] == "passed"
    assert results["service"]["status"] == "passed"
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
        runtime = [n for n in hashes if n.startswith(("src/", "scripts/", "packaging/", "requirements/")) or n in {"launch.py", "pyproject.toml"}]
        for name in runtime:
            assert z.read("docflow-lite/" + name) == (ROOT / name).read_bytes(), name

    for name in (portable.name, f"DocFlow-Lite-{VERSION}-ThirdParty-Sources.zip", "BUILD-INFO.json", "README-WINDOWS.txt", "WINDOWS-CI-RESULTS.json"):
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
        for folder in ("attachments", "generated", "templates"):
            shutil.copytree(source / folder, project / folder)
        with closing(sqlite3.connect(source / "service.db")) as src, closing(sqlite3.connect(project / "service.db")) as dst:
            src.backup(dst)
        with closing(sqlite3.connect(project / "service.db")) as c:
            c.row_factory = sqlite3.Row
            assert c.execute("pragma quick_check").fetchone()[0] == "ok"
            assert not c.execute("pragma foreign_key_check").fetchall()
            counts = {t: c.execute("select count(*) from " + t).fetchone()[0] for t in ("clients", "equipment", "repair_orders", "attachments", "generated_documents")}
            for table in ("attachments", "generated_documents"):
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
        backup = projects[0].parent / "synthetic.service-backup.zip"
        if backup.is_file():
            with zipfile.ZipFile(backup) as z:
                assert z.testzip() is None
            shutil.copy2(backup, demo / backup.name)
        (demo / "README.txt").write_text(
            "ТОЛЬКО СИНТЕТИЧЕСКИЕ ДАННЫЕ. Нет реального клиента, заказа или оплаты.\n\n"
            "Распакуйте Windows Portable целиком. Service → Настройки → Открыть другой локальный проект → папка project.\n"
            "Это проект из фактически пройденного Windows CI: " + json.dumps(counts, ensure_ascii=False) + ".\n"
            "Пять редактируемых форм находятся в project/templates, созданные документы — project/generated.\n"
            "Видео показывает встроенный пример Core, а не оборудование реального клиента.\n"
            "CSV содержит два дополнительных учебных аппарата: при импорте явно сопоставьте номер/модель и выберите вымышленного владельца.\n"
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
            "binary_ci_merge_commit": "86164b56901dab80435d77022ad8008105baab3f",
            "binary_ci_run": BUILD_RUN,
            "browser_ci_run": BROWSER_RUN,
            "current_runtime_matches_exact_build_source": True,
            "portable_sha256": PORTABLE_SHA,
            "exe_sha256": EXE_SHA,
            "demo_counts": counts,
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
        public_checks = [
            {"kind": "windows_public_v0.1.1", "status": 200, "bytes": 48776852, "sha256": "c0cac130ec4b39d7d42f0ea6ea1d5f128ff6402c89cc4cb8518bc60403f2a034", "zip_crc_ok": True, "checked_at_utc": "2026-10-23T11:41:20.507787+00:00"},
            {"kind": "public_demo", "status": 200, "bytes": 314068, "sha256": "d93b7b48be7f63dfb5d8d3bc39ea2579d1997ae79c9317ed3e80b4afe77ffd0a", "zip_crc_ok": True, "matches_repo": True, "checked_at_utc": "2026-10-23T11:41:15.559364+00:00"},
            {"kind": "public_home", "status": 200, "bytes": 31040, "service_not_deployed": True, "noindex": True, "form_action_none": True, "connect_src_none": True, "checked_at_utc": "2026-10-23T11:41:15.547671+00:00"},
        ]
        (qa / "public-downloads.json").write_text(json.dumps(public_checks, indent=2), encoding="utf-8")
        archive(qa, OUT / "DocFlow-Lite-Service-QA-and-Docs.zip")
        for p in sorted(browser.glob("*.png")):
            print("REVIEW_IMAGE " + p.name + " " + base64.b64encode(p.read_bytes()).decode("ascii"))
        print("BROWSER_REPORT " + (browser / "browser-checks.json").read_text(encoding="utf-8").replace("\n", " "))
        print("HANDOFF_PROOF " + json.dumps(proof, ensure_ascii=False))
    shutil.copy2(ROOT / "docs/service/15_HANDOFF_REPORT.md", OUT / "DocFlow-Lite-Service-Report-2026-10-23.md")
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
