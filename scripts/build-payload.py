#!/usr/bin/env python3
"""UniXNU payload volume (FAT) with an "iOS 18 (ishtar)" entry: kernel + ADT + unixnu.toml.

The payload becomes the ramdisk of the fastboot boot image (scripts/build-uefi.py DEBUG out/payload.img).
--window BASE (hex) is where DarwinBoot places the kernel window; it shows the real one on screen at boot.
--ufs adds the UFS node and rd=ufsroot0: the kernel reads userdata (read-only unless kernel_args set ufsrw=1;
the persistent log also needs ufsrw). Without it the kernel never touches the UFS host.
--root adds board.toml root_args instead: boots the iOS root installed on userdata, read-write.
usage: scripts/build-payload.py --window 0x880000000 [--kernel out/kernel.development.ishtar] [--ufs | --root]
"""
import argparse, pathlib, subprocess, sys, tempfile, tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
board = tomllib.loads((ROOT / 'board.toml').read_text())
pay = board['payload']

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('--window', required=True, type=lambda v: int(v, 16))
p.add_argument('--kernel', type=pathlib.Path, default=ROOT / 'out/kernel.development.ishtar')
p.add_argument('--ufs', action='store_true')
p.add_argument('--root', action='store_true')
p.add_argument('--extra', default='', help='extra boot args for this image (variants, overrides)')
p.add_argument('--gpu-fw', type=pathlib.Path, help='dir with A740 firmware -> ADT /ishtar-gpu (scripts/adt-a740fw.py)')
p.add_argument('--out', type=pathlib.Path, default=ROOT / 'out/payload.img')
a = p.parse_args()
a.ufs = a.ufs or a.root

size = int(pay['dram_size'], 16)
args = ' '.join(pay['kernel_args'] + (pay['root_args'] if a.root else ['rd=ufsroot0'] if a.ufs else []) + a.extra.split())
if not a.ufs and any(x.split('=')[0] in ('rd', 'ufsrw', 'rootrw') for x in pay['kernel_args']):
    sys.exit('board.toml kernel_args mount the UFS root; use --ufs')

toml = f'''version = 1

[boot]
timeout = {pay.get('timeout', 3)}
default = "ios"

[kits]
autoload = false

[[entry]]
id = "ios"
title = "{pay['title']}"
type = "xnu"
path = "Payloads/kernel.macho"
args = "{args}"
'''

with tempfile.TemporaryDirectory() as t:
    t = pathlib.Path(t)
    adt = t / 'kernel.macho.adt'
    cmd = [sys.executable, ROOT / 'tools/base/mkadt.py', adt, '--board', 'ishtar', '--mem', f'{a.window:x}:{size:x}']
    for key, flag in (('identity', '--identity'), ('display_scale', '--display-scale'), ('points', '--points')):
        if key in pay:
            cmd += [flag, str(pay[key])]
    subprocess.run([str(c) for c in cmd + ([] if a.ufs else ['--no-ufs'])], check=True)
    if a.gpu_fw:
        subprocess.run([sys.executable, str(ROOT / 'scripts/adt-a740fw.py'), str(adt), str(adt), '--fw', str(a.gpu_fw)], check=True)
    (t / 'unixnu.toml').write_text(toml)
    a.out.parent.mkdir(exist_ok=True)
    a.out.unlink(missing_ok=True)
    img = str(a.out)
    subprocess.run(['mkfile', '-n', f'{pay["size_mib"]}m', img], check=True)
    subprocess.run(['mformat', '-i', img, '-F', '-v', pay['volume'], '::'], check=True)
    for d in ('::/EFI', '::/EFI/UniXNU', '::/EFI/UniXNU/Payloads'):
        subprocess.run(['mmd', '-i', img, d], check=True)
    for src, dst in ((t / 'unixnu.toml', '::/EFI/UniXNU/unixnu.toml'), (a.kernel, '::/EFI/UniXNU/Payloads/kernel.macho'),
                     (adt, '::/EFI/UniXNU/Payloads/kernel.macho.adt')):
        subprocess.run(['mcopy', '-i', img, '-m', str(src), dst], check=True)
print(f'{a.out}: window {a.window:#x}+{size:#x}, ufs {"on" if a.ufs else "off"}\n  args: {args}')
