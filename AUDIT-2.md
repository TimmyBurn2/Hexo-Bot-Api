# HeXO Bot API: scoped re-audit of the three recent passes

Read-only re-sweep of the surface touched by the three edit passes that followed
the clean-sweep audit (`AUDIT.md`). No spec file was modified; the only new file
is this report. Method: five grounded track agents in parallel (A regression and
conditionals, B enum/status/lifecycle, C new-surface fidelity, D authority/abuse,
E doc consistency), each forbidden to edit, reconciled by the lead against an
independent read of every touched file plus the server source. Every claim is a
concrete `file:line` (spec or `server:path:line`) or a captured command result.

Severity: **blocker** (resolve before `1.0.0` of the proposal), **bug** (a real
defect a conformant client/server hits), **gap** (missing surface or
under-specification), **nit** (polish). `(server impl)` marks a server build
requirement, not a spec defect.

## Where the passes actually live (read this first)

- **Pass 1** (contract correctness + gap-fills) is commit `a5d3f36`, merged to
  `main` (PR #12).
- **Pass 2** (rating reframe, turnTimeMs fidelity, SERVER-NOTES split) is commit
  `2be825c`, merged to `main` (PR #13). `main` HEAD is `bdf684c`.
- **Pass 3** (read and identity surface) is **NOT on `main`**. It is five commits
  on the unmerged remote branch `origin/feat/read-and-identity-surface`
  (`346b8f3`, `24beb30`, `b281b9f`, `f74876e`, `ac3befe`, HEAD `ac3befe`), based
  exactly on current `main` (`merge-base == bdf684c`).

This audit was run against a read-only worktree of `ac3befe`, which stacks all
three passes cleanly, because that is the only place the Pass 3 content exists.

## Verdict

The three passes are high quality and the content largely lands clean. Pass 1's
conditionals are correct and lint stays green; Pass 2's rating and time-control
reframe is consistent across every doc; Pass 3's new endpoints are honestly
framed, fully wired into the event union, routing-safe, and free of
cross-tenant leaks. The single most important issue is integration, not content:
**Pass 3 is unmerged**, so on `main` none of the read/identity surface exists. The
content issues to fix before `1.0.0` are all small and concentrated in the
interaction between Pass 3's new `expired` lifecycle and the older
challenge-lifecycle prose: the accept/decline/cancel 404-reconcile text was never
updated to mention `challengeExpired`, the `not-owner` code is missing from the
`Error` registry, three new `bot:play` endpoints omit the `403` the rest of the
contract declares, retire is silent on what happens to a live game, and
SERVER-NOTES does not record Pass 3's new server obligations. None are blockers
for the contract's well-formedness; the merge state is the only blocker for
"repo ready."

---

## Integration state (blocker for "repo ready", not a content defect)

- **[blocker] Pass 3 is not merged to `main`.** `git rev-parse origin/main` =
  `bdf684c`; the read/identity commits live only on
  `origin/feat/read-and-identity-surface` (`ac3befe`). On `main` today there is no
  `GET /api/bot/games`, `GET /api/bot/game/{gameId}`, `GET /api/challenges`,
  `POST /api/bot/{handle}/retire`, `DELETE /api/token`, `ChallengeExpiredEvent`,
  or `Challenge.status: expired`; the reserved-word additions and the
  `challengeExpired` bot-loop case are also branch-only. **Action:** land the
  branch (after the fixes below) or the entire Pass 3 surface is absent from the
  proposal. Everything in Tracks C and D and the Pass-3 parts of B and E assumes
  this branch is the intended state.

## Track A: regression and conditional correctness (LANDED CLEAN)

- **[confirmed clean] Lint is 0 errors, 0 warnings.** `make lint` exits 0;
  Redocly reports "valid" with no warnings; Spectral on
  `dist/openapi.bundled.yaml` reports no error/warn/hint/info. Independently
  reproduced by the lead.
- **[confirmed clean] Bundle resolves; no orphans.** `make bundle` succeeds,
  `no-unresolved-refs` and `no-unused-components` pass. All six pass-introduced
  components are referenced: `ChallengeExpiredEvent` (`Event.yaml:12,21`),
  `ForbiddenRetire` (`bot-retire.yaml:41`), `GameFinished` (`game-resign.yaml`),
  `BulkPairingUnprocessable` (`bulk-pairing.yaml`), `InvalidTimeControl`
  (`challenge-create.yaml`), `ForbiddenRegister` (`bot-register.yaml`).
- **[confirmed clean] The finished-implies-result `if`/`then` behaves exactly as
  intended** on GameState, GameEventInfo, and the GameState embedded in GameFull
  (26/26 ajv 2020-12 assertions against the bundle). It rejects
  `{status: finished}` with no `finishReason`/`winner` on all three surfaces;
  rejects `{status: started, winner: p1}` (the inverse branch exists,
  `GameState.yaml:94-106`); accepts the legitimate finished shapes including
  `winner: null`; accepts a started/ongoing shape; and correctly accepts a
  GameEventInfo `gameStart` line (no `status`) while rejecting a `gameStart`
  carrying a stray `winner`/`finishReason` (`GameEventInfo.yaml:73-83`, written as
  `if not required:[status]` because that surface's `status` enum is `[finished]`
  only). Negative controls confirm the passes are not vacuous.
- **[confirmed clean] The `redocly.yaml` rule disable is correctly scoped.**
  `no-required-schema-properties-undefined` is the only rule the passes turned off
  (`/tmp/pass1.diff`); the other `off` (`no-ambiguous-paths`) is pre-existing.
  Every property named in any `if`/`then`/`not`/`required` block is declared on
  its parent's `properties` (`status`/`finishReason`/`winner` on both GameState
  and GameEventInfo; GameFull has no conditional of its own). The disable masks no
  genuinely-undefined property.
- **[confirmed clean] Every touched example validates** against its schema:
  the `{gameId}` accept body, the bulk-pairing `422 invalid-pairing` (with
  `accounts`) and `invalid-time-control` bodies, the `ChallengeExpiredEvent`
  example, and the new bot-games / game-get / challenges 200 examples.
- **[confirmed clean, explains a Track A cross-check note] `409 game-finished` is
  wired on both move and resign, via two response objects.** `game-move.yaml:73-74`
  routes 409 to `Conflict.yaml`, which documents both `not-your-turn` and
  `game-finished` (`Conflict.yaml:15-17`, with a `gameFinished` example at
  `:29-33`); `game-resign.yaml` routes 409 to the dedicated `GameFinished.yaml`
  (resign has only the one case). Both use the same `Error` schema and the same
  `error: game-finished` code, so a client branching on `error` sees identical
  behaviour. Functional and consistent; not a defect.

## Track B: enum, status and lifecycle coherence

- **[bug] The accept/decline/cancel 404-reconcile prose omits `expired` and
  `challengeExpired`.** `challenge-accept.yaml:12-15`, `challenge-decline.yaml:10-13`,
  and `challenge-cancel.yaml:8-10` all enumerate the non-pending precondition as
  "already been accepted, declined, or canceled" and (for accept/decline) tell the
  bot to reconcile "from the `challengeDeclined` or `challengeCanceled` event."
  Pass 3 (`f74876e`) made `expired` a reachable terminal state
  (`Challenge.yaml:47-53`) with its own producer event `challengeExpired`
  (`ChallengeExpiredEvent.yaml`). So accepting/declining a challenge that just
  expired now returns `404`, and the bot is pointed at two events that never fire
  for an expiry; the correct event (`challengeExpired`) is missing from the list,
  and `expired` is missing from the precondition enumeration. **Action:** add
  `expired` to the precondition list and `challengeExpired` to the reconcile-event
  list in all three files.
- **[nit] `Challenge` top-level description under-lists where a Challenge
  appears.** `Challenge.yaml:4-6` says it "Appears inside `challenge` and
  `challengeDeclined` events." A Challenge is embedded in four events:
  `challenge`, `challengeDeclined`, `challengeCanceled` (pre-existing omission),
  and `challengeExpired` (Pass 3 widened the gap). **Action:** list all four or
  generalize to "the challenge lifecycle events."
- **[confirmed clean] `accepted` is gone from `Challenge.status` everywhere.**
  `Challenge.yaml:49-53` enum is `created/declined/canceled/expired`; no `accepted`
  survives in any enum or example. The transition note (`Challenge.yaml:43-48`)
  reads cleanly and matches the reachable set, and every status has a producer
  (decline endpoint, cancel endpoint, server-timeout + `challengeExpired`).
- **[confirmed clean] `started` is gone from `GameEventInfo.status`.**
  `GameEventInfo.yaml:38-39` enum is `[finished]` only; the field is absent on
  gameStart and `finished` on gameFinish; no example carries `status: started`.
- **[confirmed clean] The terminal 409-vs-404 boundary is consistent.** Move
  (`Conflict.yaml`), resign (`GameFinished.yaml`), and `NotFound.yaml` all agree
  that a finished-but-extant game is `409 game-finished`, an unknown id is `404`.
  The new `GET /api/bot/game/{gameId}` is consistent with this: a read of a
  finished game returns `200` (a snapshot), and an unknown or not-yours id returns
  `404` (`game-get.yaml:8-9,68-69`). No `409` on a read is correct.
- **[confirmed clean] `winner` nullability is coherent across prose, schema, and
  conditional.** Prose: null on `terminated`, may be null on `disconnect`
  (`GameState.yaml:73-78`, `GameEventInfo.yaml:51-56`). Schema: `oneOf [Side, null]`
  in both. Conditional: `winner` is in `then.required` on finish, so it is
  required-but-nullable, never merely absent, and cannot be a non-null Side on a
  non-finished state.

## Track C: new-surface fidelity and grounding honesty (CLEAN)

- **[gap] (server impl) The `winningPlayerId -> Side` mapping, the whole p1/p2
  side abstraction, the session reshape, and the per-bot filtering are net-new
  server work, not existing fields.** The server stores
  `winningPlayerId: zIdentifier.nullable()` (an account id, not a side) at
  `server:packages/shared/src/sharedTypes.ts:532`, has no p1/p2 concept (only
  `firstPlayer`, which can be `random`, `:108,:119`), and exposes `GET /sessions`
  / `GET /session/:id` as **public, unauthenticated, return-everything** reads
  (`server:packages/backend/src/network/rest/createApiRouter.ts:237,247`) whose
  shapes (`LobbyInfo`/`SessionInfo`) differ substantially from
  `GameEventInfo`/`GameFull`. `bot-games.yaml:10-17` and `game-get.yaml:4-9`
  honestly frame themselves as the bot's filtered "slice/projection" (they state
  they filter to the bot's own games), so there is no overclaim; but the side
  derivation, the reshape, and the filtering are all server build requirements.
  **Action:** record as `(server impl)`; no spec change required (the
  `Side.yaml:13-17` "assigned by the server from play order" note already covers
  the assignment story).
- **[confirmed clean] Net-new surface honestly disclaims server backing.**
  `challenges.yaml:11-13` says outright "This is bot-protocol surface, not a server
  read: challenges are this contract's own concept (the server has no challenge
  object)." `bot-retire.yaml`, `token.yaml`, `Challenge.status: expired`, and the
  expiry note (`challenge-create.yaml:24-30`) all frame expiry/retire/token as a
  requested server behaviour or a bot-protocol concept, never as something the
  server already does.
