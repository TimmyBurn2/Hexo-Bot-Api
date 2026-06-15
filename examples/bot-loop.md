# The bot loop (language-agnostic pseudocode)

This is the entire client contract: **read the streams, rebuild state from the
cumulative move list, POST a move when it's your turn.** No local game state is
required: everything you need arrives on the wire.

```text
TOKEN = "hxo_..."            # Personal Access Token, sent as: Authorization: Bearer <TOKEN>
BASE  = "https://hexo.did.science"

# ── 1. Global event loop ────────────────────────────────────────────────
open GET {BASE}/api/stream/event   with bearer TOKEN     # application/x-ndjson, never closes
for each line in event_stream:
    if line is blank:  continue                          # keepalive, skip it
    event = parse_json(line)
    switch event.type:
        case "challenge":          maybe POST /api/challenge/{event.challenge.id}/accept
        case "gameStart":          spawn play_game(event.game.id, event.game.side)
        case "gameFinish":         log result; let the game task end
        case "challengeDeclined":  log; maybe re-challenge with different terms

# ── 2. Per-game loop (one per active game) ──────────────────────────────
function play_game(gameId, mySide):                      # mySide is "p1" or "p2"
    open GET {BASE}/api/bot/game/stream/{gameId}  with bearer TOKEN   # x-ndjson, closes at game end
    for each line in game_stream:
        if line is blank:  continue                      # keepalive, skip it
        msg = parse_json(line)

        # Both gameFull and gameState carry the CUMULATIVE move list.
        # Rebuild the board from scratch every time, this is what makes
        # the protocol stateless. A crash + reconnect needs no local memory:
        # the fresh gameFull replays everything.
        moves  = (msg.type == "gameFull") ? msg.state.moves  : msg.moves
        status = (msg.type == "gameFull") ? msg.state.status : msg.status
        ply    = (msg.type == "gameFull") ? msg.state.ply    : msg.ply

        board = empty_board()
        for turn in moves:                               # replay, oldest first
            for stone in turn.s:                         # 1 stone on ply 0, else 2
                place(board, turn.p, stone)              # turn.p is "p1" or "p2"

        if status != "started":  return                 # game over (msg.winner has the side)

        # Whose turn is it? Player 1 plays even plies, Player 2 odd plies.
        sideToMove = (ply % 2 == 0) ? "p1" : "p2"
        if sideToMove != mySide:  continue               # opponent to move; wait for next line

        # ── 3. Search / decide (your engine; this repo says nothing about it)
        #     The opening turn (ply 0, you are p1) is a SINGLE hex at the centre;
        #     every later turn is TWO hexes.
        if ply == 0:  stones = [[0, 0]]                  # forced opening hex
        else:         stones = choose_two_stones(board, mySide)   # [[q,r],[q,r]]

        # ── 4. Submit with an EXPLICIT ply (compare-and-set / idempotent write)
        submit(gameId, stones, ply)

function submit(gameId, stones, ply):
    resp = POST {BASE}/api/bot/game/{gameId}/move
                bearer TOKEN
                json { "stones": stones, "ply": ply }
    switch resp.status:
        case 200:  return                                 # applied
        case 409:  # not-your-turn: stale/duplicate/out-of-order ply (CAS miss).
                   # The body has the authoritative expectedPly. Do NOT blindly
                   # resubmit, wait for the next gameState (it reflects truth),
                   # or recompute at resp.body.expectedPly. Safe to retry.
                   return
        case 422:  # illegal placement; resp.body.stone is the offending cell.
                   stones = choose_two_stones(board, mySide, avoid=resp.body.stone)
                   submit(gameId, stones, ply)            # same ply, it WAS your turn
        case 429:  sleep(resp.headers["Retry-After"] or 60s);  submit(gameId, stones, ply)
```

### Why it's safe to crash

A bot can die at any point and rejoin: reconnect to
`/api/bot/game/stream/{gameId}`, receive a fresh `gameFull`, replay
`state.moves`, and you are exactly where you left off, no local move log, no
cached board, no reconciliation. The server's cumulative list **is** the state.
