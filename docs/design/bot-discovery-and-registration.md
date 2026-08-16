# Bot Discovery, Registration & Identity. Design Note

> **Status: SUPERSEDED, retained for history.** This note records the original
> reasoning behind bot discovery, registration, and identity. Several of its
> decisions have since changed; the canonical current decisions live in
> `OPEN-QUESTIONS.md` (open design questions) and `SERVER-NOTES.md` (server-facing
> requirements and open decisions). Where this note and those files disagree, they
> win. Known changes since: player-vs-bot games are now rated **for the bot only**
> (not unrated exhibitions); the rating model is a **single ladder** (the
> `wallclock`/`fixedsim` estimator split with Bradley-Terry/WHR below is dropped),
> proposed as Glicko over the server's current plain Elo; and the endpoint names
> below are stale (`POST /api/challenge/{username}` is now
> `POST /api/challenge/{handle}`, and the irreversible
> `POST /api/bot/account/upgrade` is replaced by a repeatable
> `POST /api/bot/register`).
> Original date: 2026-06-15.

Records the reasoning behind extending the HeXO Bot API with **discovery** (how a
bot finds an opponent), **multi-operator identity** (a bot is not statically tied
to one user), and the **rating-integrity** fixes those expose. Actionable tasks
live as GitHub issues (see Tracking). This note is the rationale that travels
with the spec.

---

## 1. Problem

Registration is solved but thin, discovery is absent, and identity is tangled.

- `POST /api/bot/account/upgrade` flips one Discord account into one bot,
  irreversibly. That is all of registration. (Since superseded: replaced by a
  repeatable `POST /api/bot/register`.)
- A bot can only play someone whose `id` it already knows
  (`POST /api/challenge/{handle}`), wait for challenges on the event stream, or
  be paired by an organizer via `bulk-pairing`. There is no way to find who is
  out there to play.
- Identity is one Discord account equals one bot, and the public name is a
  Discord display name. No way to run a fleet, no separation of operator from bot.

A second-order goal surfaced during review: a bot like `SealBot` should not be
owned by a single user. Multiple operators should be able to run their own
instance of it, each on their own hardware and Discord, so the bot survives if
its original author drops.

---

## 2. What already exists (do not reinvent)

`components/schemas/Player.yaml` already ships the identity split we need:

- `Player.id`: "Stable, unique account identifier (lowercased handle)". This **is**
  the `handle`.
- `Player.name`: "Display name as registered." This **is** the `display_name`.
- `Player.rating`: optional, **absent** for unrated accounts. The spec uses no
  `null` anywhere; rating is optional-absent, not nullable.

So we keep `id` and `name`. We do not add or rename `handle`/`display_name`; we
document that `id` is the handle and `name` is the display name. The genuinely
missing field is **`owner`**.

---

## 3. Identity: operator and instance

Adopt a two-layer model. A third "engine label" layer is allowed only as a
cosmetic string with zero authority.

- **Operator.** A Discord-authenticated party that owns hardware and is the
  accountable entity. Can run many instances.
- **Bot instance.** The rated, listed, challengeable unit. Owns a `handle`
  (the existing `id`), a `display_name` (the existing `name`), its own hardware
  report, and its own revocable token. Carries an `owner` field linking to the
  operator.
- **Engine label (optional, cosmetic).** A free string like `sealbot` that an
  operator may assert. It carries **no rating, no reputation, no trust, no
  moderation surface**. The litmus test: if anyone ever wants to "ban an engine
  label", the decoupling has failed. A verified-brand checkmark is out of scope
  unless we build cryptographic signing (see Open questions).

Why this satisfies the goals:

- Multiple bots per person: an operator registers many instances.
- Multiple operators run `SealBot`: each registers an instance with engine label
  `sealbot`, on their own hardware and Discord.
- Resilience if the author drops: the instance is operator-owned, so the author
  leaving removes only the author's instance. This is free, and it is exactly
  why the engine label must hold no author-controlled authority.

**Handle lifecycle:** handles are permanent and never reused. Retired or banned
bots are tombstoned, matching the Lichess model. This prevents silent identity
reassignment in historical game and rating records. Kept as-is for now; whether
the permanent key should instead be an opaque id plus a mutable public handle is
an open question (section 8).

---

## 4. Rating integrity (the keystone, independent of discovery)

Review found a live hole that exists today and that multi-instance makes
critical. `createChallenge` and `createBulkPairing` both let the caller set
`rated: true` on arbitrary account pairs. With many instances per owner this is a
rating printing press: register two of your own instances, pair them rated, throw
games one way.

