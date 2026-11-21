"""Owner-reference and mixed-surface regressions, not a new design concept."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
SITE=ROOT/'site/dist'

def ratio(a,b):
    def luminance(value):
        channels=[int(value[i:i+2],16)/255 for i in (1,3,5)]
        channels=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
        return sum(v*w for v,w in zip(channels,(.2126,.7152,.0722)))
    low,high=sorted((luminance(a),luminance(b)))
    return (high+.05)/(low+.05)

class IndustrialContrastTests(unittest.TestCase):
    def test_approved_original_reference_is_preserved(self):
        source=ROOT/'docs/brand/reference/01-industrial-contrast.html'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),'4d22b04f030eeed443ae8cd9ce3d0f3a18b5ef1b535f48c83261ab48e6435a49')
        proof=json.loads((ROOT/'docs/brand/ASSET_PROVENANCE.json').read_text(encoding='utf-8'))
        self.assertTrue(proof['design_reference']['owner_approved'])

    def test_primary_roles_match_the_approved_reference(self):
        reference=(ROOT/'docs/brand/reference/01-industrial-contrast.html').read_text(encoding='utf-8-sig')
        colors=json.loads((ROOT/'docs/brand/atelier-theme.json').read_text(encoding='utf-8'))['colors']
        pairs={'bg':'bg','surface':'bg2','text':'ink','muted':'muted','accent':'acid'}
        for actual,original in pairs.items():
            value=re.search('--'+original+r':(#[0-9a-f]{6})',reference)[1]
            self.assertEqual(colors[actual],value)

    def test_paper_and_accent_surfaces_keep_readable_states(self):
        tokens=json.loads((ROOT/'docs/brand/tokens.json').read_text(encoding='utf-8'))
        paper=tokens['paper'];dark=tokens['primitive']
        for a,b in [(paper['text'],paper['bg']),(paper['muted'],paper['bg']),
                    (paper['accent'],paper['bg']),(paper['error'],paper['bg']),
                    (dark['accent_text'],dark['accent']),('#344b32',dark['accent'])]:
            self.assertGreaterEqual(ratio(a,b),4.5,(a,b))
        for a,b in [(paper['focus'],paper['bg']),(paper['control_border'],paper['bg']),
                    (dark['control_border'],dark['raised']),(dark['focus'],dark['raised'])]:
            self.assertGreaterEqual(ratio(a,b),3,(a,b))

    def test_home_follows_the_reference_hierarchy_and_uses_real_screens(self):
        page=(SITE/'index.html').read_text(encoding='utf-8')
        self.assertIn('<h1>Excel.<br>Word.<br><em>Готово.</em></h1>',page)
        self.assertIn('class="section light-section" id="product"',page)
        self.assertIn('class="section light-section workflow-section" id="workflow"',page)
        self.assertLess(page.index('id="product"'),page.index('id="workflow"'))
        self.assertLess(page.index('id="workflow"'),page.index('id="screens"'))
        for name,image in [('index.html','core-current.png'),('service.html','service-current.png')]:
            text=(SITE/name).read_text(encoding='utf-8')
            hero=re.search(r'<figure class="contrast-visual.*?</figure>',text,re.S)[0]
            self.assertIn('src="assets/'+image+'"',hero)
            self.assertIn('НАСТОЯЩИЙ ЭКРАН',hero)
            self.assertNotIn('fake-table',hero)

    def test_commercial_offer_avoids_unverified_popularity_claims(self):
        page=(SITE/'index.html').read_text(encoding='utf-8')
        self.assertIn('Приложение бесплатно',page)
        self.assertIn('Индивидуальная настройка документов — отдельная услуга',page)
        self.assertIn('<p class="price">0 ₽</p>',page)
        self.assertIn('от 5 000 ₽',page);self.assertIn('от 9 000 ₽',page)
        self.assertNotIn('POPULAR',page)

if __name__=='__main__':unittest.main()
