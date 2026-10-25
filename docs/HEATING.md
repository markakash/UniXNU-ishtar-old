# Idle heating investigation (2026-10-28)

The user reported severe heat after leaving iOS idle. The phone was returned to fastboot and unplugged;
no temperature, battery current or power measurement was available.

## Confirmed CPU governor defect

The idle log repeatedly reports requested clocks of 2016/2803/3187 MHz (caps 15/19/20), including samples
with load 8/100/0% and no display swaps. These are EPSS requested states, not independently measured clocks.

In `bsd/dev/ishtar_cpufreq.c`, `cf8_thread` requires three low-load samples before lowering a cluster's
state. For the first two samples it holds `w` at the current state. The following `w >= cf8_set[d]`
check then clears the low-sample counter, so it never reaches three. Once raised, clocks stay raised.

Patch 2033 resets that counter against the requested state before hysteresis holds it, and clears it
after a state change. The existing LUT, hardware writes, frequency limits and load calculation stay intact.
`scripts/check-cpufreq.py PATH/TO/PATCHED/XNU` compiles the actual governor decision block on the host:
the original fails the first low-sample assertion; the fix passes downshift, convergence to the idle floor,
immediate boost, interrupted low samples, fixed-frequency mode and cap checks.

## Serial input spinner identified

Kernel thread 212 appears on a core in every one of the last 200 `running` samples. The busiest middle
cluster core frequently reports 100% load while the display swap count is unchanged. This supports a
continuously runnable kernel thread; the old `c0` fallback cannot identify its function or stack.
Patch 2032 already records kernel-thread entry functions, but that addition was made after the gov-7
image was packed. The next image includes it; resolve any `k<address>` against that exact kernel's symbols.
An entry function may identify a generic worker rather than its active callback.

The supervised heat-1 boot identified thread 212's entry as `0xfffffe00074f71e8`, exactly
`serial_keyboard_start` in the kg63 kernel. The thread runs at `MAXPRI_KERNEL`. At idle the middle cluster
remained at 2803 MHz / 100% load, while unloaded clusters fell as low as 307 and 595 MHz. This validates
the governor correction on hardware and identifies the separate continuously runnable serial reader.

`serial_init()` calls `fbcon_probe()` before checking for a UART phandle. On this framebuffer-only board
it returns without setting `uart_initted`. A later call probes again; `register_serial_functions()` links
the same static framebuffer backend onto the list again, setting its `next` to itself. Since its receive
callback always reports no input, `uart_getc()` never reaches the end of the list. `serial=3` enables the
keyboard reader, which gets stuck walking it instead of reaching its 16 ms sleep.

Patch 2034 makes a successfully mapped framebuffer backend skip subsequent probes, preserving retries
when mapping fails. `scripts/check-fbcon.py PATH/TO/PATCHED/XNU` compiles the actual probe, registration
and input functions: the original fails the repeated-probe check; the fix passes missing-device,
mapping-retry, repeated-probe and empty-input checks. The board now uses `serial=1` (output only), since
it has no serial keyboard. `out/heat-2.img` isolates this argument change using the exact same kg63 kernel
and other arguments as heat-1; it does not include patch 2034. In the supervised comparison it produced
15 governor samples with no serial-reader entry, and the later middle-cluster load was 55–63% rather
than the previous constant 100%. Requested states included 307/1171/595 MHz. Startup and other background
work still produce load and frequency bursts; neither a temperature reduction nor long-term idle power
has been measured. Both captures ended with a clean return to fastboot.

`delay()` uses a scheduler wait when interrupts/preemption permit it and the interval exceeds the CPU
idle latency; `ml_processor_info_t` is zero-initialized here, including that latency. The governor's 20 ms
and touch loop's 4 ms delays therefore do not inherently busy-wait. `recount_processor_usage` also includes
the current, ongoing idle interval. Neither justified a speculative replacement.

The GPU remains powered with a fixed performance vote and IFPC disabled. This can contribute to idle
power, but its contribution has not been measured. Do not invent GPU runtime knobs: only `gpu.maint`
is registered by the current display/GPU code. Thermal sensor feedback and automatic thermal protection
have not been validated for this port.

## Current image and remaining checks

