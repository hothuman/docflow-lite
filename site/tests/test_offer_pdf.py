"""Offline regression for the fixed static PDF, using only the standard library.

This checks its literal URI annotations and ASCII text in Flate content streams.
It is not a general PDF parser or a replacement for rendering/visual inspection.
"""
from pathlib import Path
import re
import unittest
import zlib
from zipfile import ZipFile

PDF = Path(__file__).resolve().parents[1] / 'dist/assets/DocFlow-Lite-Offer.pdf'
OFFICIAL = b'https://docflow-lite.pages.dev/'
LEGACY_HOST = b'docflow-lite.' + b'rostg2007.chatgpt.site'


class OfferPDFTests(unittest.TestCase):
    def test_clickable_site_and_contact_uris(self):
        data = PDF.read_bytes()
        uris = re.findall(rb'/URI\s*\(([^)]*)\)', data)
        self.assertCountEqual(uris, [OFFICIAL, b'https://t.me/de1grace',
                                    b'mailto:docflow.lite@gmail.com'])
        self.assertNotIn(LEGACY_HOST, data)

    def test_visible_url_is_updated_in_pdf_content(self):
        data = PDF.read_bytes()
        self.assertTrue(data.startswith(b'%PDF-'))
        self.assertTrue(data.rstrip().endswith(b'%%EOF'))
        decoded = []
        for match in re.finditer(rb'\bstream\r?\n(.*?)\r?\nendstream', data, re.S):
            stream = match.group(1)
            try:
                decoded.append(zlib.decompress(stream))
            except zlib.error:
                decoded.append(stream)
        self.assertTrue(decoded, 'Expected PDF content streams')
        self.assertEqual(sum(stream.count(b'(' + OFFICIAL + b')') for stream in decoded), 1)
        self.assertFalse(any(LEGACY_HOST in stream for stream in decoded))

    def test_current_demo_archive_uses_the_official_site(self):
        with ZipFile(PDF.with_name('DocFlow-Lite-Demo.zip')) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn(OFFICIAL, archive.read('docflow-lite/README.md'))
            self.assertFalse(any(LEGACY_HOST in archive.read(name) for name in archive.namelist()))


if __name__ == '__main__':
    unittest.main()
