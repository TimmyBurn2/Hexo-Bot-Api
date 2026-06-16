# Open questions

Tracked design questions for the HeXO bot protocol. This file is intentionally
**not referenced from the spec**: the contract must read on its own. It is a
working list, not part of the contract. Items the current proposal settles are
marked **(resolved)** in place with a short note; the rest stay open.

## 1. Playable-frontier rule: descriptive or normative? (resolved)

**Resolved: descriptive.** The radius-8 frontier (the server's
`PLACE_CELL_HEX_RADIUS` is 8) is stated descriptively only. The server is the
sole authority and rejects an out-of-frontier placement with `422 out-of-bounds`;
a bot may self-validate against the rule but is not required to, and
self-validation is not made a normative part of the contract.

## 2. Time-control union (resolved)

**Resolved: union adopted.** The `timeControl` field is now the server's `TimeControl`
union over `mode`: `unlimited`; `turn` (a per-turn cap `turnTimeMs`, the server
default at 45000 ms); and `match` (`mainTimeMs` + `incrementMs`). The earlier
single match-style clock (`initial` + `inc`) is replaced, and the
clock-validation 422 is renamed `invalid-time-control`.

## 3. Opening auto-play (resolved)

**Resolved: the server auto-plays it.** The server places the opening hex at
`[0, 0]` at ply 0; a bot never submits it. `MoveSubmit` now requires exactly two
stones (`ply >= 1`), the bot loop computes two stones every turn, and `Side`,
`CompoundMove`, and the per-game examples describe the opening as the
server-placed ply-0 entry that stays in the cumulative move list as history.

## 4. Draws

Bots are draw-free: the bot surface exposes no draw action, and the `gameState` /
`gameFinish` `finishReason` enum omits the server's `draw-agreement`. The server
itself supports a draw by mutual agreement after 50 turns
(`DRAW_REQUEST_MIN_TURNS`). Confirm bots stay draw-free, or decide to expose the
draw action.

## 5. Tournament fairness for bulk pairing (resolved)

**Resolved: the contract stops at per-game opener choice; batch opener-fairness
is server-side.** Per-game `firstPlayer` (on a single challenge) and the explicit
`p1` per pairing (in a batch) are the only opener controls the contract exposes.
Balancing who opens across a batch, so each bot plays Player 1 its share, is
server-side pairing policy, not a contract feature; it is recorded as a server
expectation in `SERVER-NOTES.md`. Whether opening is actually an advantage is a
backend measurement, not a contract claim.

## 6. Bulk pairing vs the server's tournament subsystem (resolved)

**Resolved: `bulk-pairing` is a batch seeder, not a tournament engine, so it does
not duplicate the server subsystem.** It only materializes an explicit,
caller-supplied list of pairings; it does not compute pairings, run rounds, or
track standings, which stay the server's tournament concern (Swiss + bracket).
The two sit on opposite sides of that boundary, and the boundary is now stated in
the `bulk-pairing` description.

## 7. Challenge-cancel endpoint + event (resolved)

**Resolved: added.** `POST /api/challenge/{challengeId}/cancel` lets the
challenger withdraw a still-pending challenge, and a `challengeCanceled` event
notifies the challenged account. The `canceled` challenge status is now
reachable.

## 8. Organizer-settable `rated`

Whether organizers should be able to request `rated` at all on bulk pairing, or
whether rated-ness should be fully server-decided like single challenges.

## 9. Work-list

Items deferred from the first proposal:

