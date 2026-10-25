#!/usr/bin/env python3
"""Build ../uefi-ishtar with EDK II directly (works on Apple Silicon macOS, where Mu's prebuilt BaseTools do not).

Same steps as UniXNU's scripts/unixnu/firmware.py: local BaseTools, Homebrew LLVM for CLANGPDB, Mu_Basecore
patches applied for the build and reverted after. UniXNUPkg and DarwinBootPkg come from ../UniXNU;
uefi/darwinboot-*.patch is applied to ../UniXNU/drivers/DarwinBoot the same way.
usage: scripts/build-uefi.py [DEBUG|RELEASE]
"""
import os, pathlib, shutil, subprocess, sys, tomllib

TOP = pathlib.Path(__file__).resolve().parents[2]
UEFI, UNIXNU = TOP / 'uefi-ishtar', TOP / 'UniXNU'
EDK2 = UEFI / 'Mu_Basecore'
TARGET = sys.argv[1] if len(sys.argv) > 1 else 'DEBUG'
MU_PATCHES = ['AsmMacroLib.patch', 'Auth-Service.patch', 'Boot-Manager.patch', 'Timer.patch', 'Usb-Bus.patch']
PACKAGES = ['.unixnu-packages', 'Platforms/Xiaomi', 'Common/Mu', 'Common/Mu_OEM_Sample', 'Mu_Basecore',
            'Silicon/Qualcomm', 'Silicon/Silicium', 'Silicium-ACPI', 'Silicium-ACPI/Platforms/Xiaomi',
            'Silicium-ACPI/Silicon/Qualcomm']   # ishtarPkg/DeviceBuild.py PackagesPath

sys.path.insert(0, str(UNIXNU / 'scripts'))
from unixnu.util import clang_bin  # noqa: E402

run = lambda cmd, **kw: subprocess.run([str(c) for c in cmd], check=True, **kw)

stage = UEFI / '.unixnu-packages'
stage.mkdir(exist_ok=True)
for name, src in (('UniXNUPkg', UNIXNU / 'package/UniXNUPkg'), ('DarwinBootPkg', UNIXNU / 'drivers/DarwinBoot/DarwinBootPkg')):
    link = stage / name
    if not link.exists():
        link.symlink_to(src)

fd_cfg = tomllib.loads((UEFI / 'Resources/Configs/ishtar.toml').read_text())['uefi_fd']
base, size = fd_cfg['base'], fd_cfg['size']
tools = EDK2 / 'BaseTools'
if not (tools / 'Source/C/bin/GenFw').is_file():
    run(['make', '-C', tools / 'Source/C', f'-j{os.cpu_count()}'])
conf = UEFI / 'Build/conf'
conf.mkdir(parents=True, exist_ok=True)
for name in ('target', 'tools_def', 'build_rule'):
    if not (conf / f'{name}.txt').is_file():
        shutil.copy(tools / 'Conf' / f'{name}.template', conf / f'{name}.txt')
env = dict(os.environ, WORKSPACE=str(UEFI), EDK_TOOLS_PATH=str(tools), CONF_PATH=str(conf), PYTHON_COMMAND=sys.executable,
           PACKAGES_PATH=':'.join(str(UEFI / p) for p in PACKAGES),
           CLANG_BIN=clang_bin(UEFI / 'Build/toolchain'),
           PATH=os.pathsep.join([str(tools / 'BinWrappers/PosixLike'), str(tools / 'Source/C/bin'), os.environ['PATH']]))

DARWINBOOT = UNIXNU / 'drivers/DarwinBoot'
OURS = sorted((pathlib.Path(__file__).resolve().parents[1] / 'uefi').glob('darwinboot-*.patch'))
applied = []
try:
    for p in MU_PATCHES:
        run(['git', '-C', EDK2, 'apply', UEFI / 'Resources/MuPatches' / p])
        applied.append((EDK2, UEFI / 'Resources/MuPatches' / p))
    for p in OURS:
        run(['git', '-C', DARWINBOOT, 'apply', p])
        applied.append((DARWINBOOT, p))
    run(['build', '-p', 'ishtarPkg/ishtar.dsc', '-a', 'AARCH64', '-b', TARGET, '-t', 'CLANGPDB', '-n', os.cpu_count(),
         '-D', f'FD_BASE={base:#x}', '-D', f'FD_SIZE={size:#x}', '-D', f'FD_BLOCKS={size // 0x1000:#x}',
         '-D', 'ENABLE_SECUREBOOT=0', '-D', 'MEMORY_PROTECTION=TRUE', '-D', 'SHIP_MODE=FALSE',
         '-D', 'BUILDID_STRING=ishtar', '-D', 'DEVICE_MODEL=0'], cwd=UEFI, env=env)
finally:
    for repo, p in reversed(applied):
        run(['git', '-C', repo, 'apply', '--reverse', p])

fd = UEFI / f'Build/ishtarPkg/{TARGET}_CLANGPDB/FV/SILICIUM_UEFI.fd'
if not fd.is_file() or fd.stat().st_size != size:
    sys.exit(f'{fd} missing or not {size:#x} bytes')
print(fd)

# Android boot image for `fastboot boot`, as Mu's build_uefi.py makes it: BootShim + FD, gzip, + DTB, mkbootimg.
# RAMDISK (optional 2nd arg) is the UniXNU FAT payload; without it Mu's placeholder ramdisk is used (menu-only test).
import gzip  # noqa: E402
llvm = '/opt/homebrew/opt/llvm/bin'
run(['make', '-C', UEFI / 'BootShim', '-B', f'CC={llvm}/clang', f'OBJCOPY={llvm}/llvm-objcopy',
     'REQUIRES_KERNEL_HEADER=1', f'FD_BASE={base:#x}', f'FD_SIZE={size:#x}'])
out = pathlib.Path(__file__).resolve().parents[1] / 'out'
out.mkdir(exist_ok=True)
kernel = out / 'ishtar-uefi-kernel'
kernel.write_bytes(gzip.compress((UEFI / 'BootShim/BootShim.bin').read_bytes() + fd.read_bytes(), mtime=0)
                   + (UEFI / 'Resources/DTBs/ishtar.dtb').read_bytes())
ramdisk = sys.argv[2] if len(sys.argv) > 2 else UEFI / 'Resources/ramdisk'
img = out / f'uefi-ishtar-{TARGET.lower()}.img'
run([sys.executable, UEFI / 'Resources/Scripts/mkbootimg.py', '--kernel', kernel, '--ramdisk', ramdisk,
     '--header_version', '1', '-o', img])
print(img)