- **[confirmed clean] `ChallengeExpiredEvent` matches `ChallengeCanceledEvent`
  field-by-field and is fully wired.** Same envelope (`type` const + `challenge`
  $ref, same `required`, same `additionalProperties: false`). Present in the Event
  `oneOf` (`Event.yaml:12`), in the discriminator mapping (`Event.yaml:21`), in the
  stream docs and example (`stream-event.yaml:14,95-117`), and in the bot loop
  (`bot-loop.md:22`).
- **[confirmed clean] Path routing is safe and reserved words cover every new
  literal.** `{gameId}` cannot swallow `stream`/`move`/`resign` (different path
  structures); `{handle}` cannot collide with `game`/`games`/`status`/`register`
  because those are reserved handles; `challenge` (singular) and `challenges`
  (plural) are distinct first segments. The reserved-word list
  (`bot-register.yaml:37-42`) explicitly includes `games`, `challenges`, `retire`,
  and `token`, plus `game`, `move`, `resign`, `register`, `stream`, `event`, etc.
- **[confirmed clean] Lichess parity is sane.** `listMyGames` mirrors
  `GET /api/account/playing`, `listChallenges` mirrors `GET /api/challenge`
  (`in`/`out` split), `revokeToken` mirrors `DELETE /api/token` narrowed to
  self-only. Divergences are deliberate.

