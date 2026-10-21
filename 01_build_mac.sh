#!/usr/bin/env bash
# Build WebRTC.framework for macOS arm64 (Apple Silicon).
# Run after 00_bootstrap.sh has finished successfully.
set -euo pipefail

PROJECT_DIR="/Users/chengaoyuan/opensource/WebRTC"
SRC_DIR="${PROJECT_DIR}/webrtc_src"
# export PATH="${PROJECT_DIR}/depot_tools:${PATH}"
export DEPOT_TOOLS_METRICS=0

OUT_DIR="${PROJECT_DIR}/build"

cd "${SRC_DIR}"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

mkdir -p "${OUT_DIR}"

log "Writing args.gn"
cat > "${OUT_DIR}/args.gn" <<'EOF'
target_os                 = "mac"
target_cpu                = "arm64"
is_debug                  = false
is_component_build        = false
rtc_include_tests         = false
rtc_build_examples        = false
rtc_use_h264              = false        # set to true if libavcodec is OK with license
use_custom_libcxx         = false        # use system libc++ — better Xcode interop
treat_warnings_as_errors  = false        # smoother local builds
enable_dsyms              = true
EOF

log "gn gen ${OUT_DIR}"
gn gen "${OUT_DIR}"

python3 tools/clang/scripts/generate_compdb.py \
  -p "${OUT_DIR}" \
  mac_framework_objc \
  -o "${OUT_DIR}/compile_commands.json"

log "ninja -C ${OUT_DIR} mac_framework_objc"
# mac_framework_objc is the macOS Objective-C framework target.
# If the target name has changed in your branch, try one of:
#   ninja -C ${OUT_DIR} framework_objc
#   ninja -C ${OUT_DIR} sdk:mac_framework_objc
ninja -C "${OUT_DIR}" mac_framework_objc

cat <<EOF

\033[1;32mDONE.\033[0m
  Framework: ${SRC_DIR}/${OUT_DIR}/WebRTC.framework

EOF
