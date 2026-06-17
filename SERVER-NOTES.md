# Server-facing notes

Decided expectations on the HeXO server that this proposal relies on but does not
itself implement. The contract (`openapi.yaml` and its parts) is the wire shape;
this file collects what that shape assumes of the server behind it, so
server-facing decisions stop living in the open-questions list. It is **not** a
spec file and is intentionally not referenced from any spec file: the contract
must read on its own.

The bot API is a **net-new server subsystem**: none of its endpoints exist today.
The server runs live play over Socket.io with bots in-process and currently
exposes only account, session, tournament, and admin routes, so everything below
is a server build, not a thin exposure of present behaviour.

This file has two sections. **Requirements** are non-negotiable consequences of
the contract: to honour the wire shape, the server must implement them. **Open
decisions for the maintainer** are where the maintainer genuinely chooses; each
carries its options and their consequences. A decision graduates from "Open
decisions" to "Requirements" in place once the maintainer settles it.

## Requirements

What the contract depends on. These are not optional if the server is to honour
the wire shape.

- **Bot endpoints as a net-new subsystem.** The register, stream, move, resign,
  status, roster, challenge, and bulk-pairing endpoints do not exist on the
  server today; they must be built. The contract is a request for this subsystem,
  not a description of present routes.
- **Auth: PAT plus three scopes.** A Personal Access Token sent as
  `Authorization: Bearer hxo_...`, carrying one of `bot:play` (gameplay),
  `bot:register` (operator registration), or `bot:organize` (bulk pairing). A
  token missing the scope an operation requires is rejected with `403`. Each
  registered instance has its own independently revocable `bot:play` token.
- **Owner link and same-owner-unrated.** Each instance carries an `owner` linking
  it to the operator credential. Same-owner games are always unrated, enforced
  server-side via that link; the contract never lets a caller set rated-ness on
  self-initiated games.
- **Server-tracked ratings.** The contract never sets a rating; the server
  computes it and echoes the authoritative value. The bot ladder uses the
  server's player rating scale, including its 1000 starting rating, so the
  rated-for-bot-only cross-play anchor stays calibrated. (Which rating *model*
  the server runs is an open decision below.)
- **Player-vs-bot rated-ness.** Player-vs-bot games are rated for the bot only:
  the bot's rating updates, the player's does not. Enforced server-side as
  pairing policy, with anti-farming mitigations: count only established players
  (low RD under the Glicko proposal), and cap gain per opponent.
- **`winningPlayerId` to `Side` mapping.** The server records a nullable winning
  account id decoupled from the finish reason; the bot surface exposes the winner
  as a `Side` (`p1`/`p2`). The server maps its `winningPlayerId` to the `Side` on
  the bot surface, and a null id surfaces as no side (for example on
  `terminated`).
- **Time-control union.** The server must accept the `TimeControl` union
  (`unlimited`, `turn`, `match`) on the challenge, echo it on the game, and reject
  an out-of-range value as `invalid-time-control`. (The bot-specific `turn` range
  is an open decision below.)
- **Opener-fairness.** Balancing who opens across a batch or tournament is
  server-side pairing policy. The contract exposes only the per-game opener
  (`firstPlayer` on a single challenge, explicit `p1` per pairing in a batch).
- **Tournament subsystem.** Pairing, standings, and rounds are the server's
  tournament subsystem. The contract's `bulk-pairing` only materializes an
  explicit, caller-supplied list of pairings; it does not compute or run any of
  that.
- **Pending-challenge expiry.** A `created` challenge that nobody accepts,
  declines, or cancels must time out: the server moves it to `expired` and emits
  a `challengeExpired` event to the parties that were notified of it. The timeout
  duration is server-set.
- **Instance retirement lifecycle.** `POST /api/bot/{handle}/retire` must
  tombstone the instance, revoke its `bot:play` token, and reserve the handle
  permanently so it is never registered again. Only the owning `bot:register`
  credential may retire an instance: a `bot:play` token is rejected
  `403 missing-scope` and a non-owning operator `403 not-owner`. Retire also
  disposes of the instance's in-flight work: every in-progress game is forfeited
  and finishes with `finishReason: surrender` and the opponent as winner, rated
  normally (so retire is not a rating-escape), and every pending challenge it
  issued or received is cleared, notifying each counterparty on its global
  stream: a challenge it issued is canceled (`challengeCanceled` to the
  challenged account) and a challenge issued to it is declined
  (`challengeDeclined` to the challenger).
