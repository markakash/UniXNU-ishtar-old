# ishtar (Xiaomi 13 Ultra, SM8550-AB) — iOS 18.7.8 port

Target: iPhone XR (`iPhone11,8`) iOS 18.7.8 (22H352) userland, xnu-11215.81.4 kernel
(`xnu/base` + `tools/base`, fetched by `scripts/sync-base.py` with every upstream name renamed to ishtar;
machine config `ISHTAR`), Renegade PAC rewrite. Boot: ABL → `fastboot boot` →
Mu-Silicium UEFI (`../uefi-ishtar`, from uefi-nuwa) → UniXNU menu → DarwinBoot → XNU.
iOS 26 later: same board patches on the upstream iOS 26 series (xnu-12377), synced the same way.

Source of every value below: stock ROM `OS3.0.308.0.WMACNXM` (HyperOS 3, CN), extracted by
`scripts/extract-stock.sh` into `../stock/ishtar`. Board DT = vendor_boot dtb #02 (Kalama v2, msm-id 0x207 rev 2)
+ dtbo #07 ("8550 ishtar") → `../stock/ishtar/ishtar-merged.dts`. Live-device values: TODO(`scripts/probe-device.sh`).

## Hardware inventory

| Block | ishtar | Source / note |
| --- | --- | --- |
| SoC | SM8550-AB v2, msm-id 0x207 | dtb #02. Confirm `/sys/devices/soc0/soc_id` live |
| CPU | 0-2 A510, 3-4 A715, 5-6 A710, 7 X3; MPIDR Aff1 0x000-0x700; PSCI smc | sm8550.dtsi |
| GIC | GICv3, GICD 0x17100000+0x10000, GICR 0x17180000+0x200000, stride 0x40000 | needs `xnu/patches-ishtar/2000` |
| Arch timer | PPIs 13/14/11/12; EL1 virtual timer = PPI 11 = INTID 27 | stock DT `arm,armv8-timer` |
| RAM | 12/16 GB; /memory filled by ABL at boot | TODO live `/proc/iomem` |
| Reserved memory | identical to nuwa (37 regions, diffed) | so nuwa's UEFI MemoryMapLib is reused |
| Framebuffer | splash_region 0xb8000000+0x2b00000, 1440x3200 | panel M1 42_02_0a LTPO DSC cmd |
| UEFI | BOOT.MXF.2.1.1-00218-KAILUA-1.36233.1, same build as nuwa; uefiplat.cfg identical | `uefi-ishtar/Binaries/ishtar` |
| UFS | ufshc@1d84000 (UFS 4.0), phy 0x1d80000 | Mu UFSDxe (patched) leaves host up |
| Keys | PMK8550 PON @0x1300: KPDPWR bit 7 power, RESIN bit 6 volume down; volume up PM8550 (SID 1) GPIO6; SPMI v7 core 0xc400000, obsrvr 0xc440000, EE 0 | done → `2010` |
| Touch | (2011 probe: power + bus up, SE8 is GSI-only) **ST FTS (FTM5) over SPI**, QUP SE8 spi@880000, IRQ TLMM 118 (new units: 67), reset TLMM 117, avdd = PM8008i L7 (I2C@988000 addr 9), vdd = L12B, x/y-max 14400/32000 | new driver; Goodix GT9916 node is QRD leftover |
| Wi-Fi/BT | WCN7851 (cnss-qca-converged) on PCIe0 @1c00000 | later |
| GPU | Adreno 740 | later (UniXNU Adreno740 is iPadOS-17 ABI) |

## Kernel patches to forward-port onto xnu/base (11215) (`xnu/patches-ishtar`, 2000+)

Source: `ref/negroni-ios16/xnu/patches` (SM8450, iOS 16; already renamed, so they target the same Ishtar* code).
Dry run on xnu-11215.81.4 with dxb 15.0 + `.sh` staging: 219/219 (216 base + 2000-2002).

