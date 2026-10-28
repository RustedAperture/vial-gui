"""Serve the web build locally with the cross-origin isolation headers it needs.

The browser build uses SharedArrayBuffer (threads), which Chrome only allows on
cross-origin isolated pages. Plain `python -m http.server` doesn't send the headers.

usage: python3 dev/serve-web.py [port]   (default 8000, serves dev/vendor/vial-web/src/build)
"""
import functools
import http.server
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "vial-web", "src", "build")


class IsolatedHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = functools.partial(IsolatedHandler, directory=os.path.normpath(ROOT))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print("serving {} on http://localhost:{}".format(os.path.normpath(ROOT), port))
        server.serve_forever()


main()
