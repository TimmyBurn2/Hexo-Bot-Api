# Migration plan (recommended: one org, sibling repos)

File-level plan for moving the per-game move exchange to htttx packets and
ingesting the htttx Capabilities object at registration, with htttx kept as a
sibling spec pinned for the one shared schema. This is the plan, not a change;
nothing here is applied in this pass.

## 1. Play-spec files removed

The per-game move exchange and everything that only served it.

Paths:
- `paths/game-stream.yaml` (the per-game NDJSON stream)
- `paths/game-get.yaml` (the per-game `GameFull` snapshot read)
- `paths/game-move.yaml` (the compound-move submit endpoint)

Schemas (orphaned once the three paths go):
- `components/schemas/MoveSubmit.yaml`
- `components/schemas/CompoundMove.yaml`
- `components/schemas/GameState.yaml`
- `components/schemas/GameFull.yaml`
- `components/schemas/GameStreamEvent.yaml`

Responses:
- `components/responses/Conflict.yaml` (only `game-move` used it)

Examples (stale after the move exchange leaves):
- `examples/game-stream.ndjson`
- `examples/bot-loop.md` rewritten, see section 6

## 2. Play-spec files changed (re-home, do not delete)

These hold KEEP-worthy fields that travelled inside the removed gameplay
schemas. The fields move; the schemas around them go.

- `paths/stream-event.yaml` and `components/schemas/Event.yaml`: add
  `opponentGone` as a member of the global event stream union. Today
  `OpponentGoneEvent` rides only the per-game stream, which is being removed.
  Presence and the auto-forfeit countdown are a lifecycle and referee concern,
  not an engine one, so the signal belongs on the global stream. Move
  `components/schemas/OpponentGoneEvent.yaml` from the per-game union to an
  `Event.yaml` member; keep its `finishesInSeconds` and observe-only semantics.
- `components/schemas/GameStartEvent.yaml`: net-new surface for the dialed
  model. Today `gameStart` is a pointer; under the inverted socket the bot must
  learn where to dial and how to authenticate the engine socket for this game.
  Add the connection-bootstrap fields (the engine-socket URL and a short-lived
  per-game socket token) here, so the bot reads `gameStart` from the global
  stream and dials the engine socket. This is a second coupling the
  integration-options "one shared schema" framing understates: the Capabilities
  schema crosses the repo boundary, but the dial bootstrap is net-new play-side
  surface that neither repo defines today. It lives on the play side in every
  layout option.
- `components/schemas/GameFinishEvent.yaml` and
  `components/schemas/GameEventInfo.yaml`: confirm `finishReason` and `winner`
  (as `Side`) live here, since `GameState` carried a second copy and `GameState`
  is being removed. No new field, just the surviving home for the terminal
  result.
- `components/schemas/Error.yaml`: prune the move-exchange-only fields and
  codes. Remove `expectedPly` and `stone`, and the codes `not-your-turn`,
  `occupied`, `wrong-stone-count`, `out-of-bounds`, `illegal-move`. Their only
  producer was `game-move`. Keep the envelope and every lifecycle code.
- `components/schemas/Side.yaml`: keep the `p1`/`p2` enum; strip the ply-0 and
  coordinate prose, which is now engine-protocol territory. Side remains the
  ladder's opener-ordered side label, used by `GameEventInfo` and the `winner`
  fields.
- `components/schemas/Variant.yaml`: keep the `httt6` key (it stays the
  matchmaking and identity constant; htttx has no variant field). Thin the
  frontier, win-rule, and opening prose down to a short descriptive line; the
  normative rules now live in the engine protocol.
- `components/responses/Unprocessable.yaml`: survives via `bulk-pairing`. Drop
  its `occupied`/`stone` example, which is now irrelevant to its only remaining
  referent.
- `paths/game-resign.yaml`: KEEP, unchanged. After the move exchange leaves,
  resign is the one remaining per-game HTTP control, so the prose rewrite below
  must not imply every per-game action moved to the socket. Its `409
  game-finished` response (`components/responses/GameFinished.yaml`) stays.