Decisions:

- **The server owns `rated`-ness.** It is not caller-controlled for
  self-initiated games. The server decides rated-ness from pairing policy.
- **Same-owner games are always unrated**, enforced server-side via the `owner`
  link.
- **`bulk-pairing` is organizer-scoped**, a role flag, not callable by any bot
  token.
- **Rating attaches to `(instance, mode)` only.** Never to an engine label.
  `wallclock` and `fixedsim` are separate. The same engine on different hardware
  is distinct competitors in `wallclock` by design (speed is part of the engine).
- **Anti-smurf:** new instances seed at provisional high-uncertainty rating;
  retire then re-register by the same owner inherits prior rating; cap active
  rated instances per owner.
- Rating stays **optional-absent**, not nullable. Unrated bots sort last, never
  interleaved by a default value.

This block is the most important and is mostly independent of the directory.

---

## 5. Rating model

> **SUPERSEDED.** This section's rating decisions have changed. Player-vs-bot
> games are now rated **for the bot only**, not unrated exhibitions; and the
> mode-split estimators below (`fixedsim` Bradley-Terry/WHR plus `wallclock`
> Glicko) are replaced by a **single rating ladder**, proposed as Glicko over the
> server's current plain Elo. See the rating section of `OPEN-QUESTIONS.md` and
> `SERVER-NOTES.md`. The text below is retained for history.

Section 4 removes `rated` as a caller lever. This section is the model that
decides and computes ratings. The driving fact: a bot is a **fixed-strength
engine**. A given build does not learn between games, unlike a human. That
reframes the math.

Decisions:

- **Bot-only ladder.** Bots rate against bots. Offering bots to human players is
  a goal, but human-vs-bot games are unrated exhibitions, never merged into the
  bot ladder.
- **Rated only through organized pairing.** A game counts only when it comes from
  an arena or a server-seeded pairing that ensures diverse, cross-clique,
  rating-distant opponents. Casual bot-to-bot challenges stay unrated. This is
  required twice over: the estimators below need a connected comparison graph,
  and free rated challenges are the cherry-picking and clique-rating surface.
- **Estimator split by mode.** Rating is per `(instance, mode)`.
  - `fixedsim` (hardware-neutral, constant strength): a static-strength estimator
    (Bayesian Bradley-Terry posterior or Whole-History Rating). It treats true
    strength as fixed and tightens the estimate as games accumulate. More
    accurate than Elo/Glicko for a constant target.
  - `wallclock` (speed counts, so hardware moves strength): a Glicko-style
    estimator (rating plus uncertainty). Semi-dynamic, because moving the bot to
    faster hardware genuinely changes its strength.
- **Version updates are inheriting epochs.** A new build under the same handle
  opens a fresh rating window seeded from the prior rating with widened
  uncertainty. Never a free downward reset (that would be a sandbagging lever),
  and ideally corroborated by an observed performance shift, not pure
  self-report.
- **Anti-smurf and fairness.** New instances start provisional with high
  uncertainty; a rating is shown as settled only past a minimum game count.
  Per-owner daily caps on rated games. Same-owner games never rated (section 4).
- **No inactivity decay.** A fixed build does not weaken while idle, so
  human-style decay and idle volatility growth do not apply. State this
  explicitly.

Remaining sub-decisions (smaller, for the rating-system PR):

- Pairing structure: arena format (Swiss, round-robin) versus a continuous
  server-seeded queue.
- The minimum game count and how provisional is surfaced.
- How the version performance-shift corroboration is detected.

---

## 6. Moderation

Owner-accountability is the backbone, but its cost must be priced.

- **Automated handle hygiene** on the immutable `handle`: ASCII charset
  `^[a-z0-9_]{3,20}$`, input normalized to lowercase, uniqueness on that form,
  and a reserved-word list. The reserved list must include path-segment
  collisions (`create`, `accept`, `decline`, `api`, `me`, `self`) plus
  impersonation tokens (`hexo`, `official`, `admin`, `mod`, `system`, `support`,
  `staff`, `root`). It is non-exhaustive and server-authoritative.
- **Drop confusable/homoglyph folding.** The ASCII charset already rejects
  Cyrillic and other Unicode look-alikes, so the headline example was free.
  UTS-39 confusable folding is the wrong tool here: it causes false collisions
  (`b0t` vs `bot`) and would wrongly reject immutable handles.
