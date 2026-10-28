# Developing the Key colours fork

This fork adds a **Key colours** tab: paint per-key, per-layer RGB colours that are saved on the keyboard.
It needs firmware with the key colours module: see
[RustedAperture/vial-qmk `key-colours`](https://github.com/RustedAperture/vial-qmk/tree/key-colours/users/key_colours).

Everything here assumes NixOS (`dev/shell.nix`), run from the repo root. Generated files go in
`dev/vendor/` and `dev/build/` (gitignored).

## Python environment (Python 3.11 instead of the pinned 3.6 / PyQt5 5.9)
One-time venv, using nixpkgs PyQt5/pytest/pytest-qt via `--system-site-packages`:

    nix-shell dev/shell.nix --run '
      python -m venv --system-site-packages .venv && . .venv/bin/activate
      pip install keyboard simpleeval future certifi pytest-xvfb fbs==0.9.0
      # vial cython-hidapi fork: pinned Cython 0.29.25 cannot build on 3.11, so use 0.29.37
      git clone https://github.com/vial-kb/cython-hidapi dev/vendor/hidapi-src/c
      git -C dev/vendor/hidapi-src/c checkout fa31fd46e709ac4adba80bd516b1290dd56f43e9
      git -C dev/vendor/hidapi-src/c submodule update --init
      sed -i "s/Cython==0.29.25/Cython==0.29.37/" dev/vendor/hidapi-src/c/setup.py
      pip install Cython==0.29.37 setuptools wheel
      CFLAGS="$(pkg-config --cflags libusb-1.0)" pip install --no-build-isolation dev/vendor/hidapi-src/c'

## Tests
Use `python -m pytest` so the venv's packages are visible:

    nix-shell dev/shell.nix --run '. .venv/bin/activate &&
      QT_QPA_PLATFORM=offscreen python -m pytest -q src/main/python/test'

Two upstream tests (`test_combos`, `test_tap_dance`) fail on Python 3.10+ because they pass floats
to `QPoint`. They pass on upstream's Python 3.6 CI.

## Run the app

    nix-shell dev/shell.nix --run '. .venv/bin/activate && python src/main/python/main.py'

The Key colours tab only appears for a keyboard running the key colours firmware.

## Web build (Docker)

    dev/build-web.sh             # log dev/build/web.log; first run ~15 min, re-runs ~20 s

Clones vial-kb/vial-web into `dev/vendor/vial-web` (its `vial-gui` is a symlink to this repo) and builds
in the `vial-web-builder` image (`dev/web/Dockerfile`, Ubuntu 22.04). Stamps in
`dev/vendor/vial-web/.stamps/` skip finished dependency steps; delete one to redo it.
Output: `dev/vendor/vial-web/src/build/`. Uncommitted changes in this repo are included.

Serve it locally and open in Chrome (Firefox has no WebHID):

    nix-shell dev/shell.nix --run 'python3 dev/serve-web.py 8000'

The build uses `SharedArrayBuffer`, so the server must send `Cross-Origin-Opener-Policy: same-origin`
and `Cross-Origin-Embedder-Policy: require-corp`; `serve-web.py` does. Hosts that can't set headers
(e.g. GitHub Pages) need a service-worker shim; see "Publish to GitHub Pages" below.

## Publish to GitHub Pages

    dev/publish-pages.sh         # pushes the current web build to the gh-pages branch

Live at https://rustedaperture.github.io/vial-gui/ (Chrome or Edge). The page loads
`dev/web/coi-serviceworker.min.js` (v0.1.7, MIT, pinned by SHA-256) to add the COOP/COEP headers that
Pages can't send; the first visit reloads once to activate it. `gh-pages` holds only the latest build.
