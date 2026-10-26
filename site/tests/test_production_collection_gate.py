"""Production checks use only the stdlib, including in isolated website CI."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_public_site as production

class ProductionCollectionTests(unittest.TestCase):
    def collection_check(self,added):
        body=(ROOT/'dist/index.html').read_text(encoding='utf-8').replace('</body>',added+'</body>').encode()
        def get(url):
            if url.endswith('/') or url.endswith('/index.html'):raw=body
            elif url.endswith('/sitemap.xml'):raw=b'<urlset/>'
            elif url.endswith('/robots.txt'):raw=b'User-agent: *\nDisallow: /'
            else:raw=b'placeholder'
            return {'final_url':url,'status':200,'headers':{},'redirects':[],'sha256':'synthetic'},raw
        with patch.object(production,'get',get):report=production.verify('https://docflow-lite.pages.dev/')
        return next(c['passed'] for c in report['checks'] if c['check']=='no lead form or collection inputs')
    def test_current_contact_brief_passes(self):self.assertTrue(self.collection_check(''))
    def test_reintroduced_lead_form_is_rejected(self):self.assertFalse(self.collection_check('<form action="/lead"><input name="email"></form>'))
    def test_orphan_email_input_is_rejected(self):self.assertFalse(self.collection_check('<input name="email">'))
    def test_orphan_message_input_is_rejected(self):self.assertFalse(self.collection_check('<textarea name="message"></textarea>'))
    def test_submit_control_is_rejected(self):self.assertFalse(self.collection_check('<button type="submit">Отправить</button>'))
