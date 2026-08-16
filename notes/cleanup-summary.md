# Cleanup summary: shed gameplay to the engine layer

This spec is now the **server and ladder layer** only: identity, registration,
matchmaking, challenges, ratings, and game lifecycle. The per-game move exchange
moved out to the engine protocol. The branch is `chore/shed-gameplay-to-htttx`.
The engine-protocol shape was read from a pinned reference checkout (commit
`37d2385f1016abe8b25798238a7d0c4a17a25dda`, the latest `HEAD` of
`hex-tic-tac-toe/htttx-bot-api` at the time of writing; the bridge pins the
same commit in its `pyproject.toml`); the contract itself stays self-contained
and names "the engine protocol" only conceptually.

`make lint` (Redocly + Spectral) is 0 errors, the bundle resolves, and the docs
build.

## Removed

Paths (and their root keys in `openapi.yaml`):

- `paths/game-stream.yaml` (`GET /api/bot/game/stream/{gameId}`, the per-game NDJSON stream)
- `paths/game-get.yaml` (`GET /api/bot/game/{gameId}`, the non-streaming snapshot)
- `paths/game-move.yaml` (`POST /api/bot/game/{gameId}/move`)

Schemas:

- `MoveSubmit`, `CompoundMove`, `GameState`, `GameFull`, `GameStreamEvent`

Responses:

- `Conflict` (the move-only `409 not-your-turn` / `expectedPly` path; referenced only by `game-move`)
- `Unprocessable` (the move-only `422` illegal-placement path carrying `stone`; referenced only by `game-move`). It was not on the original list but became an orphan once `game-move` was deleted, so it had to go too.

Examples:

- `examples/game-stream.ndjson` (per-game move stream sample)

Every deletion was checked against a full inbound-reference graph first: each
removed file's only inbound `$ref`s came from other removed files. `Side`,
`Variant`, `Player`, `Ok`, `GameEventInfo`, `TimeControl` are all referenced by
survivors and were kept.

## Re-homed

- **`opponentGone`** lived only on the deleted per-game stream. It is now a member
  of the global event stream union (`Event` `oneOf` + discriminator mapping). It
  gained a required **`gameId`** field, because the global stream carries every
  game the bot is in, so the disconnect countdown must name its game. Prose was
  reworded off the per-game stream ("play resumes over the engine session").

- **Terminal result (`finishReason`, `winner`, `status: finished`)** was already
  fully carried by `GameEventInfo` (via `GameFinishEvent`); nothing depended on
  `GameState` for it. What `GameState` carried that no survivor needs (the
  cumulative move list, `ply`, per-side clock, and the `started` status value) is
  gameplay/board state and was intentionally dropped. The `six-in-a-row`
  `finishReason` is kept: it is the referee's terminal-result label, not a move.

- **`Error`** kept the codes and fields other operations still return
  (`accounts` for bulk-pairing `422`, `limit` for `403 owner-instance-limit`, plus
  the generic `error`/`message`). The move-only fields **`expectedPly`** and
  **`stone`** were removed, and the move-only codes (`not-your-turn`, `occupied`,
  `wrong-stone-count`, `out-of-bounds`, `illegal-move`) were dropped from the
  `error` enum doc. The schema example was switched off `not-your-turn` to a
  surviving code (`not-accepting`).

## Capabilities ingestion shape

`engineDescription` (the old free-text cosmetic label) was replaced everywhere it
appeared (registration request, `RegisteredInstance`, `BotInstance` whoami,
`BotListing` roster) by a structured **`Capabilities`** object
(`components/schemas/Capabilities.yaml`). It mirrors the engine protocol's own
capability document:

- `meta` — name, description, authors, version, tags (human-facing label, not a capability)
- `stateless` — `versions.v1-alpha` with `api_root` (default `stateless/v1-alpha`) and `move_time_limit`
- `basic_websocket` — `versions.v1-alpha` with `api_root` (default `bws/v1-alpha`) and the feature flags (`move_time_limit`, `evaluation_time_limit`, `config.dynamic`, `free_setup`, `move_skips`, `dual_sided`, `free_move_order`, `evaluation`, `resettable_state`, `interruptible`)
- `matchmaking` — the ladder-eligibility seam (see below)

**Access pattern (a deliberate ownership flip).** In the engine protocol the bot
*hosts* its capability document and the platform reads it. Here the operator
**declares** capabilities once in the registration request body, and thereafter
the server treats the declaration as authoritative and **echoes it read-only** on
whoami and the roster. So the only caller-set point is initial declaration; every
later surface is server-authoritative and read-only. Capabilities are a label and
an eligibility marker, never a rating or pairing-strength input.

**`matchmaking` is net-new, not reused.** The engine protocol has no matchmaking
block (and the server ground truth has no matchmaking/socket/token concept either),
so this seam is owned by our ladder layer. Presence of the `matchmaking` block
marks an instance as ladder-eligible; its flags (`ladderPairing`, `bulkPairing`)
gate which pairing modes the instance opts into, eligibility only.

## Dial bootstrap (net-new, server-issued, read-only)

