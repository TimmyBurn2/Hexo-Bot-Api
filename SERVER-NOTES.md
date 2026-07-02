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

- **Bot endpoints as a net-new subsystem.** The register, stream, resign,
  status, roster, challenge, and bulk-pairing endpoints do not exist on the server
  today; they must be built. The contract is a request for this subsystem,
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
- **Active-games read.** `GET /api/bot/games` exposes the server's live-session
  list filtered to the authenticated bot's own in-progress games, reshaped from the
  server's `SessionInfo`/`LobbyInfo` into the bot surface's `GameEventInfo` pointers.
  It never reports another bot's games. This read reuses the `winningPlayerId` to
  `Side` mapping above.
- **Finished-game retention.** A finished game must stay answerable while it is
  retained: a resign returns `409 game-finished`. The natural reap point is when
  both players have disconnected (mirroring the live-session model; a tournament
  game holds the stub briefly longer for reconciliation). Once reaped, a late
  resign returns `404`, and the bot reconciles the terminal result from the
  `gameFinish` event, not the status code. The server may retain longer than the
  both-disconnected point, but a freshly finished game whose player is still
  connected must answer `409`, never `404`.
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
- **Stream keepalive bound.** The global event stream must emit a blank-line
  keepalive at least every 15 seconds while idle, so a client can set a read
  timeout at a small multiple of that interval to tell an idle-but-alive stream
  from a dead socket.
- **`opponentGone` emission.** The server must emit the observe-only
  `opponentGone` line on the global event stream (carrying the affected `gameId`)
  from its existing in-game-disconnect orphan timer (the auto-forfeit countdown),
  reporting in `finishesInSeconds` the time remaining until it auto-forfeits the
  game to the surviving side. There is no client claim action: the countdown is to
  the automatic forfeit.
- **Draw-free bot pairings.** The bot surface states the server's
  `draw-agreement` finish never appears (the `finishReason` enums omit it). The
  server does run a live `draw-agreement` path, so bot pairings must never route
  into it: a bot game never finishes as a draw.
- **Forfeit-on-illegal: `illegal-move` as a new `finishReason` value.** The
  htttx engine protocol exposes detection of illegal moves (wrong placement
  count, occupied cell, out-of-radius, wrong side, post-win, first-not-origin,
  and on the websocket path an out-of-id response); the play layer owns the
  rated result. An illegal move must forfeit the offending side: the game
  finishes with `finishReason: illegal-move` and the opponent as `winner`. This
  `finishReason` value does not exist in the server's current enum
  (`disconnect`, `surrender`, `timeout`, `terminated`, `six-in-a-row`,
  `draw-agreement` from `sharedTypes.ts`). It must be added as a new value;
  silently reusing an existing reason whose server meaning differs (such as
  `terminated`, which has no winner today) is not permitted. The current server
  behavior on an illegal move is non-fatal: the placement throw is surfaced as
  an error message and the socket stays open with no result assigned
  (`gameSimulation.ts`, `sessionManager.ts`, `createSocketServer.ts`). The
  server must change to: detect the illegal move, end the game, record
  `finishReason: illegal-move` with the opponent as winner, and emit the normal
  `gameFinish` event on the global stream.
- **Per-game engine session bootstrap.** The `gameStart` event carries an
  `engine` object with `socketUrl` and `token` that the adapter uses to dial
  the engine session. Both fields are **server-issued and read-only**; a caller
  never sets them. The server must: (a) for each started game, generate a
  per-game engine session locator and a short-lived bearer token; (b) emit
  `socketUrl` as an **absolute** `wss://` (or `ws://`) URL so a third-party
  host can issue its own; (c) ensure `token` is scoped to this one game, is not
  a Personal Access Token, and expires with the game. The server has no engine
  session or token concept today; this is a net-new server requirement.
- **Reconnect re-emits `gameStart` with a fresh engine bootstrap.** When the
  global event stream is opened (or reopened after a drop), the server must
  re-emit a `gameStart` carrying a fresh `engine` dial bootstrap for each game
  still in progress, so a restarted adapter can re-dial its live games without
  a separate recovery call.
- **Engine transport: websocket path, with optional `request_id` answer-matching.**
  The adapter dials the engine over the `socketUrl` websocket. Answer-matching
  via `request_id` is a bot-side opt-in: a bot that declares
  `basic_websocket.v1-alpha.request_id` (or `stateless.v1-alpha.request_id`) echoes
  the platform-assigned id unchanged on its response and can then detect and drop a
  mismatched or stale answer before submitting it. Without the flag, answers are
  matched only by the transport's own request/response ordering, so a transient that
  yields a mismatched or stale response has no correlation guard and is submitted
  as-is. Either way the play layer holds the bot responsible: a wrong, stale, or
  mismatched move forfeits the game as `illegal-move`, with no undeserved-forfeit
  exemption. `request_id` is the bot's tool to avoid that; it does not shift the
  responsibility. The stateless HTTP path carries the same optional `request_id`
  for correlation; it is not the rated play path. These transport details belong to
  the engine protocol layer; they are noted here because the play spec
  (EngineSession) points to that session as the gameplay path.

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
- **Resume event type.** Reconnect currently reuses `gameStart` to re-emit each
  in-progress game with a fresh engine dial bootstrap. If reusing `gameStart` for
  resumption proves ambiguous against a genuinely new game start, a distinct
  `gameResume` event type is the alternative. Undecided; align with the server
  maintainer before the contract adds a separate event.
