# HeXO Bot API: clean-sweep audit

Read-only audit of the OpenAPI 3.1 contract in this repo (a PROPOSAL layered on the
HeXO server at `hexo.did.science`). Cross-checked against the server source
(`github.com/WolverinDEV/infhex-tic-tac-toe`, cloned read-only) and the Lichess
Bot/Board API and Glickman's original Glicko paper where they sharpen a finding.
No spec files were modified.

Method: nine grounded track agents in parallel plus an adversarial verification
pass (29 of 30 defect-class findings held under scrutiny; the one refuted is
downgraded below), reconciled against a full independent read of every path,
schema, response, and example by the lead. Every claim is grounded in a concrete
`file:line` (spec or server) or a cited source.

`make lint` is clean (Redocly valid; Spectral reports no errors). The contract is
internally well-formed and self-contained. Almost everything below is design
coherence, server fidelity, or build-readiness, not lint.

Severity: **blocker** (must resolve before `1.0.0` or a build), **bug** (a real
defect a conformant client/server hits), **gap** (missing surface or
under-specification), **nit** (polish). `(server impl)` marks an item that is a
server build requirement, not a spec defect, because the bot API is unbuilt.

---

## Summary

Overall health: the contract is **clean, consistent, and unusually well
documented** for a proposal. Lint passes, the discriminated unions and examples
all validate, the ply/opening/win-line model exactly mirrors the server, and the
hardest design questions (server-owned `rated`, the openForChallenge staleness
race, owner-linkage privacy) are handled thoughtfully. The real exposure is in
two places: (1) the rating and time-control story the docs tell does not match
the server that exists, and (2) a cluster of terminal-state and challenge-lifecycle
edges the wire leaves undefined.

The single largest fact: **none of the bot endpoints exist server-side**. The
server runs live play over Socket.io with bots in-process (`packages/bot-worker`);
`createApiRouter.ts` exposes only account/session/tournament/admin routes. This is
expected (the README says "not yet implemented"), but it means the contract is a
**net-new server subsystem**, not a thin exposure of present behavior, and
SERVER-NOTES understates that.

### Top 5 to fix first

1. **Rating model contradicts the server (blocker).** The contract's docs
   (SERVER-NOTES, OPEN-QUESTIONS) build an entire original-Glicko + rating-deviation
   + RD-provisional model. The server implements plain **Elo** (`eloHandler.ts`:
   `K=30` if `gameCount<10` else `15`, floor 100, no RD). Only the 1000 start
   matches (`eloRepository.ts:28`). Either re-spec to Elo or mark Glicko as an
   explicit server replacement. The contract itself stays Glicko-free, which is
   correct; the docs do not.

2. **`turnTimeMs` is rejected by the server it targets (blocker).** The spec sets
   `turnTimeMs` default 500, min 1, max 45000 (`TimeControl.yaml:44-54`). The live
   server's game-creation validator requires `min(5000).max(120000)`
   (`createApiRouter.ts:96-98`), so every sub-5s value, including the headline
   500ms bot default, is hard-rejected today. The docs also disagree with each
   other (see F-4). Reconcile and add a bot game path.

3. **`winner` can be null on `disconnect`, but the spec forbids it (bug).** The
   server finishes a double-disconnect with `finishSessionLocked('disconnect',
   winningPlayer?.id ?? null)` (`sessionManager.ts:889-892`), i.e. null winner. The
   spec says winner is null "only on `terminated`" (`GameState.yaml:68-73`). A
   strict bot reading `winner` as a side on a `disconnect` finish breaks.

4. **The wire does not enforce "finished implies a result" (gap).** `GameState`
   and `GameEventInfo` leave `finishReason`/`winner` optional with no conditional,
   so `{status:finished}` with neither validates, and `{status:started, winner:p1}`
   validates too (ajv-confirmed). Add an `if/then`.

5. **Terminal and challenge-lifecycle races collapse to 404 (gap).**
   move/resign-after-finish, accept-after-cancel, double-accept all return a generic
   404 indistinguishable from a bad id, and there is no challenge-expiry surface.
   Define `409 game-finished` / a non-pending `409` carrying terminal status, and a
   challenge expiry.

