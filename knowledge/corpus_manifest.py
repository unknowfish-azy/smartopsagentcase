"""Versioned UTF-8 corpus snapshots; hashes cover paths and exact file bytes."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

class CorpusError(ValueError):
    pass

def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def _safe_path(name):
    p = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or str(p) != name:
        raise CorpusError('unsafe_path')
    return p

def _snapshot(root):
    root = Path(root).resolve(strict=True)
    if not root.is_dir(): raise CorpusError('missing_root')
    result = {}
    for path in sorted(root.rglob('*')):
        # Reject links, including linked directories, rather than following external assets.
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise CorpusError('linked_path')
        if path.is_file() and path.suffix == '.md':
            name = path.relative_to(root).as_posix()
            _safe_path(name)
            if not path.resolve().is_relative_to(root): raise CorpusError('unsafe_path')
            raw = path.read_bytes()
            raw.decode('utf-8', errors='strict')
            result[name] = raw
    return result

def _manifest(snapshot, version):
    if not isinstance(version, str) or not version.strip(): raise CorpusError('invalid_version')
    files = [{'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in sorted(snapshot.items())]
    payload = {'schema': 'smartops.corpus.v1', 'version': version, 'files': files}
    return {**payload, 'corpus_sha256': hashlib.sha256(_canonical(payload)).hexdigest()}

def build_manifest(root, version):
    try: return _manifest(_snapshot(root), version)
    except (OSError, UnicodeError) as exc: raise CorpusError('corpus_read_error') from exc

def verify_snapshot(root, manifest, *, expected_version=None, expected_hash=None):
    try:
        if manifest.get('schema') != 'smartops.corpus.v1': raise CorpusError('invalid_schema')
        names = [item['path'] for item in manifest['files']]
        for name in names: _safe_path(name)
        if len(names) != len(set(names)): raise CorpusError('duplicate_path')
        snapshot = _snapshot(root)
        actual = _manifest(snapshot, manifest['version'])
        if actual != manifest: raise CorpusError('manifest_mismatch')
        if expected_version is not None and actual['version'] != expected_version: raise CorpusError('version_mismatch')
        if expected_hash is not None and actual['corpus_sha256'] != expected_hash: raise CorpusError('hash_mismatch')
        # These same bytes were hashed above; never re-open document paths for ingestion.
        return [{'content': raw.decode('utf-8'), 'source': 'reference/' + name, 'version': actual['version'], 'document_id': hashlib.sha256(name.encode('utf-8') + b'\0' + raw).hexdigest()} for name, raw in sorted(snapshot.items())]
    except (OSError, UnicodeError, KeyError, TypeError, AttributeError) as exc:
        raise CorpusError('invalid_corpus') from exc

def export_bundle(root, version, destination):
    destination = Path(destination)
    if destination.exists(): raise CorpusError('destination_exists')
    snapshot = _snapshot(root)
    manifest = _manifest(snapshot, version)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=destination.parent, suffix='.tmp')
    os.close(fd)
    try:
        with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', _canonical(manifest))
            for name, raw in snapshot.items(): archive.writestr('corpus/' + name, raw)
        # Hard link publishes the completed archive atomically, refusing existing paths.
        os.link(temp, destination)
    finally:
        Path(temp).unlink(missing_ok=True)
    return manifest

def restore_bundle(archive_path, destination):
    destination = Path(destination).absolute()
    if destination.exists(): raise CorpusError('destination_exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix='.corpus-restore-'))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)): raise CorpusError('duplicate_archive_path')
            manifest = json.loads(archive.read('manifest.json').decode('utf-8'))
            for entry in archive.infolist():
                if entry.filename == 'manifest.json': continue
                name = entry.filename
                if not name.startswith('corpus/'): raise CorpusError('invalid_archive_path')
                relative = _safe_path(name[len('corpus/'):])
                if relative.suffix != '.md': raise CorpusError('unexpected_archive_file')
                target = staging.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(entry))
        verify_snapshot(staging, manifest)
        # Windows rename refuses an existing target directory; no overwrite is used.
        if destination.exists(): raise CorpusError('destination_exists')
        staging.rename(destination)
        return manifest
    except (OSError, UnicodeError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise CorpusError('restore_failed') from exc
    finally:
        if staging.exists(): shutil.rmtree(staging)
