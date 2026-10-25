"""Read-only verification and local manifest preparation. Never publishes a release."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe archive/checksum path: " + name)
    return name


def checked_zip(path):
    z = zipfile.ZipFile(path)
    try:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        for name in names:
            safe_name(name)
        if z.testzip() is not None:
            raise ValueError("ZIP CRC failed")
        return z
    except Exception:
        z.close()
        raise


def verify(directory):
    directory = Path(directory)
    info = json.loads((directory / "BUILD-INFO.json").read_text(encoding="utf-8"))
    version = info["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:a|b|rc)[0-9]+", version):
        raise ValueError("Expected an explicit prerelease version")
    if info["python"] != "3.13.16" or not re.fullmatch(r"[0-9a-f]{40}", info["commit"]):
        raise ValueError("Official candidate requires pinned Python and a full source SHA")
    required = [f"DocFlow-Lite-{version}-{suffix}.zip" for suffix in
                ("Windows-x64-Portable", "Source", "ThirdParty-Sources")]
    required += ["BUILD-INFO.json", "WINDOWS-CI-RESULTS.json", "README-WINDOWS.txt"]
    sums = {}
    for line in (directory / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value, name = line.split("  ", 1)
        safe_name(name)
        if name in sums or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Invalid or duplicate checksum")
        sums[name] = value
    for name in required:
        if name not in sums:
            raise ValueError("Missing required checksum: " + name)
    portable = directory / required[0]
    with checked_zip(portable) as z:
        exe = z.read("DocFlow-Lite/DocFlow-Lite.exe")
        if digest(exe) != info["exe_sha256"]:
            raise ValueError("EXE and BUILD-INFO differ")
        manifest = json.loads(z.read("DocFlow-Lite/BUNDLE-SHA256.json"))
        if not manifest or "THIRD-PARTY-LICENSES.json" not in manifest:
            raise ValueError("Missing bundle provenance/licenses")
        for name, value in manifest.items():
            safe_name(name)
            if digest(z.read("DocFlow-Lite/" + name)) != value:
                raise ValueError("Bundle checksum failed: " + name)
        virtual = {"DocFlow-Lite/DocFlow-Lite.exe": digest(exe)}
    for name, value in sums.items():
        if name in virtual:
            actual = virtual[name]
        else:
            p = directory / name
            if not p.is_file() or p.is_symlink():
                raise ValueError("Missing or linked asset: " + name)
            with p.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != value:
            raise ValueError("Release checksum failed: " + name)
    with checked_zip(directory / required[1]) as z:
        source_manifest = json.loads(z.read("docflow-lite/FILE_HASHES.json"))
        if not source_manifest:
            raise ValueError("Empty corresponding source manifest")
        for name, value in source_manifest.items():
            safe_name(name)
            if digest(z.read("docflow-lite/" + name)) != value:
                raise ValueError("Corresponding source checksum failed: " + name)
    with checked_zip(directory / required[2]) as z:
        if not z.namelist():
            raise ValueError("Empty third-party sources")
    results = json.loads((directory / "WINDOWS-CI-RESULTS.json").read_text(encoding="utf-8"))
    if results.get("status") != "passed" or len(results.get("runs", [])) != 2:
        raise ValueError("Frozen runtime checks are incomplete")
    return {"status": "passed", "version": version, "build_commit": info["commit"],
            "python": info["python"], "exe_sha256": info["exe_sha256"],
            "assets": [{"name": n, "sha256": sums[n], "size": (directory/n).stat().st_size}
                       for n in required]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["verify"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.directory)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(1, str(exc) + "\n")
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k,v in result.items() if k != "assets"}))
