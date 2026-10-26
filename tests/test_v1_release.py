"""Version and approval boundaries for a stable release; no publication."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from docflow.versioning import stage,is_prerelease

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))


@pytest.mark.parametrize('version,label,pre',[('0.3.0a6','alpha',True),('1.0.0rc1','RC',True),('1.0.0','stable',False)])
def test_stage_is_explicit(version,label,pre):
    assert stage(version)==label and is_prerelease(version)==pre


@pytest.mark.parametrize('version',['1.0','1.0.0-final','1.0.0rc0','1.0.0evil','1.0.0\n'])
def test_ambiguous_stage_is_rejected(version):
    with pytest.raises(ValueError):stage(version)


def test_stable_draft_requires_owner_approval_even_for_verified_assets(tmp_path,monkeypatch):
    import prepare_github_draft as draft
    monkeypatch.setattr(draft,'verify',lambda path:{'version':'1.0.0','build_commit':'a'*40})
    notes=tmp_path/'notes.md';notes.write_text('DocFlow 1.0.0')
    with pytest.raises(ValueError,match='approval'):draft.prepare(tmp_path,'a'*40,notes)
    result=draft.prepare(tmp_path,'a'*40,notes,stable_approved=True)
    assert result['draft'] is True and result['prerelease'] is False
    assert result['make_latest']=='false' and 'stable' in result['name']


def test_rc_draft_cannot_silently_be_stable(tmp_path,monkeypatch):
    import prepare_github_draft as draft
    monkeypatch.setattr(draft,'verify',lambda path:{'version':'1.0.0rc1','build_commit':'a'*40})
    notes=tmp_path/'notes.md';notes.write_text('DocFlow 1.0.0rc1')
    result=draft.prepare(tmp_path,'a'*40,notes)
    assert result['draft'] is True and result['prerelease'] is True
    assert 'alpha' not in result['name']


def test_sbom_uses_actual_notices_and_exact_source_target(tmp_path):
    from generate_sbom import generate
    notice=tmp_path/'license.txt';notice.write_bytes(b'synthetic notice')
    evidence={'python':'3.14.10','distributions':[{'name':'example','version':'1.2','license_files':['license.txt']}], 'source_archives':[]}
    (tmp_path/'THIRD-PARTY-LICENSES.json').write_text(json.dumps(evidence))
    sbom=generate(tmp_path,'1.0.0rc1','a'*40)
    assert sbom['bomFormat']=='CycloneDX' and sbom['specVersion']=='1.6'
    assert sbom['metadata']['component']['properties']==[{'name':'docflow:source-commit','value':'a'*40}]
    assert any(c.get('purl')=='pkg:pypi/example@1.2' for c in sbom['components'])
    notice.unlink()
    with pytest.raises(ValueError,match='absent'):generate(tmp_path,'1.0.0rc1','a'*40)


@pytest.mark.parametrize('version,prerelease',[('1.0.0rc1',True),('1.0.0',False)])
def test_site_activation_checks_exact_stage_and_immutable_published_bytes(tmp_path,version,prerelease):
    sys.path.insert(0,str(ROOT/'site/scripts'))
    import build_release_site as site
    sha='a'*40
    assets=[{'name':f'DocFlow-Lite-{version}-{suffix}.zip','sha256':'b'*64,'size':123}
            for suffix in ('Windows-x64-Portable','Source','ThirdParty-Sources')]
    manifest={'version':version,'tag':'v'+version,'release_target':sha,'assets':assets}
    release={'tag_name':'v'+version,'draft':False,'prerelease':prerelease,'immutable':True,'published_at':'2026-10-26T00:00:00Z',
             'assets':[{**a,'state':'uploaded','browser_download_url':site.REPO+'/releases/download/v'+version+'/'+a['name']} for a in assets]}
    def fetch(url):return release if '/releases/' in url else {'object':{'type':'commit','sha':sha}}
    # A released alpha cannot be presented as stable, and vice versa.
    release['prerelease']=not prerelease
    with pytest.raises(ValueError):site.activate(tmp_path/'wrong',manifest,fetch,lambda u:'b'*64)
    assert not (tmp_path/'wrong').exists()
    release['prerelease']=prerelease;release['immutable']=False
    with pytest.raises(ValueError,match='immutable'):site.activate(tmp_path/'mutable',manifest,fetch,lambda u:'b'*64)
    release['immutable']=True
    site.activate(tmp_path/'verified',manifest,fetch,lambda u:'b'*64)
    text=(tmp_path/'verified/index.html').read_text(encoding='utf-8')
    info=json.loads((tmp_path/'verified/build-info.json').read_text(encoding='utf-8'))
    assert info['application_version']==version and info['public_prerelease']==prerelease
    assert '/releases/download/v'+version+'/' in text and 'SHA256 Portable: '+'b'*64 in text
    assert 'alpha 0.3.0a6' not in text and '<form' not in text
    assert not info['lead_collection_enabled'] and not info['indexing_enabled']
