# Changelog

## 0.3.0
- `TimeControl` floors: `turnTimeMs` ≥ 5000, `mainTimeMs` ≥ 60000.
- `MoveRequestEvent.time_limit` per clock: `turn` → this turn's budget; `match` → remaining main time (increment applies after the move); `unlimited` → absent.
- 404 on the challenge paths also covers an existing id that is not the caller's; indistinguishable from unknown.

## 0.2.0
- First cut of the eleven operations.
