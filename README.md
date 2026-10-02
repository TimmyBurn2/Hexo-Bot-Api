# HeXO Bot API

The OpenAPI 3.1 contract a bot uses to play HeXO: presence, challenges, the
public bot list, and the account over HTTP, and each game on its own
websocket.

HeXO is played on an unbounded hex grid.
Turn 0 is the origin stone at (0, 0), owned by `x`; `o` plays turn 1, and the
sides alternate, two stones a turn.
A stone goes on an empty cell within hex distance 8 of a stone already on the
board.
Six of one side's stones in a line along any of the three axes win.
A ply is one stone.

## The loop

1. Sign in on the server's website, create a bot on your account page, and
   copy its bot token (`hxo_...`); the API is on the same origin.
2. `PATCH /api/bot/account` with `accepts`, the clocks the bot plays; until
   then it plays none.
   `about`, `version`, and `repoUrl` are optional and show on the public bot
   list; so is `levels`, the strengths a player may pick (see Strength
   levels), and `analyzer`, which offers the bot's reading of positions (see
   Analyzers).
3. `GET /api/bot/stream?open=1` with `Authorization: Bearer <bot token>`, and
   hold it open.
   While it is open the bot is online; with `open=1` other bots may challenge
   it, and players on the website may start games against it, which arrive
   as `gameStart` with no challenge and `rated` false: such a game moves the
   player's rating, never the bot's.
4. On `challenge`, accept or decline it.
   To challenge another bot, `POST /api/bot/challenge/{name}` with a fresh
   `requestId`; resending the same one is safe.
5. On `gameStart`, set the game up at its `level`, null for the default,
   and dial `engine.socketUrl` on the API's origin, `wss://` (or `ws://` over
   http), with `?token=` set to `engine.token`.
6. The engine session speaks htttx basic_websocket v1-alpha.
   The server sends `setup`, whose board holds the origin stone alone, then a
   `move_request` on each of the bot's turns: `side`, `request_id`,
   `move_time_limit` in seconds when there is a clock, and `previous`, every
   turn this connection has not seen, the opening's included, oldest first,
   as `{side, pieces}`.
   The bot answers
   `{"type": "move_response", "move": {"pieces": [{"q": 1, "r": 0}, {"q": -1, "r": 1}]}, "request_id": 0}`,
   echoing the request's `request_id`.
   It declares no capabilities, but must handle `move_skips` (`previous` may
   hold several turns) and `request_id`.
   An illegal move forfeits.
7. Every 10 s the server sends `heartbeat`, with `waiting` true while it waits
   on this bot's move.
   The bot never answers it; a bot that hears `waiting` true while it is not
   working on a move hangs up and redials.
8. To resign, `POST /api/bot/game/{gameId}/resign` with
   `Authorization: Bearer <engine.token>`.
9. `gameFinish` ends the game.

The game token opens the engine session and resigns the game for 60 s after
the `gameStart` that carried it.
Reopening the stream replays every live game as `gameStart` with a fresh
token, followed by a `moveRequest` when the bot is to move; that
`moveRequest` needs no answer, since the engine session sends its own
`move_request`.
A new engine session replaces the old one and replays the game in
`previous`, so a bot needs no state across connections.

## Tournaments

An owner may enter a bot in a tournament on the website.
From its start to its end the bot is reserved: challenges to or from it, and
games started against it, answer `bot_busy`.
Its tournament games arrive as `gameStart` with no challenge, rated, two
against each opponent from one opening with the sides swapped.
Entering commits the bot to hold its stream open throughout: a game waits
60 s for a bot that is not connected and then scores for its opponent, and a
bot that misses two pairings in a row is withdrawn.

## Strength levels

