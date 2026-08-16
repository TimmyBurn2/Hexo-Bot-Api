# Integration options: htttx engine spec and the HeXO play spec

How to lay out the two specs once the per-game move exchange moves to htttx
packets. This is analysis, not a contract change.

## The shape of the coupling

The single most important fact for this decision: after the per-game move
exchange leaves this spec, the play spec and the engine move protocol are two
almost-disjoint wire surfaces.

- The play spec is HTTP plus two NDJSON lifecycle streams: auth, registration,
  matchmaking, challenges, ratings, lifecycle, the real clock. It is a set of
  OpenAPI operations.
- The engine move protocol is a long-lived packet exchange (setup /
  move_request / move_response, plus heartbeat / config / eval). It is not a set
  of HTTP operations; htttx already strains OpenAPI to describe it, declaring a
  `POST /game` that returns `101` and carrying the packets as bare component
  schemas with a `type` discriminator.

Once `game-stream`, `game-get`, `game-move`, `MoveSubmit`, `CompoundMove`,
`GameState`, `GameFull`, and `GameStreamEvent` are removed, the play spec
carries no coordinates and no move shape at all. Every coordinate lives in the
engine protocol. The only thing the play spec still needs from htttx is the
Capabilities object, ingested once at registration and echoed read-only on the
roster and whoami. That is the entire cross-repo coupling: one schema, on a
surface that changes slowly.

One caveat to that framing: the play spec also gains net-new surface of its own,
the dial bootstrap. Under the inverted socket the bot must be told where to dial
and how to authenticate the engine socket per game, which is a `gameStart`
payload (socket URL plus a short-lived per-game token) that neither repo defines
today. That is a real second coupling, but it lives entirely on the play side in
every layout option, so it does not cross the repo boundary and does not change
the layout calculus. It is listed here so "one schema" is not read as "one
schema and nothing else."

So the layout question is really: does that one-schema cross-repo dependency
justify a single repo, or is it small enough to span two?

## Does keeping htttx standalone buy anything, given both are HeXO-only?

The brief is right that "other platforms" is not a reason: htttx is hexagonal
tic-tac-toe, same game, same `hexo.did.science`. But standalone htttx still buys
two concrete things that survive the HeXO-only constraint:

1. Non-ladder transports. htttx's stateless (`POST /turn`, full board per call)
   and BWS (`/game`, setup then delta) transports are bot-hosted analysis and
   local-play surfaces: a third-party UI or the server's own in-process engine
   sandbox dials into a bot to get a move or an evaluation, with no account, no
   rating, no clock. The server already has this shape in-process today
   (`botInterface.ts`: `suggestTurn(gameState, timeoutMs) -> [coord, coord]`
   plus a `BotEngineCapabilities` object). The ladder needs none of stateless,
   BWS, `evaluation`, `dual_sided`, `free_setup`, or `interruptible`. Those are
   real engine-protocol surface with a life the ladder never touches.

2. Release cadence. htttx's transports are explicitly `v1-alpha`. The play spec
   is marching toward `1.0.0`. Folding the alpha engine protocol into the play
   spec welds the play spec's stability promise to an alpha surface, or forces
   the engine surface to freeze before it is ready.

What standalone htttx does not buy: independent governance for its own sake, or
reuse by a different game. Both repos answer to the same maintainer and the same
game. The case for two repos rests entirely on the two points above, not on
generic "decoupling is good."

## Option A: two standalone repos, play depends on htttx

Play pins htttx (git submodule at a commit, or a vendored copy of the
Capabilities schema) and references the Capabilities object from there.

- What changes: this repo removes the three per-game paths and their schemas,
  swaps `engineDescription` for the htttx Capabilities object at registration,
  and gains a pin or a vendored `Capabilities.yaml`. htttx gains an
  inverted-socket transport (see migration-plan.md). No org-level change.
