#!/usr/bin/env python3
"""Fetch the base XNU port (see README credits) into the working tree with every upstream device/project name renamed to ishtar.

Writes xnu/base (kernel patches for xnu-11215) and tools/base (host tools). tools/base/mkadt.py is taken from the
upstream iOS 26 branch (it knows --identity) and gets tools/mkadt-ishtar.patch (the ishtar board) on top.
Upstream has no license, so this is fetched at build time and never committed here.
Apple's xnu says "sweet spot" twice and "hundredMill" once; whole words/phrases only, so patch context still matches.
usage: scripts/sync-base.py [COMMIT]
"""
import pathlib, re, shutil, subprocess, sys, tempfile

REPO = 'https://github.com/ry-diffusion/Bergamota'
COMMIT = sys.argv[1] if len(sys.argv) > 1 else 'e8e7fe0'   # develop, 2026-10-25
MKADT_COMMIT = 'b5fea74'                                   # ios26, 2026-10-25
ROOT = pathlib.Path(__file__).resolve().parents[1]

# Applied before the rename. Two upstream boards share one touch driver: keep their configs distinct. The one upstream
# board check ("is this the reference phone?") must never match ishtar's ADT, or its PMIC/charger code would run here.
SPECIAL = [('touch_beryllium', 'touch_ishtar2'), ('sweet_board_beryllium', 'ishtar_board_ref'),
           ('"xiaomi,beryllium"', '"ishtar,ref-board"'), ("'xiaomi,beryllium'", "'ishtar,ref-board'")]
NAMES = re.compile(r'(?i)sweet(?![- ]spot)|beryllium|topaz|bergamota|heartwood|poco f1|redmi note(?: 10 pro)?')
URLS = re.compile(r'https?://\S+|ry-diffusion/\w+')        # keep links and release downloads working


def case(word):
    return 'ISHTAR' if word.isupper() else 'Ishtar' if word[0].isupper() else 'ishtar'


def rn(text, links=True):
    """links=False (kernel patches): upstream links in comments become a pointer to the README credits."""
    if not links:
        text = URLS.sub(lambda m: 'upstream (see README credits)' if NAMES.search(m.group(0)) else m.group(0), text)
    for a, b in SPECIAL:
        text = text.replace(a, b)
    out, pos = [], 0
    for m in URLS.finditer(text):
        out.append(NAMES.sub(lambda w: case(w.group(0)), text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(NAMES.sub(lambda w: case(w.group(0)), text[pos:]))
    return ''.join(out)


def copy(src, dst, links=True):
    if dst.exists():
        shutil.rmtree(dst)
    for f in sorted(src.rglob('*')):
        out = dst / rn(str(f.relative_to(src)))
        if f.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        data = f.read_bytes()
        if b'\0' in data:
            shutil.copyfile(f, out)
        else:
            out.write_bytes(rn(data.decode(errors='surrogateescape'), links).encode(errors='surrogateescape'))
        out.chmod(f.stat().st_mode)


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(['git', 'clone', '-q', '--filter=blob:none', '--no-checkout', REPO, t], check=True)
        subprocess.run(['git', '-C', t, 'checkout', '-q', COMMIT], check=True)
        rev = subprocess.check_output(['git', '-C', t, 'rev-parse', 'HEAD'], text=True).strip()
        copy(pathlib.Path(t, 'xnu/patches-11215'), ROOT / 'xnu/base', links=False)
        copy(pathlib.Path(t, 'tools'), ROOT / 'tools/base')
        (ROOT / 'tools/base/mkadt.py').write_text(
            rn(subprocess.check_output(['git', '-C', t, 'show', f'{MKADT_COMMIT}:tools/mkadt.py'], text=True)))
        subprocess.run(['patch', '-s', '-p1', '-d', ROOT, '-i', ROOT / 'tools/mkadt-ishtar.patch'], check=True)
        (ROOT / 'xnu/base/UPSTREAM').write_text(f'{rev}\n')
        print(f'base {rev[:12]}: {len(list((ROOT / "xnu/base").glob("*.patch")))} patches')
