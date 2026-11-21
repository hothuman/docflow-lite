"""Paid-setup context stays local until the visitor chooses a contact app."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / 'site/dist'
PACKAGES = {'one': '1 DOCX', 'bundle': 'до 3 DOCX', 'service': 'Service'}


class Parsed(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.tags=[]; self.feed(text)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class CommercialFlowTests(unittest.TestCase):
    def test_privacy_describes_the_absent_form_without_inventing_approval(self):
        text=(SITE/'privacy.html').read_text(encoding='utf-8')
        self.assertIn('нет формы заявки', text)
        self.assertNotIn('Поля имени, контакта и описания задачи заблокированы', text)
        self.assertNotIn('пометки «Скоро»', text)
        self.assertIn('Проект для утверждения владельцем', text)
        self.assertIn('Cloudflare Pages', text)
        self.assertIn('не означает подтверждённое соответствие', text)
        terms=(SITE/'terms.html').read_text(encoding='utf-8')
        self.assertNotIn('Форма сайта заблокирована', terms)
        self.assertIn('Условия подготовлены к согласованию', terms)

    def test_each_package_has_the_same_complete_static_handoff_on_both_pages(self):
        for page in ('index.html','service.html'):
            text=(SITE/page).read_text(encoding='utf-8')
            panels=re.findall(r'<section\b[^>]*data-request-package="([a-z]+)".*?</section>',text,re.S)
            self.assertCountEqual(panels, PACKAGES, page)
            for key,label in PACKAGES.items():
                with self.subTest(page=page,package=key):
                    panel=re.search(r'<section\b[^>]*data-request-package="'+key+r'".*?</section>',text,re.S)[0]
                    tags=Parsed(panel).tags
                    mail=next(a['href'] for t,a in tags if t=='a' and 'data-request-email' in a)
                    parsed=urlsplit(mail);query=parse_qs(parsed.query)
                    self.assertEqual(parsed.scheme,'mailto')
                    self.assertEqual(parsed.path,'docflow.lite@gmail.com')
                    self.assertIn(label,query['subject'][0])
                    message=re.search(r'<pre\b[^>]*data-request-message[^>]*>(.*?)</pre>',panel,re.S)[1]
                    self.assertEqual(query['body'][0],message)
                    self.assertIn('без клиентских данных',message)
                    self.assertIn('не отправляется',panel)
                    self.assertTrue(any(t=='button' and 'data-copy-request' in a and 'hidden' in a for t,a in tags))
                    telegram=next(a for t,a in tags if t=='a' and 'data-request-telegram' in a)
                    self.assertEqual(telegram['href'],'https://t.me/de1grace')
                    self.assertNotIn('?',telegram['href'])

    def test_selected_package_is_addressable_without_javascript_or_storage(self):
        for page in ('index.html','service.html'):
            tags=Parsed((SITE/page).read_text(encoding='utf-8')).tags
            ids=[a['id'] for _,a in tags if 'id' in a]
            self.assertEqual(len(ids),len(set(ids)),page)
            for key in PACKAGES:
                self.assertIn('request-'+key,ids)
                self.assertTrue(any(t=='a' and a.get('href')=='#request-'+key and a.get('data-select-request')==key for t,a in tags))
                panel=next(a for t,a in tags if t=='section' and a.get('data-request-package')==key)
                self.assertNotIn('hidden',panel,'All package messages must be readable without JS')
            self.assertFalse(any(t in ('form','input','textarea') or (t=='button' and a.get('type')=='submit') for t,a in tags))

    def test_demo_continues_to_the_existing_offer_and_deliverables_are_visible(self):
        home=(SITE/'index.html').read_text(encoding='utf-8')
        demo=re.search(r'<section\b[^>]*id="example".*?</section>',home,re.S)[0]
        self.assertIn('href="#services"',demo)
        for text in ('профиль сопоставления','Проверочные DOCX','Инструкция','от 5 000 ₽','от 9 000 ₽'):
            self.assertIn(text,home)
        self.assertIn('за настройку шаблонов',home)
        self.assertIn('Создание документов в программе остаётся бесплатным',home)
        service=(SITE/'service.html').read_text(encoding='utf-8')
        self.assertIn('Что означает номер аппарата',service)
        self.assertIn('одного оператора',service)
        self.assertIn('индивидуальная оценка',service)

    def test_legal_delta_reconstructs_the_preserved_baseline(self):
        proof=json.loads((ROOT/'docs/brand/ASSET_PROVENANCE.json').read_text(encoding='utf-8'))
        delta=proof['legal_factual_update']
        self.assertEqual(delta['date'],'2026-11-22')
        self.assertFalse(delta['approves_service_terms_or_policy'])
        self.assertEqual(set(delta['pages']),{'privacy.html','terms.html'})
        for name,item in delta['pages'].items():
            main=re.search(r'<main\b.*?</main>',(SITE/name).read_text(encoding='utf-8'),re.S)[0]
            self.assertEqual(hashlib.sha256(main.encode()).hexdigest(),item['current_main_sha256'])
            for change in reversed(item['replacements']):
                self.assertEqual(main.count(change['after']),1)
                main=main.replace(change['after'],change['before'],1)
            self.assertEqual(hashlib.sha256(main.encode()).hexdigest(),proof['approved_legal_main_sha256'][name])


if __name__=='__main__': unittest.main()