- Lint / bundle / `$ref` impact: a submodule lets `make bundle` resolve a
  relative `$ref` into the submodule directory; it is just a path on disk, so
  Redocly resolves it and Spectral lints the bundled output as today. The cost
  is submodule ceremony (init, update, pin bumps) for one schema. A vendored
  copy avoids submodules entirely but reintroduces drift, mitigated by a pinned
  version marker. Either way the cross-file pain the brief warns about is
  contained, because only one stable schema crosses the boundary, not the packet
  set.
- Maintainership / PR direction: engine changes land in htttx, ladder changes
  land here, and a Capabilities change is an htttx PR followed by a pin bump
  here. Clean, but the split lives in two issue trackers with no shared release.
- htttx stays independently consumable: yes, fully.

## Option B: one org, sibling repos (recommended)

Identical wire and `$ref` story to Option A. The difference is organizational:
both repos sit under one GitHub org with one issue tracker, coordinated
releases, and an explicit ownership rule (engine surface -> htttx, ladder
surface -> play, Capabilities -> htttx then pin-bump here).

- What changes: same file moves as Option A, plus moving both repos under one
  org and writing down the ownership and release rule.
- Lint / bundle / `$ref` impact: same as Option A. The recommended coupling is a
  pinned submodule for the single Capabilities schema, so `make bundle` and
  `make lint` keep working with one extra resolve path and no remote fetch in
  CI.
- Maintainership / PR direction: the strongest part. Co-location gives one
  backlog and a single release train, so a Capabilities change and the pin bump
  that consumes it can ship together and be reviewed in one place, while the two
  specs still version independently.
- htttx stays independently consumable: yes, fully. The org boundary does not
  touch the wire.

## Option C: one repo, full merge

htttx's three YAML files fold into this repo's `components/` and `paths/`; htttx
ceases to exist as a separate spec.

- What changes: the largest diff. The Capabilities object, the packet schemas,
  and the inverted-socket transport all live here. The root `openapi.yaml` grows
  a packet-bearing surface that does not correspond to any HTTP operation in the
  play spec.
- Lint / bundle / `$ref` impact: no cross-repo refs, one `make bundle`, one
  `make lint`, one source of truth. That is the real upside. The downside is the
  inverse of htttx's own OpenAPI strain: the move_request / move_response /
  setup / heartbeat schemas have no referencing operation in the play spec
  (the move exchange is a dialed socket, not an HTTP path), so they trip
  `no-unused-components` unless anchored by the same `POST /game -> 101`
  placeholder hack htttx uses. The merge imports that hack into the play spec.
- Maintainership / PR direction: one repo, one backlog, simplest operationally.
  But the engine surface and the ladder surface now share a version number and a
  stability promise, and the inverted-socket transport, which is really an htttx
  transport concern, is owned here.
- htttx stays independently consumable: no. Analysis, sandbox, and local-play
  transports lose their standalone home, or get duplicated back out later.

## Recommendation

Option B: one org, sibling repos, play pinning htttx for the Capabilities
object only, with the per-game move protocol and the new inverted-socket
transport owned in htttx.

The reasoning is the coupling shape. The hard dependency is one slow-moving
schema, not the packet set, so a single repo is not needed to keep `$ref`s sane,
and the toolchain handles a pinned submodule cleanly. Against that thin coupling,
standalone htttx keeps two things that matter even though both specs are
HeXO-only: the stateless and BWS transports that serve analysis, sandbox, and
local play, which the ladder will never use, and an independent alpha-to-stable
cadence so the engine surface is not frozen by the play spec's `1.0.0` track.
One org gives the coordination that two bare repos lack (shared backlog, joint
release of a Capabilities change and its pin bump) without paying Option C's
costs: dragging engine-only socket schemas into an HTTP-shaped document where
they have no operation, and welding two release cadences together.

Option C is defensible if the maintainer values single-repo operational
simplicity above the standalone transports and accepts the orphan-component hack
and the cadence coupling. It is a real choice, not a wrong one, which is why it
is surfaced in open-decisions.md rather than closed here.