`out/heat-3.img` contains both fixes (CI run 40699694833, kernel source commit 146c2da). The kernel build
and both regression checks passed with every board patch applied. Android header, embedded 64 MiB
payload, kernel checksum and boot arguments were checked. It uses `serial=1` and the existing
`ishtar-gpu-perf=1` (220 MHz) argument with its corresponding lower bandwidth vote. Other arguments
match gov-7. The GPU change is a temporary mitigation, not GPU runtime power management. Manifest
and hashes: `out/heat-3-manifest.json` (local only).

The exact final image also passed a supervised boot: 15 governor samples, no serial-reader entry,
requested states including 307/1286/595 MHz during the live session, followed by a clean return to
fastboot (serial 8afad138 confirmed). A lower 307/499/595 sample during shutdown is excluded from the
live-session comparison. No sustained temperature or battery-current result is implied.

Longer idle temperature behavior, battery current, remaining background load and GPU power management
still need measurement. Return to fastboot if heat rises; keep further tests supervised until this is
understood. All tests used RAM boot and normal iOS root operation; no partitions were flashed.

The user's subsequent heat-3 boot supplied an additional approximately two-minute capture (25 governor
samples). The serial spinner remained absent; a later 12-sample subset had median busiest-core loads
35.5/63.5/0%, with requested frequencies varying rather than staying at their caps. PID 1 appeared often
in running-thread snapshots. This is residual background work to profile, not a measured per-process
CPU percentage. The UI also continued submitting frames, often around 10/s, so this was not a zero-work
display baseline. Saved locally as `out/heat-3-idle-live.log` and `out/heat-3-idle-summary.json`.

`IshtarBattery::publish()` currently reports `Temperature=2500` and marks it estimated. That placeholder
cannot validate physical cooling. No subjective temperature result or battery-current measurement was
available during this follow-up. A later Settings scroll trace is documented in `REFRESH-RATE.md`.

## Sustained-idle report: audio service lookup flood

The user subsequently left heat-3 idle for about 40 minutes and reported it was still hot, though less
hot than before. The kernel log showed zero new swaps over long periods, with the serial spinner absent,
but persistent middle-cluster load around 54–75% and frequent PID 1 running-thread samples.

The missing evidence was in `/private/var/log/com.apple.xpc.launchd/launchd.log`, read from the running
phone. `audiomxd` continuously requested unavailable `com.apple.BTAudioHALPlugin.xpc` and
`com.apple.bluetooth.xpc` services. The log compresses repeated lines: the latest approximately one-second
intervals contained roughly 2,000 repetitions each (median approximately 2,141 repetitions/s across 60
selected intervals). These counts describe failed lookups, not per-process CPU percentages.

The job is `user/501/com.apple.audiomxd`. PID 738 was killed with
`JETSAM_REASON_MEMORY_PERPROCESSLIMIT` after about 369 seconds; replacement PID 782 resumed the lookup
flood. This accounts for substantial ongoing launchd work despite a static display. FileProvider also
has a slower restart loop; do not assume all background work has been eliminated.

With the user's explicit approval, added only `com.apple.audiomxd=true` to the existing
`/private/var/db/com.apple.xpc.launchd/disabled.plist`, preserving all 14 existing entries. Backup and
readback are local `out/heat-3-disabled-before-audio-change.plist` and
`out/heat-3-disabled-after-audio-change.plist`; the phone readback matched the proposed 482-byte file.
Rebooted the exact same heat-3 image, with no kernel/clock/display changes.

The new launchd logs contain no audiomxd activity. One remaining Bluetooth-audio lookup from another
client is not the former continuous flood. Settled samples reached requested clocks 307/499/595 MHz
and busiest-core loads 0/3–4/0%, with occasional background bursts. This is evidence that the audio
retry loop caused a major part of the residual CPU load. It does not establish physical temperature
or total idle power after the change.

A later comparison used the last 60 pre-change governor samples and 12 post-change samples: median
busiest-core load was 34/62.5/0% before and 0/9/0% after; median requested clocks after were
307/499/595 MHz. PID 1 occurred 57 times in the 60 earlier running snapshots and zero times in the
12 later snapshots. These are different-length windows across a reboot, not a calibrated power test.
The user then explicitly reported that the case was **cooling down** on the audio-disabled boot.
Extended idle-temperature stability remains unverified. The phone is left running iOS on this boot.

Disabling the audio mixer is a temporary mitigation for the unported audio/Bluetooth stack and can
affect media/audio-session behavior. Re-enable it when those services work, or before diagnosing
audio-related app failures. Raw pre/post logs and summaries stay under `out/`, outside git.