## Track D: authority, abuse and races on the new surface (well-designed)

- **[gap] Retire is silent on what happens to a retired instance's live games and
  pending challenges.** `bot-retire.yaml:5-18` covers tombstoning, token
  revocation, and permanent-handle reservation, but never says whether in-progress
  games are forfeited, resigned, left to time out, or whether retire is even
  allowed while a game is live; nor whether pending incoming/outgoing challenges
  are canceled (and counterparties notified). This is an abuse surface: an operator
  could retire an instance to escape a losing live game with unspecified rating
  consequence. The server already has leave/disconnect/turn-timeout handling to
  hook into. **Action:** state the consequence (forfeit live games and cancel
  pending challenges with the usual events, or reject retire while live games
  exist). `(server impl for enforcement; spec defect for the silence.)`
- **[nit] The `not-owner` error code is missing from the `Error` registry.**
  `ForbiddenRetire.yaml:23,28` and `bot-retire.yaml:17` emit `error: not-owner` on
  a `403`, but `Error.yaml:14-19` lists the 403 codes as
  `forbidden / missing-scope / owner-instance-limit` and omits `not-owner`. The
  spec tells clients to "branch on `error`" (`Error.yaml:23`), so the canonical
  list should be complete. **Action:** add `not-owner` to the 403 group in
  `Error.yaml`.