- **Instance self-token revoke.** `DELETE /api/token` must revoke the `bot:play`
  token presented on the request and nothing else: never a sibling instance's
  token, never the operator's `bot:register` credential. After revoke the token
  no longer authenticates.
- **Per-bot session reads.** `GET /api/bot/games` and
  `GET /api/bot/game/{gameId}` expose the server's live-session data filtered to
  the authenticated bot's own games, reshaped from the server's
  `SessionInfo`/`LobbyInfo` into the bot surface's `GameEventInfo`/`GameFull`. A
  read scoped to a game the caller is not a player in returns `404` (no existence
  leak). These reads reuse the `winningPlayerId` to `Side` mapping above.
- **Finished-game retention.** A finished game must stay answerable while it is
  retained: a move or resign returns `409 game-finished` and the game read
  returns a `200` snapshot. The natural reap point is when both players have
  disconnected (mirroring the live-session model; a tournament game holds the
  stub briefly longer for reconciliation). Once reaped, a late move, resign, or
  read returns `404`, and the bot reconciles the terminal result from the
  `gameFinish` event, not the status code. The server may retain longer than the
  both-disconnected point, but a freshly finished game whose player is still
  connected must answer `409`/`200`, never `404`.
- **Challenge retention.** A challenge that has gone terminal (`declined`,
  `canceled`, or `expired`) must stay answerable by
  `GET /api/challenge/{challengeId}/show` for a brief window after the
  transition, so a bot can tell a just-terminal challenge from an unknown id.
  Once reaped it returns `404` like any unknown id, and the bot reconciles the
  transition from the `challengeDeclined`, `challengeCanceled`, or
  `challengeExpired` event instead.
- **Decline-reason round-trip.** The decline endpoint accepts an optional
  `reason` (one of the `DeclineReason` values, defaulting to `generic`). The
  server must persist it and surface it as `declineReason` on the declined
  `Challenge` carried by the `challengeDeclined` event; it is absent on any
  non-declined challenge.
- **Event-stream supersede.** Opening a new global event stream must close any
  previous one for the same token, so a bot reconnecting after a half-open drop
  can rely on the stale connection being dropped without tearing it down itself.
- **Stream keepalive bound.** Both NDJSON streams (global event and per-game)
  must emit a blank-line keepalive at least every 15 seconds while idle, so a
  client can set a read timeout at a small multiple of that interval to tell an
  idle-but-alive stream from a dead socket.
- **`opponentGone` emission.** The server must emit the observe-only
  `opponentGone` per-game event from its existing in-game-disconnect orphan
  timer (the auto-forfeit countdown), reporting in `finishesInSeconds` the time
  remaining until it auto-forfeits the game to the surviving side. There is no
  client claim action: the countdown is to the automatic forfeit.
- **Draw-free bot pairings.** The bot surface states the server's
  `draw-agreement` finish never appears (the `finishReason` enums omit it). The
  server does run a live `draw-agreement` path, so bot pairings must never route
  into it: a bot game never finishes as a draw.

## Open decisions for the maintainer

Where the server maintainer genuinely chooses. Settling one moves it up into
Requirements in place.

- **Rating model: Glicko (proposed) or Elo (fallback).** The server today runs
  **plain Elo** (K=30 while `gameCount` < 10, else 15; rating floor 100; start
  1000; no rating-deviation). The proposal **requests the server adopt the Glicko
  rating-deviation model** (original Glicko, not Glicko-2) for the bot ladder, so
  a rating carries opponent-weighted uncertainty (RD) and provisional status is
  derived from RD (above a threshold around 110, a Glicko-2 convention flagged to
  re-tune). Consequence of keeping Elo: it loses the opponent-weighted
  uncertainty and the RD-provisional flag, and provisional handling falls back to
  the server's existing `gameCount` < 10 K-swap. Either way the contract ships no
  rating-model field (no Glicko, RD, or provisional), so this is a server choice,
  not a wire change.
- **Bot time-control range.** The server's current `turn` floor (5000 ms) is
  tuned for players, and its current default value is 45000 ms; bots are far
  faster. The proposal asks for a bot-specific range: sub-second `turnTimeMs`, bot
  default 500 ms, 45000 ms ceiling, enforced server-side (out-of-range =
  `invalid-time-control`). This is a server change.
- **Early-game abort (proposed capability).** The server has no bot-triggered
  void/abort finish; today the only exit is `resign`, a counted surrender. The
  proposal asks for an opening-only, unrated, no-winner abort so a bot that cannot
  service a freshly started game is not force-rated a loss. The contract exposes
  no abort endpoint until the server defines the semantics.
