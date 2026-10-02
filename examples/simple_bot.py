#!/usr/bin/env python3
"""Reference bot: holds the stream open and plays each game on its engine session.

    pip install websockets
    HEXO_TOKEN=hxo_... python3 simple_bot.py [base-url]

HTTP and the NDJSON stream use the standard library; coordinates are htttx
axial q,r. Replace choose_move with an engine.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urljoin

from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

PLACEMENT_RADIUS = 8
# A dropped stream or engine session redials after 1 s, doubling up to 8 s,
# or after a refusal's longer Retry-After; a stream closed for 30 s forfeits
# every live game.
RETRY_FIRST_SECONDS = 1
RETRY_CAP_SECONDS = 8
# Tries of a request the server refuses with 429 or 503 before giving up.
REQUEST_TRIES = 3
# A challenge is open this long after it is sent.
CHALLENGE_SECONDS = 60

# Declared before the stream opens; a challenge outside accepts is refused.
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
    """Two free cells nearest the stones on the board.

    `board` is an htttx Board; the result is the `pieces` list of an htttx Move.
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


def wait_named(status, headers):
    """The seconds a 429 or 503 asks the caller to wait, or None for any other answer."""
    if status not in (429, 503):
        return None
    try:
        return max(1, int(headers.get("Retry-After", "")))
    except (TypeError, ValueError):
        return 1


def retry_after(error):
    """wait_named for an HTTP error."""
    return wait_named(error.code, error.headers)


class EngineSession(threading.Thread):
    """One game's websocket: the server asks, this bot answers."""

    def __init__(self, url, game_id):
        super().__init__(daemon=True)
        self.url = url
        self.game_id = game_id
        self.socket = None
        self.closed = False
        self.wait = RETRY_FIRST_SECONDS

    def run(self):
        # A dropped session forfeits nothing, so it redials until the game ends
        # or its token stops opening one.
        self.wait = RETRY_FIRST_SECONDS
        while not self.closed:
            try:
                self.play()
                # The server closes a session cleanly when the game ends, when
                # a newer connection takes the seat, or as it stops; a redial
                # would only find the game gone.
                return
            except InvalidStatus as error:
                status = error.response.status_code
                named = wait_named(status, error.response.headers)
                if status == 404:
                    # The game is over or its token has expired; the stream
                    # replays a live game's gameStart with a fresh token.
                    log(f"game {self.game_id}: no engine session to open; giving up on it")
                    return
                if named is None:
                    log(f"game {self.game_id}: engine session refused: {status}")
                    return
                self.wait = max(self.wait, named)
            except (ConnectionClosed, OSError) as error:
                log(f"game {self.game_id}: engine session ended: {error}")
            if self.closed:
                return
            time.sleep(self.wait)
            self.wait = min(self.wait * 2, RETRY_CAP_SECONDS)

    def play(self):
        # The board lives per connection: setup holds the stones before any
        # turn, and each move_request lists in previous every turn this
        # connection has not seen, so a redial rebuilds the whole game.
        cells = {}
        with connect(self.url) as socket:
            self.socket = socket
            # A session that opened starts the next redial's wait over.
            self.wait = RETRY_FIRST_SECONDS
            for message in socket:
                packet = json.loads(message)
                if packet["type"] == "setup":
                    cells = {(c["q"], c["r"]): c["p"] for c in packet["board"]["cells"]}
                elif packet["type"] == "move_request":
                    for move in packet["previous"]:
                        for piece in move["pieces"]:
                            cells[(piece["q"], piece["r"])] = move["side"]
                    socket.send(json.dumps(self.answer(packet, cells)))
                # A heartbeat needs no answer: this bot answers every
                # move_request at once, so it is never idle while waited on.

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
        self.closed = True
        if self.socket is not None:
            self.socket.close()


class SimpleBot:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.sessions = {}
        self.backoff = RETRY_FIRST_SECONDS

    def request(self, method, path, body=None, timeout=30):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(urljoin(self.base_url, path), data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        return urllib.request.urlopen(request, timeout=timeout)

    def call(self, method, path, body=None, within=None):
        """A request whose 429 or 503 is retried after the wait it names,
        never past `within` seconds from now when that is given."""
        deadline = None if within is None else time.monotonic() + within
        for attempt in range(REQUEST_TRIES):
            try:
                self.request(method, path, body).close()
                return
            except urllib.error.HTTPError as error:
                wait = retry_after(error)
                late = deadline is not None and wait is not None and time.monotonic() + wait > deadline
                if wait is None or late or attempt == REQUEST_TRIES - 1:
                    raise
                log(f"{method} {path}: {error.code}; retrying in {wait} s")
                time.sleep(wait)

    def run(self):
        self.call("PATCH", "/api/bot/account", DECLARATION)
        while True:
            wait = None
            try:
                self.hold_stream()
            except urllib.error.HTTPError as error:
                # A bad token or a ban never heals by waiting.
                if error.code in (401, 403):
                    sys.exit(f"stream refused: {error.code} {error.read().decode()}")
                wait = retry_after(error)
                log(f"stream refused: {error.code}")
            except OSError as error:
                log(f"stream dropped: {error}")
            wait = max(self.backoff, wait or 0)
            log(f"redialing in {wait} s")
            time.sleep(wait)
            self.backoff = min(self.backoff * 2, RETRY_CAP_SECONDS)

    def hold_stream(self):
        # open=1 takes challenges and games while the stream is held. Opening
        # replays every live game as gameStart, so a redial loses nothing; a
        # second stream would replace this one.
        with self.request("GET", "/api/bot/stream?open=1", timeout=None) as stream:
            log("stream open")
            self.backoff = RETRY_FIRST_SECONDS
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
                # Past its life the challenge is gone, so no retry outlasts it.
                self.call("POST", f"/api/bot/challenge/{challenge_id}/accept", within=CHALLENGE_SECONDS)
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
