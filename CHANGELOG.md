# Changelog

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
