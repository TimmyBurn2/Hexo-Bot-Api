#!/usr/bin/env python3
"""The same choose_move, served as an htttx stateless v1-alpha /turn endpoint.

    python3 stateless_server.py 8080
    curl -s localhost:8080/turn -d '{"board":{"to_move":"o","cells":[{"q":0,"r":0,"p":"x"}]}}'

One move function, two worlds: HeXO dials out to simple_bot.py, htttx clients dial in here.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from simple_bot import choose_move


class TurnHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path.rstrip("/") != "/turn":
            self.send_error(404)
            return
        try:
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"] or 0)))
            body = {"move": {"pieces": choose_move(request["board"])}}
        except (TypeError, ValueError, KeyError) as error:
            self.send_error(400, explain=str(error))
            return
        if "request_id" in request:
            body["request_id"] = request["request_id"]
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    HTTPServer(("127.0.0.1", port), TurnHandler).serve_forever()
