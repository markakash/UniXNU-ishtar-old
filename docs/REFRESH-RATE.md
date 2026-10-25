# Refresh-rate investigation — 2026-10-28

The panel and framebuffer notifications run at approximately 120.6 Hz. After the `gov-7` reboot with
`CADisableMinimumFrameDurationOnPhone = true` in SpringBoard and Preferences, the combined scrolling/home-screen
test exceeded 60 swaps/s. Sustained 120 fps remains unverified.

The later runtime tests below confirm **120 display-link callbacks/s inside Settings**, including a default
display link on the cooler GPU profile. Scrolling still submits substantially fewer frames to the framebuffer.
Keep app callback delivery, UIKit's own scrolling requests, GPU work and actual scanout distinct.

Heating work subsequently fixed CPU downshifting and duplicate serial-console registration, and disabled an
`audiomxd` Bluetooth-service lookup flood with the user's approval. Idle CPU load fell and the user reported
cooling. See [HEATING.md](HEATING.md) for the evidence and remaining power limitations. Refresh work has resumed.

## Measurements

Source: the existing USB kernel-log capture, framebuffer `stats+0` and `stats+320` lines. Local capture and Apple
binaries stay outside git. `up_s` is the driver's time field, not a reliable wall-clock boot time. Totals reset
between kernel boots; compare samples within one boot only.

| Observation | Before the reboot (previous recorded boot) | After the reboot and plist edits |
|---|---|---|
| Highest logged one-second swap rate | 57.68/s | 73.72/s |
| Highest rate from consecutive five-second sample totals | 287 / 5 = 57.4/s | 361 / 5 = 72.2/s |
| Second active five-second window | — | 339 / 5 = 67.8/s |
| Vsync notifications during the new test | — | approximately 120.5–120.6/s |

New-boot totals: `up_s=777 swaps=578`, `up_s=782 swaps=917`, `up_s=787 swaps=1278`.
The totals corroborate the one-second peaks; this is not just one callback burst. The tests were manual, with
different content and load, and do not isolate the two plist edits from other changes in `gov-7`.

`hz=59` in the same stats line is calculated from the initial `fVsyncUS=16667`. The DPU path subsequently schedules
from the measured panel period without updating that field. Use measured `vsync_s` for notification frequency,
`swaps_s` for submissions, and frame/latch traces for presentation. None alone proves distinct images reached the
panel at that rate.

## The per-process gate

