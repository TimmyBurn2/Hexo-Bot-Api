# HeXO Bot API vs the Lichess Bot/Board API: a comparative study

Read-only comparative analysis of this contract (an OpenAPI 3.1 PROPOSAL for a bot
playing `httt6` on `hexo.did.science`) against the Lichess Bot/Board API
ecosystem it is modelled on. The goal is a short list of HeXO-right additions, each
justified by what Lichess does and why it applies (or does not) to HeXO, then
red-teamed. This is analysis, not a fix pass: no spec file was changed.

**Method.** Four grounded research passes in parallel (endpoint coverage; shape and
semantics; client-loop robustness; scopes/auth/identity), then a separate
adversarial pass over the assembled findings. Every claim cites a concrete
reference. Sources: the published Lichess OpenAPI spec (`lichess-org/api`), the
reference bridge (`lichess-bot-devs/lichess-bot`), the Python client (`berserk`),
this repo, and the HeXO server (`WolverinDEV/infhex-tic-tac-toe`) for feasibility.

**Relationship to `AUDIT.md`.** The prior audit already ran a Lichess-parity pass
(its Track E). This study grounds the Lichess axis specifically against the real
Lichess sources and goes beyond it. Note the contract has already absorbed several
audit items since that snapshot: accept returns `gameId` inline, `409 game-finished`
exists, `Retry-After` rides the 429, the move write is described as "retry-safe (no
double-apply)" rather than idempotent, and `no-store` is on both presence reads. The
findings below are only what still fails to support a pattern Lichess actually
relies on, judged by HeXO fit.

---

## Summary

### Highest-value additions

Three carry real weight; all three are server work, but two emit from machinery the
server already runs.

1. **`opponentGone` per-game event (F3, high).** The server already arms a literal
   30-second orphan timer on an in-game disconnect and then auto-forfeits the
   survivor a win, yet the bot gets no wire signal for those 30 seconds. Lichess
   surfaces exactly this. Observe-only (HeXO needs no client claim).
2. **Ongoing-games pull / cold-start resync (F2, high).** Lichess bots seed their
   live games at boot from `GET /api/account/playing` before touching the event
   stream, and re-poll it to recover after a stream error. HeXO surfaces active
   games only via replay-on-connect, which a reconnect race can silently drop.
3. **Early-game `abort` (F1, high).** With a sub-second bot turn budget, a freshly
   started game a bot cannot service is exitable only as a counted surrender loss.
   Lichess has `abort` for exactly this. Already proposed (not settled) in
   `SERVER-NOTES.md`; the open question is whether it reuses the existing
   `terminated` no-winner finish.

Then a cluster of cheap, mostly pure-contract honesty and robustness fixes:
specify a keepalive interval (F5), round-trip the decline reason the contract
already accepts (F6), state the event-stream supersede rule (F7), soften the
"never 404 on a finished game" promise the server cannot keep (F12), expose `scopes`
on whoami (F4), a single-challenge point-read (F9), an `expired` challenge status
(F10), and a one-line honesty note on "revocable" (F13).

### Explicit non-adoptions (so they are not re-proposed)

| Lichess feature | Why not for HeXO |
| --- | --- |
| Manual `claim-victory` | Server auto-forfeits on disconnect; F3 makes that observable, so no client claim is needed. |
| `takeback` (offer/accept) | No move-undo concept in the variant. |
| `draw` offer/accept, `claim-draw` | Bot surface is draw-free by design; the server's `draw-agreement` is filtered out. |
| `berserk` | Arena-tournament chess mechanic; no analog. |
| `seek` board / open challenge | Open pairing pool is parked; both are human-pool features. |
| Challenge the AI | No server-side AI opponent to target; bots challenge by handle. |
| `start-clocks`, `add-time` | No server clock-start or add-time primitive; "time odds" is chess-think. |
| Chat (player + spectator rooms) | Non-goal for an automated ladder; lives on the same per-game union as F3 but stays out. |
| `bot/account/upgrade` | Replaced by repeatable register; the zero-games gate, BOT title, and irreversibility are all subsumed. |
| OAuth2 token-create, bulk `token/test` | Auth is opaque per-instance PATs, not OAuth2 flows; single-token introspection is covered by whoami + F4. |
| `color` / `finalColor` | Sides are `p1`/`p2` by play order, not colours. |
| Challenge `url` | Cosmetic; bots act on `id`. |
| `ChallengeStatus: offline` | Availability is resolved authoritatively at the challenge POST (`409 not-accepting`), so no persisted offline status. |
| Formal OAuth2 scope modelling | http-bearer cannot carry scopes; an `oauth2` scheme would require fabricating flow URLs we do not have. Prose + 403 is structurally correct here. |

