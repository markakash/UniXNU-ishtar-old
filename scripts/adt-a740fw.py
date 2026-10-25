#!/usr/bin/env python3
"""Add the A740 firmware to an ADT as /ishtar-gpu (read by iokit/Kernel/arm/a740/IshtarA740Firmware.cpp).

  adt-a740fw.py IN.adt OUT.adt --fw DIR
DIR holds gmu_gen70200.bin, a740_sqe.fw (linux-firmware qcom/, the versions the driver is proven with) and the
phone's signed zap: a740_zap.mbn from /odm/firmware (the copy kgsl loads; TZ refuses /vendor/firmware's split one with
0xffcfffbb), else a split a740_zap.mdt + a740_zap.bNN merged into one ELF image (segment N goes to its p_offset). Qualcomm firmware: keep it and the ADT out of git.
"""
import argparse, glob, os, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../tools/base'))
import adt  # noqa: E402


def merge_mdt(mdt_path):
    mdt = open(mdt_path, 'rb').read()
    assert mdt[:4] == b'\x7fELF' and mdt[4] == 1, 'zap: not ELF32'
    phoff, = struct.unpack_from('<I', mdt, 28)
    phent, phnum = struct.unpack_from('<HH', mdt, 42)
    phs = [struct.unpack_from('<8I', mdt, phoff + i * phent) for i in range(phnum)]
    size = max(max(p[1] + p[4] for p in phs), len(mdt))
    out = bytearray(size)
    out[:len(mdt)] = mdt
    for i, p in enumerate(phs):
        off, filesz = p[1], p[4]
        if not filesz:
            continue
        seg = mdt_path[:-3] + 'b%02d' % i
        if os.path.exists(seg):
            data = open(seg, 'rb').read()
            assert len(data) == filesz, f'{seg}: {len(data)} != p_filesz {filesz}'
            out[off:off + filesz] = data
        elif off + filesz > len(mdt):
            sys.exit(f'zap: segment {i} missing ({seg})')
    return bytes(out)


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('inp'); ap.add_argument('out'); ap.add_argument('--fw', required=True)
a = ap.parse_args()
root, _ = adt.parse(adt.load(a.inp))
root.children = [c for c in root.children if c.name != 'ishtar-gpu']
n = adt.Node()
n.props.append(('name', 0, b'ishtar-gpu\0'))
n.props.append(('gmu-firmware', 0, open(os.path.join(a.fw, 'gmu_gen70200.bin'), 'rb').read()))
n.props.append(('sqe-firmware', 0, open(os.path.join(a.fw, 'a740_sqe.fw'), 'rb').read()))
mbn = os.path.join(a.fw, 'a740_zap.mbn')   # what kgsl loads on ishtar (/odm/firmware); /vendor's split copy is rejected by TZ
n.props.append(('zap-firmware', 0, open(mbn, 'rb').read() if os.path.exists(mbn) else merge_mdt(os.path.join(a.fw, 'a740_zap.mdt'))))
root.children.append(n)
open(a.out, 'wb').write(adt.serialize(root))
print('%s: /ishtar-gpu with %s' % (a.out, ', '.join('%s (%d)' % (p, len(v)) for p, _, v in n.props[1:])))
