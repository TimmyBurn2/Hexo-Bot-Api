# Open questions

Tracked design questions for the HeXO bot protocol. This file is intentionally
**not referenced from the spec**: the contract must read on its own. It is a
working list, not part of the contract.

## 1. Exact playable-frontier spec

The coordinate space is unbounded, but legal placement is confined to a bounded
playable region that expands outward as stones are placed. The exact expansion
rule is unconfirmed: the current server expands roughly a radius-8 region
outward from placed stones.

- **Option A:** encode the expansion rule in the variant rules, so bots can
  self-validate placement.
- **Option B:** leave it server-defined; bots learn the frontier only from
  `422 out-of-bounds` rejections.

Tension: the wire is stateless, bots rebuild the board from the cumulative move
list. Without the rule, a bot cannot self-validate placement and must rely on
the server to reject out-of-region moves.

## 2. Timeout / flag-fall terminal status

Games run on real clocks, but no terminal status models a flag-fall / timeout
loss. Decide whether to add one (and its `winner` semantics).

## 3. Challenge-cancel endpoint + event

The `canceled` challenge status is currently unreachable: no operation or event
produces it. Decide whether to add a challenge-cancel endpoint plus a matching
event on the global stream.

## 4. Organizer-settable `rated`

Whether organizers should be able to request `rated` at all on bulk pairing, or
whether rated-ness should be fully server-decided like single challenges.

## 5. Work-list

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