`gameStart` now carries a required **`engine`** object
(`components/schemas/EngineSession.yaml`): `socketUrl` (the `wss://` locator the
adapter dials) and `token` (a short-lived, per-game bearer, not a PAT and not
reusable across games). The engine protocol has no server-issued locator or
per-game token, so these are ladder-layer additions; both are server-issued and
read-only. Answer-matching (request ids) was intentionally **not** added here: it
lives in the engine seam, not this spec, which is why the `ply` compare-and-set
token and all its prose were removed.

The bootstrap lives only on `gameStart`, as scoped. The crash-recovery path stays
coherent: reconnecting the global event stream **replays a `gameStart` with a
fresh `engine` bootstrap** for every game still in progress, so a restarted
adapter re-dials its live games. `GET /api/bot/games` was reframed as a
point-in-time reconciliation read (it lists `GameEventInfo` pointers; it does not
itself carry an engine session). `challenge-accept` was reworded too: its response
returns `gameId` as confirmation, but the engine session to play arrives on the
acceptor's own `gameStart` event.

## Survivors reshaped or reworded

- `openapi.yaml` — removed the three path keys; rewrote the design paragraph
  ("server is the referee" now lists pairing/clocks/ratings/lifecycle, not
  legality/turn-order), the "Shape" section (one stream, lifecycle-here /
  gameplay-on-the-engine-session), and the "Variant & sides" section (geometry
  belongs to the engine protocol). Reworded the `Stream` tag (per-game stream
  gone) and `Bot` tag ("streaming a game, submitting moves" dropped), and added
  `capabilities` to the `Directory` tag's identity list.
- `Variant` and `Side` — pared to the variant key and `p1`/`p2` play-order
  identity; coordinates/frontier/opening/win conditions moved to the engine
  protocol.
- `GameStartEvent` (added `engine`, dropped the per-game-stream sentence),
  `GameFinishEvent` (per-game stream → engine session closed), `GameEventInfo`
  (dropped "open the per-game stream", softened "line maker" → "the side that
  won").
- `stream-event` — type list now includes `opponentGone`; replay prose explains
  the fresh-`gameStart` re-issue; added `opponentGone` example and an `engine`
  block on the `gameStart` example.
- `challenge-create` (dropped "single centre hex" and "speed is part of play"),
  `bulk-pairing` (dropped the auto-opening-hex / ply-0 detail and "open its
  stream"), `bot-retire` and `RegisteredInstance` ("gameplay authority" → "play
  authority"), `NotFound` / `ChallengeRefused` / `TooManyRequests` (move-submission
  prose pared).
- `README.md` — section 1 scope note + variant bullet; section 2 table (move /
  per-game-stream / snapshot rows removed, capabilities + engine bootstrap added,
  Play → Bot); section 3 rewritten from "How a move works" to "How a game works
  (where this spec stops)"; section 4 referee/stateless bullets reworked and a
  capabilities bullet added; quickstart line pared.
- `examples/bot-loop.md` — rewritten from the move loop to the lifecycle loop that
  stops at the engine session; `examples/event-stream.ndjson` — `gameStart` now
  carries `engine`, plus an `opponentGone` line.

## Kept as-is (not touched beyond forced rewording)

Server-authoritative fields stay non-caller-settable (`rated`, `owner`,
`rating`). Identity, challenge lifecycle, directory, bulk-pairing, retirement, and
token revoke are unchanged except where a removed schema forced a reword. No
gameplay, coordinates, or move shape were reintroduced in any form.

## Red-team outcome

An independent read-only pass found **no P0 (bundle/contract-breaking) and no P1
(semantic) issues**: no dangling `$ref` or orphan component, `make lint`
genuinely 0 errors, `opponentGone` correctly gained the `gameId` it needs on the
global stream, the "finished implies a result" `allOf` on `GameEventInfo` holds
independently of the deleted `GameState` (ajv-verified), the dial bootstrap is
correctly scoped (short-lived per-game non-PAT token, server-issued, read-only),
the crash-resync path is sound, and no referee-owned field became caller-settable.

It surfaced two P2 cosmetic items, both pre-existing on `main` (not regressions of
this branch):

- `Error.yaml`'s enum doc omitted `handle-unavailable`, a live `409` returned by
  `HandleUnavailable.yaml`. **Fixed** on this branch while the enum was already
  being reshaped.
- `README.md` links to `OPEN-QUESTIONS.md` (an out-of-band scratch doc) from the
  roadmap section, a standing self-containment-rule blemish. **Left open**: it
  pre-dates this branch and is outside the gameplay-shed scope. A maintainer
  should drop the parenthetical link while keeping the open-question sentence.

## Open items

- README → `OPEN-QUESTIONS.md` link (above), pre-existing, deliberately not
  touched here.
- The reserved-handle list in `bot-register` still contains `move` (and `game`,
  `games`, `resign`). The set is explicitly non-exhaustive and handles are
  permanent, so pruning `move` is cosmetic and was deliberately left alone to keep
  the reservation stable.
- `Capabilities` uses `additionalProperties: false` throughout (including `meta`)
  to match this repo's strict style, which is slightly tighter than the engine
  protocol's extensible `meta`. This is intentional for a contract we accept and
  echo.