---

## Track A: contract correctness & governance

Lint-clean; these are things lint cannot catch.

- **[gap] `GameState`/`GameEventInfo` allow a finished state with no result, and a started state with a winner.** `GameState.yaml:4-9,47-76` (finishReason/winner documented "present only when finished" but not `required`, no `if/then`); ajv confirms both contradictory shapes validate. A bot has no schema guarantee a finished line carries its result. Add `allOf: if {status const finished} then required:[finishReason, winner]` (and the inverse) on both schemas. Self-describing without a server change.
- **[gap] `createBulkPairing` declares no response for a pairing naming a nonexistent or non-bot account.** `bulk-pairing.yaml:51-67` (p1/p2 are account ids) vs `:135-142` (only 401/403/422-time-control/429). Every other account/game-resolving op declares 404. Add a 404 or a distinct 422 `unknown-account`, and state batch semantics (all-or-nothing vs partial).
- **[nit] `Player` is the only object schema without `additionalProperties:false`.** `Player.yaml:1-7` vs all 17 other object schemas (e.g. `BotInstance.yaml:14`). It is the most widely embedded object; the looseness reads as an oversight. Add it or state why it is an extension point.
- **[nit] `wrong-stone-count` (422) is structurally unreachable.** `game-move.yaml:21`, `Error.yaml:18` vs `MoveSubmit.yaml:18-19` (`stones` fixed at `minItems/maxItems: 2`). A wrong count fails body validation first. Keep as belt-and-suspenders but say so, or drop the code.
- **[nit] `GameEventInfo.status` enum lists `started`, which never appears there.** `GameEventInfo.yaml:33-40`: gameStart omits status, gameFinish is always `finished`. Dead enum value.
- **[nit] `out-of-bounds` error code fights the "unbounded board" framing.** `Error.yaml:18`, `Unprocessable.yaml:1`, `Variant.yaml:23`. The board is explicitly unbounded; the rejection is out-of-frontier (radius 8). Consider `out-of-frontier`. Consistent today, just self-contradictory naming.
- **[confirmed clean]** All 13 operations have a unique `operationId`, summary, root-declared tag, a 2xx and a 4xx; no security overrides. Every one of 22 schema examples and 14 inline examples validates (ajv against the bundle), including the `winner:null` terminated cases and all three `TimeControl` branches. No orphan/unused components. The ply model reconciles across `Side`/`GameState`/`GameFull`/`MoveSubmit`/`CompoundMove` (no off-by-one). Scopes are prose + 403 because http-bearer cannot carry scopes (same limitation Lichess accepts); 403 coverage is consistent and the two no-scope ops correctly omit it.

## Track B: NDJSON & example integrity (not linted)

- **[gap] No `turn`-mode or `unlimited`-mode stream example; only `match` is shown.** `examples/game-stream.ndjson:1-7`. `turn` is called the server default (`TimeControl.yaml:9`) yet is never demonstrated, and `unlimited`'s `time` values are left undefined (see D-4). Add both examples.
- **[nit] The `match` example never makes the increment visible.** `game-stream.ndjson:1-7`: every side loses exactly 500ms/turn with `incrementMs:2000`, which is equally consistent with "spent 2500, gained 2000" and "spent 500, no increment". Pick non-uniform spends (or a turn that spends less than the increment so the clock rises) so the one behavior distinguishing `match` is shown.
- **[nit] `bot-loop.md` switch omits the `challengeCanceled` case.** `bot-loop.md:16-20` handles challenge/gameStart/gameFinish/challengeDeclined but not the fifth event type (`Event.yaml`, `stream-event.yaml:14`). A bot tracking a received challenge will not react to its cancellation.
- **[nit] Example ratings 1500/1480 evoke the explicitly-rejected 1500 default.** Pervasive across `examples/*` and `Player/Challenge/GameFull/BotInstance/BotListing/...`. The docs anchor new bots at 1000 and reject Glickman's 1500 (`OPEN-QUESTIONS.md:91-93`, `SERVER-NOTES.md:20`). Re-base near 1000 (e.g. 1012/996) or show one unrated bot with `rating` absent to demonstrate the optional-absent case.
- **[confirmed clean]** Every NDJSON line checks out: `ply == moves.length`; ply-0 opening is a single stone at `[0,0]`; every later turn is exactly 2; sides alternate (p1 even, p2 odd) matching `bot-loop.md:47`; clocks decrement only for the side that moved; the first `gameFull` carries the opening at `ply:1` with p2 to move; the win is a real 6+-in-a-row along the server's `[1,0]` axis; keepalive blank lines and the 409/422/429 handling match the response schemas.

