"""CycloneDX inventory of the actual collected distribution, no license inference."""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4


def generate(bundle,version,commit):
    bundle=Path(bundle)
    evidence=json.loads((bundle/'THIRD-PARTY-LICENSES.json').read_text(encoding='utf-8'))
    components=[]
    for d in evidence['distributions']:
        name=d['name'];normalized=name.lower().replace('_','-')
        purl='pkg:pypi/'+quote(normalized,safe='')+'@'+d['version']
        notices=[]
        for name in d['license_files']:
            path=bundle/name
            if not path.is_file():raise ValueError('SBOM notice is absent: '+name)
            notices.append({'name':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        components.append({'type':'library','name':d['name'],'version':d['version'],'purl':purl,'bom-ref':purl,
                           'properties':[{'name':'docflow:license-notices','value':json.dumps(notices)}]})
    components.append({'type':'framework','name':'CPython','version':evidence['python'],'bom-ref':'cpython',
                       'externalReferences':[{'type':'website','url':'https://www.python.org/'}]})
    for source in evidence['source_archives']:
        components.append({'type':'library','name':source['component']+' sources','version':source['version'],
                           'bom-ref':'source:'+source['component'],
                           'externalReferences':[{'type':'distribution','url':source['url'],
                                                  'hashes':[{'alg':'SHA-256','content':source['sha256']}]}]})
    app={'type':'application','name':'DocFlow Core / Lite + Service','version':version,'bom-ref':'docflow',
         'properties':[{'name':'docflow:source-commit','value':commit}]}
    return {'bomFormat':'CycloneDX','specVersion':'1.6','serialNumber':'urn:uuid:'+str(uuid4()),'version':1,
            'metadata':{'component':app},'components':components,
            'dependencies':[{'ref':'docflow','dependsOn':[c['bom-ref'] for c in components]}]}
