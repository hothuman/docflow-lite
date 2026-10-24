"""Check actual rendered PDFs; pdfplumber is an optional QA dependency, not runtime.

Input is the index produced by the document render workflow. This does not
substitute for opening the page PNGs or for Microsoft Word acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pdfplumber


def verify(index_path):
    index = json.loads(index_path.read_text(encoding='utf-8'))
    checks = []
    for doc in index['documents']:
        source = Path(doc['docx'])
        assert hashlib.sha256(source.read_bytes()).hexdigest() == doc['sha256'], source
        with pdfplumber.open(doc['pdf']) as pdf:
            assert len(pdf.pages) == len(doc['pages'])
            for page in pdf.pages:
                assert page.extract_text().strip(), (doc['name'], 'empty page')
                for image in page.images:
                    assert image['x0'] >= 0 and image['x1'] <= page.width + 1
                    assert image['top'] >= 0 and image['bottom'] <= page.height + 1
            if doc['name'] in ('combined', 'complex-landscape-with-images'):
                found = []
                for number, page in enumerate(pdf.pages, 1):
                    for caption in page.search(r'Вымышленная схема [12]'):
                        pictures = [im for im in page.images if im['width'] * im['height'] > 6000
                                    and 0 <= im['top'] - caption['bottom'] < 50]
                        assert len(pictures) == 1, (doc['name'], number, caption['text'])
                        found.append({'caption':caption['text'], 'page':number,
                                      'gap_points':round(pictures[0]['top'] - caption['bottom'], 2)})
                assert len(found) == 2 and len({x['caption'] for x in found}) == 2
                checks.append({'document':doc['name'], 'caption_and_picture_same_page':found})
    return {'status':'passed', 'documents':len(index['documents']),
            'pages':sum(len(d['pages']) for d in index['documents']), 'checks':checks,
            'scope':'Rendered LibreOffice PDF geometry and text, not Word or human visual review'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.index)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
