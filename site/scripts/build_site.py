"""Dependency-free static build. Does not publish or enable the lead form."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from configure_public_url import configure, normalize_base

SITE = Path(__file__).resolve().parents[1]
SOURCE = SITE / 'dist'


def build(output: Path, public_url: str = '', index_home: bool = False) -> dict:
    output = output.resolve()
    home, prefix = normalize_base(public_url) if public_url else ('', '/')
    if home and ('.chatgpt.site/' in home or home.startswith('https://chatgpt.com/')):
        raise ValueError('Website 2.0 требует новый подтверждённый адрес вне ChatGPT')
    if index_home and not home:
        raise ValueError('Для индексации нужен подтверждённый PUBLIC_SITE_URL')
    if output == SOURCE or output in SOURCE.parents or output.is_relative_to(SOURCE):
        raise ValueError('Каталог сборки не должен заменять исходники')
    if output.exists() and (not output.is_dir() or (any(output.iterdir()) and not (output / 'build-info.json').is_file())):
        raise ValueError('Отказ заменять чужой непустой каталог')
    source_files = sorted(p for p in SOURCE.rglob('*') if p.is_file())
    if any(p.is_symlink() for p in SOURCE.rglob('*')):
        raise ValueError('Символические ссылки не разрешены в статическом выводе')
    if any(p.stat().st_size > 25 * 1024 * 1024 for p in source_files):
        raise ValueError('Файл превышает лимит Pages 25 MiB; Windows ZIP должен оставаться в GitHub Release')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.website-v2-', dir=output.parent) as staging:
        stage = Path(staging) / 'build'
        shutil.copytree(SOURCE, stage, ignore=shutil.ignore_patterns('__audit*', '.*', '*.map'))
        if home:
            configure(home, stage, index_home=index_home)
        if prefix != '/':
            error_page = stage / '404.html'
            error_page.write_text(error_page.read_text(encoding='utf-8').replace('href="/', 'href="' + prefix), encoding='utf-8')
        if index_home:
            headers = stage / '_headers'
            headers.write_text(headers.read_text(encoding='utf-8').replace('  X-Robots-Tag: noindex, follow\n', ''), encoding='utf-8')
        file_hashes = {str(p.relative_to(stage)):sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file()}
        info = {'website_version':'2.0','application_version':'0.1.1','review_application_version':'0.3.0a4','public_url':home or None,
                'indexing_enabled':index_home,'lead_collection_enabled':False,'file_sha256':file_hashes}
        (stage / 'build-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        if output.exists(): shutil.rmtree(output)
        shutil.move(str(stage), str(output))
    return info


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=SITE/'build')
    parser.add_argument('--public-url', default=os.environ.get('PUBLIC_SITE_URL',''))
    parser.add_argument('--index', action='store_true', default=os.environ.get('ENABLE_INDEXING')=='1')
    args = parser.parse_args()
    branch = os.environ.get('CF_PAGES_BRANCH')
    production = os.environ.get('PRODUCTION_BRANCH','main')
    # Preview branches can never become indexable through shared environment variables.
    index = args.index and (not branch or branch == production)
    try:
        info = build(args.output, args.public_url, index)
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc)+'\n')
    print(json.dumps({'output':str(args.output.resolve()),'files':len(info['file_sha256']),
                      'public_url':info['public_url'],'indexing_enabled':info['indexing_enabled'],
                      'lead_collection_enabled':False}, ensure_ascii=False))
