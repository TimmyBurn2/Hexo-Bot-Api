# Cleanup-2 summary: htttx reconcile and server-requirement founding

This pass (branch `chore/shed-gameplay-to-htttx`, same branch as cleanup-1)
reconciles the play spec against the updated htttx engine spec and founds the
invented server mechanisms that cleanup-1 left as asserted behavior.

The htttx reference used: the `htttx-forfeit-eligibility` branch of
`hex-tic-tac-toe/htttx-bot-api`, read from `Work/Hexo/htttx-bot-api`.

`make lint` (Redocly + Spectral) is 0 errors, the bundle resolves, and the docs
build.

## 1. Matchmaking reconciliation: one source per fact

**Problem.** Cleanup-1 wrote a `matchmaking` block in `Capabilities.yaml` with
`ladderPairing` and `bulkPairing` flags. The htttx spec independently grew a
`MatchmakingCapability` carrying `versions.v1-alpha.honors_move_time_limit`.
These were two incompatible shapes under the same key: the play spec's
`additionalProperties: false` would reject a real htttx Capabilities document
that had a `versions` key.

**Resolution.** The `matchmaking` block in `Capabilities.yaml` now mirrors the
htttx `MatchmakingCapability` exactly (`versions.v1-alpha.honors_move_time_limit`).
A new **`ladder`** block holds the play-spec-owned pairing opt-in flags
(`ladderPairing`, `bulkPairing`) and is the sole ladder-eligibility marker.
Presence of `ladder` (not `matchmaking`) tells the server to enter the instance
into ladder pairing.

**Result: one source per fact.**

| Fact | Owner | Block |
|---|---|---|
| Engine honours per-move time limit | htttx engine spec | `matchmaking.versions.v1-alpha.honors_move_time_limit` |
| Instance entered into ladder pairing | play spec | `ladder.ladderPairing` |
| Instance accepts bulk pairings | play spec | `ladder.bulkPairing` |

Files changed: `Capabilities.yaml`, `BotInstance.yaml`, `BotListing.yaml`,
`RegisteredInstance.yaml`, `bot-register.yaml` (description + both examples).

## 2. additionalProperties: false loosened on ingested blocks

**Problem.** Cleanup-1 applied `additionalProperties: false` throughout
`Capabilities.yaml`, including on `meta` and on the transport-version objects.
The htttx protocol leaves `meta` open for extension and uses `x-`-prefixed
extras in config; the strict ingestion would reject real htttx documents.

**Resolution.** `additionalProperties: false` is removed from every block that
mirrors the htttx engine protocol: the top-level `Capabilities` object, `meta`,
`stateless`, `basic_websocket`, and the new `matchmaking` block. It is **kept**
on `ladder` only, which is wholly play-spec-owned and has no htttx counterpart.
Unknown fields in the ingested blocks are tolerated (ignored), not rejected.

The top-level `Capabilities` description now states this explicitly: "unknown
fields within them (including `x-`-prefixed extensions and any future htttx
additions) are tolerated so that real htttx Capabilities documents pass through
without rejection."

## 3. Forfeit-on-illegal result

**Decision.** An illegal move forfeits the offending side. The game finishes
with `finishReason: illegal-move` and the opponent as `winner`.

**Why a new value, not a reused one.** The server's current `finishReason` enum
(`disconnect`, `surrender`, `timeout`, `terminated`, `six-in-a-row`,
`draw-agreement`) has no value that means "engine submitted an illegal move and
lost." `terminated` comes closest but today means no winner. Silently reusing it
would misrepresent a decisive result as a null-winner result. A new
`illegal-move` value avoids the ambiguity.

**Server requirement.** `illegal-move` is not in today's server enum. Adding it
is a net-new server requirement. The server currently handles an illegal move
non-fatally (error message, socket stays open, no result assigned). The required
behavior: end the game, record `finishReason: illegal-move`, set opponent as
winner, emit `gameFinish` on the global stream. Recorded in `SERVER-NOTES.md`.

Files changed: `GameEventInfo.yaml` (added `illegal-move` to `finishReason`
enum, updated `winner` description).

## 4. Server requirements founded (invented mechanisms reframed)

Cleanup-1 asserted four behaviors the server does not have. Each is now recorded
in `SERVER-NOTES.md` as a requirement, not current behavior.

**Engine session bootstrap.** `gameStart` carries `engine.socketUrl` (absolute
`wss://` URL) and `engine.token` (short-lived, per-game, non-PAT). The server
has no engine session or token concept today. Requirement: server must generate
both per game and emit them in `gameStart`. The `socketUrl` is specified as
absolute so a third-party host can issue its own.

**Reconnect re-emits `gameStart` with a fresh engine bootstrap.** The contract
states the server replays in-progress games as `gameStart` events on reconnect.
This is a net-new server requirement. Open item recorded: an alternative is a
distinct `gameResume` event type if reusing `gameStart` for resumption creates
ambiguity. The maintainer must align on which approach before implementing.

**Engine transport and `request_id` answer-matching.** The adapter dials the
engine over the websocket path. On that path, `request_id` is required and
answer-matching is in force (per the htttx engine spec). The stateless HTTP path
is not the rated play path. Requirement recorded in `SERVER-NOTES.md`; the
detail lives in the htttx engine spec.

## 5. Host-agnostic note

One sentence added to the `servers:` entry in `openapi.yaml`: "The entry above
is the reference host; this contract is implementable by any host. Per-server
identity and rating federation are non-goals for this version."

## 6. README cleanup

Removed the parenthetical link to `OPEN-QUESTIONS.md` from section 6 while
keeping the open-question sentence. (`OPEN-QUESTIONS.md` is an out-of-band
scratch doc; the link violated the self-containment rule noted in cleanup-1.)

## Open items

- **Reconnect design choice.** Reusing `gameStart` for resumption vs. a distinct
  `gameResume` event is unresolved. Recorded as an open item in `SERVER-NOTES.md`.
  No change to the contract until the maintainer decides.
- **`illegal-move` server implementation.** The new `finishReason` value requires
  a server-side change. Blocking on server maintainer alignment.
- Pre-existing open items from cleanup-1 (rating model, bot time-control range,
  early-game abort) are unchanged.