- `openapi.yaml`: drop the three removed path `$ref`s; reword the root
  `description` and the `Bot` and `Stream` tag descriptions that mention
  streaming a game and submitting moves; document the engine handoff in prose
  (the move exchange happens on the dialed engine socket; resign and the game
  reconcile reads stay on this HTTP surface).

## 3. Play-spec files adapted: Capabilities ingestion at registration

The ADAPT seam. `engineDescription` (free-text label) is replaced by the htttx
Capabilities object; `hardware` stays as orthogonal telemetry.

New file:
- `components/schemas/Capabilities.yaml`: the htttx Capabilities object, pinned
  from the htttx repo (submodule path or vendored copy). It is `meta` plus the
  per-transport feature-flag blocks. The play spec references it; it does not
  redefine it.

Changed:
- `paths/bot-register.yaml`: in the request body, remove the `engineDescription`
  string and add `capabilities: $ref ../components/schemas/Capabilities.yaml`.
  Keep `hardware: $ref ../components/schemas/HardwareInfo.yaml`. The bot submits
  its Capabilities here, since under the dialed model it does not host
  `capabilities.json` for the platform to fetch.
- `components/schemas/BotInstance.yaml`: replace `engineDescription` with
  `capabilities` (read-only echo of what was registered). Keep `hardware`.
- `components/schemas/BotListing.yaml`: same swap, so the roster shows
  `capabilities.meta` (name, description, authors, version, tags) instead of a
  free-text label.
- `components/schemas/RegisteredInstance.yaml`: flows the echo back through the
  embedded `BotInstance`; update the example.
- `paths/account.yaml`: whoami returns the echoed `capabilities` via
  `BotInstance`; update the example.
- `components/schemas/Player.yaml`: unchanged shape. It carries only `hardware`,
  not `engineDescription`, so it is untouched by the swap. Decide separately
  whether the gameplay-adjacent `Player` should ever surface `capabilities.meta`
  (it does not need to).

Capabilities as matchmaking eligibility, never as a rating or pairing input:
- `move_time_limit` is the one ladder-relevant flag. It is a per-transport
  boolean: it lives inside each transport's `versions` block, so the eligibility
  gate must read it from the dialed-socket transport the bot actually plays on,
  not from the stateless or BWS analysis transports a bot may also declare. A
  bot declaring it there is eligible for `turn` and `match` time controls; a bot
  that does not is matched only into `unlimited`, or timed challenges to it are
  refused. This is an eligibility gate, identical in spirit to the existing
  label-only stance: it gates which games a bot is offered, it does not feed the
  rating or the pairing strength estimate.
- The other htttx flags (`free_setup`, `dual_sided`, `free_move_order`,
  `evaluation`, `resettable_state`, `interruptible`, `config`,
  `evaluation_time_limit`) are analysis-transport features the ladder ignores.
  The migration should record, in the `bot-register` prose, which flags the
  ladder reads and that the rest are descriptive.
- Variant stays the play spec's field. Capabilities carries no variant, so the
  challenge still names `httt6` via `Variant.yaml`.

## 4. The adapter seam: coord and side mapping

The seam sits in the platform (the referee server plus the inverted-socket
front), between the server's internal model and the engine-facing packets. The
engine never sees referee-owned state; only the per-move inputs cross.

Coordinates:
- Server stores `{ x, y }` integers; htttx packets use `{ q, r }` integers; this
  spec used `[q, r]`. All three are the same axial scheme. The mapping is a pure
  rename with no arithmetic: `q = x`, `r = y` outbound to the engine, and
  `x = q`, `y = r` inbound from `move_response.pieces`. The hex-distance,
  adjacency, and radius-8 logic are identical under the rename, so no geometry
  is recomputed at the seam.

