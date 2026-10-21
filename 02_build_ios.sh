#!/usr/bin/env bash
# Build WebRTC.xcframework for iOS (device arm64 + simulator arm64/x64).
# Run after 00_bootstrap.sh has finished successfully.
set -euo pipefail

PROJECT_DIR="/Users/chengaoyuan/opensource/WebRTC"
SRC_DIR="${PROJECT_DIR}/src"
export PATH="${PROJECT_DIR}/depot_tools:${PATH}"
export DEPOT_TOOLS_METRICS=0

cd "${SRC_DIR}"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

OUT_DIR="out/ios-release"

# WebRTC ships a helper that builds multi-arch frameworks and packages them
# as a .xcframework. Flags vary slightly across milestones — if any is rejected,
# remove it and re-run; or paste the error and I'll patch.
log "Building iOS xcframework via tools_webrtc/ios/build_ios_libs.py"

python3 tools_webrtc/ios/build_ios_libs.py \
  --output-dir "${OUT_DIR}" \
  --arch arm64 arm64_simulator x64_simulator \
  --build-config release \
  --extra-gn-args 'rtc_include_tests=false rtc_build_examples=false rtc_use_h264=false treat_warnings_as_errors=false'

cat <<EOF

\033[1;32mDONE.\033[0m
  XCFramework: ${SRC_DIR}/${OUT_DIR}/WebRTC.xcframework

EOF
