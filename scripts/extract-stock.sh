#!/bin/sh
# Extract ishtar board inputs from a HyperOS fastboot ROM.
# usage: scripts/extract-stock.sh ROM_DIR_OR_TGZ [OUT]   (OUT defaults to ../stock/ishtar)
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
TOP=$(dirname "$HERE")
ROM=$1
OUT=${2:-$TOP/stock/ishtar}
mkdir -p "$OUT/images" "$OUT/boot" "$OUT/vendor_boot" "$OUT/dtb" "$OUT/uefi"

if [ -f "$ROM" ]; then
  tar -xzf "$ROM" -C "$OUT" --include='*/images/*'
  ROM=$(dirname "$(find "$OUT" -path '*/images/boot.img' | head -1)")
fi
[ -f "$ROM/boot.img" ] || ROM=$ROM/images
for i in boot.img vendor_boot.img dtbo.img uefi.elf xbl_s.melf xbl_config.elf; do
  cp "$ROM/$i" "$OUT/images/" 2>/dev/null || echo "missing $i"
done

python3 "$TOP/tools/unpack_bootimg.py" --boot_img "$OUT/images/boot.img" --out "$OUT/boot" > "$OUT/boot/info.txt"
python3 "$TOP/tools/unpack_bootimg.py" --boot_img "$OUT/images/vendor_boot.img" --out "$OUT/vendor_boot" > "$OUT/vendor_boot/info.txt"

# vendor_boot "dtb" is a concatenation of FDTs; split on the d00dfeed magic.
python3 -I - "$OUT/vendor_boot/dtb" "$OUT/dtb" <<'EOF'
import struct, sys, pathlib
data = pathlib.Path(sys.argv[1]).read_bytes(); out = pathlib.Path(sys.argv[2]); i = n = 0
while (i := data.find(b'\xd0\x0d\xfe\xed', i)) >= 0:
    size = struct.unpack('>I', data[i + 4:i + 8])[0]
    (out / f'{n:02d}.dtb').write_bytes(data[i:i + size]); i += size; n += 1
print(f'{n} dtbs')
EOF
for d in "$OUT"/dtb/*.dtb; do dtc -q -I dtb -O dts -o "${d%.dtb}.dts" "$d"; done
grep -l "ishtar\|SM8550\|kalama" "$OUT"/dtb/*.dts | head -5

# Qualcomm UEFI DXE drivers for uefi-ishtar Binaries/ishtar.
DOTNET_ROLL_FORWARD=Major dotnet "$TOP/tools/UEFIReader/UEFIReader/bin/Release/net8.0/UEFIReader.dll" \
  "$OUT/images/uefi.elf" "$OUT/uefi" > "$OUT/uefi/reader.log" 2>&1 || tail -5 "$OUT/uefi/reader.log"
find "$OUT/uefi" -name '*.efi' | wc -l | xargs echo "efi modules:"
echo "done: $OUT"
