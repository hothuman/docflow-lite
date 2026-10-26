"""Build the public a6 site only after verifying the actual published prerelease.
No upload, release publication, indexing or collection is performed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import Request, urlopen
import build_site
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from docflow.versioning import stage,is_prerelease

API = "https://api.github.com/repos/hothuman/docflow-lite"
REPO = "https://github.com/hothuman/docflow-lite"


def get_json(url):
    with urlopen(Request(url, headers={"User-Agent": "DocFlow-Release-Verification",
                                      "Accept": "application/vnd.github+json"}), timeout=30) as response:
        return json.load(response)


def download_hash(url):
    digest = hashlib.sha256()
    with urlopen(Request(url, headers={"User-Agent": "DocFlow-Release-Verification"}), timeout=30) as response:
        while chunk := response.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_published(manifest, fetch=get_json, hash_url=download_hash):
    version = manifest["version"]
    release_stage=stage(version)
    if version not in {'0.3.0a6','1.0.0rc1','1.0.0'}:
        raise ValueError('Copy needs review for a different product version')
    prerelease=is_prerelease(version)
    required = {f"DocFlow-Lite-{version}-{suffix}.zip" for suffix in ("Windows-x64-Portable", "Source", "ThirdParty-Sources")}
    if not required.issubset(a["name"] for a in manifest["assets"]):
        raise ValueError("Missing required distribution assets")
    tag = "v" + version
    if manifest["tag"] != tag or not re.fullmatch(r"[0-9a-f]{40}", manifest["release_target"]):
        raise ValueError("Invalid release target/tag")
    release = fetch(API + "/releases/tags/" + tag)
    if release.get("draft") is not False or release.get("prerelease") is not prerelease or release.get("tag_name") != tag or not release.get("published_at"):
        raise ValueError("The exact release and stage must already be publicly published")
    if version!='0.3.0a6' and release.get('immutable') is not True:
        raise ValueError('New release must be immutable before website activation')
    ref = fetch(API + "/git/ref/tags/" + tag)["object"]
    if ref["type"] == "tag":
        ref = fetch(API + "/git/tags/" + ref["sha"])["object"]
    if ref["type"] != "commit" or ref["sha"] != manifest["release_target"]:
        raise ValueError("Published tag points to a different commit")
    actual = {a["name"]: a for a in release["assets"]}
    names = [a["name"] for a in manifest["assets"]]
    if len(names) != len(set(names)) or not names:
        raise ValueError("Invalid expected assets")
    for expected in manifest["assets"]:
        name = expected["name"]
        if "/" in name or "\\" in name or not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"]):
            raise ValueError("Unsafe asset name/hash")
        asset = actual.get(name)
        url = REPO + "/releases/download/" + tag + "/" + quote(name)
        if not asset or asset.get("state") != "uploaded" or asset.get("size") != expected["size"] or asset.get("browser_download_url") != url:
            raise ValueError("Published asset missing or differs: " + name)
        if hash_url(url) != expected["sha256"]:
            raise ValueError("Published asset SHA256 differs: " + name)
    return {"tag": tag, "commit": ref["sha"], "assets_verified": len(names)}


def activate(output, manifest, fetch=get_json, hash_url=download_hash):
    proof = verify_published(manifest, fetch, hash_url)  # Fail before writing anything.
    info = build_site.build(Path(output), "https://docflow-lite.pages.dev/", index_home=False)
    version = manifest["version"]
    portable = f"DocFlow-Lite-{version}-Windows-x64-Portable.zip"
    expected = next(a for a in manifest["assets"] if a["name"] == portable)
    replacements = {
      "Подготовительная alpha 0.3.0a6.": "Публичная alpha 0.3.0a6.",
      "https://github.com/hothuman/docflow-lite/releases/download/v0.1.1/DocFlow-Lite-0.1.1-Windows-x64-Portable.zip": REPO+"/releases/download/v"+version+"/"+portable,
      "Настоящий интерфейс новой alpha. Публичная загрузка пока остаётся v0.1.1.": "Настоящий интерфейс публичной alpha 0.3.0a6. Данные вымышлены.",
      "Публичный Core v0.1.1. Новая alpha 0.3.0a6 проходит отдельную приёмку и здесь не подменяет опубликованный файл.": "Публичная alpha 0.3.0a6 · Core + Service. EXE не подписан. Перед обновлением сохраните копию проекта. SHA256 Portable: "+expected["sha256"],
      "Alpha 0.3.0a6 не входит в публичный Release v0.1.1. Новый интерфейс подготовлен для приёмки; промышленное внедрение не заявляется.": "Публичная alpha 0.3.0a6 включает Core и Service. Сначала проверьте учебный проект; промышленное внедрение и клиентская приёмка не заявляются.",
      "Core v0.1.1 · новая alpha 0.3.0a6": "Core + Service · alpha 0.3.0a6",
      "DocFlow · Core v0.1.1 · alpha 0.3.0a6": "DocFlow · Core + Service · alpha 0.3.0a6",
      "НАЧНИТЕ С ПУБЛИЧНОЙ ВЕРСИИ": "ПУБЛИЧНЫЙ ПРЕДВАРИТЕЛЬНЫЙ ВЫПУСК",
      "Core для Windows.<br>Без установки Python.": "Core + Service для Windows.<br>Без установки Python."
    }
    if version!='0.3.0a6':
        prerelease=is_prerelease(version)
        label=('Кандидат '+version if prerelease else 'Стабильная версия '+version)
        replacements={old:new.replace('Публичная alpha 0.3.0a6',label).replace('публичной alpha 0.3.0a6',label).replace('alpha 0.3.0a6',label).replace('0.3.0a6',version) for old,new in replacements.items()}
        replacements['ПУБЛИЧНЫЙ ПРЕДВАРИТЕЛЬНЫЙ ВЫПУСК']='ПУБЛИЧНЫЙ ПРЕДВАРИТЕЛЬНЫЙ ВЫПУСК' if prerelease else 'СТАБИЛЬНЫЙ ВЫПУСК'
    for page in Path(output).glob("*.html"):
        text = page.read_text(encoding="utf-8")
        for old, new in replacements.items():
            text = text.replace(old, new)
        page.write_text(text, encoding="utf-8")
    info.update(application_version=version, public_prerelease=is_prerelease(version), release_verification=proof, source_commit=manifest["release_target"])
    info["file_sha256"] = {str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(Path(output).rglob("*")) if p.is_file() and p.name != "build-info.json"}
    (Path(output)/"build-info.json").write_text(json.dumps(info,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        proof = activate(args.output, json.loads(args.manifest.read_text(encoding="utf-8")))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        parser.exit(1, "Release site not activated: " + str(exc) + "\n")
    print(json.dumps(proof))
