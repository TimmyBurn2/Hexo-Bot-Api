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

## 2. Timeout / flag-fall terminal status (wallclock)

Wallclock games have real clocks, but no terminal status models a flag-fall /
timeout loss. Decide whether to add one (and its `winner` semantics).

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
- Handle re-layering (stable id vs display handle changes over time).
- Bot concurrency: the precise meaning of `openForChallenge` when an instance is
  already in one or more games.
- Human-vs-bot play.
- Moderation (reporting, bans, abuse handling).
- Engine brand / self-description fields.
- Operator-granting of scopes (how `bot:organize` is issued).
- Seek-board (open challenge pool rather than direct handle challenges).
