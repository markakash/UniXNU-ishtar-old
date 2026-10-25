# UniXNU-ishtar

iOS on the **Xiaomi 13 Ultra** (`ishtar`, Qualcomm SM8550-AB / Snapdragon 8 Gen 2).

Experimental bring-up, not a usable phone OS. Target: the iPhone XR (`iPhone11,8`) iOS 18.7.8 userland on an
XNU 11215 kernel, booted by Mu-Silicium UEFI and UniXNU/DarwinBoot. Status and hardware facts: [PORTING.md](PORTING.md).

## Boot chain

```
Xiaomi ABL (unlocked) -> fastboot boot (nothing flashed)
  -> uefi-ishtar (Mu-Silicium, SM8550) -> UniXNU menu -> DarwinBoot
     -> XNU (machine config ISHTAR) + Apple device tree from tools/base/mkadt.py --board ishtar
```

## Status

| Stage | State |
| --- | --- |
| UEFI | UniXNU menu on hardware (2026-10-25) |
| Kernel | patch series applies (219/219 dry run on xnu-11215.81.4); first CI build pending |
| Root, userland | not started |

## Layout

| Path | Contents |
| --- | --- |
| `board.toml` | board values, boot arguments, payload settings |
| `PORTING.md` | hardware inventory, patch plan, device log |
| `xnu/patches-ishtar/` | ishtar board patches (2000+), applied after the base port |
| `tools/mkadt-ishtar.patch` | the ishtar board for the ADT generator |
| `scripts/sync-base.py` | fetches the base XNU port at a pinned commit into `xnu/base/`, `tools/base/`, renamed to ishtar |
| `scripts/build-uefi.py` | builds `../uefi-ishtar` on macOS and packs the `fastboot boot` image |
| `uefi/darwinboot-32mb-block.patch` | DarwinBoot places 16 KiB-page kernels on 32 MiB boundaries (applied at firmware build) |
| `scripts/extract-stock.sh` | DTBs and UEFI drivers from a HyperOS fastboot ROM |
| `scripts/probe-device.sh` | hardware facts from the phone over adb |
| `.github/workflows/xnu.yml` | kernel build on GitHub's macOS 15 runner (blacktop/darwin-xnu-build, MIT) |

## Build

```sh
python3 scripts/sync-base.py                      # fetch the base port (renamed to ishtar)
gh workflow run xnu.yml                           # kernel on GitHub Actions
python3 scripts/build-uefi.py DEBUG               # needs ../uefi-ishtar and ../UniXNU
fastboot boot out/uefi-ishtar-debug.img           # temporary: a reboot returns to Android
```

Apple software (IPSW, kernelcache, device trees), Qualcomm firmware and device dumps are never committed.

## Credits

- [UniXNU](https://github.com/UniXNU/UniXNU) and [DarwinBoot](https://github.com/UniXNU/DarwinBoot): boot menu and XNU loader.
- [ry-diffusion/Bergamota](https://github.com/ry-diffusion/Bergamota): the XNU port and iOS userland tooling this
  builds on. It has no license, so it is fetched at build time and not redistributed here.
- [dipa-studio/ios-sweet](https://github.com/dipa-studio/ios-sweet) (MIT): the original XNU-on-Qualcomm port it comes from.
- [pawlickerr/UniXNU-negroni](https://github.com/pawlickerr/UniXNU-negroni) and its kernel tree: the SM8450 patches
  that `xnu/patches-ishtar` 2000-2002 are adapted from.
- [wh1stl3/uefi-nuwa](https://github.com/wh1stl3/uefi-nuwa) (BSD-2-Clause) and
  [Project-Silicium/Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium): the UEFI that `uefi-ishtar` is forked from.
- UFS clock offsets from Linux `drivers/clk/qcom/gcc-sm8550.c`.