A bot may declare 2 to 8 levels in `levels`, weakest first, with `default`
naming one; a player on the website picks one, and `gameStart.level` names
it, or is null at the default.
A level has an `id` (lowercase letters, digits, and hyphens, at most 16,
unique), a `label` (at most 24 printable ASCII characters), and optionally an
`about` (120 characters), a `note` (80), and a `budget`.
The budget holds at least one of `timeMs`, `nodes`, `depthTurns` (HeXO
turns, not stones), and `playouts`, per turn; the website shows it as the
bot's own claim.
The bot's rating belongs to its default: challenges and tournaments play it,
and a game at any other level is unrated for both sides and counts toward no
daily cap.
A bot that no longer declares a level plays its default; `"levels": null`
clears them.

An alpha-beta engine:

```json
{ "levels": { "default": "standard", "list": [
  { "id": "quick", "label": "quick", "budget": { "timeMs": 200 } },
  { "id": "standard", "label": "standard", "budget": { "nodes": 1000000 } },
  { "id": "deep", "label": "deep", "budget": { "depthTurns": 8 } }
] } }
```

A neural MCTS bot:

```json
{ "levels": { "default": "800", "list": [
  { "id": "100", "label": "100 sims", "budget": { "playouts": 100 } },
  { "id": "800", "label": "800 sims", "budget": { "playouts": 800 } },
  { "id": "6400", "label": "6400 sims", "budget": { "playouts": 6400, "timeMs": 5000 } }
] } }
```

## Analyzers

A bot may also read positions for players on the website: positions on the
analysis board and whole finished games, never a position of a game being
played.
It declares `analyzer` with `lines`, 1 to 3, the move and up to two
considerations it answers with; `maxSeconds`, 1 to 10 and 2 by default, the
longest a player may give it per position; and `whilePlaying`, false by
default, true to read while it plays a game.
`"analyzer": null` withdraws it.
Declaring one promises the basic_websocket capabilities `free_setup`,
`resettable_state`, `dual_sided`, `request_id`, `move_time_limit`, and
`interruptible`.

```json
{ "analyzer": { "lines": 3, "maxSeconds": 5 } }
```

`values`, optional, says how the bot's heuristic reads: `scale`, above 0 and
at most 1000000, 1 by default, the size it means as decided, which the site
divides by before drawing or judging a heuristic; `meaning`, `expected` when
the heuristic, divided by `scale`, is the bot's estimate of x's expected
result, 2 P(x wins) - 1, or `raw`, the default, when it is only ordered,
higher being better for x, and not calibrated; and `cuts`, the drops of the
mover's scaled value it calls an `inaccuracy`, a `mistake`, and a `blunder`,
each above 0 and at most 2, rising.
Without cuts, no turn is judged by a drop of value; forced wins, from the board
and from `win_in`, are judged either way.
Expected values suit lichess's cuts:

```json
{ "analyzer": { "lines": 3, "values": { "meaning": "expected", "cuts": { "inaccuracy": 0.1, "mistake": 0.2, "blunder": 0.3 } } } }
```

1. While the bot declares an analyzer and holds its stream, the stream sends
   `analysisSession` as it opens, after the declaration, and 5 s after the
   analysis session closes; dial its `engine.socketUrl` with `?token=` as
   for a game.
2. For each position the server sends `setup`, whose board holds the
   position's stones, then `move_request` with `previous` empty, the `side`
   to move, `move_time_limit`, and `request_id`.
3. The bot answers `move_response` with `move.evaluation`, and
   `considerations` up to its `lines`, each with its evaluation, best first.
4. `interrupt` drops the outstanding request, which then needs no answer.
   One request is outstanding at a time; analysis never counts toward the
   bot's 4 games, and a bot playing a game is sent none unless it declared
   `whilePlaying`.

An evaluation is of the board after its line: `win_in` counts turns from
that board, its side to move first.
A reading fails when the answer comes more than 3 s past `move_time_limit`,
a line is no legal turn from the position or repeats one, the move carries
no evaluation, or an evaluation contradicts the board.
When the side to move can complete six, the best line must; a line that
completes six is valued for its mover, as `win_in` 1 with the mover's sign
or a heuristic in its favor; after any other line, an odd
`win_in` belongs to the side then to move, and a `win_in` of 1 needs a six
that side can complete, while a six it can complete must not be valued
for the other side.
Three failures in 10 minutes bench the analyzer for 10 minutes.
Every reading is published under the bot's name, version, owner, and the
values it declared when it read.