---

## Coverage diff (Track 1)

Usage confirmed against `lichess-bot/lib/lichess.py` (`ENDPOINTS`) and the `berserk`
client classes. "Ours" cites our path, or `(none)` where we have no equivalent.

| Lichess capability | Lichess ref | Ours | Class | Note |
| --- | --- | --- | --- | --- |
| Whoami | `accountMe` `/api/account` | `/api/account` | present | Returns `BotInstance` (owner, rating, hardware). |
| Upgrade to bot | `botAccountUpgrade` | `/api/bot/register` | n/a | Repeatable register; instances born as bots. |
| Online bots | `apiBotOnline` `/api/bot/online` | `/api/bots` | partial | We page a full roster with filters; different axis, both serve discovery. |
| Event stream | `apiStreamEvent` `/api/stream/event` | same | present | Identical 5-event set. |
| Per-game stream | `botGameStream` | `/api/bot/game/stream/{id}` | present | gameFull then gameState per ply. |
| Make a move | `botGameMove` | `/api/bot/game/{id}/move` | present | 2-stone CAS-ply POST vs single UCI path param. |
| Abort | `botGameAbort` | `(none)` | **absent/applicable** | F1. |
| Resign | `botGameResign` | `/api/bot/game/{id}/resign` | present | Maps to server `surrender`. |
| Takeback | `botGameTakeback` | `(none)` | n/a | No undo. |
| Draw offer/accept | `botGameDraw` | `(none)` | n/a | Draw-free. |
| Claim draw | `botGameClaimDraw` | `(none)` | n/a | No draws. |
| Claim victory | `botGameClaimVictory` | `(none)` | n/a | Auto-forfeit; see F3. |
| Chat | `botGameChat` | `(none)` | n/a | Non-goal. |
| Ongoing games | `apiAccountPlaying` `/api/account/playing` | `(none)` | **absent/applicable** | F2. |
| Create challenge | `challengeCreate` `/api/challenge/{username}` | `/api/challenge/{handle}` | present | `rated` server-owned (correct). |
| Accept challenge | `challengeAccept` | `/api/challenge/{id}/accept` | present | Ours returns `gameId` inline (Lichess returns `{ok}`). |
| Decline challenge | `challengeDecline` | `/api/challenge/{id}/decline` | present | Reason enum present (minus chess values); not round-tripped (F6). |
| Cancel challenge | `challengeCancel` | `/api/challenge/{id}/cancel` | present | |
| List my challenges | `challengeList` `GET /api/challenge` | `(none)` | **absent/applicable** | F8 (low). |
| Show one challenge | `challengeShow` `GET /api/challenge/{id}` | `(none)` | **absent/applicable** | F9. |
| Challenge the AI | `challengeAi` | `(none)` | n/a | No server AI. |
| Open challenge | `challengeOpen` | `(none)` | n/a | Human URL-share. |
| Berserk | `boardGameBerserk` | `(none)` | n/a | Arena mechanic. |
| Create a seek | `apiBoardSeek` | `(none)` | n/a | Seek-board parked. |
| Start clocks | `challengeStartClocks` | `(none)` | n/a | No server clock-start. |
| Add time | `roundAddTime` | `(none)` | n/a | No server add-time. |
| Bulk pairing create | `bulkPairingCreate` | `/api/bulk-pairing` | present | Organizer scope. |
| Bulk pairing list/get | `bulkPairingList`/`Get` | `(none)` | **absent/applicable** | F17 (low). |
| Bulk export games | `bulkPairingIdGamesGet` | `(none)` | partial | Create returns per-game ids inline. |
| OAuth token create | `apiToken` `POST /api/token` | `(none)` | n/a | Opaque PAT minted at register. |
| Test tokens | `tokenTest` `POST /api/token/test` | `(none)` | partial | Whoami covers it; scopes gap is F4. |
| Token scopes | per-op `security` | prose + 403 | present | http-bearer cannot carry scopes (correct). |
| Token revoke | `DELETE /api/token` | `(none)` | deferred | Operator-scoped model parked; F13. |