- **[confirmed clean] No privilege-escalation path.** A `bot:play` token cannot
  retire itself or a sibling (`bot-retire.yaml:13-16`, `ForbiddenRetire.yaml:6-9`)
  and cannot register (`bot-register.yaml:14-18`); the minted per-instance token
  carries `bot:play` only, so it never reaches operator authority.
- **[confirmed clean] `DELETE /api/token` is structurally self-only.**
  `token.yaml:4-11` revokes "the token presented on this request," takes no
  path/body parameter, and explicitly never touches a sibling or the operator's
  `bot:register` credential; the self-revoke vs operator-retire distinction is
  drawn and non-overlapping.
- **[confirmed clean] `403 owner-instance-limit` and `429` stay distinct.** Hard
  per-owner cap (`403`, code `owner-instance-limit`, echoes `limit`,
  `ForbiddenRegister.yaml`, `Error.yaml:60-68`) vs transient rate limit (`429`,
  code `rate-limited`, `Retry-After`). The `limit` echo is the operator's own cap
  only (`Error.yaml:65-67`) and leaks nothing.
- **[confirmed clean] No cross-tenant visibility on the new reads.** `bot-games`
  returns "only the games this instance is currently a player in, never another
  bot's games" (`bot-games.yaml:10-12`); `game-get` returns the game only to a
  participant, otherwise `404` (no existence leak, `game-get.yaml:7-9`,
  `NotFound.yaml`); `challenges` is scoped to the caller's `in`/`out`
  (`challenges.yaml:5-6,38-46`).
- **[confirmed clean] Bulk pairing is genuinely all-or-nothing and names
  offenders.** "Every pairing is checked before anything is created... the whole
  batch is rejected with `422 invalid-pairing`: no games are created"
  (`bulk-pairing.yaml`), offending ids returned in the `accounts` field
  (`BulkPairingUnprocessable.yaml:24-27`, `Error.yaml:48-59`). No partial-batch
  ambiguity.

