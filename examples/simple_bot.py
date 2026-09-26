#!/usr/bin/env python3
"""Reference bot: hold the stream open, play each game on its engine session.

    pip install websockets
    HEXO_TOKEN=hxo_... python3 simple_bot.py [base-url]

One dependency: `websockets` for the engine session; HTTP and the NDJSON
stream use the standard library. Coordinates are htttx axial q,r throughout.
Replace choose_move with a real engine and nothing else here has to change.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urljoin

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

PLACEMENT_RADIUS = 8
STREAM_RETRY_SECONDS = 2

# Sent before the stream opens: what the directory shows, and which clocks
# this bot plays under. A challenge outside `accepts` is refused for it.
DECLARATION = {
    "about": "Reference bot: plays the nearest free cells. Legal, never strong.",
    "version": "0.5.0",
    "repoUrl": "https://github.com/TimmyBurn2/Hexo-Bot-Api",
    "accepts": {"turnMs": [5000, 600000], "match": True, "unlimited": True},
}


def distance(a, b):
    """Hex distance between two axial coordinates."""
    dq, dr = a[0] - b[0], a[1] - b[1]
    return (abs(dq) + abs(dq + dr) + abs(dr)) // 2


def choose_move(board):
    """Two free cells, nearest to the stones already on the board.

    Legal but weak: it never blocks and never builds a line. `board` is an
    htttx Board, the return value is the `pieces` list of an htttx Move.
    """
    taken = {(cell["q"], cell["r"]) for cell in board["cells"]}
    if not taken:
        raise ValueError("empty board: the origin stone is placed before a bot moves")
    candidates = set()
    for stone in taken:
        for dq in range(-PLACEMENT_RADIUS, PLACEMENT_RADIUS + 1):
            for dr in range(-PLACEMENT_RADIUS, PLACEMENT_RADIUS + 1):
                cell = (stone[0] + dq, stone[1] + dr)
                if cell not in taken and distance(cell, stone) <= PLACEMENT_RADIUS:
                    candidates.add(cell)
    ranked = sorted(
        candidates,
        key=lambda c: (min(distance(c, s) for s in taken), abs(c[0]), abs(c[1]), c),
    )
    return [{"q": q, "r": r} for q, r in ranked[:2]]


def log(message):
    print(message, file=sys.stderr, flush=True)


class EngineSession(threading.Thread):
    """One game's websocket: the server asks, this bot answers."""

    def __init__(self, url, game_id):
        super().__init__(daemon=True)
        self.url = url
        self.game_id = game_id
        self.socket = None

    def run(self):
        # The board lives per connection: setup holds the stones before any
        # turn, and each move_request lists in `previous` every turn this
        # connection has not seen, the bot's own and the server's opening
        # included, so a redial rebuilds the whole game.
        cells = {}
        try:
            with connect(self.url) as socket:
                self.socket = socket
                for message in socket:
                    packet = json.loads(message)
                    if packet["type"] == "setup":
                        cells = {(c["q"], c["r"]): c["p"] for c in packet["board"]["cells"]}
                    elif packet["type"] == "move_request":
                        for move in packet["previous"]:
                            for piece in move["pieces"]:
                                cells[(piece["q"], piece["r"])] = move["side"]
                        socket.send(json.dumps(self.answer(packet, cells)))
                    # A heartbeat needs no answer: this bot replies to every
                    # move_request at once, so it is never idle while waited on.
        except (ConnectionClosed, OSError) as error:
            log(f"game {self.game_id}: engine session ended: {error}")

    @staticmethod
    def answer(packet, cells):
        board = {
            "to_move": packet["side"],
            "cells": [{"q": q, "r": r, "p": p} for (q, r), p in cells.items()],
        }
        response = {"type": "move_response", "move": {"pieces": choose_move(board)}}
        # A move_response without the request's id is dropped.
        if "request_id" in packet:
            response["request_id"] = packet["request_id"]
        return response

    def close(self):
        if self.socket is not None:
            self.socket.close()


class SimpleBot:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.sessions = {}

    def request(self, method, path, body=None, timeout=30):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(urljoin(self.base_url, path), data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        return urllib.request.urlopen(request, timeout=timeout)

    def run(self):
        self.request("PATCH", "/api/bot/account", DECLARATION).close()
        while True:
            try:
                self.hold_stream()
            except OSError as error:
                log(f"stream dropped: {error}; redialing")
            time.sleep(STREAM_RETRY_SECONDS)

    def hold_stream(self):
        # open=1: take challenges and games for as long as this is held.
        # Opening replays every live game as gameStart, so a redial loses
        # nothing and the bot keeps no state across connections.
        with self.request("GET", "/api/bot/stream?open=1", timeout=None) as stream:
            log("stream open")
            for line in stream:
                if line.strip():
                    self.handle(json.loads(line))

    def handle(self, event):
        kind = event["type"]
        if kind == "gameStart":
            self.start_game(event)
        elif kind == "challenge":
            challenge_id = event["challenge"]["challengeId"]
            try:
                self.request("POST", f"/api/bot/challenge/{challenge_id}/accept").close()
            except urllib.error.HTTPError as error:
                log(f"could not accept {challenge_id}: {error.code} {error.read().decode()}")
        elif kind == "gameFinish":
            log(f"game {event['gameId']} over: {event['reason']}, winner {event['winner']}")
            session = self.sessions.pop(event["gameId"], None)
            if session is not None:
                session.close()
        # A replayed moveRequest needs nothing: the engine session dialed for
        # its gameStart receives the outstanding request itself.

    def start_game(self, event):
        game_id = event["gameId"]
        log(
            f"game {game_id} vs {event['opponent']['name']}, playing {event['side']},"
            f" opening of {event['openingPlies']} plies"
        )
        # Each gameStart carries a fresh token, and a new connection replaces
        # the previous one on the server as well.
        previous = self.sessions.pop(game_id, None)
        if previous is not None:
            previous.close()
        url = urljoin(self.base_url, event["engine"]["socketUrl"])
        url = url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        session = EngineSession(f"{url}?{urlencode({'token': event['engine']['token']})}", game_id)
        self.sessions[game_id] = session
        session.start()


if __name__ == "__main__":
    bot_token = os.environ.get("HEXO_TOKEN")
    if not bot_token:
        sys.exit("set HEXO_TOKEN to a bot token")
    host = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000"
    SimpleBot(host, bot_token).run()
