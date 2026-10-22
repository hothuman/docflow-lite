"""Offline URL fixtures do not assert that a fixture site is published."""
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree
import importlib.util
import re
import shutil
import unittest

SITE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_url", SITE / "scripts/configure_public_url.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ROOT_URL = "https://docflow-lite.pages.dev/"
PAGES_FIXTURE = "https://hothuman.github.io/docflow-lite/"


class PublicURLTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for name in ("index.html", "privacy.html", "terms.html"):
            shutil.copyfile(SITE / "dist" / name, self.directory / name)

    def canonical(self, name):
        text = (self.directory / name).read_text(encoding="utf-8")
        return re.findall(r'<link rel="canonical" href="([^"]+)"', text)

    def test_root_and_direct_page_canonicals(self):
        self.assertEqual(module.configure(ROOT_URL, self.directory), ROOT_URL)
        self.assertEqual(self.canonical("index.html"), [ROOT_URL])
        self.assertEqual(self.canonical("privacy.html"), [ROOT_URL + "privacy.html"])
        self.assertEqual(self.canonical("terms.html"), [ROOT_URL + "terms.html"])

    def test_github_pages_subdirectory(self):
        self.assertEqual(module.configure(PAGES_FIXTURE.rstrip("/"), self.directory), PAGES_FIXTURE)
        text = (self.directory / "index.html").read_text(encoding="utf-8")
        self.assertIn('property="og:url" content="' + PAGES_FIXTURE + '"', text)
        self.assertIn('property="og:image" content="' + PAGES_FIXTURE + 'assets/social-card.png"', text)
        self.assertEqual(self.canonical("privacy.html"), [PAGES_FIXTURE + "privacy.html"])

    def test_switching_hosts_is_idempotent(self):
        module.configure(ROOT_URL, self.directory)
        module.configure(PAGES_FIXTURE, self.directory)
        before = {p.name:p.read_bytes() for p in self.directory.iterdir()}
        module.configure(PAGES_FIXTURE, self.directory)
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.directory.iterdir()})
        for name in ("index.html", "privacy.html", "terms.html"):
            text = (self.directory / name).read_text(encoding="utf-8")
            self.assertEqual(text.count('rel="canonical"'), 1)
            self.assertEqual(text.count('property="og:url"'), 1)

    def test_sitemap_and_robots_scope(self):
        module.configure(PAGES_FIXTURE, self.directory)
        tree = ElementTree.parse(self.directory / "sitemap.xml")
        urls = [n.text for n in tree.findall(".//{*}loc")]
        self.assertEqual(urls, [PAGES_FIXTURE])
        robots = (self.directory / "robots.txt").read_text()
        self.assertIn("Allow: /docflow-lite/", robots)
        self.assertIn("Sitemap: " + PAGES_FIXTURE + "sitemap.xml", robots)
        self.assertIn('content="noindex,follow"', (self.directory / "privacy.html").read_text())

    def test_resources_keep_subdirectory(self):
        module.configure(PAGES_FIXTURE, self.directory)
        for name in ("index.html", "privacy.html", "terms.html"):
            page = PAGES_FIXTURE + (name if name != "index.html" else "")
            text = (self.directory / name).read_text(encoding="utf-8")
            for value in re.findall(r'(?:href|src|poster)="([^"]+)"', text):
                if urlsplit(value).scheme:
                    continue
                absolute = urljoin(page, value)
                self.assertTrue(urlsplit(absolute).path.startswith("/docflow-lite/"), value)

    def test_rejects_unsafe_or_ambiguous_urls_without_writes(self):
        invalid = ["http://hothuman.github.io/docflow-lite/", "https://x@hothuman.github.io/",
                   "https://hothuman.github.io/?token=x", "https://hothuman.github.io/#x",
                   "https://hothuman.github.io/../docflow-lite/", "https://hothuman.github.io/a//b/",
                   "https://hothuman.github.io/%2e%2e/", "https://hothuman.github.io/a%2fb/",
                   "https://hothuman.github.io:0/", "https://hothuman.github.io/a b/",
                   "https://hothuman.github.io/a\\b/"]
        before = {p.name:p.read_bytes() for p in self.directory.iterdir()}
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.configure(value, self.directory)
            self.assertEqual(before, {p.name:p.read_bytes() for p in self.directory.iterdir()})


if __name__ == "__main__":
    unittest.main()
