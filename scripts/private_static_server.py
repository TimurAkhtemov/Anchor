#!/usr/bin/env python3
"""Loopback static server for the private site.

Unlike `python -m http.server` it rejects any Host header other than this server's own
loopback names, so a DNS-rebinding page in the browser cannot read the dashboard. The
directory is resolved per request, so swapping the `current` symlink needs no restart,
and a missing directory answers 404 instead of crashing.
"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class _Handler(SimpleHTTPRequestHandler):
    def send_head(self):
        port = self.server.server_port
        if (self.headers.get("Host") or "").lower() not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            self.send_error(403, "Forbidden host")
            return None
        return super().send_head()


def make_server(port: int, directory: str) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), partial(_Handler, directory=directory))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", type=int)
    parser.add_argument("directory")
    args = parser.parse_args()
    make_server(args.port, args.directory).serve_forever()


if __name__ == "__main__":
    main()
