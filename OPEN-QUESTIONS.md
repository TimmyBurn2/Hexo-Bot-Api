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

## 5. Tournament fairness for bulk pairing

Whether bulk pairing should balance who opens, so each bot plays Player 1 at
least once across a batch. A fixed minimum-match rule is likely not the right
mechanism, so the exact approach is unbaked. `firstPlayer` on a single challenge
is a per-game request, not a batch-level fairness guarantee.

## 6. Bulk pairing vs the server's tournament subsystem

The server already has a tournament subsystem (Swiss + bracket). Does the spec's
`bulk-pairing` duplicate server-owned tournament logic, and should it instead
expose the existing system rather than carry its own pairing surface?

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
    - New or unrated bot: rating 1500, RD 350.
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
    mirrors common practice (for example Lichess). The only contract-visible
    sliver this implies is a possible future optional `provisional` flag on the
    rating; it is not added in this pass.
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
      - It contradicts the current baseline that player-vs-bot games are unrated
        exhibitions. Pick one: fully unrated (no anchor), or rated-for-bot-only
        (accept the asymmetry and its costs).
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
    relative-only. Player cross-play (option B) is the live path that would tie
    it to an external player scale through direct play; options C and D anchor
    it without players. None is chosen here.
  - Dependency: options A, C, and D are decidable now. Option B and any other
    player-anchoring path are gated on the **Player-vs-bot play** item below
    (whether players belong in the rated loop at all); settle that first.
- Handle re-layering (stable id vs display handle changes over time).
- Bot concurrency: the precise meaning of `openForChallenge` when an instance is
  already in one or more games.
- Player-vs-bot play.
- Moderation (reporting, bans, abuse handling).
- Engine brand / self-description fields. **Partially resolved:** an opt-in,
  label-only `engineDescription` (short free text, cosmetic) now ships on
  registration and the roster; richer structured brand metadata stays deferred.
- Operator-granting of scopes (how `bot:organize` is issued).
- Seek-board (open challenge pool rather than direct handle challenges).