## Track C: server fidelity (mirror / invent / diverge / duplicate)

Most of these are `(server impl)` because the divergence is "the server does not do
this yet". See the build checklist for the pure "does not exist" items.

- **[blocker] (server impl) Rating model diverges: Glicko/RD vs Elo.** `SERVER-NOTES.md:18-23`, `OPEN-QUESTIONS.md:90-133` assert original Glicko with RD and an RD-derived provisional flag. Server is Elo, no RD: `eloHandler.ts:22-51`, `zPlayerRating={eloScore,gameCount}` (`sharedTypes.ts:483-487`). The provisional mechanism also mismatches: spec gates on `RD>~110`, server swaps K-factor on `gameCount<10` (`eloHandler.ts:6,49`). Only the 1000 start matches. Reconcile to Elo or treat Glicko as a server replacement; do not present Glicko as current server behavior.
- **[blocker] (server impl) `turnTimeMs` 500/1..45000 is invented and rejected by the server.** `TimeControl.yaml:44-54` vs `createApiRouter.ts:96-98` (`turnTimeMs.min(5000).max(120000)`) and `DEFAULT_LOBBY_OPTIONS turnTimeMs=45000` (`sharedTypes.ts:112-120`, a literal value, not a ceiling). The server has no 500ms default, a 5000ms floor (not min 1), and no `invalid-time-control` range rejection. Add a bot game path that accepts sub-second values; fix the `minimum:1` vs server-floor mismatch.
- **[bug] (server impl) `winner` is a side, but the server records a nullable account id, decoupled from `finishReason`.** `GameState.yaml:68-76`, `GameEventInfo.yaml:52-59` vs `sharedTypes.ts:579,532` (`winningPlayerId: zIdentifier.nullable()`, `reason` separate). The spec assumes a server-side `winningPlayerId -> side` translation that does not exist (the server emits an id). Flag the mapping as server work, or carry the account id.
- **[bug] (server impl) Move model diverges: 2-stone CAS-ply POST vs single-cell Socket.io.** `MoveSubmit.yaml`, `game-move.yaml` vs `createSocketServer.ts:480-485` (`place-cell`, one `{x,y}` cell), `applyGameMove` (`sharedTypes.ts:331-372`, no ply, no compare-and-set). The stateless cumulative-moves + CAS-ply wire is invented; the server's natural error is `GameRuleError`, not `409 {expectedPly}` / `422 {stone}`. New endpoint + error mapping required.
- **[bug] (server impl) Compound-turn atomicity is unspecified, and the bot loop silently depends on it.** `applyGameMove` pushes the first cell before validating the second (`sharedTypes.ts:348-380`), one placement per call. `bot-loop.md:69-71` resubmits both stones at the same ply on a 422, which is only correct if a 422 places neither stone. `Unprocessable.yaml:5` returns a single offending stone. Declare in `game-move.yaml`/`MoveSubmit` that a two-stone turn is applied atomically (422 places neither, ply unchanged), and require the server move endpoint to be one transaction.
- **[bug] (server impl) Identity model diverges and is unenforceable today.** `BotInstance.yaml:17-40`, `bot-register.yaml:27-48` (handle `^[a-z0-9_]{3,20}$`, opaque `owner`, per-instance PAT, reserved words) vs `zNormalizedUsername` 2-32 chars allowing spaces/unicode (`sharedTypes.ts:668-675`) and Discord-OAuth `AccountProfile` (`:738-749`). No owner/operator/handle/PAT/scope/reserved-word concept exists server-side, so "same-owner games always unrated" cannot be enforced. Reconcile the namespaces and build the link.
- **[gap] Coordinate representation diverges (intentional).** `[q,r]` arrays (`CompoundMove.yaml:26-38`, `MoveSubmit.yaml:11-26`) vs server `{x,y}` objects (`sharedTypes.ts:13-16`). Mathematically equivalent (`q=x, r=y`; `getHexDistance` matches). Keep `[q,r]` for compactness but state the equivalence so the adapter is wired correctly.
- **[gap] (server impl) `Side` p1/p2 is a derived abstraction, not a server field.** `Side.yaml:22-24` vs server `firstPlayer host|guest|random` (`sharedTypes.ts:52`) + player ordering driving alternation (`:363-368`). `firstPlayer:random` (the default) means p1/p2 is known only after the server resolves the opener. Document the derivation; the `SERVER-NOTES` opener-fairness note is consistent.
- **[gap] (server impl) `rated` is server-owned on the challenge surface (good), but the server's lobby `rated` is caller-set and `bulk-pairing` reintroduces a caller value.** `Challenge.yaml:30-36`, `GameFull.yaml:43-47` (read-only, correct) vs `zLobbyOptions.rated` caller-settable (`sharedTypes.ts:104-108`) and `bulk-pairing.yaml:70-76` (organizer-requested default, OPEN-Q #8 still open). The "force same-owner to false" guarantee has no implementation (depends on the missing owner link).
- **[confirmed clean]** The `finishReason` set is a faithful draw-free subset of the server's six reasons (drops only `draw-agreement`). The auto-played single-stone opening at origin, two placements per turn, radius-8 frontier, and 6-in-a-row win all mirror the server exactly (`botInterface.ts:35-38`, `sharedTypes.ts:5-6,317,348-378`).

