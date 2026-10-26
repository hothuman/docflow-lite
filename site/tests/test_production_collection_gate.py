"""The real production checker accepts the brief and rejects accidental lead collection."""
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_public_site as production

@pytest.mark.parametrize('added',['','<form action="/lead"><input name="email"></form>','<input name="email">','<textarea name="message"></textarea>','<button type="submit">Отправить</button>'])
def test_production_collection_gate_on_current_page(monkeypatch,added):
    body=(ROOT/'dist/index.html').read_text(encoding='utf-8').replace('</body>',added+'</body>').encode()
    def get(url):
        if url.endswith('/') or url.endswith('/index.html'):raw=body
        elif url.endswith('/sitemap.xml'):raw=b'<urlset/>'
        elif url.endswith('/robots.txt'):raw=b'User-agent: *\nDisallow: /'
        else:raw=b'placeholder'
        return {'final_url':url,'status':200,'headers':{},'redirects':[],'sha256':'synthetic'},raw
    monkeypatch.setattr(production,'get',get)
    report=production.verify('https://docflow-lite.pages.dev/')
    check=next(c for c in report['checks'] if c['check']=='no lead form or collection inputs')
    assert check['passed'] is (not added)