In games too, a move's evaluation and up to two considerations, when
present, are published with the finished game.

## Limits

Every 429 and 503 carries `Retry-After`, in whole seconds.

| What | Limit | Past it |
| --- | --- | --- |
| Requests with one bot token or game token | a burst of 20, then 2 a second | 429 `rate_limited` |
| Requests from one network address | a burst of 60, then 10 a second | 429 `rate_limited` |
| Requests without a credential, from everyone | a burst of 300, then 100 a second | 429 `rate_limited` |
| Stream opens, per bot | a burst of 5, then 1 every 10 s | 429 `rate_limited` |
| Engine session dials, per bot per game | a burst of 5, then 1 every 10 s | 429 `rate_limited` |
| Analysis session dials, per bot | a burst of 5, then 1 every 10 s | 429 `rate_limited` |
| Challenges sent | 200 a UTC day | 429 `daily_challenge_cap` until 00:00 UTC |
| Bot-vs-bot games | 100 a UTC day per bot, 20 per pair | 429 `daily_bot_cap`, `daily_pair_cap` until 00:00 UTC |
| Live games | 4 per bot | 400 `bot_busy` |
| Failed readings | 3 in 10 minutes | the analyzer gets nothing for 10 minutes |
| Pending challenges | 1 per challenger and target; 10 per target | 400 `challenge_pending`, `inbox_full` |
| Request body | 16 KiB | 413 `payload_too_large` |
| Frame the bot sends | 16 KiB | close 1009 |
| Frames that answer no request | 10 per engine session | the next closes 1008, as a malformed frame or a protocol violation does |
| Unread lines or frames | 128 KiB | the stream ends; the session closes 1008 |
| Line or frame the server sends | 64 KiB | |
| Game length | 500 turns | the game ends `terminated`, no winner |

## Reconnecting

1. On 429 or 503, wait `Retry-After` before trying again.
2. Redial a dropped stream after 1 s, doubling the wait up to 8 s, or after a
   longer `Retry-After`; a stream closed for 30 s forfeits the bot's live
   games.
3. Hold one stream per bot; a second one replaces the first.
4. A dropped engine session forfeits nothing, but the clock runs: redial it
   the same way. A clean close means the game ended or a newer connection
   took the seat, and a 404 that the game is over or its token expired;
   reopening the stream replays a live game's `gameStart` with a fresh token.

## Links

- [`openapi.yaml`](openapi.yaml): every operation, event, and limit.
- [`examples/simple_bot.py`](examples/simple_bot.py): the loop above, with
  `websockets` as its one dependency, and two levels that set its pace;
  replace `choose_move` with an engine.
- [`examples/stream.ndjson`](examples/stream.ndjson): one line per event type.
- [`CHANGELOG.md`](CHANGELOG.md): what each version changed.
- [htttx-bot-api](https://github.com/hex-tic-tac-toe/htttx-bot-api) at commit
  `37d2385`: the basic_websocket v1-alpha protocol, and the source of `Coord`,
  `Board`, `PositionEvaluation`, `Move`, `MoveRequest`, and `MoveResponse`,
  copied verbatim under its MIT License (`NOTICE`).
  Coordinates are axial `q,r`: +q right, +r top-right.

## Maintaining

`openapi.yaml` and `examples/stream.ndjson` are generated by the reference
server's `pnpm spec:export`; never edit them by hand.
`make lint` runs Redocly and Spectral, both at 0 errors; `make check-htttx`
diffs the vendored block against upstream; `make docs` renders
`dist/index.html`.
`make check-breaking` fails on a breaking change since the previous release
tag, with oasdiff in Docker; `breaking-ignore.txt` lists, each with its
reason, the changes oasdiff reads as breaking that only a bot that opted in
can meet.
