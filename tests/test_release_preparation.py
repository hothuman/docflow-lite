"""Release safety regressions with synthetic assets and no network/publication."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import importlib.util
import json
import sys
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"site/scripts"))
import build_release_site
spec=importlib.util.spec_from_file_location("release_candidate",ROOT/"scripts/release_candidate.py")
candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)

class ReleasePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.version="0.3.0a6";self.sha="a"*40
        names=[f"DocFlow-Lite-{self.version}-{s}.zip" for s in ("Windows-x64-Portable","Source","ThirdParty-Sources")]
        self.manifest={"version":self.version,"tag":"v"+self.version,"release_target":self.sha,
                       "assets":[{"name":n,"sha256":"b"*64,"size":123} for n in names]}
        self.release={"tag_name":"v"+self.version,"draft":False,"prerelease":True,"published_at":"2026-10-25T00:00:00Z",
                      "assets":[{**a,"state":"uploaded","browser_download_url":build_release_site.REPO+"/releases/download/v"+self.version+"/"+a["name"]} for a in self.manifest["assets"]]}
    def fetch(self,url):
        return self.release if "/releases/tags/" in url else {"object":{"type":"commit","sha":self.sha}}
    def activate(self):
        return build_release_site.activate(self.root/"site",self.manifest,self.fetch,lambda url:"b"*64)
    def test_unpublished_or_stable_release_does_not_write_site(self):
        for changes in ({"draft":True},{"published_at":None},{"prerelease":False},{"tag_name":"v0.1.1"}):
            saved=dict(self.release);self.release.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.activate()
            self.assertFalse((self.root/"site").exists());self.release=saved
    def test_wrong_tag_commit_and_asset_tampering_block_activation(self):
        with self.assertRaises(ValueError):
            build_release_site.activate(self.root/"site",self.manifest,lambda url:self.release if "/releases/" in url else {"object":{"type":"commit","sha":"c"*40}},lambda url:"b"*64)
        with self.assertRaises(ValueError):
            build_release_site.activate(self.root/"site",self.manifest,self.fetch,lambda url:"c"*64)
        self.assertFalse((self.root/"site").exists())
    def test_missing_required_file_blocks_before_writing(self):
        self.manifest["assets"].pop()
        with self.assertRaises(ValueError):self.activate()
        self.assertFalse((self.root/"site").exists())
    def test_verified_release_activates_matching_link_and_preserves_privacy(self):
        proof=self.activate();self.assertEqual(proof["assets_verified"],3)
        text=(self.root/"site/index.html").read_text(encoding="utf-8")
        self.assertIn("/releases/download/v0.3.0a6/DocFlow-Lite-0.3.0a6-Windows-x64-Portable.zip",text)
        self.assertNotIn("/releases/download/v0.1.1",text)
        self.assertIn("SHA256 Portable: "+"b"*64,text)
        self.assertNotIn("не входит в публичный Release",(self.root/"site/service.html").read_text(encoding="utf-8"))
        self.assertNotIn("<form",text)
        self.assertIn("Что написать для оценки",text)
        info=json.loads((self.root/"site/build-info.json").read_text(encoding="utf-8"))
        self.assertEqual(info["application_version"],self.version)
        self.assertFalse(info["indexing_enabled"]);self.assertFalse(info["lead_collection_enabled"])
        self.assertNotIn("v0.1.1",(self.root/"site/terms.html").read_text(encoding="utf-8"))
        self.assertNotIn("Подготовительная alpha",(self.root/"site/service.html").read_text(encoding="utf-8"))
        self.assertIn("software.html",(self.root/"site/terms.html").read_text(encoding="utf-8"))
        self.assertIn("connect-src 'none'",(self.root/"site/_headers").read_text(encoding="utf-8"))
    def fixtures(self):
        folder=self.root/"assets";folder.mkdir()
        names=[a["name"] for a in self.manifest["assets"]]
        exe=b"synthetic test executable";license_data=b"{}"
        files={"DocFlow-Lite.exe":exe,"THIRD-PARTY-LICENSES.json":license_data,"LICENSE.txt":b"Synthetic original terms"}
        if self.version!='0.3.0a6':
            sbom={'bomFormat':'CycloneDX','specVersion':'1.6','metadata':{'component':{'version':self.version,'properties':[{'name':'docflow:source-commit','value':self.sha}]}}}
            files['SBOM.cdx.json']=json.dumps(sbom).encode()
            (folder/'SBOM.cdx.json').write_bytes(files['SBOM.cdx.json'])
        with zipfile.ZipFile(folder/names[0],"w") as z:
            for n,b in files.items():z.writestr("DocFlow-Lite/"+n,b)
            z.writestr("DocFlow-Lite/BUNDLE-SHA256.json",json.dumps({n:candidate.digest(b) for n,b in files.items()}))
        with zipfile.ZipFile(folder/names[1],"w") as z:
            z.writestr("docflow-lite/example.txt",b"source")
            z.writestr("docflow-lite/FILE_HASHES.json",json.dumps({"example.txt":candidate.digest(b"source")}))
        with zipfile.ZipFile(folder/names[2],"w") as z:z.writestr("ThirdParty-Sources/example.txt",b"dependency source")
        (folder/"BUILD-INFO.json").write_text(json.dumps({"version":self.version,"python":"3.13.16" if self.version=="0.3.0a6" else "3.14.10","commit":self.sha,"exe_sha256":candidate.digest(exe)}))
        (folder/"README-WINDOWS.txt").write_text("Example instructions")
        (folder/"LICENSE.txt").write_text("Synthetic original terms")
        (folder/"WINDOWS-CI-RESULTS.json").write_text(json.dumps({"status":"passed","runs":[{},{}]}))
        self.resum(folder)
        return folder
    def resum(self,folder):
        (folder/"SHA256SUMS.txt").write_text("".join(candidate.digest(p.read_bytes())+"  "+p.name+"\n" for p in sorted(folder.iterdir()) if p.name!="SHA256SUMS.txt"))
    def test_candidate_checks_corresponding_sources_bundle_and_all_assets(self):
        folder=self.fixtures();result=candidate.verify(folder)
        self.assertEqual(result["status"],"passed")
        (folder/"README-WINDOWS.txt").write_text("tampered")
        with self.assertRaisesRegex(ValueError,"checksum failed"):candidate.verify(folder)
    def test_source_tampering_is_caught_even_with_updated_outer_checksum(self):
        folder=self.fixtures();source=folder/self.manifest["assets"][1]["name"]
        with zipfile.ZipFile(source,"w") as z:
            z.writestr("docflow-lite/example.txt",b"tampered")
            z.writestr("docflow-lite/FILE_HASHES.json",json.dumps({"example.txt":candidate.digest(b"source")}))
        self.resum(folder)
        with self.assertRaisesRegex(ValueError,"source checksum failed"):candidate.verify(folder)
    def test_unsafe_checksum_paths_and_nonpinned_build_rejected(self):
        folder=self.fixtures()
        with (folder/"SHA256SUMS.txt").open("a") as f:f.write("b"*64+"  ../private.txt\n")
        with self.assertRaisesRegex(ValueError,"Unsafe"):candidate.verify(folder)
        self.resum(folder);info=json.loads((folder/"BUILD-INFO.json").read_text(encoding="utf-8"));info["python"]="3.12.10"
        (folder/"BUILD-INFO.json").write_text(json.dumps(info));self.resum(folder)
        with self.assertRaisesRegex(ValueError,"pinned Python"):candidate.verify(folder)
    def test_unsafe_zip_entries_rejected_without_extraction(self):
        p=self.root/"unsafe.zip"
        with zipfile.ZipFile(p,"w") as z:z.writestr("../private.txt",b"bad")
        with self.assertRaisesRegex(ValueError,"Unsafe"):candidate.checked_zip(p)
        self.assertFalse((self.root.parent/"private.txt").exists())

    def test_draft_payload_preserves_prerelease_and_exact_build_target(self):
        sys.path.insert(0,str(ROOT/"scripts"))
        from prepare_github_draft import prepare
        folder=self.fixtures();notes=self.root/"notes.md";notes.write_text("Version "+self.version)
        result=prepare(folder,self.sha,notes)
        self.assertTrue(result["draft"]);self.assertTrue(result["prerelease"])
        self.assertEqual(result["target_commitish"],self.sha)
        self.assertIn("LICENSE.txt",result["asset_names"])
        self.assertFalse((folder/"draft-payload.json").exists())

    def test_draft_preparation_rejects_source_target_and_notes_mismatch(self):
        sys.path.insert(0,str(ROOT/"scripts"))
        from prepare_github_draft import prepare
        folder=self.fixtures();notes=self.root/"notes.md";notes.write_text("Version "+self.version)
        with self.assertRaisesRegex(ValueError,"commit differs"):prepare(folder,"c"*40,notes)
        notes.write_text("Other version")
        with self.assertRaisesRegex(ValueError,"notes"):prepare(folder,self.sha,notes)


    def test_unmanifested_source_file_blocks_even_when_zip_checksum_is_updated(self):
        folder=self.fixtures();source=folder/self.manifest['assets'][1]['name']
        with zipfile.ZipFile(source,'a') as z:z.writestr('docflow-lite/private-untracked.txt',b'synthetic privacy sentinel')
        self.resum(folder)
        with self.assertRaisesRegex(ValueError,'source|Source'):candidate.verify(folder)

    def test_unmanifested_bundle_file_blocks_even_when_zip_checksum_is_updated(self):
        folder=self.fixtures();portable=folder/self.manifest['assets'][0]['name']
        with zipfile.ZipFile(portable,'a') as z:z.writestr('DocFlow-Lite/_internal/unexpected.dll',b'synthetic unexpected binary')
        self.resum(folder)
        with self.assertRaisesRegex(ValueError,'Bundle|bundle'):candidate.verify(folder)

    def rc_fixture(self):
        self.version='1.0.0rc1'
        for asset in self.manifest['assets']:asset['name']=asset['name'].replace('0.3.0a6',self.version)
        return self.fixtures()

    def test_rc_requires_sbom_even_when_outer_checksums_are_updated(self):
        folder=self.rc_fixture();candidate.verify(folder)
        (folder/'SBOM.cdx.json').unlink();self.resum(folder)
        with self.assertRaisesRegex(ValueError,'SBOM'):candidate.verify(folder)

    def test_rc_rejects_sbom_from_another_commit(self):
        folder=self.rc_fixture();sbom=json.loads((folder/'SBOM.cdx.json').read_text())
        sbom['metadata']['component']['properties'][0]['value']='c'*40
        (folder/'SBOM.cdx.json').write_text(json.dumps(sbom));self.resum(folder)
        with self.assertRaisesRegex(ValueError,'SBOM'):candidate.verify(folder)
