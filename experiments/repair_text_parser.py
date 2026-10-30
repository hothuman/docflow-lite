"""PROTOTYPE / NOT_APPROVED_FOR_DELIVERY. Synthetic text only. No app imports."""
import argparse,json,re

FIELDS={'жалоба':'complaint','диагностика':'defects','план':'plan'}
def propose(raw):
    result={'status':'PROTOTYPE / NOT_APPROVED_FOR_DELIVERY','suggestions':{},'review':[],'writes_database':False,'network':False,'money_dates_status':False}
    if not isinstance(raw,str) or len(raw)>5000 or len(raw.splitlines())>30:
        result['review'].append('Unsupported input size/type');return result
    if any(ord(c)<32 and c not in '\n\t\r' for c in raw) or re.search(r'(?i)(ignore|system\s*:|игнорир|удали.*баз|https?://|file:)',raw):
        result['review'].append('Untrusted instruction or control sequence; no suggestions');return result
    duplicates=set()
    for line in raw.splitlines():
        match=re.fullmatch(r'\s*(Жалоба|Диагностика|План)\s*:\s*(\S.*)',line,re.I)
        if not match:result['review'].append('Unrecognized line: manual review required');continue
        key=FIELDS[match[1].casefold()]
        if key in result['suggestions'] or key in duplicates:result['suggestions'].pop(key,None);duplicates.add(key);result['review'].append('Duplicate field: '+key);continue
        result['suggestions'][key]={'text':match[2],'source_line':line,'requires_human_confirmation':True}
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--synthetic-text',required=True);args=parser.parse_args()
    print(json.dumps(propose(args.synthetic_text),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
