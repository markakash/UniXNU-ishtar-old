#!/usr/bin/env python3
"""Keep make's view of a freshly cloned and patched xnu tree incremental across CI runs.

  ci-mtimes.py restore TREE MANIFEST   files whose content equals the manifest's get the manifest's mtime back
  ci-mtimes.py save TREE MANIFEST      record content hash and mtime of every file

The tree is cloned and patched anew in every run (so every patch is still applied and checked), which makes every file
newer than the cached objects. Restoring the old mtime of unchanged files leaves make with only the files our patches
changed since the last run.
"""
import hashlib, json, os, sys


def files(tree):
    for root, dirs, names in os.walk(tree):
        dirs[:] = [d for d in dirs if d != '.git']
        for n in names:
            p = os.path.join(root, n)
            if os.path.isfile(p) and not os.path.islink(p):
                yield os.path.relpath(p, tree), p


def digest(path):
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


mode, tree, manifest = sys.argv[1:4]
if mode == 'save':
    data = {rel: [digest(p), os.stat(p).st_mtime_ns] for rel, p in files(tree)}
    json.dump(data, open(manifest, 'w'))
    print(f'ci-mtimes: saved {len(data)} files')
elif mode == 'restore':
    if not os.path.exists(manifest):
        print('ci-mtimes: no manifest (first run or clean build)')
        sys.exit(0)
    old = json.load(open(manifest))
    kept = changed = 0
    for rel, p in files(tree):
        entry = old.get(rel)
        if entry and entry[0] == digest(p):
            os.utime(p, ns=(entry[1], entry[1]))
            kept += 1
        else:
            changed += 1
    print(f'ci-mtimes: {kept} files unchanged (old mtime), {changed} new or changed')
else:
    sys.exit(__doc__)