## Track E: doc consistency after the reframe (consistent)

- **[gap] (server impl) Pass 3's new server obligations are not recorded in
  SERVER-NOTES, and the retire model is still filed as deferred.** Pass 3 did not
  touch `SERVER-NOTES.md` (confirmed: empty diff between the branches for that
  file), yet it adds four server requirements that the wire now depends on:
  challenge-expiry timeout (`Challenge.yaml:47-48`, `ChallengeExpiredEvent.yaml:5-8`),
  retire lifecycle including disposition of live games/pending challenges
  (`bot-retire.yaml`), self-token revoke (`token.yaml`), and per-bot session-read
  scoping (`bot-games.yaml`, `game-get.yaml`). Meanwhile `SERVER-NOTES.md:91-96`
  still lists "Token lifecycle / instance retirement (model, endpoint deferred)"
  under **Open decisions**, saying "The contract endpoint for this is deferred to a
  later pass" - but Pass 3 is that later pass and ships the endpoint. **Action:**
  graduate retirement from Open decisions to Requirements and add the four new
  requirements. `(doc gap to flag, not a contract defect.)`
- **[confirmed clean] The rating reframe is consistent everywhere.** No doc
  asserts Glicko/RD as current server behaviour; Elo is stated current
  (`SERVER-NOTES.md:70-71`, `OPEN-QUESTIONS.md:77-78`), Glicko proposed, Elo the
  fallback (`SERVER-NOTES.md:70`, `OPEN-QUESTIONS.md:80,137`); README defers to
  OPEN-QUESTIONS; CLAUDE.md makes no rating claim. No rating field leaked into the
  contract (no `elo`/`glicko`/`rd`/`deviation`/`provisional` field anywhere;
  `provisional` is explicitly "not added to the contract in this pass").
- **[confirmed clean] turnTimeMs default-vs-ceiling is identical across files.**
  500 ms bot default / 45000 ms ceiling, with the server's current 45000 ms value
  and 5000 ms player floor framed as the thing being changed, consistent across
  `CLAUDE.md:44`, `OPEN-QUESTIONS.md:19-22`, `README.md:135-139`,
  `SERVER-NOTES.md:81-85`, `openapi.yaml:48-50`, `TimeControl.yaml:9-12,48,52`. The
  prior-audit "default 45000" remnants in CLAUDE.md and OPEN-QUESTIONS are gone.
- **[confirmed clean] The SUPERSEDED design note is neutralized.** The top banner
  (`docs/design/bot-discovery-and-registration.md:3-16`) and the section-5 inline
  banner (`128-133`) cover the stale endpoint names, the dropped
  wallclock/fixedsim + Bradley-Terry/WHR estimator split, and the
  unrated-exhibition-vs-rated-for-bot-only reversal. No lingering decision reads as
  current.
- **[confirmed clean] The spec is fully self-contained.** No spec file
  (openapi.yaml, paths, components, examples) references OPEN-QUESTIONS,
  SERVER-NOTES, README, the design note, issue numbers, branch names, or pass
  numbers, including every new Pass 3 file.

---

## Regressions and issues introduced by the recent passes (highest-value list)

Sorted by severity. These are problems the passes created or left, distinct from
the pre-existing items in `AUDIT.md`.

1. **[blocker] Pass 3 is unmerged.** The read/identity surface exists only on
   `origin/feat/read-and-identity-surface`, not on `main`. Integration state, not a
   content defect, but it gates "repo ready."
2. **[bug] `challengeExpired` reconcile gap.** Pass 3 added `expired` without
   updating the accept/decline/cancel non-pending prose
   (`challenge-accept.yaml:12-15`, `challenge-decline.yaml:10-13`,
   `challenge-cancel.yaml:8-10`).
3. **[gap] Retire mid-game disposition undefined.** New `bot-retire.yaml` is silent
   on live games and pending challenges (`bot-retire.yaml:5-18`).
4. **[gap] (server impl / doc) SERVER-NOTES not updated for Pass 3.** New
   obligations absent; retirement still filed as "endpoint deferred"
   (`SERVER-NOTES.md:91-96`).