---

## Findings

Sorted by priority. Each carries the Lichess grounding, the HeXO analog and server
feasibility, the proposed change, and the red-team verdict. `server work` and
`pure contract` are marked distinctly.

### High

#### F1. Early-game `abort`, distinct from a counted resign loss
- **Priority:** high. **Type:** server work.
- **Lichess grounding:** `botGameAbort` (`tags/bot/api-bot-game-gameId-abort.yaml`),
  called by the bridge only while abortable (`lichess-bot/lib/lichess_bot.py:900-908`).
- **HeXO analog / feasibility:** Real. `POST /resign` is always a `surrender` with
  the opponent as winner (`paths/game-resign.yaml`), and the server has no void or
  abort path (finish reasons in `sharedTypes.ts`: `disconnect|surrender|timeout|terminated|six-in-a-row|draw-agreement`).
  With a 500 ms default bot turn budget (`components/schemas/TimeControl.yaml`), an
  unservable fresh game becomes an inevitable rated loss. Already proposed (not
  settled) in `SERVER-NOTES.md:86-90`.
- **Proposed change:** add `POST /api/bot/game/{gameId}/abort` returning `Ok`, with
  `409 game-finished`, plus a no-winner terminal on `GameState`/`GameFinishEvent`.
- **Red-team verdict: KEEP.** The grounding holds and it duplicates no server logic
  (no abort exists). One open server-semantics question it raises: `terminated`
  already exists as a no-winner finish (`components/schemas/GameState.yaml:70`), so
  the proposal must justify a distinct `aborted` value rather than letting a bot
  trigger `terminated` early-game, unrated. That distinction is the server decision,
  not a contract blocker.

#### F2. Ongoing-games pull for cold start and resync
- **Priority:** high. **Type:** server work (net-new per-token view, not a light filter).
- **Lichess grounding:** `apiAccountPlaying` (`GET /api/account/playing`, `tags/games/api-account-playing.yaml`).
  The bridge seeds live games at boot before consuming the event stream
  (`lichess_bot.py:347`), gates challenge acceptance on it, and recovers after a
  stream error via `game_is_active` (`lichess_bot.py:544-549,763`).
- **HeXO analog / feasibility:** Real. Active games surface only via
  replay-on-connect (`paths/stream-event.yaml:11-14`); a reconnect that drops during
  a `gameStart` push loses that game until the next replay. The server tracks live
  sessions, but its existing reads (`apiQueryService.listSessions()` returning
  `LobbyInfo[]`, `getSession()` returning `SessionInfo`) are neither token-scoped nor
  carry `yourTurn`/`side`, so this is a genuine new view, not a thin filter.
