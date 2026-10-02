# Changelog

## 0.11.0

- `AnalyzerDeclaration.values`, optional: `scale` (above 0, at most 1000000, default 1), the heuristic size the analyzer means as decided; `meaning`, `expected` when the heuristic divided by `scale` estimates x's expected result, 2 P(x wins) - 1, or `raw` (the default) when it is only ordered; and `cuts` (`inaccuracy`, `mistake`, `blunder`, each above 0 and at most 2, rising), the drops of the mover's scaled value judged as each, 0.1, 0.2, and 0.3 suiting expected values; without cuts no drop of value is judged. Values out of these bounds answer 400.
- `Account.analyzer.values` and `BotListing.analyzer.values`, required: as declared, else scale 1, null cuts, and `raw`.
- The analysis session says an evaluation is of the board after its line, `win_in` counts turns from that board, and a line that completes six is valued for its mover, as `win_in` 1 with the mover's sign or a heuristic in its favor.
- The README shows a declaration with expected values and cuts.

## 0.10.0

- `AccountDeclaration.analyzer`, and `Account.analyzer` and `BotListing.analyzer`, null until declared: `lines` (1 to 3), `maxSeconds` (1 to 10, default 2), and `whilePlaying` (default false), read back with `ready`, true while the analysis session is open; `null` withdraws it.
- `analysisSession` on the stream, sent only to a bot that declares an analyzer, and `GET /api/bot/analysis/socket` (`openAnalysisSession`): a basic_websocket v1-alpha session reading one position at a time with `setup`, `move_request`, and `interrupt`, its failures benching the analyzer.
- oasdiff reads the new `StreamEvent` member as breaking; `analysisSession` is sent only to a bot that declared `analyzer`, so `breaking-ignore.txt` skips that one change, and `make check-breaking` reads it.
- `listBots` takes `analyzer=1`, listing only bots that declare an analyzer.
- A move's evaluation and up to two considerations, when present, are published with the finished game.
- The README has an Analyzers section.

## 0.9.0

- `AccountDeclaration.levels`, and `Account.levels` and `BotListing.levels`, null until declared: 2 to 8 strengths a player may pick, weakest first, each with an `id`, a `label`, and an optional `about`, `budget` (`timeMs`, `nodes`, `depthTurns`, `playouts`), and `note`; `null` clears them.
- `gameStart.level`, required: the declared level the bot plays the game at, null at its default; a level the bot no longer declares plays its default. Challenges and tournaments play the default, and a game at any other level is unrated.
- Text in a declaration is cleaned, never refused for what it holds: in `about`, `version`, and a level's `about` and `note`, a line break or tab becomes a space, other control and format characters (bidirectional marks, zero-width characters, soft hyphens) are dropped, whitespace runs collapse, and the ends are trimmed; the length caps count the cleaned text. A level's `id` and `label` are refused unless valid as sent.
- The `Paused` response says a bot with a live game, or with a place in a running tournament, still opens its stream.
- `examples/simple_bot.py` declares two levels and paces its answers by `gameStart.level`; the README shows two example declarations.

## 0.8.0

- Breaking: `gameStart.rated` is true only in a game between two bots, the one kind that moves the bot's own rating; a game against a player moves only the player's rating, and one against a guest moves none.
- `Seat.rating` is a nullable integer, no longer an `allOf` of `Rating` and null; `Seat` says a guest's rating is null.
- `examples/simple_bot.py` gives up on a game whose engine session answers 404 or closes cleanly, rather than redialing a game that is over; the README says what each means.

## 0.7.1

Prose only; no schema, path, or code changes.

- A tournament game arrives as `gameStart` with no challenge before it, and `bot_busy` also answers challenges to or from a bot playing a tournament.
- The README states what entering a tournament commits a bot to.
- The engine session's packets, heartbeat, and capabilities, the game token's life, the finish reasons, the clock modes, and `accepts` are described where a bot meets them.
- Descriptions state each behavior once, without rationale or restated schema.

