"""Loopback-only demo interface. Team identities are illustrative here."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from uuid import uuid4
from .agent import process
from .presentation import render, export


def serve(store, port=8787):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, value, content_type="application/json"):
            data = (
                value.encode() if isinstance(value, str) else json.dumps(value).encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                self.reply(
                    200,
                    Path(__file__).with_name("index.html").read_text(encoding="utf-8"),
                    "text/html",
                )
            elif self.path == "/state":
                self.reply(200, store.snapshot())
            else:
                self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if self.headers.get("Origin") not in (
                None,
                "http://127.0.0.1:8787",
                "http://localhost:8787",
            ):
                self.reply(403, {"error": "Local origin required"})
                return
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size > 16384:
                    raise ValueError("Request too large")
                body = json.loads(self.rfile.read(size))
                identity = body.get("id") or str(uuid4())
                if self.path == "/message":
                    result = process(
                        store,
                        identity,
                        "demo",
                        "shift",
                        body.get("sender", "owner"),
                        body["text"],
                        "owner",
                    )
                elif self.path == "/plan":
                    result = store.handle(
                        identity, "demo", "shift", "owner", {"kind": "plan"}, "owner"
                    )
                elif self.path == "/approve":
                    result = store.handle(
                        identity,
                        "demo",
                        "shift",
                        "owner",
                        {"kind": "approve", "proposal_id": body["proposal_id"]},
                        "owner",
                    )
                else:
                    self.reply(404, {"error": "Not found"})
                    return
                store.delivered(
                    identity
                )  # Demo replies are rendered synchronously, never sent to Switch.
                if result["kind"] in ("proposal", "approved"):
                    export(store.folder / "artifacts", result)
                self.reply(200, {"result": result, "text": render(result)})
            except (ValueError, KeyError, RuntimeError) as error:
                self.reply(400, {"error": str(error)})

    print(f"Kitchen Shift demo http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
