# System files changed on the phone (temporary)

Files of the iOS root that were edited in place over the push link (`scripts/push.py`). The originals are kept on the Mac
in `tools/research/plist-orig/` (git-ignored: Apple files). Pushing an original back undoes the change (remove first,
then push, then reboot).

| File | Change | Date | Why | Undo when |
|---|---|---|---|---|
| `/System/Library/CoreServices/SpringBoard.app/Info.plist` | `CADisableMinimumFrameDurationOnPhone = true` | 2026-10-28 | test: does CoreAnimation render SpringBoard above 60 fps (panel at 120 Hz, IOMFBDisplayRefresh published) | the test shows no effect, or a better 120 Hz switch is found |
| `/Applications/Preferences.app/Info.plist` | `CADisableMinimumFrameDurationOnPhone = true` | 2026-10-28 | same test in Settings | same |

After rebooting `gov-7` on 2026-10-28, the scrolling/home-screen test exceeded 60 swaps/s: 73.72/s in a logged
one-second window, and 361 swaps between the `up_s=782` and `up_s=787` samples (about 72.2/s over five seconds).
Vsync stayed around 120.5–120.6/s. Keep the flags while testing; this is evidence against a remaining hard 60 fps
ceiling, **not** proof of sustained 120 fps or an isolated comparison of either plist. See [refresh investigation](REFRESH-RATE.md).

## Undo

```sh
python3 scripts/push.py --rm /System/Library/CoreServices/SpringBoard.app/Info.plist
python3 scripts/push.py tools/research/plist-orig/SpringBoard.Info.plist /System/Library/CoreServices/SpringBoard.app/Info.plist
python3 scripts/push.py --rm /Applications/Preferences.app/Info.plist
python3 scripts/push.py tools/research/plist-orig/Preferences.Info.plist /Applications/Preferences.app/Info.plist
```
