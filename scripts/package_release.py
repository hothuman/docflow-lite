"""Package only intended deliverables; exclude local environments and stale runs."""
import hashlib
import json
import shutil
import zipfile
import tomllib
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "deliverables"
DIST = ROOT / "site" / "dist"
SKIP = {".venv", "__pycache__", ".pytest_cache", ".git", "docflow-output", "build"}
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def eligible(path):
    relative = path.relative_to(ROOT)
    return (relative.parts[0] not in {"dist", "build", "release", "artifacts", "wheelhouse"}
            and path.name not in {"FILE_HASHES.json", "__audit.html"}
            and not (set(relative.parts) & SKIP)
            and not any(x.endswith(".egg-info") for x in path.parts)
            and path.suffix != ".pyc")


def add(z, path, arc=None):
    z.write(path, arcname=Path(arc or (Path("docflow-lite") / path.relative_to(ROOT))).as_posix())


def main():
    OUT.mkdir(exist_ok=True)
    runs = sorted(p for p in (ROOT / "demo-output").iterdir() if p.is_dir() and (p / "report.json").is_file())
    if not runs:
        raise RuntimeError("Generate a sample before packaging")
    sample = runs[-1]
    report = json.loads((sample / "report.json").read_text(encoding="utf-8"))
    assert report["documents"] == 4 and len(list(sample.rglob("*.docx"))) == 4
    # The website's public demo never includes internal launch strategy or marketing drafts.
    public_demo = DIST / "assets" / "DocFlow-Lite-Demo.zip"
    with zipfile.ZipFile(public_demo, "w", zipfile.ZIP_DEFLATED) as z:
        for folder in ("src", "tests", "third-party-licenses"):
            for path in sorted((ROOT / folder).rglob("*")):
                if path.is_file() and eligible(path):
                    add(z, path)
        for filename in (".gitignore", "pyproject.toml", "launch.py", "start_windows.bat", "THIRD_PARTY.md", "scripts/make_examples.py", "scripts/build_windows.ps1", "docs/dependency-metadata.json", "docs/tested-dependencies.txt"):
            add(z, ROOT / filename)
        for path in sorted(sample.rglob("*")):
            if path.is_file():
                add(z, path)
        readme = (ROOT / "README.md").read_text(encoding="utf-8").split("## Что где лежит")[0]
        readme = readme.replace("В этом архиве находится первая рабочая версия из исходников, сайт и демонстрационные материалы.", "В этом архиве находится первая рабочая версия приложения из исходников и демонстрационные документы.")
        z.writestr("docflow-lite/README.md", readme)
    # The full founder package includes the site, ready demo and publication draft.
    archive = OUT / f"DocFlow_Lite_v{VERSION}_Starter.zip"
    manifest = {}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or not eligible(path):
                continue
            rel = path.relative_to(ROOT)
            if "demo-output" in rel.parts and not path.is_relative_to(sample):
                continue
            add(z, path)
            manifest[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        z.writestr("docflow-lite/FILE_HASHES.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    for p in (public_demo, archive):
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None
            assert len(z.namelist()) == len(set(z.namelist())), "Duplicate ZIP entry"
    shutil.copy2(DIST / "assets/demo.mp4", OUT / "DocFlow_Lite_Demo_24s.mp4")
    shutil.copy2(DIST / "assets/app.png", OUT / "DocFlow_Lite_Interface.png")
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key not in {"src", "href", "poster"} or not value or value.startswith(("#", "http", "mailto:", "data:")):
                    continue
                assert (self.base / value.split("#")[0]).exists(), value
    for html in DIST.glob("*.html"):
        parser = Links(); parser.base = html.parent; parser.feed(html.read_text(encoding="utf-8"))
    print(json.dumps({"files":[{"path":str(p),"bytes":p.stat().st_size} for p in OUT.iterdir() if p.is_file()],"sample_run":sample.name,"source_files":len(manifest),"website_links":"all local assets present"},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()

