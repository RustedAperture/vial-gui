#!/usr/bin/env bash
# Build this Vial GUI fork for the browser (vial-kb/vial-web: Qt5 + CPython -> wasm) inside Docker.
# Idempotent: fetched/built deps are kept in dev/vendor/vial-web and skipped via .stamps/*.
# vial-web/vial-gui is a symlink to this repo. Output: dev/vendor/vial-web/src/build. Log: dev/build/web.log
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV="$ROOT/dev"
LOG="$DEV/build/web.log"
IMAGE=vial-web-builder
# The build reads git metadata; mount it too when this checkout is a submodule (git dir outside ROOT)
GITDIR="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)"
EXTRA_MOUNT=()
case "$GITDIR" in "$ROOT"/*) ;; *) EXTRA_MOUNT=(-v "$GITDIR:$GITDIR:ro") ;; esac
mkdir -p "$DEV/build" "$DEV/vendor"
: >"$LOG"
{
  docker build -t "$IMAGE" "$DEV/web" || exit $?
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e ROOT="$ROOT" \
    -v "$ROOT:$ROOT" "${EXTRA_MOUNT[@]}" -w "$ROOT" "$IMAGE" bash -c '
set -eu
step() { echo "=== STEP: $*"; }
V="$ROOT/dev/vendor/vial-web"
git config --global --add safe.directory "*"
[ -d "$V" ] || git clone https://github.com/vial-kb/vial-web "$V"
cd "$V"
[ -e vial-gui ] || ln -s ../../.. vial-gui
[ -d via-keymap-precompiled ] || git clone https://github.com/vial-kb/via-keymap-precompiled
mkdir -p .stamps
run() { n=$1; shift; if [ -e .stamps/$n ]; then echo "=== SKIP (done): $n"; else step $n; "$@" || { rc=$?; echo "=== FAILED: $n rc=$rc"; exit $rc; }; touch .stamps/$n; fi; }
run emsdk ./fetch-emsdk.sh
run fetch-deps ./fetch-deps.sh
run build-deps ./build-deps.sh
step src-build
cd src && ./build.sh || { rc=$?; echo "=== FAILED: src-build rc=$rc"; exit $rc; }
echo "=== DONE: $V/src/build"
'
} >>"$LOG" 2>&1
rc=$?
echo "web build exit code: $rc (log: $LOG)"
exit $rc