| Patch | State |
| --- | --- |
| 0082 gicr-stride-from-adt | applies cleanly → `2000-ishtar-gicr-stride-from-adt.patch` |
| 0083 no-physical-timer-write (Gunyah) | done → `2001` |
| 0087 sm8450-keys → PMK8550 | 4 hunks, base keys driver was rewritten upstream |
| 0088 framebuffer size | likely obsolete: base 0100 canvas-from-adt |
| 0089 UFS power (SM8550 GCC offsets from Linux v6.12 gcc-sm8550.c), no battery | done → `2002` |
| 0090/0092 UFS sense, START UNIT to W-LUN | done → `2008` (base already decodes sense) |
| 0096/0098 cpufreq EPSS | 3+3 hunks |
| early framebuffer (base hard-codes 0x9c000000, a protected carve-out on SM8550) | done → `2003` (0xb8000000, 1440x3200) |
| 0119 usb sm8450 | 1 hunk, later |
| touch | new: ST FTS SPI on GENI SE8 + PM8008 L7 |
| 2033 CPU governor downshift | fixes a counter reset that prevented clocks falling after load; host/CI regression passes; hardware requested states fall to 307/1171/595 MHz after disabling the serial spinner; see `docs/HEATING.md` |
| 2034 framebuffer console probe | prevents re-registering a static backend into a circular list; original fails host regression, fix passes; `serial=1` removes unused input reader, verified in a controlled hardware comparison |
| 2035 ADSP battery | **works (2026-10-29)**: UEFI starts the ADSP (`uefi-ishtar` `Binaries/ishtar/RawFiles/uefipil.cfg` `[AUTO]` + `FULL_ADSP`), `bsd/dev/ishtar_adsp.c` takes it over (SMP2P, GLINK, QRTR + PD locator) and reads battmgr every 10 s into `IshtarBattery` (personality back). First read: 82%, charging, 4.25 V, 34.3 C, full 4756/design 4880 mAh, 211 cycles; battmgr current is negative while charging (flipped). Boot-arg `ishtar-adsp=1`. Loading the ADSP from XNU (`ishtar-adsp=2`, TZ PAS dtb 36 then adsp 1) still hangs the SoC inside MEM_SETUP of pas 36 (init_image returns 0; bandwidth votes and an uncached metadata page did not help). SMEM must be mapped as device memory: a write-combining map of all 2 MiB hung the UI minutes later. Firmware for the XNU loader: `out/adsp-fw` -> `/private/var/ishtar/adsp/` |

## Device log

