# The lifecycle loop (language-agnostic pseudocode)

This is the entire client contract for **this** spec: **read the global event
stream, answer challenges, and on `gameStart` open the game's engine session.**
Gameplay itself (the move exchange) is the **engine protocol** and is not shown
here: this spec stops at the session boundary. The `gameStart` event hands you a
dial bootstrap (a socket URL and a short-lived per-game token); you connect there
to play.

```text
TOKEN = "hxo_..."            # Personal Access Token, sent as: Authorization: Bearer <TOKEN>
BASE  = "https://hexo.did.science"

# ── Global event loop ───────────────────────────────────────────────────
open GET {BASE}/api/stream/event   with bearer TOKEN     # application/x-ndjson, never closes
for each line in event_stream:
    if line is blank:  continue                          # keepalive, skip it
    event = parse_json(line)
    switch event.type:
        case "challenge":          maybe POST /api/challenge/{event.challenge.id}/accept
        case "gameStart":          spawn play_game(event.game, event.engine)
        case "gameFinish":         log result (event.game.finishReason / winner); let the game task end
        case "opponentGone":       # observe-only: the opponent dropped in event.gameId and the
                                   # server is counting down (event.finishesInSeconds) to an
                                   # auto-forfeit. Take no action; if they return, play resumes
                                   # on the engine session, otherwise a gameFinish follows.
                                   continue
        case "challengeDeclined":  log; maybe re-challenge with different terms
        case "challengeCanceled":  log; drop the pending challenge, it is gone
        case "challengeExpired":   log; drop the pending challenge, it timed out

# ── Reaching a game (the handoff to the engine protocol) ─────────────────
function play_game(game, engine):                        # game.side is "p1" or "p2"
    # engine.socketUrl + engine.token are the dial bootstrap from the gameStart
    # event: server-issued, read-only, scoped to this one game.
    open_engine_session(engine.socketUrl, engine.token)  # speak the ENGINE PROTOCOL here

    # Everything from here on (board state, move requests, answer-matching) is the
    # engine protocol and is out of scope for this contract. This spec only got you
    # to the session; how you choose and submit moves lives there.

# ── Conceding (a lifecycle action that stays on this spec) ───────────────
function resign(gameId):
    POST {BASE}/api/bot/game/{gameId}/resign  with bearer TOKEN
    # 200 ok; 409 game-finished if it already ended; 404 once the server reaps it.
```

### Why it's safe to crash

A bot can die at any point and rejoin: reopen `GET /api/stream/event`. On connect
the server replays your current state, re-issuing a `gameStart` (with a **fresh**
`engine` dial bootstrap) for every game still in progress, so you re-dial and
continue. `GET /api/bot/games` is a point-in-time reconciliation read of which
games you are in; it does not itself carry an engine session.