Sides (map by opener, not by array index):
- The server has no side token. Colour is assigned by player-array index, which
  is independent of who opens, so array index is not the side source. The opener
  is resolved separately, and the server default `firstPlayer` is `random`, so
  the opener can be either array index. Mapping the engine side to "array index
  0" would disagree with the opener whenever `random` seats index 1 first.
- Map the engine side to the opener: the opener is `x` (cross, the side the
  fixed origin stone belongs to), the other player is `o`. This matches htttx,
  where `free_setup:false` makes the one opening stone a cross. The platform
  tells the bot its side on every `move_request` via the `side` field, derived
  from whether the bot is the referee's resolved starting player. The bot never
  sees player ids.
- The ladder's user-facing `Side` stays `p1`/`p2`, with `p1` defined as the
  opener (the side the opening belongs to, as `Side.yaml` already states), not
  as array index 0. The `winningPlayerId -> Side` mapping the server already
  does is unchanged, and a null `winningPlayerId` (for example on `terminated`)
  stays a null side. The winner never crosses to the engine; it surfaces only on
  the lifecycle stream. For `p1`, the opener, and engine `x` to always name the
  same side, the bot subsystem should resolve `firstPlayer` to a concrete player
  at game start and key all three off that, never off the colour index. Whether
  the ladder should also adopt `x`/`o` is an open decision, not resolved here.

The opening (a server-change dependency, not a current fact):
- The play spec's resolved design is that the server auto-plays the origin (0,0)
  stone for bot games, so the bot never submits it and every engine turn is a
  full two-stone move. Under that design the platform hands the engine a setup
  that already contains the opening cross, the engine's first `move_request` is
  the first two-stone turn, and this matches htttx's `free_setup:false` default.
- That is a server change, not current behavior. The live referee makes the
  opener submit the origin as a single-stone first turn: `applyGameMove` requires
  the current player to place (0,0) when the board is empty, and
  `initializeGameState` starts the opener with `placementsRemaining` 1 (2
  thereafter); the only auto-place is a frontend account preference defaulting
  off. So the seam depends on the server adopting the auto-play rule the play
  spec already records as resolved. Treat it as a requirement on the bot
  subsystem, surfaced in open-decisions.md.
- Fallback if the server keeps current behavior: the opener's first engine turn
  is a single stone at the origin, so the dialed move shape must allow one or
  two pieces, not exactly two (see below). Either way the engine never chooses
  the opening square; it is the fixed origin.

Two stones per turn:
- A normal turn is two coordinates in `move_response`. htttx does not actually
  constrain this: its `pieces` arrays use `minLength`/`maxLength`, which are
  string keywords and no-ops on a JSON-Schema array, so the "exactly 2"
  guarantee is vacuous in the current htttx schema. The dialed-variant PR must
  use `minItems`/`maxItems`, and the count must be one-or-two, not a fixed two,
  so the single-stone opening turn is representable when the server does not
  auto-play the origin. The platform applies the pieces as the turn. This
  preserves httt6's compound move with no new schema in the play spec.

Time units:
- The play-spec clock is milliseconds (`turnTimeMs`, `mainTimeMs`,
  `incrementMs`); htttx time fields are seconds. The platform converts. For
  `turn` mode the per-move limit is `turnTimeMs / 1000`. For `match` mode there
  is no per-move sub-budget on the server: the deadline is the mover's whole
  remaining clock, and the increment is added server-side after the move
  completes, so the limit sent to the engine is the mover's remaining clock in
  seconds, not remaining-plus-increment. The engine receives one deadline, not
  the full clock; a bot that paces by total time left does not see it on this
  surface (see open-decisions.md). The dialed-variant PR should state the unit
  explicitly to avoid a 1000x error.

## 5. The htttx-side change, framed as a PR against htttx

The inverted socket is a new transport variant of htttx: same packets, flipped
listener. Today both htttx transports have the bot as listener (stateless hosts
`/turn`, BWS hosts `/game`). The ladder needs the bot to dial out so a
self-hosted bot behind NAT can play. The PR adds a dialed transport, it does not
fork the packet vocabulary.