## Track D: design coherence, abuse, races, privacy

- **[bug] `winner` can be null on `disconnect`.** `sessionManager.ts:889-892` finishes `('disconnect', winningPlayer?.id ?? null)` when `connectedPlayers.length <= 1` (0 means both gone). Spec says null winner only on `terminated` (`GameState.yaml:68-73`, `GameEventInfo.yaml:52-59`). Broaden the prose: winner MAY be null on `disconnect` (no surviving side). The schema `oneOf [Side, null]` already permits it; only the description is wrong.
- **[gap] move/resign-after-finish has no terminal code: only generic 404.** `game-move.yaml:54-65`, `game-resign.yaml:26-33`, `NotFound.yaml`. A finished game still exists, so collapsing "game over" into 404 is ambiguous with a bad id, and a bot cannot tell it lost the resign/move race to a six-in-a-row or timeout. The server's finish is idempotent (`sessionManager.ts:914-918`), so this is purely a missing wire code. Add `409 game-finished` (or 410) and state in `NotFound.yaml` that a finished-but-extant game is not 404.
- **[gap] accept/decline define no non-pending path; canceled/declined/already-accepted all become 404.** `challenge-accept.yaml:18-34`, `challenge-decline.yaml:42-58` vs `challenge-cancel.yaml:8-10` (which does document the not-pending -> 404 transition). Accepting a challenge the challenger canceled a millisecond earlier is indistinguishable from a typo'd id, and the accept-vs-cancel race winner is undefined. Add a 409 carrying the terminal `challenge.status`, or document that any non-pending challenge returns 404 and the bot reconciles via the challengeCanceled/challengeDeclined event.
- **[gap] `time` is required on every `GameState` including `unlimited`, with undefined values there.** `GameState.yaml:4-9,26-46` (time required, p1/p2 required non-negative ints) vs `:31` ("not enforced under unlimited"). No rule for what value to send: 0? a constant? A bot that reasons about the clock sees a meaningless number, and there is no clean "no clock" representation. Make `time` nullable/omittable under unlimited, or define a fixed non-decrementing sentinel.
- **[gap] The CAS-ply "idempotent" claim is overstated.** `game-move.yaml:10-12` calls the write "idempotent, safe to retry". A retry of a successful submit sends a now-stale ply and gets `409`, not `200` (the prior write applied). That is retry-safe but not idempotent; a bot may treat the 409 as failure. Reword to "retry-safe (no double-apply)" and have `Conflict.yaml` note that a 409 after a retry can mean the prior submit already landed (re-read the stream / trust `expectedPly`).
- **[gap] `409 not-your-turn` conflates three races under one code.** `game-move.yaml:16-19`, `Conflict.yaml`. Stale ply, duplicate, and "structurally the opponent's turn" all map to `not-your-turn` + `expectedPly`. With 2-stone turns, `expectedPly` alone does not say whether that ply is the bot's or the opponent's, so blindly resubmitting at `expectedPly` can loop. Add a whose-turn hint, or document that the bot must wait for the next `gameState` whose ply is `expectedPly` and whose side-to-move is this bot.
- **[gap] (server impl) No per-owner instance cap in the contract; the blessed fleet pattern is an unbounded Sybil flooder.** `bot-register.yaml:7-8` invites "call it repeatedly to run a fleet", `BotInstance.yaml:8` "one operator may run many instances", and each instance seeds onto the ladder (`BotInstance.yaml:41-48`), but nothing bounds the count. Caps live only in prose (`docs/design/...:182-183`, `OPEN-QUESTIONS.md:199-201`). A server built strictly to this spec has zero registration-time Sybil resistance. Add a contract-visible cap refusal (e.g. `403 owner-instance-limit` with the limit) or at least state the server enforces a per-owner cap and which status it returns.
- **[gap] (server impl) Rating-farming mitigations are prose-only and invisible at the point of attack.** The selected anchor is rated-for-bot-only player cross-play, a one-sided non-conservative update (`OPEN-QUESTIONS.md:143-157`); the mitigations (count only established low-RD players, cap gain per opponent, rate-limit) live only in OPEN-QUESTIONS/SERVER-NOTES. The wire that decides rated-ness (`challenge-create.yaml:24-31`, `Challenge.rated`) exposes a single boolean, so a bot cannot tell whether an opponent counts, whether gain is capped, or whether a game was rate-limited out. Surface a reason (e.g. an opponent-eligibility hint or a `rated:false` reason), or state explicitly that the boolean is not the whole rated-ness story.
- **[gap] Orphaned-challenge lifecycle is undefined.** `challenge-create.yaml:18-21` admits a 200 only means "created and pushed", tells the challenger to "time out and move on", but no expiry, auto-cancel, or terminal event exists for a `created` challenge whose target never acts (or whose stream dropped post-POST). The Event union has no `challengeExpired` and `Challenge.status` no `expired`. Define an expiry/terminal status (ties to E-3, the missing challenge list).
- **[gap] No `Cache-Control: no-store` on presence-bearing responses.** `bots.yaml:86-128`, `bot-status.yaml:58-78` return live `openForChallenge`, but neither declares a cache header, though the design note explicitly requires it (`docs/design/...:215-216`). A cached presence response can be served stale by intermediaries, leaking past availability beyond the "current-state only" guarantee. Add the header to both 200s.
- **[nit] `owner` exposure is by-design, but the `owner` query filter amplifies it to whole-fleet enumeration.** (Verification downgraded this from a bug: `BotListing.yaml:13-16,37-47` makes the linkage intentional and documented, which is defensible since same-owner games are unrated.) The residual point: `GET /api/bots?owner=...` (`bots.yaml:41-50`) turns per-entry linkage into a one-shot fleet roster. Consider gating the `owner` filter behind `bot:organize`, and state the fleet-enumeration tradeoff in the field description so it is an accepted risk, not an unexamined one.
- **[nit] Roster polling reconstructs presence timelines despite "no timestamps".** `bots.yaml:8-11`. Any valid token can poll (the only throttle is a generic 429), so activity hours and fleet co-availability windows are recoverable. Minor activity-correlation leak, already acknowledged; the "no timestamps" framing slightly overstates the protection. Optionally require a gameplay scope or a tighter rate limit on presence reads.
- **[confirmed handled well]** The openForChallenge staleness race is correctly resolved by making the challenge POST authoritative with `409 not-accepting`/`at-capacity` (`challenge-create.yaml:11-21`, `ChallengeRefused.yaml`). Single-actor winner attribution (surrender/timeout/single-disconnect) matches the server (`sessionManager.ts:402,729,891`). `engineDescription`/`hardware` are opt-in, label-only, and the roster re-consent is handled (`BotListing.yaml:65-71` notes the same coarse report already rides on `Player`). Double-finish is benign server-side (idempotent finish).

