#!/usr/bin/env python3
"""Host regression check: check-cpufreq.py PATH/TO/PATCHED/XNU (requires Xcode)."""
import pathlib
import subprocess
import sys
import tempfile

source = (pathlib.Path(sys.argv[1]) / 'bsd/dev/ishtar_cpufreq.c').read_text()
start = source.index('\t\t\tconst uint32_t cap = MIN(cf8_want[d]')
end = source.index('\n\t\t}\n\t\tif (ticks % 250', start)
tick = source[start:end].replace('__asm__ volatile ("dsb sy" ::: "memory");', '')
harness = r'''
#include <assert.h>
#include <stdint.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
static uint32_t cf8_want[3]={15}, cf8_gov=1, cf8_set[3]={15};
static uint32_t cf8_rows[3]={16}, cf8_low[3], cf8_load_seen[3];
static uint32_t mmio[0x400/4];
static uintptr_t cf8_base[3];
static unsigned sample;
static uint32_t cf8_load(unsigned d,uint64_t wall) {(void)d;(void)wall;return sample;}
static uint32_t cf8_khz(unsigned d,uint32_t state) {(void)d;return 300000+state*100000;}
static void tick(unsigned busy) {
    const unsigned d=0; const uint64_t wall=1; sample=busy;
''' + tick + r'''
}
int main(void) {
    cf8_base[0]=(uintptr_t)mmio;
    tick(0); assert(cf8_set[0]==15 && cf8_low[0]==1);
    tick(0); assert(cf8_set[0]==15 && cf8_low[0]==2);
    tick(0); assert(cf8_set[0]==13 && cf8_low[0]==0 && mmio[0x320/4]==13);
    for(unsigned i=0;i<21;i++) tick(0);
    assert(cf8_set[0]==0 && mmio[0x320/4]==0);
    tick(90); assert(cf8_set[0]==15 && cf8_low[0]==0);
    tick(0); tick(70); assert(cf8_set[0]==15 && cf8_low[0]==0);
    tick(0); tick(0); assert(cf8_set[0]==15 && cf8_low[0]==2);
    tick(100); assert(cf8_set[0]==15 && cf8_low[0]==0);
    cf8_want[0]=3; tick(100); assert(cf8_set[0]==3);
    cf8_gov=0; cf8_want[0]=7; tick(0); assert(cf8_set[0]==7);
    cf8_want[0]=0; tick(0); assert(cf8_set[0]==0 && cf8_low[0]==0);
    cf8_gov=1; tick(0); assert(cf8_set[0]==0 && cf8_low[0]==0);
    cf8_want[0]=99; tick(100); assert(cf8_set[0]==15);
    return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory)
    (path / 'check.c').write_text(harness)
    sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
    subprocess.run(['xcrun', '--sdk', 'macosx', 'clang', '-isysroot', sdk,
                    '-std=c11', '-Wall', '-Wextra', '-Werror',
                    str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
print('CPU governor checks passed: downshift, idle floor, boost, interrupted low samples, fixed mode, caps')
