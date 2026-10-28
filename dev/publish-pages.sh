#!/usr/bin/env bash
# Publish the web build (dev/build-web.sh output) to the gh-pages branch of a GitHub repo.
# GitHub Pages can't send the COOP/COEP headers SharedArrayBuffer needs, so the page loads
# coi-serviceworker (dev/web/coi-serviceworker.min.js, v0.1.7, MIT), which adds them in the browser.
# usage: dev/publish-pages.sh [git-remote-url]   (default: git@github.com:RustedAperture/vial-gui.git)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/dev/vendor/vial-web/src/build"
REMOTE="${1:-git@github.com:RustedAperture/vial-gui.git}"
COI_SHA256=03d2f35be3249f5eeb4e214c5daf2be8067e2b24630aaef26a1247b723f2d05d

[ -f "$BUILD/index.html" ] || { echo "no web build at $BUILD; run dev/build-web.sh first" >&2; exit 1; }
echo "$COI_SHA256  $ROOT/dev/web/coi-serviceworker.min.js" | sha256sum -c --quiet -

SITE="$(mktemp -d)"
trap 'rm -rf "$SITE"' EXIT
cp "$BUILD"/* "$SITE"/
cp "$ROOT/dev/web/coi-serviceworker.min.js" "$SITE"/
touch "$SITE/.nojekyll"
# Served from /<repo>/, so links must be relative; the service worker script must load first.
sed -i 's|href="/icon.png"|href="icon.png"|; s|<head>|<head>\n<script src="coi-serviceworker.min.js"></script>|' "$SITE/index.html"
grep -q 'coi-serviceworker.min.js' "$SITE/index.html" || { echo "failed to patch index.html" >&2; exit 1; }

COMMIT="$(git -C "$ROOT" rev-parse --short HEAD)"
git -C "$SITE" init -q -b gh-pages
git -C "$SITE" add -A
git -C "$SITE" -c user.name="$(git -C "$ROOT" config user.name)" -c user.email="$(git -C "$ROOT" config user.email)" \
    commit -q -m "Web build of vial-gui $COMMIT"
# gh-pages holds only the latest build, so it is replaced on every publish.
git -C "$SITE" push -q --force "$REMOTE" gh-pages
echo "published vial-gui $COMMIT to gh-pages on $REMOTE"
