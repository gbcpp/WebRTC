#!/usr/bin/env bash
# WebRTC bootstrap: installs depot_tools, fetches source, configures for mac+ios,
# checks out the latest stable branch-heads, and runs gclient sync.
#
# Run once. Takes ~1-2h and uses 20+ GB.
set -euo pipefail

PROJECT_DIR="/Users/chengaoyuan/opensource/WebRTC"
DEPOT_TOOLS_DIR="/Users/chengaoyuan/tools/depot_tools"
SRC_DIR="${PROJECT_DIR}/src"

cd "${PROJECT_DIR}"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

# # --- 1. depot_tools ----------------------------------------------------------
# log "depot_tools"
# if [ ! -d "${DEPOT_TOOLS_DIR}/.git" ]; then
#   git clone --depth=1 https://chromium.googlesource.com/chromium/tools/depot_tools.git "${DEPOT_TOOLS_DIR}"
# else
#   (cd "${DEPOT_TOOLS_DIR}" && git pull --rebase --quiet || true)
# fi
# export PATH="${DEPOT_TOOLS_DIR}:${PATH}"

# Avoid Google's metrics prompt blocking the script.
export DEPOT_TOOLS_METRICS=0

# --- 2. fetch the WebRTC source ---------------------------------------------
if [ ! -d "${SRC_DIR}/.git" ]; then
  log "fetch --nohooks webrtc  (this is the big download)"
  fetch --nohooks webrtc
else
  log "WebRTC source already present, skipping fetch"
fi

# --- 3. add mac + ios to target_os in .gclient ------------------------------
log "Configuring .gclient for mac + ios"
if ! grep -q "target_os" "${PROJECT_DIR}/.gclient" 2>/dev/null; then
  printf "\ntarget_os = ['mac', 'ios']\n" >> "${PROJECT_DIR}/.gclient"
fi

# --- 4. enable branch-heads refs and find latest stable ---------------------
log "Enabling branch-heads refs"
cd "${SRC_DIR}"
# Make sure both heads and branch-heads are fetched.
git config --replace-all remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
git config --add        remote.origin.fetch '+refs/branch-heads/*:refs/remotes/branch-heads/*'
git fetch origin --tags --prune

LATEST=$(git for-each-ref --format='%(refname:short)' 'refs/remotes/branch-heads/*' \
  | awk -F/ '{print $NF}' | grep -E '^[0-9]+$' | sort -n | tail -1)

if [ -z "${LATEST}" ]; then
  echo "ERROR: could not detect a branch-heads/* ref. Check git output above."
  exit 1
fi
log "Latest stable branch: branch-heads/${LATEST}"
git checkout -B "stable-${LATEST}" "branch-heads/${LATEST}"

# --- 5. sync all DEPS, including mac+ios SDKs and branch-heads --------------
cd "${PROJECT_DIR}"
log "gclient sync --with_branch_heads -D  (downloads SDKs, runtimes, etc.)"
gclient sync --with_branch_heads -D

cat <<EOF

\033[1;32mDONE.\033[0m
  Source dir   : ${SRC_DIR}
  Stable branch: branch-heads/${LATEST}
  depot_tools  : ${DEPOT_TOOLS_DIR}

Next:
  bash ${PROJECT_DIR}/01_build_mac.sh
  bash ${PROJECT_DIR}/02_build_ios.sh

Tip: add depot_tools to PATH for future shells:
  echo 'export PATH="${DEPOT_TOOLS_DIR}:\$PATH"' >> ~/.zshrc
EOF
