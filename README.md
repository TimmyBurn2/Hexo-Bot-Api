# HeXO Bot API

**Status: 0.3, served in development.** The whole contract is answered by the
[`TimmyBurn2/HeXO`](https://github.com/TimmyBurn2/HeXO) branch `challenges`
(behind `BOT_API_ENABLED`); upstreaming is pending the bot-account PR (#125)
landing first. No production deployment answers these paths today.

## What this is

`openapi.yaml` is the HTTP surface a bot uses to play on
[HeXO](https://hexo.did.science): one file, eleven operations, nothing the
server is not going to implement. The per-move engine exchange is htttx's, not
HeXO's.

Every field maps to something the play-core implements, and nothing HeXO-internal
leaks through: a bot is handed a `gameId` and never a session id, so another
server can answer this contract without adopting HeXO's lobby model. The
website-only surface (the roster's Play button, the owner's challenge routes,
account management) is deliberately outside this file: it answers to browser
cookies, not bot tokens.

## The loop

1. Get a bot-account token (`hxo_...`) from the owner's account page.
2. `GET /api/bot/stream?open=1` and hold it open. The connection is the bot's
   presence, and `open=1` says it is taking challenges; both end with it.
3. On `gameStart`, note the `gameId` and which side you play.
4. On `moveRequest`, read `request.board`, pick two cells, and
   `POST /api/bot/game/{gameId}/move` with an htttx `MoveResponse`.
5. A `400` means the move was illegal. The clock keeps running, so send another.
6. On `gameFinish`, the game is over.

Reconnecting replays every active game as a `gameStart`, plus a fresh
`moveRequest` if it is the bot's turn, so a bot needs no local game state. The
server auto-places the opening stone for bots, so every `moveRequest` wants
exactly two placements.

## Versions

`0.2` — first cut of the eleven operations. `0.3` — the clock floors on
`TimeControl`, the `time_limit` rule per clock mode, and the 404 wording on the
challenge paths; see `CHANGELOG.md`.

## Engine schemas

`Coord`, `Board`, `PositionEvaluation`, `Move`, `MoveRequest`, and
`MoveResponse` are copied verbatim from [htttx-bot-api](https://github.com/hex-tic-tac-toe/htttx-bot-api) at commit
`37d2385`; `scripts/check-htttx.sh` diffs the vendored block against upstream.

Those schemas use axial `q,r`. HeXO stores axial `x,y` and converts with
`x = q + r`, `y = -r`, so a bot only ever sees `q,r`.

## Examples

- [`examples/simple_bot.py`](examples/simple_bot.py) — the loop above, using
  `requests` only. `choose_move` returns the free cells nearest the stones
  already placed; replace it with an engine and nothing else changes.
- [`examples/stateless_server.py`](examples/stateless_server.py) — the same
  `choose_move` served as an htttx `/turn` endpoint, standard library only.
- [`examples/stream.ndjson`](examples/stream.ndjson) — one line per event type.

## Linting

```
make lint          # Redocly + Spectral, both must report 0 errors
make check-htttx   # diff the vendored block against upstream (needs network)
make docs          # render dist/index.html
```

`make lint` reads `openapi.yaml`, `redocly.yaml` and `.spectral.yaml`, and
nothing else. Beyond the npm registry `npx` fetches the linters from,
`make check-htttx` is the only target that reaches the network.

## Rating

[`RATING-NOTES.md`](RATING-NOTES.md) records the one unanswered question the bot
ladder inherits: what anchors its scale, and the farming surface that comes with
the answer.