| Date | Image | Result |
| --- | --- | --- |
| 2026-10-25 | uefi-ishtar DEBUG, nuwa memory map | display up (panel M1 detected, hw id 0x5); PILDxe `pil-abl Failed to read from partition` → target panic → watchdog reset |
| 2026-10-25 | + `#ABL` in uefipil.cfg `[AUTO]` | past PIL; `AllocatePoolPages failed` on the 69 MiB DXE heap, BdsDxe not loaded, DxeMain.c(581) ASSERT |
| 2026-10-25 | + DXE heap 0xBAE00000+0x0D1C0000 (sheng's size; free per stock reserved-memory) | **UniXNU 0.1.0 menu, "no boot entry found"** (no payload) |
| 2026-10-25 | + payload, kernel 07863d7 | entry listed; DarwinBoot: kernel pa 0x8C0004000, va 0xFFFFFE0007004000, window 0xC0000000, video 0xB8000000 1440x3200; green bar, then hang (base start.s writes 0x9c000000) |
| 2026-10-25 | + 2003 (early fb 0xb8000000) | same hang. Cause: DarwinBoot aligns VA/PA mod 2 MiB, the 16 KiB-page kernel maps 32 MiB blocks (VA 0x...7004000 vs PA 0x8C0004000 differ by 16 MiB mod 32 MiB) → `uefi/darwinboot-32mb-block.patch` |
| 2026-10-25 | + DarwinBoot 32 MiB, `ishtarearlyfb=1` | **XNU 11215 runs**: verbose console, VM, zones, AMFI, "platform expert registered", then stop |
| 2026-10-25 | + 2004 heartbeat, `io=0xc` | all nubs register (cpu0-7, arm-io, fbcon, buttons, wdt, disp0); no driver starts, no heartbeat → interrupts. ABL/UEFI leave SPIs enabled+pending → `2005` disables/clears them |
| 2026-10-25 | + 2005, 2006 raw-pixel diagnostics | threads scheduled, one IPI taken, no timer IRQ ever: ADT said virtual-timer-intid 19 (SM7150/SDM845 PPI 3); SM8550 virtual timer is PPI 11 = INTID 27 → `vtimer=27` in the ADT board |
| 2026-10-25 | + vtimer 27 (ADT only, kernel 4380727) | **IOKit + BSD up**: IshtarCPU cpu0, AppleCLCD 1440x3200 (presented 1125x2436), watchdog, IOSurface, HID services, AMFI/Sandbox stand-ins, HFS, lo0; ends at `Waiting on <dict>…IOMedia…Apple_HFS` (UFS off by design). Timer IRQs and heartbeat work |
| 2026-10-25 | 2006 parked, `io=0xc` dropped, `ishtarfb_statlog=0`, **`cpus=8`** | **SMP works**: PSCI CPU_ON rc=0 for cpu1-7, "8/8 CPUs initialized, SGI1 verified", heartbeat steady, ends at the same root wait |
| 2026-10-25 | `--ufs` (rd=ufsroot0, no ufsrw) | host taken over, TUR → NOT READY (sense key 2): UEFI leaves the device powered down |
| 2026-10-25 | + 2007 (10 s before root panic), 2008 START STOP UNIT active → W-LUN 0xd0 | **UFS read-only works**: `device power mode active: 0`, TUR 0, `"userdata" on LUN 0: first block 0x2f3040, 229483 MiB, read-only`; HFS rejects the Android volume (signature 0x821e), `cannot mount root, errno = 19` — expected |
| 2026-10-25 | iOS 18.7.8 root (`renegade root --no-jb`, 15.2 GiB simg) flashed to userdata; `build-payload.py --root` | **iOS 18 boots to the lock screen** (seen ~1 s), then black: iOS powers the display off, the fb blanks it (no WLED control on ishtar), no keys/touch to wake → `2009` `ishtarfb_keepon=1` |
| 2026-10-25 | + 2009 keepon, 2010 keys (SPMI v7, PMK8550 PON + PM8550 GPIO6) | **power and volume keys work in iOS**; lock screen stays visible |
| 2026-10-25 | 2011 touch probe, stages 1-5 (`ishtartouchprobe=20 ishtartouchstage=5`) | touch path cold after ABL. Stage 2: wrap2 SE0 + I2C hub clocks voted (s-ahb are HW-gated, 0x80000002 = fine), pins routed (SPI gpio0/1/109/107 mux 2, I2C gpio20/21 mux 1). Stage 3: hub SE2 fw 0x303 (I2C), PM8008 at 0x8 type 81 subtype 44. Stage 4: **L7 3.3 V VREG_READY** (0x4640/41 = mV LE, 0x4646 bit 7). Stage 5: SE8 fw 0x102 (SPI) but **GENI_IF_DISABLE_RO = 1: FIFO interface disabled, GSI (GPI DMA) only**. Next: GPI DMA (+ SMMU) for SPI |
| 2026-10-26 | 2012 USB (SM8550 GCC offsets, GUCTL1 force-2.0, SMMU sid 0x40 auto identity map; identity map widened to 64 GiB) | **USB Ethernet works**: Mac en13, phone 192.168.7.2 ping 2 ms, live kernel log over UDP 5140 |
| 2026-10-26 | 2013 touch over GPI DMA (stage 6, `ishtartouchdefer=25` so the steps reach the live log) | SMMU sid 0x436 mapped (cb 6, smr 6); GPI ee_offset 0x10000 (downstream `qcom,gpi-ee-offset`). GPII 0-5 contexts read 0; **reading GPII 6 resets the SoC** (not HLOS); **the first write to GPII 1 EV_CMD resets the SoC**. Downstream does nothing extra at probe; candidates: ICC/bandwidth votes for QUP/GPI, interrupt config before the first command, or hypervisor assignment |
| 2026-10-26 | 2013 + Linux gpi_config_interrupts before the first command (image G, GPII 1) | **GPI accepts commands**: event ring allocated, both channels allocated and STARTED; SoC resets at the doorbells (first DMA). Suspect: no interconnect (BCM) vote for the QUP master path, or DMA/SMMU detail. Image I (`out/touch-I.img`) splits RX/TX doorbells with state dumps — not booted yet |
| 2026-10-26 | Image I (split doorbells) | RX doorbell OK (ch1 started, rp at ring base, no error); **SoC resets on the TX doorbell** (CONFIG0 + GO + DMA TREs). 2014 adds RPMh BCM votes (QUP2, SN3 = aggre2 carrying qhm_qup2, SN0, SH0, MC0) via apps_rsc drv-2 (RSC v3) before GPI bring-up; image J (`out/touch-J.img`): **votes complete (done 0x1f), still resets at TX** → not BCM. Downstream DT: SE8 `dmas` option 2 = **static GPII 0** (`qcom,static-gpii-mask = <1>`); we used GPII 1. Image K: `ishtartouchgpii=0` |
| 2026-10-26 | Image K (GPII 0) | **still resets at TX doorbell**. Stock ishtar DT (stock/ishtar/ishtar-merged.dts) matches: SE8 dmas option 2, gpi_dma2 static mask 1, `qcom,iommu-dma-addr-pool = <0x100000 0x100000>`, dma-coherent. 2015 maps IOVA 0x100000 → the GPI DMA block (4K pages in the shared SMMU bank, L1[0]); image L |
| 2026-10-26 | Image L (IOVA 0x100000) | **no reset**: the whole probe runs. TX doorbell → ch0 state 5, rp not advanced, TYPE_IRQ 0x40 (general = downstream `MSM_GPI_QUP_FW_ERROR`), 0 events; chip ID 00. Image M dumps GPII/SE8 state on failure |
| 2026-10-26 | Image M | GPII_IRQ_STTS 0x2 = **bus error** fetching the first TX TRE (rp stays at ring base); SE8 idle (status 0, no M IRQ). Cause: L3 table PA from pmap_find_phys(t+4K) is the 16K page base → L2 pointed at itself. Fixed (l3 = l2 + 4K); image N |
| 2026-10-26 | Image N (valid low IOVA) | **resets at TX doorbell again**. Valid translation → reset (I/J/K, N); faulting translation → bus error, no reset (L/M): the reset follows successful TRE processing (completion IRQ or SE traffic). 2016 masks GPII IRQs, prints GICD enable for INTID 620-631, sends one flagless LOCK TRE first; image O |
| 2026-10-26 | Image O | GICD has INTID 620-631 disabled (not an IRQ issue); **LOCK TRE consumed (rp +0x10), no reset**: GSI fetch path fine. Resets once CONFIG0/GO/DMA reach SE8. Image P: UNLOCK+IEOT (event write) then one doorbell per SPI TRE; TREs now exactly Linux gpi_create_spi_tre (DUPLEX GO rx_len 0, RX DMA no IEOT) |
| 2026-10-26 | Image P | CONFIG0 consumed; GO consumed (SE8 status 0x41, command active); **reset on the DMA TRE** (first GSI memory write / SE data). UNLOCK+IEOT gave no event |
| 2026-10-26 | HyperOS ground truth (Magisk root, ipc_logging 880000.spi / gpi_dma800000) | SE8 = GPII 0 (`gpi_of_dma_xlate: gpii:0 ... proto:1 SE:0`); CONFIG0 **word 4 pack 3 idx 2 div 4** (48 MHz / 4 = 12 MHz, fts spi-max); never duplex: writes = CONFIG0 + GO(cmd 1) + DMA(IEOT), reads = GO(cmd 1, FRAG) + DMA then GO(cmd 2, rx_len, link_rx, IEOB) + RX DMA; TX doorbell before RX. Touch IRQ on this unit = **GPIO 67** (`xiaomi_tpfts`), GPII0 = INTID 620. 2017 copies that pattern; image Q |
| 2026-10-26 | Image Q (stock TRE pattern) | still resets on the write part. Stock DT: **qupv3_2 wrapper @8c0000 has its own SID 0x423** (pool 0x40000000+256M); stock spi-msm-geni maps data buffers on the wrapper device → data moves on SID 0x423, unmapped here (USFCFG=1). 2017 maps 0x423 to the same bank; image R |
| 2026-10-26 | Image R (SID 0x423 mapped) | **touch SPI over GPI works**: no reset, every transfer completes (3 events, RX lengths right), iOS boots. Chip answers 00: FTM5 without fw runs SPI3 (MISO unused). Pins match stock (mux 2 = qup2_se0_lX_mirb). Next: stock fts_spi4_mode_set (SALIXP: 0x20000032=0x10, 34=0x02, 3e=0x07, 3d=0x30, ICR 2d=0x02) + system reset; image S |
| 2026-10-26 | Image S | chip id 00 before/after SPI4 set and system reset. Image T: SE loopback self-test (CONFIG0 loopback, duplex) + RX buffer prefilled A5 to tell "no RX data" from "MISO low" |
| 2026-10-26 | Image T | **SE loopback returns 12 34 .. f0** and the A5 prefill is overwritten: GPI + both SIDs + SE + DMA all proven; the FTM5 MISO is really silent |
| 2026-10-27 | HyperOS capture (`tools/research/hyperos-cap/`, git-ignored; script `tools/research/capture/hyperos-capture.sh`) | stock fts: vdd = pm_humu_l12 (L12B, rpmh `ldob12`) 1.8 V, avdd = pm8008i_l7 3304 mV, reset gpio 117 (out high, 8 mA, pull-up), irq gpio 67 (pull-up); system reset -> event 03, FW VER 0015 (chip has fw, SPI4 by itself). 2018: SPMI read of L12B, rpmh VRM vote ldob12 1800 mV, stock power order (reset low -> vdd -> avdd -> 16 ms -> reset high); image U |
| 2026-10-27 | Image U | **FTM5 answers: chip id 36 40, system reset -> event 03 (controller ready)**. Root cause of the silence: vdd L12B was off (rpmh vote `ldob12` fixed it). 2019: FTM5 event loop (scan on A0 00 01, irq gpio67 poll, FIFO 87, super-resolution x/y /10 -> 1440x3200, ids 13/23/33) feeding ishtar_hid_touch; image V |
| 2026-10-27 | Image V | loop runs, scan-on acked (43 01 a0 00 01), but no touch events. Stock (event7 "fts" = kernel driver, not THP) does scan 01,00,01. Image W: stock scan sequence + FIFO polled every 500 ms regardless of irq + 5 s heartbeat (irq level, reads, events) |
| 2026-10-27 | Image W | loop stalls after 2 FIFO reads (no heartbeat; last TX TRE ~element 47-56 of 64, suspect TX ring wrap). Image X: failures always logged, per-read line (ring pointers), 2 s watchdog thread (stage, counters, ring and channel state) |
| 2026-10-27 | Image X | TX ring wrap fine (wp > 64, 3 events per read). **irq gpio67 held low, FIFO reads all 00** (first read had the 4 status events); later EOT events stop (fails grow). Stock idles irq high. PM8008 L7 is NPM, no OCP. Image Y: raw dummy + 9 bytes per read, chip-id alive check every 20 reads; spi4-mode writes now off (stock does them only when system reset fails = no fw) |
| 2026-10-27 | Image Y | chip alive (id 36 40 every check), FIFO empty, irq low; force-cal status events as stock. **HyperOS runs THP** (logcat [THP-ALG] alg_input_report: raw frames to a userspace algorithm). Stock fts_enable_thp_onoff(0) = A0 00 00, C0 21 01, A0 00 01 gives native fw reporting; image Z |
| 2026-10-27 | Image Z (`out/touch-Z.img`) | **TOUCH WORKS in iOS**: THP off acked (43 01 c0 21 01), native events 13/23/33 (e.g. 13 01 f5 1e bf 7c = x 792, y 3193 of 1440x3200), irq gpio67 behaves, 0 failed reads. Chain: rpmh BCM + ldob12 (vdd) votes, PM8008 L7 (avdd), stock power order, GPII 0, SIDs 0x436 + 0x423 at IOVA 0x100000, stock TRE pattern (CONFIG0 idx2/div4), THP off. Next: run by default (no probe boot-args), drop probe-only steps, GIC irq instead of 4 ms poll |
| 2026-10-27 | Image Z, longer use | touch worked (lock screen -> home), then froze: after ~650 completion events ev_rp desynced from the engine (fixed "3 events per transfer" assumption), events stopped, every read failed. Fix (Linux gpi_process_events): drain events up to EV CNTXT_4, completion = channel RP == WP; image AA |
| 2026-10-27 | Image AA | **touch stable**: 2090 events, 0 failures across unlock, home screen, lock/unlock. `out/ios-touch-baseline.img` |
| 2026-10-27 | 2020 A740 GPU (kernel only, not booted) | `scripts/port-a740.py` imports UniXNU Adreno740 + AdrenoPM4/AdrenoFirmware/ArmSmmu4K kits (MIT), SM8550 GMU kit and the SM8550 reference board's staged `GpuPowerProbe` (BSD-2-Clause-Patent) into `iokit/Kernel/arm/a740/` (62 files, names -> SM8550/ishtar). `scripts/gen-a740-sources.py` generates the GMU register/RSC/OPP/BCM/cmd-db headers from pinned sm8550-mainline@42f3b40c. 16K-kernel fixes: page numbers via PAGE_SHIFT, buffers rounded to whole kernel pages. Firmware from ADT `/ishtar-gpu` (`build-payload.py --gpu-fw DIR`, `scripts/adt-a740fw.py`; GMU = stock = pinned sha, SQE = stock 76724 = linux-firmware, zap = stock mdt+b00-02 merged). Boot-args `ishtar-gpu-power=1..9` (1 read-only ... 9 CP+zap+IRQ), `ishtar-gpu-delay=S`. Images `out/gpu-s{1,3,5,6,7,8,9}.img` |
| 2026-10-27 | GPU G1 on hardware: **all stages pass** | s1 probe, s3 CX GDSC, s5 GMU SMMU ctx + cmd-db, s6 GMU clocks, s7 GMU firmware running + HFI (4 msgs, no fault), s8 GX on, s9 GPU ctx + CP (scratch write, CP_MEMCPY 1023/1023), zap (init/mem_setup/auth 0, CP left secure mode), GPU IRQ (SPI 300) firing. Fixes on the way: probe at the board's timing (16 MB contiguous GMU memory only early), exact buffer sizes on 16K pages (descriptor rounded, size not), ml_io_unmap of whole 16K pages (4K unmap panicked = the "freezes"), SPI attach in pe_fiq.c + sleh_irq dispatch, zap = /odm/firmware/a740_zap.mbn (the /vendor split copy is refused with 0xffcfffbb), kernel window 8 GiB (`board.toml dram_size`; 3 GiB starved the 1.5 GB BO pool). Image `out/gpu-s9-zap.img` |
| 2026-10-27 | GPU G2: **Metal on iOS 18, UI composited on the A740** | NativeAdrenoPublish user client behind our IOAcceleratorES (`ishtarmetal=1`), plugin pushed over USB (patch 2021 `ishtar_push.c`, `scripts/push.py`). Plugin for iOS 18 (`gpu/adrenometal-0001-ios18.patch`: _MTLDevice 600 bytes, unknown setters ignored). User GPU test 4/4, Turnip smoke v1024, frontend F0; publish mode = backboardd on the GPU; clients list = icons/widgets/posters. Fixes: pooled BOs exact sizes, GPU idle wait before the panel copy (ghosted/empty frames), CPU scaler rows + 5 threads + `ishtarfb_hz=60` (9 -> 30-36 fps), `ishtarfb_scale=2` (no bars), VFS patch 2023 (class D, newer attribute bits), **ADT identity iPhone XR n841ap** (the root's own device: default wallpaper + artwork; 828x1792 canvas). Wallpaper + Settings icons render. Image `out/g2-l.img` |
| 2026-10-27 | Display: SM8550 DPU page flip (patch 2025 `IshtarDpu.cpp`, boot-arg `ishtardpu=1`) | Ground truth: mainline `dpu_9_0_sm8550.h` + single-register dump (dpu-3; a block dump of the DPU top stalled the bus): MDSS 9.0.0, CTL0 -> INTF_1 (DSI0 cmd mode, tear check, autorefresh 0x80000001), DSC0+1, VIG0+VIG1 each 720 columns of 0xb8000000 (stride 5760). Panel `xiaomi 42 02 0a cmd mode dsc` (1440x3200, DSC 1.2, 30/40/60/90/120 Hz timings). Double buffering in the 45 MB UEFI carve-out, both pipes + one CTL flush: tear-free (953 flips, 0 latch waits/timeouts). Streaks were stale cache lines of the GPU-written surface: rows are invalidated (dc civac) before the copy. Image `out/flip-2.img` |

Live probe (no root): 12 GB (MemTotal 11458772 kB), soc_id 519 rev 2.0, CPU features include `paca pacg jscvt bti`,
no MTE; slot _a; userdata = sda30 (LUN 0), ~224 GiB.

## First-boot order

1. ~~UEFI menu on screen~~ done 2026-10-25. Next: payload FAT seen (initrd), entry listed.
2. ~~DarwinBoot hands off; XNU early console~~ done; ~~IOKit/BSD up to root wait~~ done 2026-10-25.
3. ~~UFS root (HFS+ image from Renegade in `userdata`), launchd~~ lock screen 2026-10-25.
4. Keys, touch, cpufreq (SMP done 2026-10-25). Then GPU / Wi-Fi.
