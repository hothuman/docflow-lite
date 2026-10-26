"""Offline published-layout fixture for browser CI; never upload this directory.

Uses the real activation path with synthetic release metadata/hash I/O. This
catches narrow-screen SHA/download copy defects without an external release.
"""
from pathlib import Path
import argparse,json,sys
SITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SITE/'scripts'))
import build_release_site


def build(output,version='1.0.0rc1'):
    commit='a'*40
    names=[f'DocFlow-Lite-{version}-{suffix}.zip' for suffix in ('Windows-x64-Portable','Source','ThirdParty-Sources')]
    manifest={'version':version,'tag':'v'+version,'release_target':commit,'assets':[{'name':n,'sha256':'b'*64,'size':123} for n in names]}
    release={'tag_name':manifest['tag'],'draft':False,'prerelease':build_release_site.is_prerelease(version),'immutable':True,'published_at':'2026-10-26T00:00:00Z','assets':[{**a,'state':'uploaded','browser_download_url':build_release_site.REPO+'/releases/download/'+manifest['tag']+'/'+a['name']} for a in manifest['assets']]}
    def fetch(url):return release if '/releases/tags/' in url else {'object':{'type':'commit','sha':commit}}
    build_release_site.activate(output,manifest,fetch,lambda url:'b'*64)
    path=output/'build-info.json';info=json.loads(path.read_text(encoding='utf-8'));info['synthetic_acceptance_fixture']=True;path.write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')
    print('Synthetic activated-layout fixture; not public release verification; NEVER DEPLOY')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=SITE/'build');p.add_argument('--version',choices=['0.3.0a6','1.0.0rc1','1.0.0'],default='1.0.0rc1');args=p.parse_args();build(args.output,args.version)
