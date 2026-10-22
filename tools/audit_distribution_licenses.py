"""Read-only ZIP/PE/source evidence; does not certify legal compliance or run EXEs."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import struct
import tarfile
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pe_details(data):
    assert data[:2] == b'MZ'
    pe = struct.unpack_from('<I', data, 60)[0]
    assert data[pe:pe+4] == b'PE\0\0'
    machine, count = struct.unpack_from('<HH', data, pe+4)
    optional_size = struct.unpack_from('<H', data, pe+20)[0]
    optional = pe+24
    assert machine == 0x8664 and struct.unpack_from('<H', data, optional)[0] == 0x20b
    sections = []
    for index in range(count):
        start = optional+optional_size+40*index
        virtual_size, rva, raw_size, offset = struct.unpack_from('<IIII', data, start+8)
        sections.append((rva, max(virtual_size, raw_size), offset, raw_size))

    def offset(rva):
        for start, size, raw, _ in sections:
            if start <= rva < start+size:
                return raw+rva-start
        raise ValueError('RVA outside sections')

    import_rva = struct.unpack_from('<I', data, optional+112+8)[0]
    imports = []
    if import_rva:
        start = offset(import_rva)
        for index in range(512):
            descriptor = struct.unpack_from('<IIIII', data, start+index*20)
            if not any(descriptor):
                break
            name = offset(descriptor[3])
            imports.append(data[name:data.index(b'\0', name)].decode('ascii'))
        else:
            raise ValueError('Import table exceeded bound')
    versions = []
    signature = b'\xbd\x04\xef\xfe'
    for _, _, raw, size in sections:
        location = data.find(signature, raw, raw+size)
        if location >= 0:
            ms, ls = struct.unpack_from('<II', data, location+8)
            versions.append([ms >> 16, ms & 65535, ls >> 16, ls & 65535])
    return {'architecture': 'x64', 'imports': imports, 'fixed_file_versions': versions}


def audit(portable, sources):
    root = 'DocFlow-Lite/'
    with zipfile.ZipFile(portable) as bundle, zipfile.ZipFile(sources) as source_zip:
        assert bundle.testzip() is None and source_zip.testzip() is None
        for archive in (bundle, source_zip):
            for name in archive.namelist():
                path = PurePosixPath(name)
                assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
        inventory = json.loads(bundle.read(root+'THIRD-PARTY-LICENSES.json'))
        source_items = json.loads(bundle.read(root+'THIRD-PARTY-SOURCES.json'))
        manifest = json.loads(bundle.read(root+'BUNDLE-SHA256.json'))
        for name, expected in manifest.items():
            assert digest(bundle.read(root+name)) == expected, name
        for dist in inventory['distributions']:
            assert dist['license_files']
            for name in dist['license_files']:
                assert len(bundle.read(root+name)) > 40, name
        names = bundle.namelist()
        lgpl = [n for n in names if n.endswith('LGPL-3.0-only.txt')]
        gpl = [n for n in names if n.endswith('GPL-3.0-only.txt')]
        assert lgpl and gpl
        assert b'GNU LESSER GENERAL PUBLIC LICENSE' in bundle.read(lgpl[0])
        assert b'GNU GENERAL PUBLIC LICENSE' in bundle.read(gpl[0])
        notice = bundle.read(root+'QT-LGPL-NOTICE.txt').decode('utf-8')
        assert all(word in notice for word in ['LGPL', 'reverse engineering', 'replaceable', 'ThirdParty-Sources'])
        archives = []
        for item in source_items:
            raw = source_zip.read('ThirdParty-Sources/'+item['file'])
            assert digest(raw) == item['sha256'] and len(raw) == item['bytes']
            flags = {'source_files': False, 'build_files': False, 'license_files': False, 'shiboken_source': False}
            with tarfile.open(fileobj=io.BytesIO(raw), mode='r|xz') as tar:
                for member in tar:
                    if not member.isfile():
                        continue
                    path = PurePosixPath(member.name)
                    assert not path.is_absolute() and '..' not in path.parts
                    flags['source_files'] |= path.suffix in ('.cpp', '.h', '.py')
                    flags['build_files'] |= path.name in ('CMakeLists.txt', 'setup.py')
                    flags['license_files'] |= 'LICENSES' in path.parts
                    flags['shiboken_source'] |= 'shiboken6' in path.parts and path.suffix in ('.cpp', '.h', '.py')
            assert flags['source_files'] and flags['build_files'] and flags['license_files'], item['component']
            if item['component'] == 'pyside-setup':
                assert flags['shiboken_source']
            archives.append({**item, 'verified': True, **flags})
        binaries = {}
        for name in names:
            leaf = PurePosixPath(name).name
            if leaf.startswith('Qt6') and leaf.endswith('.dll') or leaf in ('QtCore.pyd', 'QtGui.pyd', 'QtWidgets.pyd', 'pyside6.abi3.dll', 'shiboken6.abi3.dll'):
                raw = bundle.read(name)
                binaries[name[len(root):]] = {'sha256': digest(raw), **pe_details(raw)}
        for leaf in ('QtCore.pyd', 'QtGui.pyd', 'QtWidgets.pyd'):
            binary = next(v for n, v in binaries.items() if PurePosixPath(n).name == leaf)
            assert any(n.lower().startswith('qt6') and n.lower().endswith('.dll') for n in binary['imports'])
        for leaf in ('Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll'):
            binary = next(v for n, v in binaries.items() if PurePosixPath(n).name == leaf)
            assert any(v[:3] == [6, 10, 2] for v in binary['fixed_file_versions']), leaf
        return {
            'status': 'technical_checks_passed_legal_approval_pending',
            'scope': 'Read-only actual ZIP/PE/source inspection; no executable or library changed or run.',
            'portable': {'name': portable.name, 'bytes': portable.stat().st_size, 'sha256': digest(portable.read_bytes())},
            'third_party_sources': {'name': sources.name, 'bytes': sources.stat().st_size, 'sha256': digest(sources.read_bytes())},
            'manifest_files_verified': len(manifest), 'inventory': inventory,
            'lgpl_texts': lgpl, 'gpl_texts': gpl, 'source_archives_verified': archives,
            'native_libraries': binaries,
            'limits': ['No native run with substituted compatible libraries in this legal audit.',
                       'Static external DLL layout/imports are not proof of complete LGPL compliance.',
                       'Original application rights and approved own-code user terms are not established by third-party notices.',
                       'Exact upstream wheel build configuration/modifications not independently reconstructed.']
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.portable, args.sources)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key: report[key] for key in ('status', 'portable', 'manifest_files_verified')}, ensure_ascii=False))