The PR should contain:

1. A new capability block, sibling to `stateless` and `basic_websocket`, for the
   dialed transport (name it for the direction, for example `dialed_socket`).
   Its `versions` map mirrors the BWS one. It reuses `setup`, `move_request`,
   `move_response`, and `heartbeat`. It does not require `eval`, `config`,
   `dual_sided`, `free_setup`, `interruptible`, or `free_move_order`; those stay
   analysis-only and may be absent.

2. The flipped connection lifecycle: the bot opens the socket to a
   platform-provided URL and authenticates outbound; the platform then drives
   `move_request` down the socket and reads `move_response` back. Endpoint
   discovery and auth are out of band (handed to the bot by the play spec at
   game start, not via a hosted `capabilities.json`). State this explicitly,
   since htttx today assumes the platform fetches `capabilities.json` from the
   bot.

3. Full-board-per-turn semantics for the dialed variant, taken from htttx's
   stateless model rather than BWS deltas. Each `move_request` carries the full
   board (the referee already holds it), so the bot keeps no per-game state, a
   dropped request self-heals on the next one, and there is no delta-after-setup
   desync to reconnect around. Use the stateless `Board` shape, which carries
   `to_move`; the BWS `Board` has only `cells` and no turn marker, so reusing it
   would leave whose-turn ambiguous once a single-stone opening makes
   stone-count parity unreliable. The `move_request.side` field is the
   authoritative turn signal regardless. This trades a few bytes per turn (httt6
   boards are sparse within radius 8) for statelessness. Constrain the dialed
   move shape's `pieces` with `minItems`/`maxItems` (one-or-two, per section 4),
   not the no-op `minLength`/`maxLength` htttx currently uses.

4. Time units: keep seconds in the packet (htttx convention) and note that the
   driving platform converts from its own clock. Or, if htttx prefers, add a
   units note to the time fields. Either way it must be unambiguous.

5. Desync and idempotency for rated games: htttx native is socket-kill on a
   `waiting`-flag mismatch with no correlation id. The dialed variant should add
   a turn-correlation token on `move_request`, echoed on `move_response`, so the
   platform can discard a `move_response` that answers a superseded request
   instead of killing the socket. Treat this as necessary, not optional, for
   rated play: removing this spec's `ply` compare-and-set leaves the server with
   no compare-and-set of its own (`applyGameMove` checks only turn-owner and
   occupancy). Those checks reject a full duplicate (its cells are now occupied)
   and a move for the wrong turn, but not a stale-but-legal answer produced after
   a resync, which is exactly what the token catches. See open-decisions.md
   section 3.

6. The interrupt packet: htttx references `interruptible` and an interrupt
   packet but defines no schema for it. The dialed variant does not need
   interruptibility for the ladder, so the PR can leave it out of the dialed
   capability and, separately, file the missing-schema gap against the BWS
   transport.

## 6. Examples and docs

- Replace `examples/game-stream.ndjson` with an engine-socket sample: a setup
  carrying the opening cross at the origin, a `move_request` with `side` and the
  full board, and a `move_response` with two `{q,r}` pieces.
- Rewrite `examples/bot-loop.md` so the loop is: read the global event stream
  for `gameStart`, dial the engine socket for the game, answer `move_request`s,
  and reconcile the terminal result from the global `gameFinish` event. The
  live per-ply board view (old `GameState`) is gone from this surface; the bot
  sees the board on the engine socket and the result on the lifecycle stream.

## 7. Lint and bundle check after the change

- `no-unused-components` must pass: confirm the orphan list in section 1 is
  fully removed and that `Side`, `Variant`, `Error`, `Ok`, `Unprocessable`,
  `NotFound`, `Forbidden` still have at least one live referent (they do, via
  KEEP paths).
- `make bundle` must resolve `Capabilities.yaml` through the pin (submodule path
  or vendored file) with no remote fetch in CI.
- `make lint` must be 0 errors before any commit, per the repo gate.
