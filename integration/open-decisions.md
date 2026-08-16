# Open decisions

Decisions the htttx merge raises that are the maintainer's to make, not the
analysis's to close. Each carries a recommendation and the reasoning, with the
call left open. Red-team findings that could not be resolved in the plan are
folded in at the end.

## 1. Independently-usable htttx, or full merge

The layout choice from integration-options.md.

- Recommendation: keep htttx standalone under one shared org, with the play spec
  pinning it for the Capabilities object only (Option B).
- Why: the hard coupling is one slow-moving schema, not the packet set, so a
  single repo is not needed to keep `$ref`s sane. Standalone htttx keeps its
  stateless and BWS transports for analysis, sandbox, and local play (which the
  ladder never uses) and an independent alpha-to-stable cadence.
- The alternative: a full single-repo merge (Option C) is simpler operationally
  and removes cross-repo pins, at the cost of dragging engine-only socket
  schemas into an HTTP-shaped document where they trip `no-unused-components`,
  and welding the engine surface's alpha cadence to the play spec's `1.0.0`
  track. A real choice if single-repo simplicity is valued above the standalone
  transports.

## 2. Engine-facing side and coordinate convention

What the dialed socket carries, and whether the ladder's user-facing labels
should follow it.

- Recommendation: the engine seam adopts htttx native, `x`/`o` sides and
  `{ q, r }` coordinates, because that is what an htttx bot already implements
  and it keeps the engine protocol pure. The ladder's user-facing surface keeps
  `Side` as `p1`/`p2`, mapped at the platform by opener: `p1` is the opener
  (the side the origin stone belongs to) and is engine `x` (cross); `p2` is the
  other player and is `o`.
- Mapping must key off the opener, not the server's player-array index. Colour
  on the server is assigned by array index, which is independent of who opens,
  and the server default `firstPlayer` is `random`, so index 0 is not reliably
  the opener. To keep `p1`, the opener, and engine `x` always naming one side,
  the bot subsystem should resolve `firstPlayer` to a concrete player at game
  start and key all three off that. This is a small but real decision: confirm
  the bot subsystem resolves the opener deterministically rather than inheriting
  the lobby's `random` default.
- Why two conventions: after the move exchange leaves, the play spec carries no
  coordinates at all, so there is no coordinate convention left to reconcile on
  the ladder side; coordinates exist only at the engine seam, where htttx
  `{q,r}` is the natural choice. Sides do survive on the ladder (winner and
  side pointers), and `p1`/`p2` reads as opener-ordered without implying the
  engine's cross/circle colour matters to the ladder.
- The alternative: adopt `x`/`o` end to end, including on the lifecycle surface,
  for one vocabulary. This churns `Side`, `GameEventInfo`, and the
  `winningPlayerId` mapping for symmetry the ladder does not need, and it leaks
  an engine colour concept into matchmaking. The mapping is mechanical either
  way; the question is only which label the ladder shows.

## 3. Idempotency under the inverted socket: socket-kill, or a correlation id

htttx native has no move-request id. It handles desync by terminating the socket
when the heartbeat `waiting` flag disagrees with the bot's internal state. For
rated games, is socket-kill enough, or is a correlation token needed?

- Recommendation: add an optional turn-correlation token on `move_request`,
  echoed on `move_response`, in the dialed variant. The token lets the platform
  discard a `move_response` that answers a superseded request (a stale answer
  after a resync, a duplicate after a reconnect) instead of killing the socket
  and forfeiting a rated game over a transient.
