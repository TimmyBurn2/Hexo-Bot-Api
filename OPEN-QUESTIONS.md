# Open questions

Tracked design questions for the HeXO bot protocol. This file is intentionally
**not referenced from the spec**: the contract must read on its own. It is a
working list, not part of the contract.

## 1. Playable-frontier rule: descriptive or normative?

The coordinate space is unbounded integer axial, but a cell is legal only within
hex-distance 8 of an already-placed stone (the server's `PLACE_CELL_HEX_RADIUS`
is 8), so the legal region is a bounded frontier that expands as stones are
placed. The spec now states this rule descriptively, enough for a bot to
self-validate.

- **Option A:** keep it descriptive only, as now. A bot may self-validate, but
  the server stays the sole authority and rejects an out-of-frontier placement
  with `422 out-of-bounds`.
- **Option B:** make self-validation a normative part of the contract (a bot
  MUST place within the frontier), not just a stated rule.

Tension: the wire is stateless, bots rebuild the board from the cumulative move
list. The radius-8 rule is enough to self-validate, but the server remains the
referee under either option.

## 2. Time-control union

The server's time control is a union: `unlimited`; `turn` (a per-turn cap
`turnTimeMs`, default 45000 ms); and `match` (`mainTimeMs` + `incrementMs`). The
server default is `turn`, the per-move-budget mode. The spec currently exposes
only a single match-style clock (`initial` + `inc`).

- Mirror the full union, or keep the match-style subset?
- If mirroring, note that `turn` (a per-move budget) is the server default and
  is not expressible as a single `initial` + `inc` clock.

## 3. Opening auto-play

The server auto-plays the opening hex at `[0, 0]`; the spec's bot loop instead
has Player 1 submit the opening itself as ply 0 (a single centre hex). Reconcile
which the wire API uses. It affects the one-stone case of `MoveSubmit`,
`CompoundMove`, the bot loop, and `Side` (which all state that `p1` opens with a
single centre hex).

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

## 7. Challenge-cancel endpoint + event

The `canceled` challenge status is currently unreachable: no operation or event
produces it. Decide whether to add a challenge-cancel endpoint plus a matching
event on the global stream.

## 8. Organizer-settable `rated`

Whether organizers should be able to request `rated` at all on bulk pairing, or
whether rated-ness should be fully server-decided like single challenges.

## 9. Work-list

Items deferred from the first proposal:

- Rating internals (formula, provisional handling, deviation).
  - **The anchor question.** A bot round-robin yields only *relative* ratings:
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
- Engine brand / self-description fields.
- Operator-granting of scopes (how `bot:organize` is issued).
- Seek-board (open challenge pool rather than direct handle challenges).
