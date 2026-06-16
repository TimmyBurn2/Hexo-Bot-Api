# Server-facing notes

Decided expectations on the HeXO server that this proposal relies on but does not
itself implement. The contract (`openapi.yaml` and its parts) is the wire shape;
this file collects what that shape assumes of the server behind it, so
server-facing decisions stop living in the open-questions list. It is **not** a
spec file and is intentionally not referenced from any spec file: the contract
must read on its own.

This is a starting point, not a full migration. Only the items below are routed
here; the open-questions list still holds the rest.

## Expectations

- **Time control.** The server must accept fine-grained, sub-second `turnTimeMs`
  for bot games (bot default 500 ms, 45000 ms ceiling), enforce the range, and
  reject out-of-range values as `invalid-time-control`.
- **Ratings.** Server-tracked via Glicko (the original Glicko, not Glicko-2)
  using rating-deviation (RD); the contract never sets a rating. The bot ladder
  uses the server's player rating scale, including its 1000 starting rating, so
  the rated-for-bot-only cross-play anchor stays calibrated. RD-based provisional
  status is computed server-side (see the provisional sliver in
  `OPEN-QUESTIONS.md`).
- **Player-vs-bot rated-ness.** Player-vs-bot games are rated for the bot only:
  the bot's rating updates, the player's does not. Enforced server-side as
  pairing policy, with anti-farming mitigations: count only established low-RD
  players, and cap gain per opponent.
- **Opener-fairness.** Balancing who opens across a batch or tournament is
  server-side pairing policy. The contract exposes only the per-game opener
  (`firstPlayer` on a single challenge, explicit `p1` per pairing in a batch).
- **Tournament subsystem.** Pairing, standings, and rounds are the server's
  tournament subsystem. The contract's `bulk-pairing` only materializes an
  explicit, caller-supplied list of pairings; it does not compute or run any of
  that.
