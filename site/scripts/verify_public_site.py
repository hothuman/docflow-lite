"""Real HTTPS checks for an existing deployment; no uploads or form submission.

Run again with --expect-pdf after Direct Upload. Exit 1 means a check failed,
including a deployment that still serves the previous PDF. TLS uses this
machine's trusted certificate store; an intercepting proxy limits origin checks.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, HTTPSHandler, Request
from xml.etree import ElementTree

from configure_public_url import normalize_base


class Redirects(HTTPRedirectHandler):
    def __init__(self):
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append({'status':code, 'from':req.full_url, 'to':newurl})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Page(HTMLParser):
    def __init__(self, data):
        super().__init__()
        self.tags = []
        self.feed(data.decode('utf-8'))

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def get(url):
    redirects = Redirects()
    opener = build_opener(redirects, HTTPSHandler(context=ssl.create_default_context()))
    try:
        response = opener.open(Request(url, headers={'User-Agent':'DocFlow-Lite-Website-QA'}), timeout=25)
    except HTTPError as exc:
        response = exc  # 404 is an HTTP response, not a successful page.
    with response:
        body = response.read()
        result = {'requested_url':url, 'final_url':response.url, 'status':response.code,
                  'redirects':redirects.chain, 'headers':dict(response.headers.items()),
                  'bytes':len(body), 'sha256':sha256(body).hexdigest()}
    return result, body


def verify(base, expected_pdf=None, expected_demo=None, release_manifest=None):
    home, _ = normalize_base(base)
    responses, bodies, checks = {}, {}, []

    def check(name, passed):
        checks.append({'check':name, 'passed':bool(passed)})

    paths = ['', 'privacy.html', 'terms.html', '__docflow_verification_missing_20261022__/',
             'index.html', 'robots.txt', 'sitemap.xml', 'assets/DocFlow-Lite-Offer.pdf',
             'app.js', 'assets/demo-data.js']
    if expected_demo is not None:
        paths.append('assets/DocFlow-Lite-Demo.zip')
    if release_manifest is not None:
        paths += ['service.html','software.html','build-info.json']
    for path in paths:
        try:
            responses[path], bodies[path] = get(urljoin(home, path))
        except (URLError, OSError, ValueError) as exc:
            responses[path] = {'requested_url':urljoin(home,path), 'error':str(exc)}
            checks.append({'check':'GET '+path, 'passed':False})

    for path in paths:
        if path not in bodies:
            continue
        r = responses[path]
        check('HTTPS '+path, urlsplit(r['final_url']).scheme == 'https')
        check('HTTP status '+path, r['status'] == (404 if path.startswith('__docflow_') else 200))
        if path in ('', 'privacy.html', 'terms.html', 'service.html', 'software.html') or path.startswith('__docflow_'):
            h = {k.lower():v for k,v in r['headers'].items()}
            csp = {part.strip() for part in h.get('content-security-policy','').split(';')}
            check('CSP disabled data submission '+path,
                  {"form-action 'none'", "connect-src 'none'"}.issubset(csp))
            check('nosniff '+path, h.get('x-content-type-options') == 'nosniff')
            check('Referrer-Policy '+path, h.get('referrer-policy') == 'strict-origin-when-cross-origin')
            check('X-Robots-Tag '+path, 'noindex' in h.get('x-robots-tag','').lower())

    if 'index.html' in bodies:
        check('index redirect', bool(responses['index.html']['redirects']) and
              responses['index.html']['redirects'][0]['status'] == 301 and
              responses['index.html']['final_url'] == home)
    if '' in bodies:
        page = Page(bodies[''])
        check('HTML noindex', any(t=='meta' and a.get('name')=='robots' and
                                 'noindex' in a.get('content','') for t,a in page.tags))
        forms = [a for t,a in page.tags if t=='form']
        check('no form endpoint', len(forms)==1 and 'action' not in forms[0])
        check('form fieldset disabled', any(t=='fieldset' and 'disabled' in a for t,a in page.tags))
        check('submit disabled', any(t=='button' and a.get('type')=='submit' and 'disabled' in a for t,a in page.tags))
    if 'robots.txt' in bodies:
        check('robots disallow', 'Disallow: /' in bodies['robots.txt'].decode())
    if 'sitemap.xml' in bodies:
        try:
            check('sitemap empty', not ElementTree.fromstring(bodies['sitemap.xml']).findall('.//{*}loc'))
        except ElementTree.ParseError:
            check('sitemap valid XML', False)
    for path in ('app.js', 'assets/demo-data.js'):
        if path in bodies:
            check('no data submission/storage calls '+path, not any(token in bodies[path] for token in
                  (b'fetch(', b'XMLHttpRequest', b'sendBeacon', b'localStorage', b'sessionStorage', b'indexedDB', b'document.cookie')))
    if expected_pdf is not None:
        expected_hash = sha256(expected_pdf.read_bytes()).hexdigest()
        check('deployed PDF SHA256 matches expected', responses.get('assets/DocFlow-Lite-Offer.pdf',{}).get('sha256') == expected_hash)
    else:
        expected_hash = None
    expected_demo_hash = sha256(expected_demo.read_bytes()).hexdigest() if expected_demo is not None else None
    if expected_demo is not None:
        check('deployed demo SHA256 matches expected', responses.get('assets/DocFlow-Lite-Demo.zip',{}).get('sha256') == expected_demo_hash)
    if release_manifest is not None:
        from build_release_site import verify_published
        try:
            proof=verify_published(release_manifest)
            check('published release target and all asset SHA256',True)
        except (OSError,ValueError,KeyError) as exc:
            check('published release target and all asset SHA256',False)
        info=json.loads(bodies.get('build-info.json',b'{}'))
        check('deployed application version',info.get('application_version')==release_manifest['version'])
        check('deployed source commit',info.get('source_commit')==release_manifest['release_target'])
        check('deployed collection remains disabled',info.get('lead_collection_enabled') is False)
        name='DocFlow-Lite-'+release_manifest['version']+'-Windows-x64-Portable.zip'
        url='https://github.com/hothuman/docflow-lite/releases/download/'+release_manifest['tag']+'/'+name
        check('deployed Windows link matches verified asset',url.encode() in bodies.get('',b''))
    return {'checked_at_utc':datetime.now(timezone.utc).isoformat(), 'public_url':home,
            'expected_pdf_sha256':expected_hash, 'expected_demo_sha256':expected_demo_hash,
            'all_checks_passed':all(c['passed'] for c in checks),
            'checks':checks, 'responses':responses,
            'scope':'Real GET responses with normal TLS verification. No form submission or deployment. '
                    'Static source checks are not a full browser network capture. '
                    'Proxy trust does not independently validate the Cloudflare origin certificate.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://docflow-lite.pages.dev/')
    parser.add_argument('--expect-pdf', type=Path)
    parser.add_argument('--expect-demo', type=Path)
    parser.add_argument('--release-manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest=json.loads(args.release_manifest.read_text(encoding="utf-8")) if args.release_manifest else None
    result = verify(args.url, args.expect_pdf, args.expect_demo, manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    failures = [c['check'] for c in result['checks'] if not c['passed']]
    print(json.dumps({'passed':not failures, 'checks':len(result['checks']), 'failures':failures}, ensure_ascii=False))
    raise SystemExit(1 if failures else 0)