- **Profanity is reactive, not an automated gate.** Substring profanity matching
  on an immutable identifier is the Scunthorpe problem with no appeal path.
  Handle profanity is dealt with by report plus owner accountability.
- **`display_name` is reactive:** report, then force-reset to the `handle`. Absent
  `display_name` renders as the `handle`.
- **Price the evasion.** Free Discord accounts make owner-banning weak on its own.
  Add Discord account-age or verification gates, per-owner registration caps, and
  rate limits on register. Owner-banning deters casual abuse; persistent abuse
  also needs handle tombstoning and heuristic signals. Any abuse-correlation
  fingerprint is a different axis from rating and must be kept provably out of
  rating math, with that distinction stated explicitly.

---

## 7. Discovery: the directory

Use a dedicated `BotListing` schema, not an overload of `Player` (which is
embedded in every challenge and game event). Trust keys on the **operator**, not
the engine label.

- **A. Roster.** `GET /api/bots`, paginated. Fields: `handle`, `display_name`,
  `owner`, optional engine label, optional `hardware`, rating-or-absent, and
  opt-in open-for-challenge status. Needs a new `Directory` tag (declared and
  described), at least one 4xx response, and a valid example, or it fails lint.
- **B. Availability and filters.** One **open-for-challenge** flag, not separate
  `online` and `acceptingChallenges`: a bot is listed as available when it is
  taking challenges (online-but-closed has no use case). The flag is advisory and
  opt-in; the authoritative answer is the challenge POST, which gains a defined
  refusal response (a `409`, mirroring the compare-and-set `ply` ethos) when the
  bot is at capacity or declines. The directory also serves human players, not
  just bots: it is how a player finds a bot to play. Filters by variant, owner,
  and open-for-challenge. **No rating-range filter** until a rating system exists
  (section 5 / task list). Whether "open" accounts for free capacity depends on
  bot concurrency (section 8).
- **Challenge flow unchanged.** Pick a target from the directory, then
  `POST /api/challenge/{handle}` where `{handle}` is the target's handle. (The
  param was renamed from `{username}` to `{handle}`; see section 8.)
- **Organizer-mode** reuses the roster plus the now organizer-scoped
  `bulk-pairing`, with same-owner pairs forced unrated and per-owner dedupe in
  tournaments.
- **Privacy and serving.** Cursor pagination, default sort by `handle` (always
  present), no exposed total count, and `Cache-Control: no-store` or short
  max-age on presence-bearing responses. Exposing `hardware` in a public roster
  widens the original opt-in consent, so reconfirm that consent scope.

---

## 8. Open questions (parked)

- **Verified engine brand.** Cosmetic label only for now (no authority). If a
  trusted shared brand is ever built, the candidate is an **engine as a
  first-class entity with a maintainer set** (co-owners, admit/remove,
  succession), walled off from all rating/pairing/trust so it survives a
  maintainer leaving without becoming a collusion or rating-pollution vector.
  Cryptographic signing is rejected for this: it breaks the operator-to-Discord
  accountability chain and has shared-key revocation problems.
- **Rating system internals.** The model is decided (section 5). Remaining:
  pairing structure, the minimum-game threshold, and version performance-shift
  corroboration. The algorithm is unbuilt.
- **Seek-board (C).** A directory of open game offers. When specced, reconcile
  with server-owns-pairing: the seek is an intent, the server still adjudicates.
- **Presence mechanics.** Heartbeat and timeout relative to the existing
  event-stream keepalive (a missed keepalive is not necessarily offline).
- **`{username}` path param.** Decided: rename to `handle` (in the directory PR).
- **Handle re-layering.** Liked but deferred: replace the operator-chosen
  permanent handle with an opaque, server-minted permanent id plus a mutable,
  unique, alias-tombstoned public handle (Discord/GitHub style). Fixes rename and
  permanent brand-squatting at the cost of an alias/redirect layer. Keep the
  shipped permanent-handle model until this is decided.
- **Bot concurrency.** How many simultaneous games or connections a bot accepts.
  Gates whether "open for challenge" means "has free capacity", and matters once
  bots are offered to many human players. Later.

---

## 9. Rejected / non-vectors

- **DID-based identity.** The `did.science` domain is just a domain name. Not
  pursued.
- **Engine label as a trust or rating unit.** It is an impersonation and
  reputation-laundering primitive if it carries authority. Cosmetic only.
- **Server-assigned-only names.** Loses brand identity. Rejected in favor of
  operator-chosen handles plus owner accountability.
