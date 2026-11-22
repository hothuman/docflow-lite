"""Product, provenance and publication boundaries of the Atelier website."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'site/scripts'))
import build_site
import build_release_site


class Tags(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.tags=[]; self.feed(text)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class AtelierTests(unittest.TestCase):
    def test_source_and_default_build_keep_public_version_and_candidate_separate(self):
        with TemporaryDirectory() as folder:
            out=Path(folder)/'build'; info=build_site.build(out)
            self.assertEqual(info['application_version'],'1.0.0')
            self.assertEqual(info['review_application_version'],'1.0.1')
            page=(out/'download.html').read_text(encoding='utf-8')
            tags=Tags(page).tags
            links=[a['href'] for t,a in tags if t=='a' and 'data-release-asset' in a]
            self.assertEqual(len(links),3)
            self.assertTrue(all('/releases/download/v1.0.0/' in link for link in links))
            self.assertNotIn('/releases/download/v1.0.1/',page)
            self.assertIn('Draft Release',page)
            self.assertIn('не имеет цифровой подписи',page)

    def test_approved_legal_body_is_preserved_exactly(self):
        proof=json.loads((ROOT/'docs/brand/ASSET_PROVENANCE.json').read_text(encoding='utf-8'))
        for name, expected in proof['approved_legal_main_sha256'].items():
            text=(ROOT/'site/dist'/name).read_text(encoding='utf-8')
            main=re.search(r'<main\b.*?</main>',text,re.S)[0]
            # Only the owner-requested factual delta is allowed. Reversing it
            # must recover the previous exact body, including all draft terms.
            page=proof.get('legal_factual_update',{}).get('pages',{}).get(name)
            if page:
                for change in reversed(page['replacements']):
                    self.assertEqual(main.count(change['after']),1,name)
                    main=main.replace(change['after'],change['before'],1)
            self.assertEqual(hashlib.sha256(main.encode()).hexdigest(),expected,name)

    def test_actual_screenshots_and_font_have_reproducible_provenance(self):
        proof=json.loads((ROOT/'docs/brand/ASSET_PROVENANCE.json').read_text(encoding='utf-8'))
        self.assertEqual(proof['application_version'],'1.0.1')
        self.assertEqual(proof['data'],'synthetic')
        for name, item in proof['screenshots'].items():
            self.assertEqual(hashlib.sha256((ROOT/'site/dist/assets'/name).read_bytes()).hexdigest(),item['sha256'],name)
        self.assertEqual(hashlib.sha256((ROOT/proof['font']['local_file']).read_bytes()).hexdigest(),proof['font']['sha256'])
        self.assertIn('SIL OPEN FONT LICENSE',(ROOT/'site/dist/assets/fonts/OFL.txt').read_text(encoding='utf-8'))

    def test_optional_pages_receive_canonical_and_remain_noindex(self):
        with TemporaryDirectory() as folder:
            out=Path(folder)/'build'; build_site.build(out,'https://review.example.test/subdir/')
            for name in ('download.html','docs.html'):
                page=(out/name).read_text(encoding='utf-8')
                self.assertIn('href="https://review.example.test/subdir/'+name+'"',page)
                self.assertIn('noindex,follow',page)
                self.assertIn('https://review.example.test/subdir/assets/social-card.png',page)

    def test_semantic_tokens_match_implemented_roles(self):
        theme=json.loads((ROOT/'docs/brand/atelier-theme.json').read_text(encoding='utf-8'))
        tokens=json.loads((ROOT/'docs/brand/tokens.json').read_text(encoding='utf-8'))
        css=(ROOT/'site/dist/style.css').read_text(encoding='utf-8')
        self.assertEqual(tokens['primitive'],theme['colors'])
        for name in ('bg','surface','raised','text','muted','accent','focus'):
            self.assertIn('--'+name+':'+theme['colors'][name],css)
        self.assertIn('--control-border:'+theme['colors']['control_border'],css)

    def test_metadata_must_be_verified_before_output_is_written(self):
        version='1.0.1';sha='a'*40
        assets=[{'name':f'DocFlow-Lite-{version}-{s}.zip','sha256':'b'*64,'size':123} for s in ('Windows-x64-Portable','Source','ThirdParty-Sources')]
        manifest={'version':version,'tag':'v'+version,'release_target':sha,'assets':assets}
        release={'tag_name':'v'+version,'draft':False,'prerelease':False,'immutable':True,'published_at':'2026-11-21T00:00:00Z',
                 'assets':[{**a,'state':'uploaded','browser_download_url':build_release_site.REPO+'/releases/download/v'+version+'/'+a['name']} for a in assets]}
        def fetch(url):return release if '/releases/' in url else {'object':{'type':'commit','sha':sha}}
        with TemporaryDirectory() as folder:
            out=Path(folder)/'build'
            with self.assertRaisesRegex(ValueError,'metadata must be verified'):
                build_release_site.activate(out,manifest,fetch,lambda url:'b'*64)
            self.assertFalse(out.exists())

    def test_primary_pages_have_explanations_and_no_fake_product_claims(self):
        home=(ROOT/'site/dist/index.html').read_text(encoding='utf-8')
        service=(ROOT/'site/dist/service.html').read_text(encoding='utf-8')
        self.assertIn('от 5 000 ₽',home);self.assertIn('от 9 000 ₽',home)
        self.assertIn('Приложение бесплатно',home)
        self.assertIn('Иллюстрация связей на вымышленных данных',service)
        self.assertIn('Прямое подключение не заявляется',service)
        for name in ('index.html','service.html','download.html','docs.html'):
            text=(ROOT/'site/dist'/name).read_text(encoding='utf-8')
            tags=Tags(text).tags
            self.assertEqual(sum(t=='h1' for t,a in tags),1)
            self.assertFalse(any(t in {'form','input','textarea'} for t,a in tags))
            if name!='download.html':
                self.assertIn('data-release-preview',text)


if __name__=='__main__':unittest.main()
