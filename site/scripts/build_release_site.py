"""Build the download page only after verifying the actual published release.
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
    if version not in {'0.3.0a6','1.0.0rc1','1.0.0','1.0.1'}:
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
    if not {'SHA256SUMS.txt', 'BUILD-INFO.json', 'SBOM.cdx.json'}.issubset(a['name'] for a in manifest['assets']):
        raise ValueError('Download page metadata must be verified before writing')
    info = build_site.build(Path(output), "https://docflow-lite.pages.dev/", index_home=False)
    version = manifest["version"]
    portable = f"DocFlow-Lite-{version}-Windows-x64-Portable.zip"
    expected = next(a for a in manifest["assets"] if a["name"] == portable)
    # Semantic markers keep release activation independent of marketing copy.
    # Only this function may change the download after verify_published succeeds.
    prerelease = is_prerelease(version)
    label = ('Публичный предварительный выпуск' if prerelease else 'Публичный стабильный выпуск')
    base = REPO + '/releases/download/v' + version + '/'
    def render(text):
        text = re.sub(r'data-public-version="[^"]+"', 'data-public-version="'+version+'"', text)
        text = re.sub(r'(<[^>]+ data-release-version[^>]*>)[^<]*(</[^>]+>)',
                      lambda m: m[1] + version + m[2], text)
        text = re.sub(r'(<[^>]+ data-release-stage[^>]*>)[^<]*(</[^>]+>)',
                      lambda m: m[1] + label + m[2], text)
        text = re.sub(r'(<[^>]+ data-release-sha[^>]*>)[^<]*(</[^>]+>)',
                      lambda m: m[1] + expected['sha256'] + m[2], text)
        def link(match):
            tag = match[0]
            suffix = re.search(r'data-release-asset="([^"]+)"', tag)
            file = re.search(r'data-release-file="([^"]+)"', tag)
            if suffix:
                if suffix[1] not in {'Windows-x64-Portable', 'Source', 'ThirdParty-Sources'}:
                    raise ValueError('Unknown release asset marker')
                name = f'DocFlow-Lite-{version}-{suffix[1]}.zip'
            else:
                name = file[1]
                if name not in {'SHA256SUMS.txt', 'BUILD-INFO.json', 'SBOM.cdx.json'}:
                    raise ValueError('Unknown release metadata marker')
            if name not in {asset['name'] for asset in manifest['assets']}:
                raise ValueError('Linked release file was not verified: ' + name)
            return re.sub(r'href="[^"]*"', 'href="' + base + quote(name) + '"', tag)
        text = re.sub(r'<a\b[^>]* data-release-(?:asset|file)="[^"]+"[^>]*>', link, text)
        if version == '1.0.1':
            text = re.sub(r'<div\b[^>]* data-release-candidate[^>]*>.*?</div>',
                          '<div class="candidate-note"><h3>Версия 1.0.1 опубликована</h3>'
                          '<p>Перед обновлением сохраните копию проекта. Проверяйте документы на ваших шаблонах.</p></div>',
                          text, flags=re.S)
            text = text.replace('подготовленного кандидата 1.0.1', 'версии 1.0.1')
            text = text.replace('подготовленного 1.0.1', 'версии 1.0.1')
            text = text.replace('подготовленный кандидат. Публичная загрузка пока 1.0.0.', 'публичный выпуск.')
            text = text.replace('подготовленный кандидат', 'публичный выпуск')
        return text
    for page in Path(output).glob('*.html'):
        page.write_text(render(page.read_text(encoding='utf-8')), encoding='utf-8')
    info.update(application_version=version, public_prerelease=is_prerelease(version), release_verification=proof, source_commit=manifest["release_target"])
    info["file_sha256"] = {p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
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