- **Confusable/homoglyph folding.** Redundant under the ASCII charset and a
  source of false rejections. Dropped.
- **`nullable` rating.** Keep the existing optional-absent convention.
- **Roster-only, no presence.** Kept as layer A under B, not the only mechanism.

---

## 10. Sequenced backlog

Each item is a PR that includes its own example, tag, and schema-reference
updates so the bundled spec stays lint-clean (Spectral runs on the bundle, and
`no-unused-components` / `operation-tag-defined` / `no-invalid-schema-examples`
are repo-wide errors). Decisions are issues, not PRs. `★` marks the critical path.

**Rating integrity (do first, independent of discovery)**

1. **★ Server owns `rated`. [DONE, contract]** Removed caller-set `rated` from
   self-initiated challenges (the field is gone from the `createChallenge` body;
   the server sets it and echoes the authoritative value on the `Challenge`, and
   now on `GameFull`/`GameEventInfo` so a bulk-paired bot, which never sees a
   Challenge, can still read its game's rated-ness). Documented same-owner games
   as always unrated (server policy, pending the `owner` link). Scoped
   `bulk-pairing` to the new `bot:organize` role, kept its `rated` as an
   organizer-requested default (omitted defaults to `false`) that the server
   overrides for same-owner pairs, and added the authoritative per-game `rated`
   to its response. Touched `challenge-create.yaml`, `bulk-pairing.yaml`,
   `Challenge.yaml`, `GameFull.yaml`, `GameEventInfo.yaml`, `GameStartEvent.yaml`,
   `GameFinishEvent.yaml`, `openapi.yaml`, the new `ForbiddenOrganizer.yaml`, and
   their examples / the two stream paths.

   This removes the *caller-labelled* printing press (a token can no longer stamp
   `rated: true` on a pair it picks). Two enforcement pieces are deliberately out
   of this PR and gate the *full* close: the `owner` link that makes "same-owner
   unrated" machine-checkable (task 2), and anti-collusion for *distinct*
   accounts a single party controls (free Discord accounts make two non-same-owner
   feeders possible). The latter is the anti-smurf / per-owner-cap work in section
   4 and the rating-system task (task 8); rated-ness here is removed as a *lever*
   but the pairing-policy that decides it for distinct accounts is specced there,
   not in this PR. A server-side rated decision at accept time (downgrade a feeder
   pair on accept, not just at create) is a follow-up to consider with task 8.

**Identity foundation**

2. **★ Add `owner` and a per-instance token model.** Add `owner` to the listing
   schema; specify per-instance, individually revocable PATs. Decide the
   registration shape (see issue below).
3. **Replace the irreversible `upgrade`.** Add `POST /api/bot/register`
   (owner-scoped, repeatable) that mints an instance handle, hardware report, and
   token. Deprecate `upgrade`; migrate existing upgraded accounts to
   `(owner=self, instance=self)` so nothing breaks.
4. **Document handle hygiene and lifecycle.** ASCII charset, lowercase
   normalization, reserved words including path-segment collisions, permanent
   non-reused handles with tombstoning, reactive profanity and display_name. Must
   land before or with task 3, since register enforces these rules.
5. **Engine label as cosmetic field.** Optional, unverified, no authority.

**Directory**

6. **`BotListing` schema + roster.** `GET /api/bots`, new `Directory` tag,
   cursor pagination, default sort by handle, 4xx responses, valid example,
   `hardware` consent reconfirmed.
7. **Presence and filters.** Opt-in coarse presence, advisory
   `acceptingChallenges` with a `409` refusal on the challenge POST, filters by
   variant/owner/accepting. No rating filter yet.

**Parked (issues, larger / later)**

8. **Rating system.** Implement the section 5 model: organized-pairing-only rated
   games, mode-split estimators (static for `fixedsim`, Glicko-style for
   `wallclock`), inheriting version epochs, provisional seeding, per-owner caps.
   Only then can rating filtering (re-add to task 7 scope) be defined.
9. **Seek-board (C).** Open offers reconciled with server-owns-pairing.
10. **Verified engine brand.** Only if cryptographic signing is committed to.

**Decisions to track as issues (not PRs):** identity registration shape for task
3; whether to rename `{username}` to `handle`; whether to ever build engine-brand
verification.

---

## 11. Tracking

Both, by design. This note holds decisions and rationale and lives with the spec.
GitHub issues hold actionable tasks and the open decisions above, filed via a
design-proposal issue template. The README points contributors there.