## Track E: gaps & missing surface (Lichess parity)

Each classified as a documented-deliberate omission or a real gap.

- **[gap] No way to list your ongoing/active games.** Only the event-stream replay-on-connect (`stream-event.yaml:11-14`) surfaces them; there is no pull endpoint and the omission is not documented. Lichess provides `GET /api/account/playing` for exactly this resync/cold-start case. Add an equivalent or document that game enumeration is intentionally stream-only.
- **[gap] No single-game or single-challenge point read outside the streams.** `openapi.yaml:116-142`: every challenge route is a POST mutation; the only game read is the NDJSON stream. `acceptChallenge` returns `{ok:true}`, not the started game id (`challenge-accept.yaml:23-26`), so the acceptor depends on event-stream timing to find its own game. At minimum, return the game id on accept; ideally add a lightweight non-streaming game/challenge fetch.
- **[gap] No challenge list (incoming/outgoing).** `openapi.yaml:133-140`. A challenger cannot reconcile which of its outgoing challenges are still pending before deciding to cancel/re-challenge; Lichess offers `GET /api/challenge`. Add one or document the stream-only model.
- **[gap] No `abort` (pre-move, no rating) distinct from `resign` (always a surrender loss).** `game-resign.yaml:4-6`. With a 500ms bot turn budget, a freshly-started game a bot cannot service can only be exited as a counted surrender. There is no documented decision that abort is folded into resign. Add an abort (opening-only, no rating effect) or document the deliberate omission.
- **[nit] `Challenge.status: accepted` is a dead value.** `Challenge.yaml:43-47`: accept yields a `gameStart` carrying `GameEventInfo`, never a `status:accepted` Challenge (`created`, `declined`, `canceled` are each reachable). Remove `accepted` or mark it reserved, and add a one-line transition note: `created -> {accepted|declined|canceled}`, terminal.
- **[nit] No token-revocation or instance-retirement endpoint despite "revocable".** `RegisteredInstance.yaml`, README, and the design-note tombstoning all promise revocability, but there is no DELETE/retire route. Add one or document how an operator revokes an instance token.
- **[nit] No "list my instances" endpoint for a fleet operator.** Workable via `GET /api/bots?owner=self` (owner learned from `GET /api/account`), but a fleet operator has no direct "my instances" view. Note the intended path.
- **[confirmed deliberate, fine]** No `claim-victory` (the server auto-forfeits on `disconnect` with the opponent as winner; only a tournament-scoped `claim-win` exists, `createApiRouter.ts:697`). No seek-board (open in `OPEN-QUESTIONS.md:206`). No account-upgrade (replaced by repeatable register, `docs/design/...:302-304`). No takeback/berserk/draw-offer/claim-draw (draw-free by design; variant has no such concept). No chat (reasonable non-goal for an automated ladder). `429` is declared on all 13 operations.

