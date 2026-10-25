#!/bin/sh
# Collect hardware facts from a booted stock ishtar over adb. Root (su) gets the live FDT and iomem.
# usage: scripts/probe-device.sh [OUT]   (OUT defaults to ../stock/ishtar/live)
set -u
OUT=${1:-$(cd "$(dirname "$0")/../.." && pwd)/stock/ishtar/live}
mkdir -p "$OUT"
a() { adb shell "$@" 2>&1; }
r() { adb shell su -c "'$*'" 2>&1; }

adb devices -l > "$OUT/devices.txt"
a getprop > "$OUT/getprop.txt"
a cat /proc/meminfo > "$OUT/meminfo.txt"
a cat /proc/cpuinfo > "$OUT/cpuinfo.txt"
a ls -l /dev/block/by-name/ > "$OUT/partitions.txt"
a cat /proc/partitions > "$OUT/proc-partitions.txt"
a ls /sys/bus/i2c/devices /sys/bus/spi/devices /sys/bus/platform/devices > "$OUT/buses.txt"

if a su -c id | grep -q uid=0; then
  r cat /proc/iomem > "$OUT/iomem.txt"
  r dmesg > "$OUT/dmesg.txt"
  r cp /sys/firmware/fdt /data/local/tmp/fdt && adb pull /data/local/tmp/fdt "$OUT/live.dtb" && dtc -q -I dtb -O dts -o "$OUT/live.dts" "$OUT/live.dtb"
  r cat /sys/firmware/devicetree/base/memory/reg | xxd > "$OUT/memory-reg.txt"
  r cat /proc/cmdline > "$OUT/cmdline.txt"
  r lspci > "$OUT/lspci.txt"
else
  echo "no root: skipped iomem, dmesg, live FDT" | tee "$OUT/NO-ROOT"
fi
ls "$OUT"
