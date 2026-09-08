# Rating notes

What the bot ladder inherits, and the question this leaves open.

## What the server runs today

Plain Elo, in `packages/backend/src/elo/eloHandler.ts`: ratings start at 1000,
K is 30 while a profile has fewer than 10 rated games and 15 after that, and the
result is floored at 100. There is no rating deviation and nothing provisional
on the wire. The update is symmetric: `sessionManager.ts` applies the result to
every player in the session that has a profile.

This spec keeps that unchanged for rating v1. Bots join the same Elo pool, with
three guardrails: owner-versus-own-bot games are unrated, a per-pair daily cap
on rated games, and Players / Bots / All tabs on the leaderboard. A
rating-deviation model such as [Glicko](http://www.glicko.net/glicko.html) and
the anchoring question below are deferred to their own RFC. Both change how the
server computes a number, not what this contract carries.

## The deferred question: what anchors the scale

Bots that play only each other produce ratings that are internally consistent
and externally meaningless. The pool free-floats: its zero point is arbitrary
and comparable to nothing outside itself. Pinning it needs exactly one anchor.
Four options, none of them free:

**A. Closed pool.** Bots play bots and nothing else. Simplest, and makes no
claim about absolute strength.

**B. Player cross-play.** A bot's rating updates from its games against human
players while the player's rating is held fixed, pulling bots onto the player
scale. This is what the earlier proposal favoured. It is not what rating v1
does, and it is not a setting: today's update is symmetric, so B is a server
change.

**C. Calibrated reference bot.** One bot of declared strength fixes the zero and
the pool propagates from it. No players, no asymmetry, no farming surface, but
it requires trusting the declared strength.

**D. Fixed benchmark.** A frozen set of positions of known difficulty fixes the
zero. It has to be built first, and a static set decays as engines overfit it.

These combine: C or D can fix the zero while occasional player cross-play
calibrates it. Each combination inherits the costs of its parts.

## What option B would cost

- The update becomes one-sided, so it is no longer Elo-conservative. It is
  defensible as a one-directional pull toward a frozen reference, not as
  symmetric play.
- It assumes players and bots share one scale and one estimator. If they do not,
  equal numbers on the two ladders are not comparable.
- It opens a farming surface: pumping a bot against weak or provisional players,
  or a confederate dumping games to it. The owner-versus-own-bot rule catches
  neither, because the player is not owner-linked. The per-pair daily cap limits
  how fast one confederate can feed a bot, but not how many confederates there
  are.

Unspecified if B is ever adopted: whether to count only games against
established opponents, and what the per-opponent gain ceiling should be.

## Still open

Anchoring itself is a separate RFC, not decided here.