## Track F: documentation drift & open-questions hygiene

The contract reads self-contained; the drift is in the surrounding docs, mostly the
untracked design note (`?? docs/`).

- **[bug] Design note section 5 contradicts the resolved rated-for-bot-only anchor.** `docs/design/bot-discovery-and-registration.md:122-124` ("Bot-only ladder ... human-vs-bot games are unrated exhibitions") vs `OPEN-QUESTIONS.md:154-157` and `SERVER-NOTES.md:24-27` (resolved: rated-for-bot-only). The note carries the superseded baseline as a live decision.
- **[bug] Design note section 5 uses a wallclock/fixedsim estimator split (Bradley-Terry/WHR + Glicko) that the single-ladder Glicko decision dropped.** `docs/design/...:100-102,129-136,324-325` vs `OPEN-QUESTIONS.md:77-133` (one original-Glicko + RD ladder) and `SERVER-NOTES.md:18-23`. `fixedsim`/`wallclock`/Bradley-Terry/WHR appear nowhere else in the repo.
- **[bug] Design note references stale endpoint names.** `POST /api/bot/account/upgrade` and `POST /api/challenge/{username}` (`docs/design/...:18,24,208`) vs the shipped `/api/challenge/{handle}` (`challenge-create.yaml:40`) and no upgrade endpoint. The note's own section 8 already records the `{username} -> handle` rename, but its body still uses the old name.
- **[bug] `turnTimeMs` default contradicts itself across docs.** `CLAUDE.md:44` and `OPEN-QUESTIONS.md:20` say "server default 45000 ms"; `README.md:136`, `SERVER-NOTES.md:16`, `openapi.yaml:50`, `TimeControl.yaml:11-12,52` say "500 ms default, 45000 ms ceiling". (Server reality: 45000 literal value, 5000 floor.) A reader cannot tell whether 45000 is the default or the ceiling. State plainly that the server's current default value is 45000 and the contract proposes a 500ms bot default with a 45000ms ceiling pending a server change.
- **[gap] (server impl) SERVER-NOTES/OPEN-QUESTIONS assert "Server-tracked via Glicko/RD" as a server fact; the server is Elo.** `SERVER-NOTES.md:18-23`, `OPEN-QUESTIONS.md:77-133` (same root as C-1, doc-fidelity angle). The contract stays clean (no Glicko/RD field ships); only the notes assert a server behavior that does not exist.
- **[nit] `CLAUDE.md:7` still says "infinite hexagonal tic-tac-toe".** The contract moved to "unbounded grid / bounded frontier" (`openapi.yaml:71-74`, `README.md:24`). Sole "infinite" remnant; align it or keep as a colloquial gloss.
- **[nit] Handle-charset note vs server username.** `docs/design/...:163` `^[a-z0-9_]{3,20}$` matches the spec (`BotInstance.yaml:23`) but both diverge from the server's `zNormalizedUsername` (2-32, spaces/unicode allowed); a third form `^[A-Za-z0-9_]{3,40}$` is used for `owner`/pre-normalization input. Reconcile or document the stricter bot namespace.
- **[confirmed clean]** No spec file references OPEN-QUESTIONS / SERVER-NOTES / README / design notes / issue numbers / branch names (grep empty); the CLAUDE.md self-containment rule holds. Resolved OPEN-QUESTIONS items #1,2,3,5,6,7 are correctly marked and match the shipped spec; open items #4 (draws) and #8 (organizer `rated`) are correctly still-open and consistent with the draw-free surface and the shipped `bulk-pairing.rated` default; #2's "initial + inc" mention is legitimate historical narration, not a stale field.

