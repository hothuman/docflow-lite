"""Offline build/privacy regressions. Reserved .test URLs are not live deployments."""
from pathlib import Path
from tempfile import TemporaryDirectory
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree
import importlib.util
import json
import os
import subprocess
import sys
import unittest

SITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SITE/'scripts'))
import build_site


class Page(HTMLParser):
    def __init__(self,text):
        super().__init__(); self.tags=[];self.feed(text)
    def handle_starttag(self,tag,attrs): self.tags.append((tag,dict(attrs)))


class WebsiteV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
    def build(self,**kwargs):
        out=self.base/'build'; build_site.build(out,**kwargs);return out
    def test_default_build_is_not_indexed_and_has_no_invented_domain(self):
        out=self.build(); info=json.loads((out/'build-info.json').read_text(encoding="utf-8"))
        self.assertIsNone(info['public_url']);self.assertFalse(info['lead_collection_enabled'])
        for file in out.glob('*.html'):
            self.assertIn('noindex',file.read_text(encoding="utf-8"))
            self.assertNotIn('chatgpt.site',file.read_text(encoding="utf-8"))
            self.assertNotIn('rel="canonical"',file.read_text(encoding="utf-8"))
        self.assertIn('Disallow: /',(out/'robots.txt').read_text(encoding="utf-8"))
        self.assertEqual(ElementTree.parse(out/'sitemap.xml').findall('.//{*}loc'),[])
    def test_confirmed_url_can_remain_in_review_mode(self):
        out=self.build(public_url='https://review.example.test/subdir/')
        text=(out/'index.html').read_text(encoding="utf-8")
        self.assertIn('href="https://review.example.test/subdir/"',text)
        self.assertIn('content="https://review.example.test/subdir/assets/social-card.png"',text)
        self.assertIn('noindex,follow',text)
        self.assertIn('href="https://review.example.test/subdir/software.html"',(out/'software.html').read_text(encoding='utf-8'))
        self.assertIn('Disallow: /',(out/'robots.txt').read_text(encoding="utf-8"))
        self.assertIn('href="/subdir/style.css"',(out/'404.html').read_text(encoding="utf-8"))
    def test_explicit_indexing_only_indexes_home(self):
        out=self.build(public_url='https://approved.example.test/',index_home=True)
        self.assertIn('content="index,follow"',(out/'index.html').read_text(encoding="utf-8"))
        for name in ('privacy.html','terms.html','404.html'):
            self.assertIn('noindex',(out/name).read_text(encoding="utf-8"))
        self.assertNotIn('X-Robots-Tag:',(out/'_headers').read_text(encoding="utf-8"))
        self.assertEqual([v.text for v in ElementTree.parse(out/'sitemap.xml').findall('.//{*}loc')],['https://approved.example.test/'])
    def test_preview_branch_never_inherits_production_indexing(self):
        out=self.base/'preview'
        env={**os.environ,'ENABLE_INDEXING':'1','PUBLIC_SITE_URL':'https://approved.example.test/',
             'CF_PAGES_BRANCH':'feature/website-v2','PRODUCTION_BRANCH':'main'}
        run=subprocess.run([sys.executable,str(SITE/'scripts/build_site.py'),'--output',str(out)],env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertFalse(json.loads((out/'build-info.json').read_text(encoding="utf-8"))['indexing_enabled'])
    def test_invalid_configuration_does_not_write(self):
        for url in ('http://bad.example.test','https://user:secret@bad.example.test','https://bad.example.test/?key=x','https://bad.example.test/%2e%2e/','https://product.chatgpt.site/'):
            with self.subTest(url=url),self.assertRaises(ValueError): self.build(public_url=url)
            self.assertFalse((self.base/'build').exists())
        with self.assertRaises(ValueError): self.build(index_home=True)
        protected=self.base/'owned-by-user';protected.mkdir();(protected/'keep.txt').write_text('keep')
        with self.assertRaises(ValueError): build_site.build(protected)
        self.assertEqual((protected/'keep.txt').read_text(encoding="utf-8"),'keep')
        with self.assertRaises(ValueError): build_site.build(SITE/'dist')
    def test_build_is_deterministic_and_preserves_source(self):
        before={str(p):p.read_bytes() for p in (SITE/'dist').rglob('*') if p.is_file()}
        out=self.build();first={str(p.relative_to(out)):p.read_bytes() for p in out.rglob('*') if p.is_file()}
        build_site.build(out)
        self.assertEqual(first,{str(p.relative_to(out)):p.read_bytes() for p in out.rglob('*') if p.is_file()})
        self.assertEqual(before,{str(p):p.read_bytes() for p in (SITE/'dist').rglob('*') if p.is_file()})
    def test_all_local_resources_and_fragments_resolve(self):
        out=self.build()
        for file in out.glob('*.html'):
            page=Page(file.read_text(encoding="utf-8"))
            ids=[a['id'] for _,a in page.tags if 'id' in a]
            self.assertEqual(len(ids),len(set(ids)),str(file))
            for tag,attrs in page.tags:
                for key in ('href','src','poster'):
                    value=attrs.get(key)
                    if not value: continue
                    link=urlsplit(urljoin('https://offline.example.test/'+('' if file.name=='index.html' else file.name),value))
                    if link.netloc!='offline.example.test': continue
                    target=out/(link.path.lstrip('/') or 'index.html')
                    self.assertTrue(target.is_file(),(file.name,value))
                    if link.fragment:
                        self.assertIn(link.fragment,[a.get('id') for _,a in Page(target.read_text(encoding="utf-8")).tags],(file.name,value))
                if tag=='img': self.assertIn('alt',attrs)
                if tag=='a' and attrs.get('target')=='_blank': self.assertIn('noopener',attrs.get('rel',''))
    def test_intake_disabled_without_javascript(self):
        text=(SITE/'dist/index.html').read_text(encoding='utf-8')
        page=Page(text)
        forms=[a for t,a in page.tags if t=='form'];self.assertEqual(forms,[])
        self.assertFalse([a for t,a in page.tags if t in {'input','textarea','fieldset'}])
        self.assertIn('Что написать для оценки',text)
        self.assertIn('Не присылайте клиентские базы',text)
        headers=(SITE/'dist/_headers').read_text(encoding="utf-8")
        self.assertIn("form-action 'none'",headers);self.assertIn("connect-src 'none'",headers)
        self.assertIn('X-Robots-Tag: noindex',headers)
    def test_no_external_resource_dependencies_or_storage_calls(self):
        for file in (SITE/'dist').glob('*.html'):
            for tag,a in Page(file.read_text(encoding="utf-8")).tags:
                if tag in ('script','img','source','track') or (tag=='link' and a.get('rel')=='stylesheet'):
                    self.assertFalse(urlsplit(a.get('src',a.get('href',''))).scheme,(file.name,a))
        script=(SITE/'dist/app.js').read_text(encoding="utf-8")
        for call in ('fetch(', 'XMLHttpRequest', 'sendBeacon', 'localStorage', 'sessionStorage','indexedDB','document.cookie'):
            self.assertNotIn(call,script)
    def test_service_review_is_current_and_not_an_unpublished_download(self):
        html=(SITE/'dist/service.html').read_text(encoding="utf-8")
        self.assertIn('0.3.0a6',html)
        self.assertNotIn('0.3.0a2',html)
        for name in ('service.png','service-repair.png'):
            self.assertIn('assets/'+name,html)
            self.assertTrue((SITE/'dist/assets'/name).is_file())
        self.assertIn('не входит в публичный Release v0.1.1',html)
        self.assertNotIn('releases/download/v0.3',html)
        self.assertIn('предварительной и окончательной сметы',html)
        self.assertIn('мастер',html.lower())
        out=self.build(public_url='https://docflow-lite.pages.dev/')
        built=(out/'service.html').read_text(encoding="utf-8")
        self.assertIn('href="https://docflow-lite.pages.dev/service.html"',built)
        self.assertIn('noindex',built)

    def test_core_palette_contrast(self):
        def luminance(h):
            c=[int(h[i:i+2],16)/255 for i in (0,2,4)]
            c=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in c]
            return sum(v*w for v,w in zip(c,(.2126,.7152,.0722)))
        import re
        css=(SITE/'dist/style.css').read_text(encoding="utf-8")
        colors=dict(re.findall(r'--([a-z-]+):#([0-9a-fA-F]{6})',css))
        pairs=[(colors['text'],colors['bg']),(colors['muted'],colors['surface']),(colors['accent-text'],colors['accent']),(colors['accent-text'],colors['accent-hover']),(colors['teal'],colors['teal-soft']),(colors['error'],colors['error-soft'])]
        for foreground,background in pairs:
            a,b=sorted((luminance(foreground),luminance(background)))
            self.assertGreaterEqual((b+.05)/(a+.05),4.5,(foreground,background))


if __name__=='__main__':unittest.main()