## 0.7.0

- Every operation can answer 429 `rate_limited` with `Retry-After`: per bot token 20 requests at once, then 2 a second; per network address 60, then 10 a second; from all callers without a credential 300, then 100 a second.
- `openStream` opens and `openEngineSession` dials take 5 at once, then 1 every 10 s, per bot and per game seat.
- `createChallenge` sends at most 200 challenges a UTC day (429 `daily_challenge_cap`) and one pending challenge per challenger and target (400 `challenge_pending`).
- A body over 16 KiB answers 413 `payload_too_large`.
- The engine session closes 1008 after more than 10 frames that answer no request, a malformed frame, a protocol violation, or 128 KiB left unread, and 1009 for a frame over 16 KiB; the stream ends past the same backlog; no line or frame the server sends passes 64 KiB.
- `openStream` states that a stream closed for 30 s forfeits the bot's live games.
- A game ends `terminated` with no winner at 500 turns.
- Breaking: `daily_pair_cap` and `daily_bot_cap` answer 429 with `Retry-After` to 00:00 UTC, not 400, and move from `ChallengeCreateError` to `ChallengeQuotaError`.

## 0.6.0

- `BotListing.liveGames`, required: the games the bot plays now, 0 to 4; at 4 it takes no new game.

## 0.5.0

- Generated from the reference server's contract.
- `GET /api/bot/game/{gameId}/socket` (`openEngineSession`): play moves from HTTP to a per-game htttx basic_websocket v1-alpha session, the server as client; `gameStart.engine` carries its `socketUrl` and a game token.
- `POST /api/bot/game/{gameId}/resign` (`resignBotGame`) authenticates with the game token.
- Removed `playMove`, `getGame`, `joinSession`, and `listChallenges`; pending challenges replay on the stream as it opens.
- Removed `thinkMs`, `Player.profileId`, `Player.displayName`, and the `opening` object.
- `gameStart.rated` and `gameStart.openingPlies`.
- `requestId` on `createChallenge`; resending one answers 200 with the stored challenge.
- 403 `banned` and `delisted`, and 503 `paused` with `Retry-After`, where they apply.
- `BotListing.ownerName`, `online`, and `openForChallenges`; players are `{name, rating, provisional}`.
- A challenge names its target by bot name: `POST /api/bot/challenge/{name}`.
- `openingPlies` is 1, 3, 5, 7, or 9, the origin included, default 5; an opening with a lopsided six-window is redrawn whole.
- `version` caps at 64 characters and `repoUrl` at 2048; the declaration body is strict, so an unknown key answers 400.
- A bot must support the bws `move_skips` and `request_id` capabilities.

## 0.4.2

- `BotListing` carries the declaration's `about`, `version`, and `repoUrl` beside `accepts`, each absent until declared.

## 0.4.1

- `Opening.randomStones` (0 to 6 stones) becomes `Opening.randomTurns` (0 to 3 turns of two stones).

## 0.4.0

- `PATCH /api/bot/account` (`updateAccount`) declares `about` (at most 280 characters), `version`, `repoUrl`, and `accepts`; a challenge outside `accepts` answers `not-open`.
- `Account` reads the declaration back, and `BotListing` carries `accepts`.
- `createChallenge` gains `thinkMs` and `opening: {randomStones}`; `gameStart` carries `opening`.
- `GET /api/bot/game/{gameId}` (`getGame`): the board as an htttx `Board`, with clock and status.

## 0.3.0

- `TimeControl` floors: `turnTimeMs` at least 5000, `mainTimeMs` at least 60000.
- `MoveRequestEvent.time_limit` per clock: this turn's budget for `turn`, the remaining main time for `match`, absent for `unlimited`.
- 404 on the challenge paths also covers a challenge that is not the caller's.

## 0.2.0

- First cut of the eleven operations.
