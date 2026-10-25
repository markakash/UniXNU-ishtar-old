# Services disabled on the phone (temporary)

iOS services that crash-loop because their hardware or trust chain is not brought up yet are switched off through launchd's
own override list, `/private/var/db/com.apple.xpc.launchd/disabled.plist` (a label set to `true` is not started). This is
the phone's data, not a kernel or image change: nothing in a build turns them back on.

**Re-enable a service when its driver works** (set its label to `false` or delete the key, push, reboot).

| Label | Disabled on | Why | Re-enable when |
|---|---|---|---|
| `com.apple.bluetoothd` | 2026-10-28 | restarted ~9 times per boot, no Bluetooth driver | Bluetooth (WCN7851) is up |
| `com.apple.wifip2pd` | 2026-10-28 | restarted ~7 times per boot, no Wi-Fi driver | Wi-Fi is up |
| `com.apple.linkd` | 2026-10-28 | restarted ~7 times per boot | Wi-Fi/networking is up |
| `com.apple.mobile.softwareupdated` | 2026-10-28 | 25 crash reports; updates cannot work on this setup | never needed here |
| `com.apple.spaceattributiond` | 2026-10-28 | restarted ~9 times per boot | storage accounting works (HFS+ root: see the iPhone Storage page bug) |
| `com.apple.gamepolicyd` | 2026-10-28 | memory high watermark -> killed, respawn loop (also on the SDM845 reference port: 27 launches in 5 min) | memory limits are sorted out, or games need it |
| `com.apple.fairplayd.H2` | 2026-10-28 | restarted ~9-20 times per boot | App Store apps fail to launch (FairPlay DRM): re-enable first if they do |
| `com.apple.asd` | 2026-10-28 | crash reports in a loop | never needed here |
| `com.apple.SepUpdateTimer` | 2026-10-28 | Secure Enclave updater (seputil), no SEP here | never needed here |
| `com.apple.audiomxd` | 2026-10-28 | user-approved heating test: about 2,100 failed Bluetooth-audio service lookups/s, plus memory-limit kills and restarts; audio hardware is not ported | audio/Bluetooth services work; re-enable before diagnosing audio-related app failures |

The five entries that were already there are iOS defaults and stay as they are: `com.apple.bootpd`, `com.apple.dhcp6d`,
`com.apple.magicswitchd.companion` and `com.apple.security.otpaird` (all `true`), `com.apple.ftp-proxy-embedded` (`false`).

Still crash-looping (plug-ins started on demand by audio clients, not launchd jobs): the speech
synthesizers `MauiAUSP`, `SiriAUSP`, `KonaSynthesizer`, `MacinTalkAUSP` (abort: no audio hardware), and `cryptexd`
(image4 checks without SEP), kept on because other services wait for it.

The audio-mixer override is temporary and may affect media/audio session behavior. The original override file was saved
locally before the one-key addition and the phone readback was verified. The first post-reboot launchd log contains no
`audiomxd` activity or its Bluetooth lookup flood. Settled samples reached 307/499/595 MHz and cluster
busiest-core loads 0/3–4/0% after the same image rebooted. Physical temperature and total idle power remain
unmeasured; see `HEATING.md` for the comparison and limitations.

## Commands

```sh
# what the phone has now
python3 scripts/push.py --get /private/var/db/com.apple.xpc.launchd/disabled.plist /tmp/disabled.plist && plutil -p /tmp/disabled.plist

# re-enable one service (example: bluetoothd), then reboot the phone
python3 - <<'EOF'
import plistlib
p = '/tmp/disabled.plist'
d = plistlib.load(open(p, 'rb'))
d.pop('com.apple.bluetoothd', None)
plistlib.dump(d, open(p, 'wb'), fmt=plistlib.FMT_BINARY)
EOF
python3 scripts/push.py /tmp/disabled.plist /private/var/db/com.apple.xpc.launchd/disabled.plist
```