5. **[nit] `not-owner` missing from the `Error` registry.** Used by
   `ForbiddenRetire.yaml` but absent from `Error.yaml:14-19`.
6. **[nit] `403` not declared on three new `bot:play` endpoints.**
   `bot-games.yaml`, `challenges.yaml`, and `token.yaml` each state they require
   `bot:play` yet omit the `403` response that every other scope-requiring op
   declares (`bot-status`, `game-move`, `game-resign`, `game-stream`,
   `stream-event`, and the Pass-3 sibling `game-get` all declare it; `account` and
   `bots` correctly omit it because they need no scope). Even within Pass 3 this is
   inconsistent: `game-get` declares `403`, its siblings do not. For `token.yaml`
   there is an added semantic tension - "Requires `bot:play`" plus "a token can
   revoke only itself" leaves it unclear whether self-revoke should require
   `bot:play` or work for any token. **Action:** add `403` (Forbidden) to
   `bot-games`/`challenges`/`token` for consistency, and clarify `token.yaml`'s
   scope intent. (Lead cross-check finding, grounded in a per-path 403/scope
   tabulation.)
7. **[nit] `Challenge` description under-lists its embedding events**
   (`Challenge.yaml:4-6`), a gap Pass 3 widened by adding `challengeExpired`.

## Confirmed clean (touched areas, do not re-check next time)

- Lint is 0 errors / 0 warnings; bundle resolves; no orphan components (Track A).
- The finished-implies-result conditional is correct on GameState, GameEventInfo,
  and GameFull-embedded (26/26 ajv), and the `redocly.yaml` disable is scoped to
  exactly one rule and masks nothing (Track A).
- Every example the passes touched validates against its schema (Track A).
- `409 game-finished` is wired on both move (via `Conflict.yaml`) and resign (via
  `GameFinished.yaml`) with the same code (Track A/B).
- `accepted` is fully removed from `Challenge.status`; `started` is removed from
  `GameEventInfo.status` (Track B).
- `winner` nullability is coherent across prose, schema, and conditional (Track B).
- The terminal `409`-vs-`404` boundary is consistent across move, resign,
  NotFound, and the new game read (Track B).
- `ChallengeExpiredEvent` matches `ChallengeCanceledEvent` and is fully wired
  (oneOf, discriminator, stream docs, bot loop); the `expired` status is fully
  wired (Track C/A).
- Path routing is safe; the reserved-word list covers `games`, `challenges`,
  `retire`, `token`; `challenge` and `challenges` are distinct (Track C).
- The new read endpoints honestly frame themselves as a filtered slice, and the
  net-new endpoints disclaim server backing (Track C).
- No privilege-escalation path; `DELETE /api/token` is self-only;
  `owner-instance-limit` (403) and `rate-limited` (429) are distinct and the
  `limit` echo leaks nothing; the new reads are caller-scoped with no existence
  leak; bulk pairing is all-or-nothing and names offenders (Track D).
- The rating reframe (Elo current / Glicko proposed / Elo fallback), the
  turnTimeMs default-vs-ceiling story, and the spec's self-containment are
  consistent across all docs and the spec; the SUPERSEDED design note is
  neutralized (Track E).

## Server build requirements surfaced by Pass 3 (not spec defects)

- Derive a deterministic `p1`/`p2` side identity (the server has only
  `firstPlayer`, which can be `random`) and map `winningPlayerId` (an account id)
  to a `Side`.
- Reshape `SessionInfo`/`LobbyInfo` into `GameFull`/`GameEventInfo` and filter the
  currently-public `/sessions` and `/session/:id` reads to the authenticated bot's
  own games.
- Implement a pending-challenge expiry timeout that moves a `created` challenge to
  `expired` and emits `challengeExpired`.
- Implement retire lifecycle: tombstone, revoke the `bot:play` token, reserve the
  handle forever, enforce `bot:register`-owns / `403 not-owner`, and define the
  fate of live games and pending challenges.
- Enforce all three scopes and the owner link (none exist server-side today).