## Track G: external grounding

- **[confirmed] The Glicko formula set in `OPEN-QUESTIONS.md` section 9 is faithful to Glickman's original paper.** Verified every constant and formula against "The Glicko system" (glicko.net): `q=ln(10)/400=0.0057565`, `g(RD)`, `E`, `d^2`, `r'`, `RD'`, the inactivity inflation with `c~63.2` from the worked example, the `r +/- 1.96 RD` interval, the ~30 RD floor, and the 350 new-player RD all match (pp.3-6). The two divergences from the textbook (start 1000 not 1500; provisional `RD>110`) are both disclosed, not silent. One caveat: `RD>110` is a Lichess Glicko-2 convention borrowed onto Glicko-1 and may need re-tuning. This fidelity is, however, moot against the live server, which is Elo (see C-1).
- **Lichess parity** is otherwise covered under Track E. The defensible divergences (no claim-victory, no upgrade, no takeback/berserk/draw/chat) are listed there.

---

## Needs server implementation (build checklist)

The bot API is a net-new subsystem. None of these exist in `createApiRouter.ts`
today (play runs over Socket.io; bots run in-process via `packages/bot-worker`).

1. **`POST /api/bot/register`** + per-instance opaque PAT mint carrying `bot:play` only; derive `owner` from the operator credential; validate/lowercase the handle; enforce the reserved-word list, uniqueness, and permanence.
2. **Bearer-PAT auth middleware + 3-scope model** (`bot:play` / `bot:register` / `bot:organize`) with `403` on missing scope (existing routes use Discord session cookies and only distinguish `admin`).
3. **Global never-closing NDJSON event stream** (`/api/stream/event`): replay active challenges/games on connect, then push the five Event types, blank-line keepalive. This connection also gates `openForChallenge` presence.
4. **Per-game NDJSON stream** (`/api/bot/game/stream/{id}`): one `gameFull`, then a `gameState` per ply (cumulative moves), keepalive, close on `finished`.
5. **`POST /move` with CAS ply and a two-stone atomic compound turn**: map `[q,r] -> {x,y}`, return `409 {expectedPly}` and `422 {stone}`/`wrong-stone-count`, apply both placements in one transaction (the atomicity invariant the bot loop relies on).
6. **`POST /resign`** (HTTP, by `gameId`) -> `surrender` + opponent as winner.
7. **`POST /api/bot/status`** + presence-gated `openForChallenge` (advertised intent ANDed with live event-stream presence, bounded disconnect detection).
8. **`GET /api/bots` roster**: a bot-instance store, stable handle ordering, opaque cursor (server uses page/pageSize today), and the `variant`/`owner`/`openForChallenge` filters.
9. **Challenge create/accept/decline/cancel** routes + a challenge entity + the challenge/challengeDeclined/challengeCanceled events; create a game and emit `gameStart` to both on accept; define a challenge expiry.
10. **`POST /api/bulk-pairing`** under `bot:organize`: one game per pairing (shared variant/timeControl), `gameStart` to each, authoritative per-game `rated`.
11. **Ratings**: adopt original Glicko + RD + RD-provisional to match the proposal, or re-spec the docs to the live Elo (`K=30/15` on `gameCount`, floor 100, start 1000). Do not ship an RD-derived `provisional` field until RD exists.
12. **Player-vs-bot rated-for-bot-only**: asymmetric (bot updates, player does not) plus anti-farming (count only established low-RD players, cap gain per opponent, rate-limit). Currently the server applies symmetric Elo to both (`sessionManager.ts:1606`).
13. **Same-owner-unrated enforcement** via the owner link (no owner concept exists today).
14. **Sub-second `turnTimeMs` path** (1..45000, default 500) distinct from the human lobby's 5000ms floor (`createApiRouter.ts:96-98`).
15. **`engineDescription` + `HardwareInfo` storage** and echo on whoami/roster (label-only, never a rating/pairing input).
16. **`winningPlayerId -> Side` mapping** on the bot surface, and surface `terminated` (null winner) from the existing admin session-terminate path (`createApiRouter.ts:1030`).

## Deliberate omissions confirmed fine (do not re-raise)

- **Seek-board / open-challenge pool** is omitted and tracked open (`OPEN-QUESTIONS.md:206`).
- **Account-upgrade** is intentionally replaced by repeatable `register` (`docs/design/...:302-304`); no "zero games to upgrade" rule is needed because instances are born as bots.
- **claim-victory** is unnecessary: the server auto-forfeits on `disconnect` with the opponent as winner; the only `claim-win` route is tournament-scoped.
- **takeback / berserk / draw-offer / claim-draw** are out by design (draw-free; the variant has no takeback or berserk).
- **chat** is a reasonable non-goal for an automated bot ladder.
- **Scopes as prose + 403** is the correct encoding for an http-bearer scheme (the same limitation Lichess accepts); 403 wiring is consistent.
- **`terminated` (null winner)** is correctly modeled as observe-only (an out-of-band admin action), never bot-triggered.
- **The Glicko math transcription** in OPEN-QUESTIONS is faithful to the original paper; no constant or formula needs fixing (the issue is that the server runs Elo, not that the formulas are wrong).