- **Rating internals.** The rating model (formula and deviation) and provisional
  handling are resolved below; the anchor (the scale's zero point) is still open.
  - **(resolved) Uncertainty model: Glicko rating-deviation (RD).** The original
    Glicko, not Glicko-2. RD is a per-rating confidence that tightens as a bot
    plays and widens with inactivity, and it weights opponent strength, which is
    what the "2/2 versus strong should not outrank 9/10 versus weak" goal needs.
  - **Glicko-1, not Glicko-2.** Glicko-2 adds a volatility term for erratic
    performance; that is partly redundant here, since version epochs already
    model a bot's strength step-changes. Glicko-1 is simpler and sufficient.
  - **Wilson score is reserved, not the ladder model.** A Wilson score interval
    scores a raw win rate: it ignores opponent strength and assumes a single
    fixed win probability, so it breaks the opponent-weighting the ladder needs.
    Reserve Wilson only for a fixed-benchmark anchor (a frozen puzzle or position
    set, option D below), where every attempt is exchangeable and the Wilson
    lower bound is a clean, calibrated score.
  - **Implementation summary** (original Glicko, glicko.net):
    - New or unrated bot: rating 1000, RD 350. The starting rating matches the
      HeXO server's player ladder (players start at 1000), not Glickman's
      conventional 1500: the rated-for-bot-only anchor (option B) pulls bots onto
      the player scale, so the two must share one zero point and one estimator
      (the "one scale and one estimator" option-B consequence above). The scale
      spacing (`q = ln(10)/400`, a 400-point gap = 10:1 odds) and all the RD math
      below are independent of the zero point and unchanged; only the starting
      rating differs from the textbook default.
    - Outcomes are win or loss only (bots are draw-free), so `s` is in {1, 0}.
    - A rating period groups its games as simultaneous; the paper recommends
      roughly 5 to 10 games per player per period, which maps naturally to a
      round-robin batch.
    - Per-period RD inflation for inactivity:
      `RD = min(sqrt(RD_old^2 + c^2 * t), 350)`, `t` in rating periods. Choose
      `c` by deciding how many idle periods should return a typical RD to the
      350 maximum; the paper's worked example gives `c ~= 63.2`.
    - Update step, with `q = ln(10)/400 = 0.0057565`:
      - `g(RD) = 1 / sqrt(1 + 3 q^2 RD^2 / pi^2)`
      - `E = 1 / (1 + 10^(-g(RD_j) (r - r_j) / 400))`
      - `d^2 = (q^2 * sum_j g(RD_j)^2 E (1 - E))^-1`
      - `r' = r + (q / (1/RD^2 + 1/d^2)) * sum_j g(RD_j) (s_j - E)`
      - `RD' = sqrt((1/RD^2 + 1/d^2)^-1)`
    - The 95% interval is `r +/- 1.96 RD`.
    - Floor RD at about 30 so a very active bot's rating can still move.
    - Glicko's update is intrinsically asymmetric (an opponent's change depends
      on both RDs), which suits the player-anchor path (option B): a bot's rating
      can update from games versus established players while the player's rating
      is held fixed, pulling the bot toward the player scale. The option-B
      caveats below (count only established low-RD players, cap gain per
      opponent) stay as the anti-farming note.
    - On a version performance-shift, raise the bot's RD (reopen uncertainty)
      rather than hard-resetting; this reuses the version-epoch mechanism.
  - **(resolved) Provisional handling.** A rating is provisional while its RD is
    above a threshold (around 110) and becomes established after enough games
    (roughly 15 to 20), with provisional ratings moving in larger steps. This
    mirrors common practice (for example Lichess). The one contract-visible
    sliver this implies is an optional, server-derived `provisional` boolean on
    the rating (`Player`, `BotInstance`, `BotListing`): `true` while RD is above
    the provisional threshold, omitted or `false` once established;
    server-authoritative and read-only like `rating`. It is informational only
    and does **not** gate matchmaking or rated-ness, a provisional bot still
    rates normally. Gated on the server emitting RD-based provisional status: a
    ready-to-add field, not added to the contract in this pass.
  - **The anchor question (still open).** A bot round-robin yields only *relative* ratings:
    a closed pool free-floats, its zero point arbitrary and comparable to
    nothing external. Pinning the scale to anything outside the pool needs
    exactly one anchor. Which anchor is open; the options below, none chosen:
    - **A. Closed pool, round-robin only.** Simplest. Ratings are internally
      consistent but externally meaningless: no claim about absolute strength.
    - **B. Player cross-play as anchor.** A bot's rating updates from its games
      against players while the player's rating is unaffected, pulling bots onto
      the player scale. Consequences:
      - A one-sided update, where the bot moves and the player does not, is not
        Elo-conservative. It is defensible only as a one-directional pull
        toward a frozen, trusted reference, not as symmetric play.
      - It assumes players and bots share one scale and one estimator, else
        equal numbers are not comparable.
      - Farming and collusion surface: pumping a bot off weak or provisional
        players, or a confederate dumping games. The same-owner-unrated rule
        does not catch this, since the player is not owner-linked. Candidate
        mitigations: count only games versus established low-RD players, cap
        gain per opponent, rate-limit.
      - It revises the earlier baseline that player-vs-bot games are unrated
        exhibitions. **Resolved: rated-for-bot-only** (the bot's rating updates,
        the player's does not), accepting the asymmetry and its costs. The
        asymmetry itself and the farming mitigations still need server-side
        specification.
    - **C. Calibrated reference bot as anchor.** One declared-strength
      reference bot fixes the zero; the round-robin propagates from it. No
      players, no asymmetry, no farming surface. Costs: partially reopens the
      stance that no engine entity carries trust or rating leverage, and it
      requires trusting the reference's declared strength.
    - **D. Fixed external benchmark as anchor.** A frozen position or puzzle
      set of known difficulty fixes the zero; scoring against it needs neither
      players nor a trusted reference bot. Costs: the benchmark must be built
      and frozen, and a static set can be overfit, decaying as an anchor as
      engines train against it.
    - These can combine: a reference bot or benchmark can fix the zero while
      occasional player cross-play calibrates it (hybrid), and a ladder with no
      direct anchor can borrow one transitively through bots rated on two
      ladders at once (a bridge). Each combination inherits the costs of its
      parts.
  - Holds for any choice here: on its own the single time-control ladder is
    relative-only. Player cross-play (option B) is now the **selected live anchor
    path**: with player-vs-bot games rated-for-bot-only (resolved above), a bot's
    rating updates from its games against established players while the player's
    rating is held fixed, pulling bots onto the player scale. Options C and D
    remain available to anchor without players and are not foreclosed.
  - The gate is lifted, not the whole design. Option B was gated on the
    **Player-vs-bot play** item below (whether players belong in the rated loop
    at all); rated-for-bot-only settles that yes-for-the-bot, so options A, C, and
    D are still decidable now and B is live. Still open within B: the one-sided
    update asymmetry and the anti-farming mitigations (count only established
    low-RD players, cap gain per opponent, rate-limit) are unspecified. They are
    server-side and recorded in `SERVER-NOTES.md`. So the anchor is no longer
    free-floating in principle, but its full design is not finished.
- Handle re-layering (stable id vs display handle changes over time).
- Bot concurrency: the precise meaning of `openForChallenge` when an instance is
  already in one or more games.
- **Player-vs-bot play.** How a player reaches a bot from the website (the entry
  path) is open and mostly server/web policy: from the bot's wire view a player
  challenge is identical to a bot one (a `Player` in the challenger slot without
  `title: BOT`), so the contract surface does not change. The one
  contract-relevant decision inside it, rated-ness, is settled: player-vs-bot
  games are **rated-for-bot-only** (see the anchor entry above), which selects
  player cross-play as the live anchor path.
- **Moderation (parked, not addressed this pass).** Covers report, force-reset,
  owner ban, and Sybil resistance (per-owner registration caps, account-age
  gates, rate limits). Pulled forward by the multi-instance pattern, which widens
  the Sybil surface (one owner, many instances), and loosely gated on identity
  (handle re-layering) and operator-granting. Not designed here.
- Engine brand / self-description fields. **Partially resolved:** an opt-in,
  label-only `engineDescription` (short free text, cosmetic) now ships on
  registration and the roster; richer structured brand metadata stays deferred.
- Operator-granting of scopes (how `bot:organize` is issued).
- Seek-board (open challenge pool rather than direct handle challenges).
