#!/usr/bin/env python3
"""Generate the SM8550 GMU input headers for iokit/Kernel/arm/a740 from pinned Linux sources (no device I/O).

Adapted from the SM8550 reference board's prepare-*-gmu*.py (BSD-2-Clause-Patent). Inputs: ianchb/sm8550-mainline
@42f3b40c (the revision UniXNU pins), fetched into tools/research/a740-linux and hash-checked against UniXNU's
scripts/data/adreno-inputs.json. GPU/GMU registers, RSC/PDC setup, OPPs, BCMs and the cmd-db carve-out are SoC
facts (sm8550.dtsi, no board override). Writes Sm8550GmuSource.h, Sm8550GmuVotesSource.h, Sm8550GmuCommandDbSource.h.
usage: scripts/gen-a740-sources.py XNU_TREE
"""
import ast, hashlib, json, re, sys, pathlib, xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parents[1]
SRC = HERE / 'tools/research/a740-linux'
OUT = pathlib.Path(sys.argv[1]) / 'iokit/Kernel/arm/a740'
pins = json.loads((HERE.parent / 'UniXNU/scripts/data/adreno-inputs.json').read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['drivers/gpu/drm/msm/adreno/' + s for s in ['a6xx_gmu.c', 'a6xx_gmu.h', 'a6xx_gpu.c', 'a6xx_gpu.h', 'a6xx_catalog.c']] + \
        ['drivers/gpu/drm/msm/registers/adreno/' + s for s in ['a6xx.xml', 'a6xx_gmu.xml']]:
    if sha(SRC / name) != pins['linux']['files'][name]['sha256']:
        sys.exit('pinned source differs: ' + name)
dtsi = (SRC / 'arch/arm64/boot/dts/qcom/sm8550.dtsi').read_text()
if sha(SRC / 'arch/arm64/boot/dts/qcom/sm8550.dtsi') != pins['board']['sha256']['arch/arm64/boot/dts/qcom/sm8550.dtsi']:
    sys.exit('pinned sm8550.dtsi differs')
levels = {m[0]: int(m[1]) for m in re.findall(r'#define\s+(RPMH_REGULATOR_LEVEL_\w+)\s+(\d+)',
                                                 (SRC / 'include/dt-bindings/power/qcom,rpmhpd.h').read_text())}


def block(start):
    i = dtsi.index(start)
    depth, j = 0, dtsi.index('{', i)
    for k in range(j, len(dtsi)):
        depth += {'{': 1, '}': -1}.get(dtsi[k], 0)
        if depth == 0:
            return dtsi[j:k + 1]


def windows(node):
    b = block(node)
    regs = [int(x, 16) for x in re.findall(r'0x[0-9a-f]+', re.search(r'\breg = ([^;]+);', b)[1])]
    names = re.findall(r'"([^"]+)"', re.search(r'reg-names = ([^;]+);', b)[1])
    return {n: dict(base=(regs[4 * i] << 32) | regs[4 * i + 1], bytes=(regs[4 * i + 2] << 32) | regs[4 * i + 3])
            for i, n in enumerate(names)}


def opps(node):
    out = []
    for name, body in re.findall(r'(opp-\d+) \{([^{}]*)\}', block(node).split('opp-table', 1)[1]):
        hz = int(re.search(r'opp-hz = /bits/ 64 <(\d+)>', body)[1])
        level = levels[re.search(r'opp-level = <(\w+)>', body)[1]]
        kbps = re.search(r'opp-peak-kBps = <(\d+)>', body)
        acd = re.search(r'qcom,opp-acd-level = <(0x[0-9a-f]+)>', body)
        out.append(dict(hz=hz, level=level, kbps=int(kbps[1]) if kbps else 0, acd_present=bool(acd),
                        acd=int(acd[1], 16) if acd else 0))
    out.sort(key=lambda e: e['hz'])
    return [dict(hz=0, level=0, kbps=0, acd_present=False, acd=0)] + out


# ---- Sm8550GmuSource.h (prepare-*-gmu.py) ----
ranges = {**windows('gpu: gpu@3d00000'), **windows('gmu: gmu@3d6a000')}
win = [ranges[n] for n in ['gmu', 'rscc', 'gmu_pdc', 'kgsl_3d0_reg_memory', 'cx_mem']]
ns = {'r': 'http://nouveau.freedesktop.org/'}
trees = [ET.parse(SRC / ('drivers/gpu/drm/msm/registers/adreno/' + s)).getroot() for s in ['a6xx.xml', 'a6xx_gmu.xml']]
regs = {}


def register(symbol, domain, name, variant=None):
    m = [n for t in trees for d in t.findall('r:domain', ns) if d.attrib['name'] == domain
         for n in d.findall('r:reg32', ns) if n.attrib.get('name') == name and (variant is None or n.attrib.get('variants') == variant)]
    if len(m) != 1:
        sys.exit('ambiguous/missing register ' + symbol)
    regs[symbol] = int(m[0].attrib['offset'], 0)


for n in ['GMU_CM3_ITCM_START', 'GMU_CM3_DTCM_START', 'GMU_CM3_SYSRESET', 'GMU_CM3_BOOT_CONFIG', 'GMU_CM3_FW_INIT_RESULT',
          'GMU_CM3_CFG', 'GMU_HFI_QTBL_ADDR', 'GMU_HFI_QTBL_INFO', 'GMU_HFI_CTRL_INIT', 'GMU_HFI_CTRL_STATUS',
          'GMU_HOST2GMU_INTR_SET', 'GMU_SYS_BUS_CONFIG', 'GMU_ICACHE_CONFIG', 'GMU_DCACHE_CONFIG', 'GMU_AHB_FENCE_RANGE_0',
          'GMU_GMU2HOST_INTR_INFO', 'GMU_AO_HOST_INTERRUPT_STATUS']:
    register('REG_' + n, 'A6XX', n)
for n in ['GPU_GMU_CX_GMU_CX_FALNEXT_INTF', 'GPU_GMU_CX_GMU_CX_FAL_INTF']:
    register('REG_' + n, 'A6XX', n, 'A6XX')
for i in [8, 9, 10]:
    register('REG_GMU_GENERAL_%d' % i, 'A6XX', 'GMU_GENERAL_%d' % i, 'A7XX')
for n in ['GPU_RSCC_RSC_STATUS0_DRV0', 'RSCC_PDC_SLAVE_ID_DRV0', 'RSCC_HIDDEN_TCS_CMD0_ADDR', 'RSCC_HIDDEN_TCS_CMD0_DATA',
          'RSCC_OVERRIDE_START_ADDR', 'RSCC_PDC_SEQ_START_ADDR', 'RSCC_PDC_MATCH_VALUE_LO', 'RSCC_PDC_MATCH_VALUE_HI',
          'RSCC_SEQ_BUSY_DRV0']:
    register('REG_' + n, 'A6XX', n)
register('REG_RSCC_SEQ_MEM_0_DRV0_A740', 'A6XX', 'RSCC_SEQ_MEM_0_DRV0_A740', 'A7XX')
register('REG_CX_MISC_TCM_RET_CNTL', 'A6XX_CX_MISC', 'CX_MISC_TCM_RET_CNTL', 'A7XX-')
register('REG_GBIF_QSB_SIDE0', 'A6XX', 'GBIF_QSB_SIDE0')
for n in ['SEQ_START_ADDR', 'ENABLE_PDC']:
    register('REG_PDC_GPU_' + n, 'A6XX_PDC', 'GPU_' + n)


def field(domain, name, bit):
    for t in trees:
        for d in t.findall('r:domain', ns):
            if d.attrib['name'] == domain:
                for r in d.findall('r:reg32', ns):
                    if r.attrib.get('name') == name:
                        for f in r.findall('r:bitfield', ns):
                            if f.attrib.get('name') == bit:
                                return 1 << int(f.attrib['pos'])
    sys.exit('missing bit ' + bit)


fatal = sum(field('A6XX', 'GMU_AO_HOST_INTERRUPT_STATUS', b) for b in ['WDOG_BITE', 'FENCE_ERR', 'HOST_AHB_BUS_ERROR'])
cm3 = field('A6XX', 'GMU_GMU2HOST_INTR_INFO', 'CM3_FAULT')
src = (SRC / 'drivers/gpu/drm/msm/adreno/a6xx_gmu.c').read_text()
init = src[src.index('static void a6xx_gmu_rpmh_init('):src.index('/*\n * The lowest 16 bits')]


def number(e):
    e = e.strip()
    if '?' in e:
        assert e.startswith('adreno_is_a740_family(adreno_gpu)'), e
        e = e.split('?', 1)[1].split(':', 1)[0].strip()
    e = re.sub(r'BIT\((\d+)\)', lambda m: str(1 << int(m[1])), e).replace('seqmem0_drv0_reg', str(regs['REG_RSCC_SEQ_MEM_0_DRV0_A740']))
    for k, v in regs.items():
        e = re.sub(r'\b' + k.replace('REG_', 'REG_A6XX_', 1) + r'\b', str(v), e)
    t = ast.parse(e, mode='eval')
    assert all(isinstance(n, (ast.Expression, ast.Constant, ast.BinOp, ast.Add)) for n in ast.walk(t)), e
    return eval(compile(t, '<src>', 'eval'), {'__builtins__': {}})


setup = []
pre = init[init.index('/* Disable SDE clock gating */'):init.index('/* The second spin')]
setup += [(1, 4 * number(r), number(v)) for r, v in re.findall(r'gmu_write_rscc\(gmu,\s*([^,]+),\s*([\s\S]*?)\);', pre)]
assert 'seqmem0_drv0_reg = REG_A7XX_RSCC_SEQ_MEM_0_DRV0_A740;' in init
s0 = init.index('gmu_write_rscc(gmu, seqmem0_drv0_reg,')
setup += [(1, 4 * number(r), number(v)) for r, v in re.findall(r'gmu_write_rscc\(gmu,\s*([^,]+),\s*([^;]+)\);', init[s0:init.index('} else {', s0)])]
setup += [(2, 4 * number(r), number(v)) for r, v in re.findall(r'pdc_write\(pdcptr,\s*([^,]+),\s*([^;]+)\);', init[init.index('setup_pdc:'):])]
assert len(setup) == 19, len(setup)
catalog = (SRC / 'drivers/gpu/drm/msm/adreno/a6xx_catalog.c').read_text()
record = re.search(r'\.chip_ids = ADRENO_CHIP_IDS\(0x43050a01\)([\s\S]*?)\.preempt_record_size', catalog)[1]
chip = int(re.search(r'\.gmu_chipid = (0x[0-9a-f]+)', record)[1], 0)
fw = pins['firmware']['files']['qcom/gmu_gen70200.bin']
t = '/* Generated by scripts/gen-a740-sources.py from pinned sm8550-mainline sources. */\n#include <stdint.h>\n#include <stddef.h>\n'
t += ''.join('#define %s UINT32_C(%s)\n' % (k, hex(v)) for k, v in regs.items())
t += '#define ISHTAR_GMU_CHIP_ID UINT32_C(0x43050a01)\n#define ISHTAR_GMU_FW_CHIP_ID UINT32_C(%s)\n' % hex(chip)
t += '#define ISHTAR_GMU_CORE_GPU_DELTA %su\n' % hex(win[0]['base'] - win[3]['base'])
t += '#define ISHTAR_GMU_FIRMWARE_BYTES %du\n' % fw['bytes']
t += '#define ISHTAR_GMU_AO_FATAL_MASK %su\n#define ISHTAR_GMU_CM3_FATAL_MASK %su\n' % (hex(fatal), hex(cm3))
t += 'static const uint8_t ishtar_gmu_firmware_sha256[32]={%s};\n' % ','.join('0x' + fw['sha256'][i:i + 2] for i in range(0, 64, 2))
t += 'static const uint64_t ishtar_gmu_window_physical[5]={%s};\n' % ','.join(hex(w['base']) for w in win)
t += 'static const size_t ishtar_gmu_window_bytes[5]={%s};\n' % ','.join(hex(w['bytes']) for w in win)
t += 'typedef struct {unsigned window;size_t byte_offset;uint32_t value;} Sm8550GmuSetupWrite;\n'
t += '#define ISHTAR_GMU_RSC_SETUP_COUNT 19u\nstatic const Sm8550GmuSetupWrite ishtar_gmu_rsc_setup[19]={\n'
t += '\n'.join('{%d,%s,%s},' % (w, hex(o), hex(v)) for w, o, v in setup) + '\n};\n'
(OUT / 'Sm8550GmuSource.h').write_text(t)

# ---- Sm8550GmuVotesSource.h (prepare-*-gmu-votes.py) ----
rec = {'gpu': opps('gpu: gpu@3d00000'), 'gmu': opps('gmu: gmu@3d6a000')}
ents = re.findall(r'\{\s*\.name = "([A-Z0-9]+)",([^{}]+)\}', record)
assert [e[0] for e in ents] == ['SH0', 'MC0', 'ACV'], ents
pol = []
for name, body in ents:
    if name != 'ACV':
        pol.append(dict(buswidth=int(re.fullmatch(r'\s*\.buswidth = (\d+)\s*', body)[1]), fixed=0, perfmode=0, perfmode_kbps=0))
    else:
        m = re.fullmatch(r'\s*\.fixed = true,\s*\.perfmode = BIT\((\d+)\),\s*\.perfmode_bw = (\d+),\s*', body)
        pol.append(dict(buswidth=0, fixed=1, perfmode=1 << int(m[1]), perfmode_kbps=int(m[2])))
bw = sorted({e['kbps'] for e in rec['gpu']})
t = '/* Generated by scripts/gen-a740-sources.py from pinned sm8550.dtsi/a6xx_catalog.c. */\n#include <stdint.h>\n'
t += '#define ISHTAR_GMU_VOTES_CHIP_ID 0x43050a01u\ntypedef struct {uint64_t hz;uint32_t level,kbps,acd_present,acd;} Sm8550GmuOpp;\n'
for k in ['gpu', 'gmu']:
    t += '#define ISHTAR_%s_OPPS %du\nstatic const Sm8550GmuOpp ishtar_%s_opps[]={\n' % (k.upper(), len(rec[k]), k)
    t += '\n'.join('{%s},' % ','.join(str(int(e[f])) for f in ['hz', 'level', 'kbps', 'acd_present', 'acd']) for e in rec[k]) + '\n};\n'
t += '#define ISHTAR_GPU_BANDWIDTHS %du\nstatic const uint32_t ishtar_gpu_bandwidths[]={%s};\n' % (len(bw), ','.join(map(str, bw)))
t += 'static const AdrenoHfiBcm ishtar_bcm_policy[3]={\n' + '\n'.join(
    '{.buswidth=%d,.fixed=%d,.perfmode=%d,.perfmode_kbps=%d},' % (e['buswidth'], e['fixed'], e['perfmode'], e['perfmode_kbps']) for e in pol) + '\n};\n'
(OUT / 'Sm8550GmuVotesSource.h').write_text(t)

# ---- Sm8550GmuCommandDbSource.h ----
m = re.search(r'aop-cmd-db-region@81c60000 \{[^}]*reg = <0 (0x[0-9a-f]+) 0 (0x[0-9a-f]+)>;[^}]*no-map;', dtsi)
(OUT / 'Sm8550GmuCommandDbSource.h').write_text('/* sm8550.dtsi reservation (same on ishtar\'s live DT). */\n'
    '#define ISHTAR_GMU_COMMAND_DB_BASE UINT64_C(%s)\n#define ISHTAR_GMU_COMMAND_DB_BYTES %du\n' % (m[1], int(m[2], 16)))
print('generated: %d registers, %d rsc/pdc writes, gpu %d / gmu %d opps, bw %s, gmu fw chip %#x' %
      (len(regs), len(setup), len(rec['gpu']), len(rec['gmu']), bw, chip))
