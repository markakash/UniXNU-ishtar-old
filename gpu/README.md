# GPU userspace on the phone (pushed with scripts/push.py, image boot-args `ishtarpush=1 ishtarmetal=1`)

- `/System/Library/Extensions/NativeAdrenoMetal.bundle`: UniXNU `build/adreno-metal-plugin` (AdrenoMetal + `adrenometal-0001-ios18.patch`)
- `/System/Library/Extensions/NativeAdrenoMetal.publish` (empty): backboardd composites through the GPU
- `/System/Library/Extensions/NativeAdrenoMetal.clients` (this directory): other processes that get a native Metal device
  (icons, widgets, wallpaper posters). `push.py --rm` removes a file; boot without `ishtarmetal=1` to skip the plugin.

Plugin source: UniXNU/AdrenoMetal at ce5e19e (2026-10-28) with adrenometal-0001-ios18.patch on top; the previous build
(ed654b4) is kept outside the repo for rollback. WidgetRenderer_Default is off the client list: since the bridge's
draw-path patches (01ea556) one of its compute pipelines fails (function constant 124 not given), its pass is refused and
the widgets came out black. It renders as before GPU compositing until that is fixed.
