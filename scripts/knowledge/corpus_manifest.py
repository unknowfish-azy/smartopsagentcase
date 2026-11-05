"""Run from repository root: python scripts/knowledge/corpus_manifest.py --help."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from knowledge.corpus_manifest import build_manifest, export_bundle, restore_bundle, verify_snapshot

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['create', 'verify', 'backup', 'restore'])
    parser.add_argument('root', help='corpus root; restore destination for restore')
    parser.add_argument('artifact', help='manifest JSON or ZIP archive')
    parser.add_argument('--version', default='reference-v1')
    parser.add_argument('--expected-hash')
    args = parser.parse_args()
    if args.action == 'create':
        result = build_manifest(args.root, args.version)
        # Exclusive create prevents replacing an existing version declaration.
        with open(args.artifact, 'x', encoding='utf-8') as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
    elif args.action == 'verify':
        result = json.loads(Path(args.artifact).read_text(encoding='utf-8'))
        verify_snapshot(args.root, result, expected_version=args.version, expected_hash=args.expected_hash)
    elif args.action == 'backup': result = export_bundle(args.root, args.version, args.artifact)
    else: result = restore_bundle(args.artifact, args.root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

if __name__ == '__main__': main()
