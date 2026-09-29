# Changelog

## 0.6.0
- `BotListing.liveGames`, required: the games the bot is playing now, from 0 to 4; at 4 it takes no new game, so a caller can see a busy bot before a challenge fails.

## 0.5.0
Generated from the reference server's contract; play moves off HTTP onto a per-game engine session.

Removed:
- `POST /api/bot/game/{gameId}/move` (`playMove`): moves travel on the engine session.
- `GET /api/bot/game/{gameId}` (`getGame`) and `POST /api/bot/session/{sessionId}/join` (`joinSession`).
- `GET /api/bot/challenges` (`listChallenges`): pending challenges replay on the stream as it opens.
- `thinkMs` on challenges.
- `Player.profileId` and `Player.displayName`; `Opening.randomTurns` and the `opening` object.

Added:
- `GET /api/bot/game/{gameId}/socket` (`openEngineSession`): htttx basic_websocket v1-alpha, the server as client and the bot as bot; `gameStart.engine` carries its `socketUrl` and a game token.
- `gameStart.rated` and `gameStart.openingPlies`.
- `POST /api/bot/game/{gameId}/resign` (`resignBotGame`) authenticates with the game token.
- `requestId` on `createChallenge`: resending one answers 200 with the stored challenge.
- 403 `banned` and `delisted`, and 503 `paused` with `Retry-After`, where they apply.
- `BotListing.ownerName`, `online`, and `openForChallenges`.
- Players are `{name, rating, provisional}`.

Changed:
- A challenge names its target by bot name: `POST /api/bot/challenge/{name}`.
- `openingPlies` is one of 1, 3, 5, 7, 9, the origin included, default 5; an opening with a lopsided six-window is redrawn whole.
- `version` caps at 64 characters and `repoUrl` at 2048; the declaration body is strict, so an unknown key answers 400.
- A bot playing here must support the bws `move_skips` and `request_id` capabilities.

## 0.4.2
- `BotListing` carries the declaration's text fields (`about`, `version`, `repoUrl`) beside `accepts`, each absent when never declared: one public read serves a bot's whole profile.

## 0.4.1
- `Opening.randomStones` (0–6 stones) is `Opening.randomTurns` (0–3 turns of two stones) before anything implemented it: stones come in pairs after the origin, so an odd count left a half turn no engine could answer, and "0 to 6, even" is a rule hidden in a comment. Same reachable openings, expressed in the game's unit.

## 0.4.0
- `PATCH /api/bot/account` (`updateAccount`): the bot declares `about` (≤ 280), `version`, `repoUrl`, and `accepts` — what it will play under; a challenge outside `accepts` answers `not-open`. `Account` reads the declaration back, `BotListing` carries `accepts`.
- `createChallenge` gains `thinkMs` (required for a server-driven target, ignored otherwise) and `opening: {randomStones}` (0–6 server-placed stones after the origin); `gameStart` carries `opening`.
- `GET /api/bot/game/{gameId}` (`getGame`): the board as an htttx `Board`, plus clock and status, for observers and adapters.

## 0.3.0
- `TimeControl` floors: `turnTimeMs` ≥ 5000, `mainTimeMs` ≥ 60000.
- `MoveRequestEvent.time_limit` per clock: `turn` → this turn's budget; `match` → remaining main time (increment applies after the move); `unlimited` → absent.
- 404 on the challenge paths also covers an existing id that is not the caller's; indistinguishable from unknown.

## 0.2.0
- First cut of the eleven operations.