[Apple documents](https://developer.apple.com/documentation/quartzcore/optimizing-iphone-and-ipad-apps-to-support-promotion-displays)
the Info.plist opt-in for frame rates above 60 on iPhone. The locally extracted iOS 18.7.8 (22H352) QuartzCore
also contains the actual reader and clamp, at these **unslid, build-specific** addresses:

| Function | Address | Relevant behavior |
|---|---|---|
| `CADeviceDisableMinimumFrameDurationOnPhone` initialization block | `0x1848764fc` | Reads `CADisableMinimumFrameDurationOnPhone` from the main bundle's Info.plist and caches the Boolean |
| `CA::Display::DisplayLinkItem::set_preferred_fps_range_locked` | `0x1847976cc` | Phone restriction reads that cached Boolean at `0x18479779c`; without opt-in, clamps the requested interval range |
| `CA::DynamicFrameRateSource::set_preferred_fps_range` | `0x184717fb0` | Also checks the cached Boolean (`0x1847180d8`) |
| `-[CAAnimation _setCARenderAnimation:layer:]` | `0x1847c9324` | Propagates the phone opt-in into animation flags (`0x1847c9520`) |

The Boolean is initialized once per process. Editing the plist requires restarting the processes; in this
experiment the user rebooted the phone. Originals and undo commands are in
[MODIFIED-SYSTEM-FILES.md](MODIFIED-SYSTEM-FILES.md). The key permits higher rates; it does not request or force 120.

## Other findings, not established fixes

- `SupportsPerseus` (`GdXjx1ixZYvN9Gg8iSf68A`) is queried by QuartzCore at `0x1847f7f30`. It gates adaptive display
  timing behavior. The Settings runtime probe below reads its live answer as **false**, while Settings still reports
  a 120 fps maximum. This does not establish whether the false capability affects scrolling's requested rate.
  The saved MobileGestalt backup has a binary
  `CacheData` blob, so absence from `CacheExtra` says nothing about that Boolean. Do not overwrite the cache on
  that assumption. Changing ADT identity alone does not establish the live capability answer.
- `IOMobileFramebuffer::_kern_GetSupportedDigitalOutModes` (`0x1ba87f418`) requires both `ColorElements` and
  `TimingElements` arrays. The current driver publishes only the latter. However, QuartzCore's internal-display
  path deliberately falls back for a single color/timing pair (`0x18489d56c`–`0x18489d614`). Adding `ColorElements`
  alone is therefore not a demonstrated 120 fps fix; the runtime probe below confirms the existing fallback
  already reports a 120 fps maximum to Settings. A complete future multi-mode implementation also needs
  matching current-mode IDs and actual mode-setting behavior. No speculative mode patch was applied.
- The current vsync notification sends a zero third 64-bit value. iOS 18's callback consumes it as an offset to
  the supplied timestamp. Its correct hardware meaning and any pacing effect need a trace before changing it.

## Next measurement

Use the existing frame trace, without another kernel build:

```sh
python3 scripts/push.py --set fb.trace 128
```

Scroll while the next stats window is recorded. `fb.trace` clears itself after one dump. The log then contains
`id swap_us scan_us latch_us done_us wcall_us wret_us`. Compare intervals between swap arrivals with the
swap-to-scan and scan-to-latch delays to distinguish client pacing from display-path stalls. Times are relative
to the oldest swap; zero means not observed, except that the oldest swap itself also starts at zero.

## Live trace after the heating fixes

Direct device access is now available. The user booted `heat-3` (both CPU fixes, GPU perf1 = 220 MHz) and
scrolled Settings while the existing `fb.trace` knob recorded four active windows of 128 frames each.
Local files: `out/heat-3-scroll-live.log` and `out/heat-3-scroll-summary.json` (not committed).

| Measurement | Four scrolling windows |
|---|---|
| Swap arrival rate across each 128-frame window | 39.19–41.05/s |
| Median gap between swap arrivals | 24.63–24.91 ms |
| Median swap to scan programming | 7.71–7.82 ms |
| Median scan to observed latch | 4.94–5.28 ms |
| Median successful SwapWait call duration | 11.59–11.95 ms |

The framebuffer's independent GPU-wait counters report approximately 7.4–7.9 ms per frame in these
windows, matching the swap-to-scan delay. `present()` waits for GPU completion before programming the
DPU. `swapWaitInner()` then waits for that swap's latch; its fast path can observe the latch before the
vsync callback records the trace's done/latch timestamps, so these timestamps need not match exactly.

This identifies substantial GPU and presentation backpressure on this deliberately slow GPU profile.
It does not measure maximum rendering speed at perf8, prove that all delays add without overlap, or
establish the final CoreAnimation policy above 60. The trace records arrivals and driver events, not the
application's requested display-link rate. A single sub-10-ms arrival gap is not evidence of sustained 120.

Previous experiments already showed black bands when SwapWait returned before surfaces were safe to
reuse; surface in-use flags alone did not prevent it. Do not remove the latch wait as a performance fix
without preserving buffer ownership. The next useful work is to determine how to overlap rendering and
presentation safely, while keeping higher GPU clocks conditional on actual work. No timing-mode or
MobileGestalt patch was applied during this capture; `fb.trace` clears itself after each dump.

## Controlled faster-GPU comparison

RAM-booted `hz-perf8-audio-off.img` for a 90-second capture, then automatically restored `heat-3.img` and verified
network access and the normal knobs. Both images contain the exact same `kg64` kernel; the sole boot-argument
change is `ishtar-gpu-perf=1` (220 MHz) to `8` (680 MHz). The audio-service override remains applied in both.
The user confirmed scrolling during this capture. Local manifests, raw log, summary and restoration state are
`out/hz-perf8-audio-off-*` and `out/hz-perf8-session.json`.

The clearest three active 128-frame windows (IDs 994–1121, 1313–1440, 1634–1761) measured:

| Measurement | GPU 680 MHz |
|---|---|
| Swap arrivals | 61.81–64.52/s |
| Median swap gap | 16.03–16.31 ms |
| Median swap to scan programming | 1.61–1.67 ms |
| Median scan to observed latch | 7.02–7.44 ms |
| Median successful SwapWait duration | 7.62–7.74 ms |
| Median previous wait return to next swap | 7.92–8.10 ms |

Other windows include pauses and transitions and are slower. These are short manual captures, not a repeatable
rendering benchmark. Higher GPU clocks substantially reduced GPU waiting but did not produce sustained 120
submissions/s. The remaining gap can involve client scheduling and the serialized render/present/latch path;
the trace still does not reveal the app's requested frame rate or runtime policy limits. `dpu.layerlog` only
logs multiple-layer swaps, so its lack of output here does not establish surface rotation.

## Settings runtime policy probe — captured and original files restored

`scripts/refresh-probe.m` is a temporary dylib for Settings. Seven seconds after launch it reads the actual
process's Info.plist opt-in, `UIScreen.maximumFramesPerSecond`, CoreAnimation refresh rate, hardware rate,
minimum duration, current/available modes, and MobileGestalt `SupportsPerseus`. It only calls getters, writes
`/private/var/tmp/ishtar-refresh-probe.log` and emits progress/results to the existing USB UDP log. It does not
override the display or request a frame rate.

Prepared local files and hashes are in `out/refresh-probe-proposal.json`. The downloaded original Settings
executable is `out/refresh-probe-Preferences.original`. The candidate adds one **weak** dylib dependency;
all 40 original file-backed sections are identical and all 659 entitlements are preserved. Missing the probe
library therefore does not by itself make the dependency mandatory. Both candidates pass signature verification
and PAC scans. The user approved installation and restoration, and the probe ran successfully in the actual
Settings process (`com.apple.Preferences`, PID 444) on `heat-3`. Host checks cover KVC integer/double boxing, object/class getters,
missing keys and missing displays:

```sh
xcrun --sdk macosx clang -fobjc-arc -Wall -Wextra -Werror -DISHTAR_REFRESH_PROBE_CHECK \
  -framework Foundation scripts/refresh-probe.m -o out/refresh-probe-check
out/refresh-probe-check
```

The first attempt produced no output because the library was no longer present in `/private/var/tmp` after
reboot. The patched executable remained intact and its weak dependency let Settings open. Re-uploaded the
library during the running boot; the user fully closed and reopened Settings. The second version's UDP
startup/callback markers and file output both succeeded. For reuse, upload the library **after boot**, then
restart Settings; do not depend on temporary storage surviving reboot.

| Value read inside Settings | Result |
|---|---|
| Bundle `CADisableMinimumFrameDurationOnPhone` | true |
| `UIScreen.maximumFramesPerSecond` | **120** |
| `CADisplay.refreshRate` | 0.008333333333333333 seconds (120 Hz interval) |
| `CADisplay.hardwareRefreshRate` | same 120 Hz interval |
| `CADisplay.minimumFrameDuration` | 1 display frame |
| `CADisplay.supportsVariableFrameDuration` | false |
| Current and available modes | one fixed internal mode, 828 × 1792 |
| `CADisplay.highestLocalPreferredFrameRateRequest` | 0 at this sample |
| MobileGestalt `SupportsPerseus` | false |

This rules out a blanket **reported** 60 fps capability limit in Settings with its opt-in enabled. It does not
measure the scrolling code's requested rate or an active display link's delivered rate. The preferred-request
sample was not synchronized with scrolling; zero is not proof that the app never requests 120. Other apps'
opt-ins are unchanged. The fixed-rate/false-Perseus result also does not justify blindly overriding MobileGestalt.
Next distinguish actual app frame requests from the render/present/latch backpressure measured above.

Raw result: `out/refresh-probe-live.log`; UDP capture: `out/refresh-probe-v2-live.log`; approval, hashes, cleanup
and results: `out/refresh-probe-proposal.json` (all local only). Restored the original Settings executable and
verified its read-back SHA256 against the pre-install backup, **then** removed the temporary library and phone
log. The original existing Info.plist opt-ins and approved audio-service override remain. A final clean reboot
uses the exact cooler `heat-3.img` to unload the probe.

## Active callback test and scrolling comparison — complete

The user separately approved the active test in `scripts/refresh-link-probe.m`. It includes the getter probe,
then creates a default `CADisplayLink` for three seconds followed by a link requesting a 120/120/120 range for
three seconds, without drawing. Both links are invalidated; an additional cleanup timer bounds a stalled test.
Rates below use actual callback arrivals (`CACurrentMediaTime`), not just advertised timestamps or duration.
Host checks cover interval counting and missing intervals; the iOS library passed signing and PAC checks.

Installed the library after boot and verified both file hashes. The user relaunched Settings for the idle test,
then relaunched again and scrolled continuously for the comparison. Both tests used `heat-3`, **GPU220**.

| Workload | Link request | Actual callbacks/s | Longest callback gap |
|---|---|---|---|
| Settings idle | Default (0/0/0) | **120.006** | 8.469 ms |
| Settings idle | 120/120/120 | **120.000** | 8.522 ms |
| Settings scrolling | Default (0/0/0) | **117.305** | 36.890 ms |
| Settings scrolling | 120/120/120 | **98.612** | 49.740 ms |

The two scrolling phases are successive manual workload windows, not evidence that the explicit request makes
performance worse. All four report a nominal display-link duration of 1/120 second. Four simultaneous 128-frame
framebuffer trace windows measured **37.08, 39.07, 39.68 and 42.30 submissions/s**. Their median swap-to-scan
delays were 6.38–8.22 ms; successful SwapWait medians were 7.76–12.58 ms.

This establishes that the opted-in app can receive 120 Hz callbacks even with `SupportsPerseus=false`. The
added diagnostic links participate in frame-rate arbitration; they do not directly trace UIKit's own scrolling
link or prove every callback produces a distinct rendered/presented image. UIKit's scrolling request and the
compositor's render/present waits remain the next distinctions to measure. No new global frame-rate, mode,
MobileGestalt or SwapWait override was made.

Local results: `out/refresh-link-summary.json` (idle), `out/refresh-link-all-summary.json` (both runs),
`out/refresh-link-scroll-frame-summary.json`, corresponding raw logs, and `out/refresh-link-probe-proposal.json`.
Restored the exact original executable, verified its hash, removed the library and phone log, and cleanly
rebooted the exact cooler image. Network readiness after restoration is recorded in the proposal. Both probes
are **removed and unloaded**; existing opt-in plists and audio-service override remain.

During scrolling, the DEVELOPMENT kernel also prints managed-page mapping backtraces. NativeAdreno's user-view
code intentionally builds raw physical descriptors to obtain uncached CPU views. These messages have not been
profiled as a frame-time bottleneck. Preserve memory ownership and cache coherency when investigating them;
silencing the diagnostic is not an established refresh fix.