- **Proposed change:** add a `GET` ongoing-games list returning at least
  `{ gameId, side, yourTurn }` per live game (drop Lichess's `color`/`fen`/`perf`).
  This also covers the per-game liveness point-read the bridge uses.
- **Red-team verdict: KEEP, with the effort correction above.** Direct analog,
  read-only (respects referee), contradicts nothing parked. The original "light
  server work" framing is wrong; price it as a net-new per-token query.

#### F3. `opponentGone` per-game event
- **Priority:** high. **Type:** server work (light: emit from the existing timer).
- **Lichess grounding:** `OpponentGoneEvent` (`schemas/OpponentGoneEvent.yaml`,
  `{ gone, claimWinInSeconds }`) on the per-game stream union
  (`tags/bot/api-bot-game-stream-gameId.yaml`).
- **HeXO analog / feasibility:** Real, and the mechanism already runs. On an in-game
  disconnect the server orphans the connection and arms a literal `30_000` ms timer
  (`sessionManager.ts:1087-1096`), then finishes the game as `disconnect` with the
  survivor as winner (`sessionManager.ts:889-892`). For those 30 seconds the
  opponent has no wire signal that its rival vanished or that a win is imminent. Our
  per-game union is `gameFull`/`gameState` only (`components/schemas/GameStreamEvent.yaml`).
- **Proposed change:** add an observe-only `OpponentGoneEvent`
  (`{ type: opponentGone, gone, finishesInSeconds }`) to the per-game union. No
  client `claim` action: HeXO auto-forfeits, unlike Lichess, so drop
  `claimWinInSeconds` semantics and report the countdown to the automatic forfeit.
- **Red-team verdict: KEEP (strongest of the high set).** The signal gap is concrete
  and the emit point already exists. Goes beyond the prior audit, which noted
  "claim-victory unnecessary" but missed that the disconnect-countdown visibility is
  a distinct, real gap.

### Medium

#### F4. Expose `scopes` on whoami
- **Priority:** medium (downgraded from high). **Type:** pure contract.
- **Lichess grounding:** `POST /api/token/test` returns a token's scopes; the bridge
  validates at boot (`lichess.py:151-163`, asserts `bot:play` is present, else
  raises with the actual scopes).
- **HeXO analog / feasibility:** A bridge handed a `bot:play` token out of band (the
  normal case: register and play are different processes) cannot discover its scopes.
  `GET /api/account` returns a `BotInstance` with no `scopes` field (`paths/account.yaml`),
  though registration does return them (`components/schemas/RegisteredInstance.yaml`).
  The auth middleware already resolves scopes to enforce 403, so echoing them is free.
- **Proposed change:** add a read-only `scopes` array to the whoami 200 / `BotInstance`.
- **Red-team verdict: KEEP, downgraded to medium.** The analog is loose (Lichess uses
  a dedicated test endpoint, not whoami) and an instance token has exactly one
  possible scope set (`[bot:play]`, pinned by `RegisteredInstance`), so discovery
  value is low. Worth it for the out-of-band case, not high. Skip the bulk
  `token/test` analog; it is chess-think for an opaque-PAT model.

#### F5. Specify a concrete keepalive interval on both streams
- **Priority:** medium. **Type:** pure contract wording (plus a trivial server guarantee).
- **Lichess grounding:** "An empty line is sent every 7 seconds for keep alive
  purposes" (`tags/board/api-stream-event.yaml:7`). The bridge sets a 15 s stream
  read timeout for dead-peer detection (`lichess.py:403,407`) and reconnects on
  `ReadTimeout` (`lichess_bot.py:127-129,760-763`).
- **HeXO analog / feasibility:** Both our streams promise a blank-line keepalive but
  only "periodically" (`paths/stream-event.yaml:17-19`, `paths/game-stream.yaml:19`),
  giving a client no basis to choose a read timeout, so it cannot tell "idle but
  alive" from "dead socket". The server already emits keepalives; it need only commit
  to a bound.
- **Proposed change:** state a maximum interval ("a blank line at least every N
  seconds") on both streams so a client can set a read timeout at a small multiple of N.
- **Red-team verdict: KEEP.** Cheap, pre-1.0-safe, no logic duplication. (Track 3
  rated it high; the red-team and this report settle it at medium since it is purely
  a robustness convenience.)

#### F6. Round-trip the decline reason to the challenger
- **Priority:** medium. **Type:** pure contract.
- **Lichess grounding:** `ChallengeDeclinedJson.declineReasonKey` rides the
  `challengeDeclined` event (`schemas/ChallengeDeclinedJson.yaml`).
- **HeXO analog / feasibility:** Self-inflicted asymmetry. Decline accepts the reason
  enum (`paths/challenge-decline.yaml:32-47`) and the op text promises it "lets the
  challenger's bot decide whether to re-challenge" (`:6`), yet
  `components/schemas/ChallengeDeclinedEvent.yaml` and `Challenge.yaml` carry no
  `declineReason` field, so the challenger never receives it. The server has the
  reason from the decline body.
- **Proposed change:** add `declineReason` (the same enum) to `Challenge` (present
  when `status: declined`) or to `ChallengeDeclinedEvent`.
- **Red-team verdict: KEEP.** The input enum already exists; only the output
  round-trip is missing, and the contract currently contradicts its own stated
  purpose, so this is more than cosmetic. Corrects the prior audit's framing, which
  called the input enum a gap; it is not.

#### F7. State the event-stream supersede rule
- **Priority:** medium. **Type:** server requirement (plus contract wording).
- **Lichess grounding:** "Only one global event stream can be active at a time. When
  the stream opens, the previous one with the same access token is closed"
  (`tags/board/api-stream-event.yaml:18`). The bridge relies on it, reconnecting
  without tearing down the stale connection (`lichess_bot.py:119-129`).
- **HeXO analog / feasibility:** Ours is advisory only: "Typically only one event
  stream per token should be open at a time" (`paths/stream-event.yaml:22`). A bot
  reconnecting after a half-open drop cannot know whether the old connection is
  auto-closed (safe to re-open) or must be torn down first.
- **Proposed change:** state the guarantee ("opening a new event stream closes any
  previous one for the same token"). Matches the presence-gating design, where the
  stream already gates `openForChallenge`.
- **Red-team verdict: KEEP.** Flag honestly that this is a server requirement (the
  server must actually supersede), not just wording.

#### F8 was downgraded to low (see below). Listed here so numbering tracks priority intent.

#### F9. Single-challenge point-read
- **Priority:** medium. **Type:** server work (read over the challenge entity).
- **Lichess grounding:** `challengeShow` (`GET /api/challenge/{id}`,
  `tags/challenges/api-challenge-id-show.yaml`), which works "even if recently
  accepted, canceled or declined".
- **HeXO analog / feasibility:** Real and specific. Accept- or decline-after-cancel
  collapses to a generic 404 indistinguishable from a bad id; a point-read returning
  the terminal `challenge.status` lets a bot tell "bad id" from "canceled a
  millisecond ago" without depending on event-stream timing.
- **Proposed change:** `GET /api/challenge/{challengeId}` returning `Challenge`
  including terminal status. Pairs well with a non-pending `409` on accept/decline.
- **Red-team verdict: KEEP, above F8.** It resolves an ambiguity the current contract
  itself creates, which the bare list does not.

#### F10. `expired` challenge status (or a documented fixed expiry)
- **Priority:** medium. **Type:** server work.
- **Lichess grounding:** the bridge self-cancels its own challenge after a 20 s timer
  ("Challenges expire after 20 seconds", `lichess-bot/lib/matchmaking.py:29,58-65`);
  Lichess also auto-expires server-side.
- **HeXO analog / feasibility:** `Challenge.status` is `created|declined|canceled`
  (`components/schemas/Challenge.yaml:47-50`), there is no `expired` and no
  `challengeExpired` in the five-event union, and `challenge-create.yaml` tells the
  challenger only to "time out and move on". A challenger whose target never acts gets
  no terminal signal and must invent a private timer with no way to confirm the server
  agrees the challenge is dead.
- **Proposed change:** add an `expired` status plus a `challengeExpired` event; or, as
  the cheaper minimal form, document a fixed server expiry the challenger can rely on.
- **Red-team verdict: KEEP.** Additive and safe. Offer the document-a-fixed-expiry
  form as the low-cost option.

#### F12. "Never 404 on a finished game" over-promises
- **Priority:** medium (the strongest correctness finding). **Type:** server work (retention) or contract softening.
- **Grounding:** the contract guarantees a move/resign on a finished game returns
  `409 game-finished`, never `404`, because "a finished game still exists"
  (`components/responses/Conflict.yaml`, `paths/game-move.yaml:28-29`,
  `paths/game-resign.yaml`, `components/responses/NotFound.yaml`). But the server
  reaps the live session the moment both players disconnect in the finished state:
  `deleteSession(session, 'empty-finished')` once `connectedPlayers.length === 0`
  (`sessionManager.ts:900-905`), and the 30 s retention guard just above it is
  tournament-only. The game then survives only in a separate finished-games store, so
  a late move would naturally 404, contradicting the invariant.
- **Proposed change:** either require the server to retain a finished-game stub long
  enough to keep answering `409 game-finished` (a `SERVER-NOTES` requirement), or
  soften the contract to "a recently finished game returns 409; after the server
  reaps it, 404 is permitted" and tell the bot to reconcile from the `gameFinish`
  event rather than the move's status code.
- **Red-team verdict: KEEP.** The contract states something the server cannot honor;
  do not drop. Verified the `empty-finished` reap is immediate and the retention guard
  is tournament-only.

#### F13. Stop asserting "revocable" with no surface
- **Priority:** medium. **Type:** pure contract (documentation honesty). Respects the deferral.
- **Lichess grounding:** `DELETE /api/token` self-revokes (`tags/oauth/api-token.yaml`).
- **HeXO analog / feasibility:** "revocable" is asserted in `openapi.yaml:39,151-155`,
  `RegisteredInstance.yaml`, and `BotInstance.yaml`, but no endpoint ships.
  `SERVER-NOTES.md:91-97` deliberately defers it with a sound operator-scoped model (a
  `bot:play` token must never retire siblings), which is actually stronger than
  Lichess's bearer self-revoke.
- **Proposed change:** not an endpoint now. A one-line note that revocation is
  operator-side and not yet exposed, matching how `bot-register.yaml` documents the
  deferred owner-instance-limit.
- **Red-team verdict: KEEP, respects the deferral.** Removes a claim the surface does
  not back without reopening the parked endpoint.

### Low

#### F8. Challenge list (incoming/outgoing)
- **Priority:** low (downgraded from medium). **Type:** server work.
- **Grounding:** `challengeList` (`GET /api/challenge`, `tags/challenges/api-challenge.yaml`);
  `berserk` first-class (`challenges.py get_mine`).
- **Analog:** A challenger cannot reconcile which outgoing challenges are still
  pending except via the stream.
- **Red-team verdict: DOWNGRADE to low.** It is a `challenge:read` convenience, the
  event stream already replays active challenges on connect, and F2 (playing list) and
  F9 (point-read) cover the gaps that actually bite a loop. Least load-bearing of the
  reconciliation trio.

#### F11. Challenge `direction` (in/out)
- **Priority:** low (downgraded from medium). **Type:** pure contract.
- **Grounding:** `ChallengeJson.direction` `in|out` (`schemas/ChallengeJson.yaml:39-43`).
- **Analog:** Our `ChallengeEvent` says "incoming (or outgoing)" but `Challenge` has
  no field to distinguish; a bot compares `challenger.id` against its own id.
- **Red-team verdict: DOWNGRADE to low.** Pure convenience, derivable from
  `challenger.id` (known from whoami), and the event types already disambiguate
  issued from received. Additive and safe, low value.

#### F14. List-my-instances, bundled with the deferred operator surface
- **Priority:** low (downgraded from medium). **Type:** server work, deferred.
- **Grounding:** the `GET /api/bots?owner=self` workaround is a public roster filter,
  not an operator-authenticated management view, and cannot show retired instances
  (`AUDIT.md:128,142`).
- **Red-team verdict: DOWNGRADE to low.** Gated on the same deferred operator-scoped
  surface as F13. Bundle revoke and list-my-instances as one future operator surface
  and say so once, rather than scattering three omissions.

#### F15. Echo the resolved opener on the `Challenge`
- **Priority:** low. **Type:** pure contract.
- **Grounding:** Lichess echoes `finalColor` (`schemas/ChallengeJson.yaml:27-28`).
- **Analog:** We accept `firstPlayer` on the request (`paths/challenge-create.yaml:60-73`)
  but never echo the resolved opener; with `firstPlayer: random` the opener is unknown
  until `gameStart`.
- **Red-team verdict: DOWNGRADE (drop acceptable).** The opener already arrives at
  `gameStart` via `GameEventInfo.side` (`components/schemas/GameEventInfo.yaml:19-21`).
  No loop needs it earlier. Keep only as a minor convenience or drop.

#### F16. First-move / abort countdown on `gameState`
- **Priority:** low, defer. **Type:** server work, gated on F1.
- **Grounding:** Lichess `GameStateEvent.expiration { idleMillis, millisToMove }`.
- **Red-team verdict: DEFER.** A countdown to nothing is noise without an abort action.
  Correctly gated on the parked F1 decision; revisit only if abort lands.

#### F17. Bulk-pairing read-back (list + get one)
- **Priority:** low. **Type:** server work, organizer-only.
- **Grounding:** `bulkPairingList`/`bulkPairingGet` (`tags/bulkpairings/`); `berserk`
  first-class (`bulk_pairings.py`).
- **Analog:** Lets an organizer re-read a batch after a restart; our create already
  returns the batch and per-game ids inline (`paths/bulk-pairing.yaml`), so the resync
  need is weaker than for self-play. Does not touch the parked organizer-`rated`
  decision (pure read).
- **Red-team verdict: KEEP at low.**

#### F18. Recommend a `User-Agent` convention
- **Priority:** low. **Type:** pure contract (prose only).
- **Grounding:** the bridge sends `User-Agent: lichess-bot/{version} user:{name}`
  (`lichess.py:442-445`).
- **Red-team verdict: KEEP at low (borderline drop).** Operational nicety, not
  load-bearing; add a one-line SHOULD at most.

### Dropped

#### F19. `Cache-Control: no-store` on presence reads
- **Verdict: DROP, already present.** Both `paths/bots.yaml:90` and
  `paths/bot-status.yaml:62` already declare `Cache-Control: no-store`. The audit note
  predates that addition. Nothing to do.

---

## Server requirements surfaced

Three findings lean on behavior the server must guarantee, not just wire shape.
Worth recording in `SERVER-NOTES.md` alongside the existing expectations:

- **F7:** opening a new event stream must close the previous one for the same token.
- **F12:** a finished game must remain answerable as `409 game-finished` for some
  retention window, or the contract must permit `404` after reap.
- **Draw invariant (non-adoption consequence):** the bot surface states the server's
  `draw-agreement` finish "never appears". The server does have a live
  `draw-agreement` path (`sessionManager.ts:442`, `winningPlayerId: null`), so this is
  a server requirement (bot pairings must not route into the draw path), parallel to
  F12. The spec already filters the reason out (`components/schemas/GameState.yaml:63-65`);
  the requirement should be explicit so the invariant is not as soft as F12's.

---

## Deliberate divergences confirmed fine

Where we differ from Lichess on purpose, settled so they are not re-litigated:

- **CAS `ply` token on move submit** (`components/schemas/MoveSubmit.yaml`). Lichess
  has no equivalent and relies on turn legality. Intentional stateless-wire safety.
- **Two-stone atomic compound turn and a structured `moves` array** of `CompoundMove`
  vs Lichess's UCI move string. Matches the variant.
- **`status` + `finishReason` + `winner` triple** vs Lichess's flat `GameStatusName`
  enum. A cleaner, draw-free subset.
- **`time` nullable under `unlimited`** vs Lichess omitting `clock`. Resolves the
  prior "undefined unlimited time" cleanly.
- **Decline-reason enum trimmed** to a single variant (drops `standard`/`variant`).
- **Accept returns `gameId` inline** (`paths/challenge-accept.yaml:27-45`), an
  improvement over Lichess's `{ ok: true }`: the acceptor opens the per-game stream
  without waiting for its own `gameStart`.
- **Per-instance token plus operator/register split**, a real improvement over
  Lichess's single-account-token model for fleets: scoped minting, independent
  revocation, an unforgeable `owner` link powering same-owner-unrated, no privilege
  escalation.
- **Scopes as prose plus a 403** on an http-bearer scheme. Structurally correct, not
  a cosmetic shortcut: our auth is opaque PATs, not OAuth2 flows, so a formal `oauth2`
  scheme would require fabricating authorization and token URLs that do not exist.
- **`Retry-After` already on the 429** (`components/responses/TooManyRequests.yaml`),
  matching the bridge's honor-`Retry-After`-else-60s behavior.
- **Availability resolved at the challenge POST** (`409 not-accepting`) rather than a
  persisted `offline` challenge status.
- **Bot identity via repeatable register** rather than a one-shot account upgrade. The
  zero-prior-games gate (n/a by construction), the `BOT` title, and irreversibility
  (handle permanence) are all subsumed.
