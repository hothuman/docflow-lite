"""Prepare a local GitHub draft payload from verified exact-target release assets."""
import argparse
import json
from pathlib import Path
from release_candidate import verify


def prepare(directory,target,notes):
    report=verify(directory)
    if report['build_commit']!=target:
        raise ValueError('Build commit differs from the release target; rebuild the exact target')
    text=Path(notes).read_text(encoding='utf-8')
    if report['version'] not in text:
        raise ValueError('Release notes do not describe the candidate version')
    return {'tag_name':'v'+report['version'],'target_commitish':target,
            'name':'DocFlow v'+report['version']+' — Core + Service alpha',
            'draft':True,'prerelease':True,'make_latest':'false','body':text,
            'asset_names':[p.name for p in sorted(Path(directory).iterdir()) if p.is_file()]}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--target',required=True)
    p.add_argument('--notes',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:result=prepare(a.directory,a.target,a.notes)
    except (ValueError,OSError,KeyError) as exc:p.exit(1,str(exc)+'\n')
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'tag':result['tag_name'],'target':a.target,'draft':True,'assets':len(result['asset_names'])}))
