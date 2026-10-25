#!/usr/bin/env python3
"""Host regression check: check-fbcon.py PATH/TO/PATCHED/XNU (requires Xcode)."""
import pathlib
import subprocess
import sys
import tempfile

source = (pathlib.Path(sys.argv[1]) / 'pexpert/arm/pe_serial.c').read_text()


def function(name):
    start = source.index(name + '(')
    return source[start:source.index('\n}', start) + 2]


harness = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
typedef void *DTEntry;
enum {kSuccess=0};
struct pe_serial_functions {
    unsigned (*receive_ready)(void);
    uint8_t (*receive_data)(void);
    struct pe_serial_functions *next;
};
static struct pe_serial_functions *gPESF;
static volatile uint32_t *fbcon_base;
static uint32_t framebuffer[64*64], fbcon_width=64, fbcon_height=64, fbcon_stride=256;
static unsigned available, allow_map, maps, serial_do_transmit;
static int SecureDTFindEntry(const char *key,const char *name,DTEntry *entry) {
    (void)key;(void)name;*entry=0;return available?0:1;
}
static int SecureDTGetProperty(DTEntry entry,const char *key,const void **data,unsigned *size) {
    static const uint64_t reg[]={0x1000,sizeof(framebuffer)};
    (void)entry;if(strcmp(key,"reg"))return 1;*data=reg;*size=sizeof(reg);return 0;
}
static void *ml_io_map_wcomb(uint64_t base,uint64_t size) {
    (void)base;(void)size;maps++;return allow_map?framebuffer:0;
}
#define ishtar_early_mark(stage,text) ((void)0)
static unsigned ''' + function('fbcon_receive_ready') + '\nstatic uint8_t ' + function('fbcon_receive_data') + r'''
static struct pe_serial_functions ishtar_fbcon_serial_functions={fbcon_receive_ready,fbcon_receive_data,0};
static void ''' + function('register_serial_functions') + '\nstatic void ' + function('fbcon_probe') + '\nint ' + function('uart_getc') + r'''
int main(void) {
    fbcon_probe(); assert(!gPESF && maps==0);
    available=1; fbcon_probe(); assert(!gPESF && !fbcon_base && maps==1);
    allow_map=1; fbcon_probe(); assert(gPESF==&ishtar_fbcon_serial_functions && maps==2);
    for(unsigned i=0;i<100;i++) fbcon_probe();
    assert(gPESF->next==0 && maps==2);
    assert(uart_getc()==-1);
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
    subprocess.run([str(path / 'check')], timeout=5, check=True)
print('Framebuffer console checks passed: missing device, map retry, repeated probe, empty input')