- Why the token is necessary, not optional: removing this spec's `ply`
  compare-and-set leaves the system with no compare-and-set at all. The server
  has none of its own; `applyGameMove` checks only that the mover owns the turn
  and the target cell is unoccupied. Those checks reject a full duplicate (its
  cells are already occupied) and a move for the wrong turn, but they accept a
  stale-but-legal answer produced after a resync (different cells, still the
  bot's turn, still unoccupied), and within a turn the server accepts two
  placements from the same player. The token is what lets the platform bind one
  `move_response` to the `move_request` it answered and discard a superseded
  one. The full-board-per-turn choice removes board desync, but it does not
  remove this answer-matching need.
- The alternative: rely on socket-kill alone, as htttx does. Simpler, and fine
  for unrated analysis, but it converts a recoverable transient (a late or
  duplicate answer) into a lost rated game, and it cannot tell a stale-legal
  answer from a fresh one. The decision is whether to accept that for rated
  play; the recommendation is no.

## 4. Illegal-move policy for rated games: forfeit-on-illegal, or reject-and-resubmit

htttx native terminates the socket if the bot is sent or produces an illegal
position. This spec rejected an illegal placement with `422 { stone }` and a
compare-and-set retry. Which governs a rated game?

- Recommendation: the server (referee) rejects the illegal move and re-issues a
  `move_request` within the remaining turn budget. A bot that keeps producing
  illegal moves, or has no legal move it will play, simply runs out the clock
  and loses on `timeout`. The existing server clock is the bound, so no special
  illegal-forfeit finish is needed, and a transient bug gets one or more retries
  inside the budget rather than an instant rated loss.
- This is bounded under `turn` and `match` controls: the server sets the turn
  deadline once when the turn begins and resets it only when the turn flips to
  the other player, not per placement and not on a rejected move (an illegal
  move throws before any clock update), so a reissue loop cannot extend the
  clock. It is the only illegal-handling behavior the server supports today; an
  illegal placement throws and is rejected, with no game-finishing path. The one
  gap is `unlimited`, which has no deadline at all, so an illegal-spamming bot
  there is unbounded; that folds into decision 5.
- Why not forfeit-on-illegal: it is harsh for rated play (one malformed packet
  ends a rated game) and it duplicates what the clock already enforces. The
  re-issue costs the platform a second `move_request`, which the full-board
  stateless model already supports as just another request.
- The alternative: forfeit-on-illegal (htttx native), mapped to a finish reason.
  Simpler and matches htttx, but it makes the engine's correctness a
  rated-result hazard rather than a clock-bounded one, and it needs new server
  work: there is no illegal-specific `finishReason` and no server path that
  finishes a game from an illegal move today (`terminated` is produced only by
  admin termination, not gameplay). If chosen, decide which `finishReason` it
  maps to (`terminated` with a null winner, or `surrender`) and add the server
  path.

## 5. Capabilities-as-eligibility: trusting a self-declared `move_time_limit`

Surfaced by the red-team mandate. A bot could lie about `move_time_limit` to
dodge or game a time control.

- Position taken in the plan: the flag is an eligibility gate, never a rating or
  pairing input, and the authoritative server clock is the enforcement. A bot
  that declares `move_time_limit: true` to enter timed games but then overruns
  loses on `timeout`, server-judged. Declaring `false` only restricts the bot to
  `unlimited`, which is no advantage. So the flag is self-policing and does not
  need a trust mechanism.
- Open part for the maintainer: whether an `unlimited`-only bot (one that
  declares no `move_time_limit`) is allowed on the rated ladder at all, or only
  in unrated exhibitions. An unlimited rated game has no clock to bound a stall,
  confirmed in the server clock: `unlimited` mode sets the turn deadline to
  null, so no timeout is armed and the time check never fires. The only existing
  end bound is disconnect handling, which needs a dropped socket; a
  connected-but-silent dialed bot hangs the opponent indefinitely. If unlimited
  rated games are allowed, they need a new non-response bound (an abandonment
  timer that fires on a connected-but-idle bot), independent of the time
  control. This is a server pairing-policy decision the contract does not set.

## 6. `rated` ownership: a verified contradiction to reconcile

Surfaced by server-fact verification, not a merge decision, but it touches the
"server is referee" premise and should be settled in the same pass.

- Finding: the play spec asserts `rated` is referee-owned and never
  caller-settable. The server's existing human lobby contradicts this:
  `rated` is a caller-supplied lobby option that the server only gates and
  demotes (rated requires a signed-in account; demoted for tournaments, guests,
  duplicates). The server does not own the initial value today.
- Why it does not block the merge: challenge creation is KEEP, untouched by the
  htttx move-exchange swap, and the bot subsystem is net-new (none of these
  endpoints exist on the server yet). The spec is requesting referee-owned
  `rated` for bots, which is a stricter rule than the human lobby's, not a
  description of current behavior.
- Decision for the maintainer: confirm that the bot subsystem will own `rated`
  server-side (the stricter rule the contract already encodes), accepting that
  it diverges from the human lobby, or align the two. Either way the contract's
  no-caller-set-`rated` shape stays; this is about what the server implements
  behind it.

## 7. Live clock visibility for the engine

Surfaced during synthesis. The removed per-game `GameState` carried the live
clock (`time`) and status; the engine seam carries only a per-move budget
(`move_time_limit`).

- Position: an engine needs the per-move budget to play, and the dialed
  `move_request` provides it, so nothing playable is lost. A bot that wants the
  opponent's remaining clock for time strategy no longer sees it on this
  surface.
- Decision for the maintainer: accept that the engine sees only its per-move
  budget (recommended, it keeps the engine protocol clock-agnostic), or carry a
  compact clock summary on `move_request` for bots that pace by total time
  remaining. The latter adds clock state to the engine packet, which the
  full-board stateless model otherwise keeps out.

## 8. Origin opening: confirm the server auto-plays it for bot games

Surfaced by server-fact verification. The seam design assumes the server
auto-plays the (0,0) opening, which the play spec already records as resolved,
but the live server does not do it.

- Finding: the play spec's resolved design is that the server places the origin
  stone at ply 0 and the bot only ever submits two-stone turns. The live referee
  does not: `applyGameMove` requires the current player to place the origin when
  the board is empty, and the opener starts with one placement remaining, so the
  opener's first submitted turn is a single origin stone. The only auto-place is
  a frontend account preference that defaults off. So the resolved design is a
  server change for the net-new bot subsystem, like referee-owned `rated` and
  the sub-second clock, not current behavior.
- Why it matters to the seam: it sets whether an engine turn is always exactly
  two stones (server auto-plays the opening) or sometimes one (the opener's
  first turn, if the server does not). That choice fixes the `pieces` cardinality
  on the dialed move shape: `minItems`/`maxItems` of one-to-two if not
  auto-played, exactly two if auto-played. The migration plan builds for
  one-to-two so it is correct either way, but the contract example and prose
  should match whichever the server commits to.
- Decision for the maintainer: confirm the bot subsystem auto-plays the origin
  (the resolved design, recommended, it makes every engine turn uniform), or
  accept the live single-stone opening and keep the one-to-two move shape. Note
  that htttx's own `pieces` constraint is currently a no-op (`minLength`/
  `maxLength` on an array), so either way the dialed-variant PR must restate it
  with the array keywords.
