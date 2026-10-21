# WebRTC local build — macOS + iOS (Apple Silicon)

Three scripts in this folder. Run them in order, in your Mac Terminal.

## Order

```bash
cd /Users/chengaoyuan/opensource/WebRTC

bash 00_bootstrap.sh    # ~1–2h, downloads ~20 GB
bash 01_build_mac.sh    # ~20–40 min, produces WebRTC.framework
bash 02_build_ios.sh    # ~40–90 min, produces WebRTC.xcframework
```

## What each script does

**`00_bootstrap.sh`**
1. Clones `depot_tools` into `./depot_tools/`.
2. Runs `fetch --nohooks webrtc` to clone source into `./src/`.
3. Adds `target_os = ['mac', 'ios']` to `.gclient` so iOS SDKs are synced.
4. Enables `branch-heads/*` refs and checks out the **latest numeric `branch-heads/<N>`** (Chromium milestone branches).
5. Runs `gclient sync --with_branch_heads -D` to pull DEPS, mac/ios SDKs, runtime hooks.

**`01_build_mac.sh`**
- `target_cpu = "arm64"`, release, no tests, no examples.
- Output: `src/out/mac-arm64-release/WebRTC.framework`.

**`02_build_ios.sh`**
- Uses upstream's `tools_webrtc/ios/build_ios_libs.py` to build a multi-arch xcframework.
- Output: `src/out/ios-release/WebRTC.xcframework`.

## When something fails

Compile failures on WebRTC are normal — the build is sensitive to Xcode versions, SDK versions, and the specific milestone you land on. **Paste the last 30–80 lines of the error back to me in chat.** I'll read the relevant files in `src/` directly (this folder is mounted on my side too), figure out the fix, and either:

- Edit a `BUILD.gn`, `args.gn`, or source file in place, or
- Hand you a small patch to apply.

Then re-run the same `0X_build_*.sh`.

## Common things I'll need to know when debugging

- `xcodebuild -version` output
- The branch number `00_bootstrap.sh` checked out (printed at the end of its run)
- Whether the error is from `gn gen` (config) or `ninja` (compile/link)

## Useful one-liners

```bash
# Re-source PATH if a new shell can't find gn/ninja
export PATH="/Users/chengaoyuan/opensource/WebRTC/depot_tools:$PATH"

# Resync after I change DEPS or args
cd /Users/chengaoyuan/opensource/WebRTC && gclient sync --with_branch_heads -D

# Clean a single out dir
rm -rf src/out/mac-arm64-release

# Show which branch-heads ref is checked out
cd src && git rev-parse --abbrev-ref HEAD
```
