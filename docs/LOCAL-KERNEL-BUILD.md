# Local kernel build (handoff)

Goal: build the ishtar XNU kernel on a fast local Mac instead of GitHub Actions, incrementally (only changed files are
recompiled), and hand the resulting `kernel.development.ishtar` back. The phone, the image tools and the test loop stay on
the other Mac; this machine only builds kernels.

## Rules (from the repo owner)

- No Claude/AI authorship in commits or PRs.
- No other device or project names in anything committed: everything is "ishtar" (the owner has the list).
- Never commit Apple binaries, Qualcomm blobs, device dumps or unlicensed upstream code. Build outputs stay out of git.
- `markakash/UniXNU-ishtar` may be amended and force-pushed; keep it to one commit on `main` as it is now.
- Do not touch any phone; this machine has none attached.

## What a kernel build is

`.github/workflows/xnu.yml` is the reference. In short:

1. `python3 scripts/sync-base.py` writes `xnu/base/` (the base port patches, renamed to ishtar).
2. blacktop/darwin-xnu-build (MIT) at the pinned `DXB_SHA` in the workflow is cloned to `dxb/`. Its `build.sh` clones
   xnu for `MACOS_VERSION=15.3` (xnu-11215.81.4), applies `dxb/patches/15.0/*`, builds the tools it needs into
   `dxb/fakeroot`, then runs xnu's `make install` with `MACHINE_CONFIG=ISHTAR KERNEL_CONFIG=DEVELOPMENT`.
3. Our patches are copied in as `dxb/patches/15.0/ishtar-*`: `xnu/base/*.patch`, `xnu/base/*.sh`,
   `xnu/patches-ishtar/*.patch` (2000+, in name order).
4. `dxb/build.sh` gets one sed fix (libfirehose_kernel must also build arm64: see the workflow).
5. Output: `dxb/fakeroot/System/Library/Kernels/kernel.development.ishtar` (Mach-O arm64).
6. Checks: `grep 'Skipping patch' dxb/build.log | grep ishtar-` must print nothing (dxb's own `link_kdk146` and
   `remove_tightbeam` are always skipped, that is normal); `file` on the kernel says Mach-O 64-bit arm64.

Toolchain on CI: macOS 15 runner, **Xcode 16.2** (`xcode-select -s /Applications/Xcode_16.2.app`), Homebrew `jq gum
bash cmake ninja`, and a dummy `xcodes` in PATH (build.sh only checks it exists). xnu-11215 is not known to build with
newer Xcode releases: install Xcode 16.2 next to the current one and select it for the build.

## Incremental builds (the point of doing this locally)

The workflow already supports it, see "Restore build cache" and `scripts/ci-mtimes.py`: xnu is cloned and patched anew
each time (so every patch is verified), then `ci-mtimes.py restore` gives every file whose content did not change its
previous mtime back, so make only rebuilds what our patches changed. Locally:

- keep `dxb/build` and `dxb/fakeroot` between builds (they are the cache);
- before each build: delete `dxb/build/xnu.obj/kernel.*` (build.sh skips xnu when it exists) and
  `dxb/fakeroot/System/Library/Kernels` (so a failed build can never hand over an old kernel);
- remove `dxb/xnu` so build.sh clones and patches it again (or keep a pristine clone and copy it, to save the
  network clone);
- after a successful build: `python3 scripts/ci-mtimes.py save dxb/xnu dxb/build/xnu-src.mtimes`.
- use the machine's cores: build.sh passes `-j8` and `KERNEL_BUILDS_IN_PARALLEL`; raise them (e.g. `-j32`) in the
  local copy of build.sh only.

Write this as one script, `scripts/build-kernel-local.sh`, that does steps 1-6 plus the incremental handling, stops on
any skipped `ishtar-` patch, and prints the kernel path and its sha256 at the end. Commit the script (it is ours, MIT
like the repo); never commit `dxb/`.

## Handing the kernel back

The other Mac expects the file at `out/kgNN/ishtar-kernel/kernel.development.ishtar` (any new NN). Copy just that file
(about 18 MB) over whatever link the owner sets up (shared folder, scp, AirDrop). It is built from open-source xnu
plus our patches, but keep it out of git and public places anyway: it is a build output.

## Getting the latest patches

The other Mac amends and force-pushes `main` of `markakash/UniXNU-ishtar`. Before every build: `git fetch && git reset
--hard origin/main` (this repo only holds patches and scripts; nothing local to lose except the build script, which is
committed). The kernel sources under `refs/` on the other Mac are not needed: everything comes from the patches.

## First steps

1. Clone `https://github.com/markakash/UniXNU-ishtar` (the owner gives access).
2. Install Xcode 16.2 and the Homebrew tools above; check `xcodebuild -version`.
3. Write `scripts/build-kernel-local.sh`, run a full build (expect roughly 10-20 min the first time), check it as in
   step 6.
4. Touch one of our patches (any comment in `xnu/patches-ishtar/2025-*.patch`), rebuild, and check that only a few
   files were compiled and the build took a few minutes at most.
5. Report the timings and the kernel's sha256 to the owner, then hand the kernel over.
