# HeXO Bot API

> **Status: WIP, not yet implemented.**

> This repository is a *proposed* bot protocol for HeXO, published for review.
> No server currently serves these endpoints; they still need to be implemented.
> Names, shapes, and paths may change before a `1.0.0` release.
> Treat this as a request-for-comment, not a finalized contract.

The **bot protocol contract** for [HeXO](https://hexo.did.science), the [OpenAPI 3.1](./openapi.yaml) spec a bot speaks to play on `https://hexo.did.science`.

**Just the contract:** spec + this README.
No server, no bot; those are separate programs that agree only on `openapi.yaml`.
A reference bridge (bot adapter) is planned as its own repo.
Modelled on the [Lichess Bot/Board API](https://github.com/lichess-org/api).

---

## 1. What this is

- **Server (proposed):** `https://hexo.did.science`
- **Product:** [`openapi.yaml`](./openapi.yaml) (split into [`paths/`](./paths) and [`components/`](./components)) + this README.
- **Game:** `httt6`, HeXO's hexagonal tic-tac-toe.
  The coordinate space is unbounded (integer **axial coordinates** `[q, r]`, any value), but a cell is legal to play only within hex-distance 8 of an already-placed stone, so legal placement is a bounded frontier that widens as stones are placed: at the opening only the centre `[0, 0]` is available.
  **The server auto-plays the opening single centre hex on Player 1's behalf; every turn after that places two hexes.**
  Win by connecting **six** of your own hexes in a straight line along any of the **3 board axes**.
  The variant key is defined once in [`components/schemas/Variant.yaml`](./components/schemas/Variant.yaml) and must match the server's registry.
- **Sides:** the two players are identified by **play order, `p1` and `p2`** (not colours; the game UI renders colours, the protocol does not).
  Defined once in [`components/schemas/Side.yaml`](./components/schemas/Side.yaml).
- **Examples:** runnable-shaped samples in [`examples/`](./examples).

---

## 2. Current API at a glance

What the contract lets a bot do today. Every call is authenticated with a Personal Access Token (`Authorization: Bearer hxo_...`). An operator registers instances with a `bot:register` token; each registered instance gets its own `bot:play` token. `bot:organize` covers bulk pairing.

| Area | Operation | What it does |
| --- | --- | --- |
| **Account** | `POST /api/bot/register` | Register a bot instance and receive its own scoped token. Requires `bot:register`. |
| **Account** | `GET /api/account` | Whoami: your id, owner, rating, and opt-in hardware label. |
| **Streaming** | `GET /api/stream/event` | Global event stream: challenges, game start and finish. |
| **Streaming** | `GET /api/bot/game/stream/{gameId}` | Per-game stream: full state on connect, then live updates. |
| **Play** | `POST /api/bot/game/{gameId}/move` | Submit your compound move, guarded by the compare-and-set `ply`. |
| **Play** | `POST /api/bot/game/{gameId}/resign` | Resign a game. |
| **Play** | `POST /api/bot/status` | Advertise whether you are taking challenges. Held only while your event stream is connected; surfaced as `openForChallenge` in the directory. |
| **Directory** | `GET /api/bots` | Browse the public bot roster to find an opponent. Cursor-paged; filter by variant, owner, or `openForChallenge`. |
| **Challenges** | `POST /api/challenge/{handle}` | Challenge an account you know by handle. The authoritative availability check: `409` if the target is not accepting. |
| **Challenges** | `POST /api/challenge/{challengeId}/accept` | Accept a challenge. |
| **Challenges** | `POST /api/challenge/{challengeId}/decline` | Decline a challenge. |
| **Challenges** | `POST /api/challenge/{challengeId}/cancel` | Cancel a challenge you issued (still pending). |
| **Organizer** | `POST /api/bulk-pairing` | Seed many games at once for an eval ladder. Requires `bot:organize`. |

Every game carries a time control (`unlimited`, `turn`, or `match`; see section 4). Whether a game is rated is decided by the server, not the caller.

---

## 3. How a move works

A HeXO **turn** places hexes on the board, and the protocol models one turn as a single object, a *compound move*, because a normal turn is two hexes at once.

**Coordinates.**
Every cell is an **axial coordinate** `[q, r]` (two integers).
`q` runs along one axis, `r` along another; the implied third axis is `s = −q − r`.
The centre is `[0, 0]`. The coordinate space is unbounded, so `q`/`r` can be **any integer, including negatives**, but a cell is legal to play only **within hex-distance 8 of an already-placed stone**, so the playable region is a bounded frontier that widens as stones are placed.
The hex-distance between `[q1, r1]` and `[q2, r2]` is `(|q1−q2| + |r1−r2| + |(q1+r1)−(q2+r2)|) / 2`; a bot can use this to self-validate a candidate before submitting. Pre-validation is optional: the server is the sole authority and rejects an out-of-frontier placement with `422 out-of-bounds`, which the bot must handle.
A cell's six neighbours are the six axial directions: `[+1,0] [+1,−1] [0,−1] [−1,0] [−1,+1] [0,+1]`.
You win with six of your hexes in a line along one of the three axes.

**The opening is asymmetric:**

| Ply | Side | Hexes placed |
| --- | --- | --- |
| 0 | `p1` | **1** (the centre, `[0,0]`) |
| 1 | `p2` | 2 |
| 2+ | alternating | 2 each |

Ply 0 is **auto-played by the server** on `p1`'s behalf; a bot never submits it. The first turn a bot submits is ply 1 (`p2`), and every submitted turn places two hexes.

**Down-stream: what the server sends you.**
Inside every `gameState`, `moves` is the **cumulative** list of all turns so far:

```json
"moves": [
  { "p": "p1", "s": [[0,0]] },          // ply 0: server-placed opening single hex at centre
  { "p": "p2", "s": [[0,1],[1,1]] },    // ply 1: two hexes
  { "p": "p1", "s": [[1,0],[2,0]] }     // ply 2: two hexes
]
```

- **`p`**: the side that made the turn (`p1` or `p2`).
- **`s`**: the hex(es) placed that turn, each an `[q, r]` axial coordinate (length 1 only on the server-placed ply-0 opening, otherwise 2).
- **Position in the array = the ply** (0-based).
  The list **grows by one entry each turn**, turn 5's `moves` contains turns 0-4 plus turn 5.
  That is what makes the protocol stateless:
  you replay this list from scratch to rebuild the board, so you never store anything locally.

**Up-stream: what you send back.** When it's your turn you POST a `MoveSubmit`:

```json
{ "stones": [[3,0],[4,0]], "ply": 4 }
```

- **`stones`**: the two hexes you're placing. A submitted turn is always two hexes; the server auto-plays the opening, so you never send a single stone.
- **`ply`**: which turn index you're filling. It must equal the server's next expected ply:
  this is a **compare-and-set token** that makes retries safe.
  A stale/duplicate `ply` → `409 { expectedPly }`;
  an illegal placement → `422 { stone }`.
  You **don't** send your side; the server knows whose turn it is from the ply.

---

## 4. Design philosophy (the ideas behind it)

**The server is the referee.**
It is the single source of truth for legality, turn order, pairing, clocks, and ratings.
Bots never adjudicate; they ask, and the server decides.

**A proposal layered on the server.**
This contract is a proposal over the existing HeXO server, not a parallel design.
It mirrors or exposes concepts the server already implements rather than duplicating server-owned logic, and where the two differ the server is authoritative.

**Bots own everything else.** State, reconnection, search, and time management are the bot's problem.
The contract assumes nothing about how a bot thinks.

**Stateless by design.**
Both streams send the **cumulative** move list, not deltas. A bot replays it to rebuild the board -> zero required local state.
A crash mid-game won't cause a problem.
Reconnect and receive a fresh `gameFull`, replay and continue. (See [`examples/bot-loop.md`](./examples/bot-loop.md).)

**Bot-agnostic.**
Nothing depends on any particular bot's internals. **KrakenBot** and **SealBot** in the examples are illustrative only.

**One ladder, one time control per game.** Every game carries a time control set
on the challenge: `unlimited`, `turn` (a per-turn budget `turnTimeMs`, the server
default at 45000 ms), or `match` (`mainTimeMs` plus `incrementMs` per side).
Under `turn` or `match`, ratings measure the whole engine, speed included.

**Hardware telemetry is a label.**
A bot may *opt in* to a coarse self-report (`HardwareInfo`:
GPU class, CPU cores, RAM GB) at registration time.
It is shown as a **label only** and is **not used as a rating or pairing input**:
the server never feeds it into the rating formula or pairing.
Under a timed control (`turn` or `match`) faster hardware can still affect
results through move speed; the label itself carries no rating weight.
No serials, MAC addresses, or hostnames are collected.

---

## 5. Rendering & linting the docs

The spec is the product, so it is kept lint-clean and renderable.
You only need Node.js (`npx`); nothing is installed globally.

```bash
make docs      # render a static HTML reference (Redocly build-docs → dist/index.html)
make preview   # live-reloading docs preview
make lint      # Redocly + Spectral, must be 0 errors
make bundle    # resolve every $ref into one self-contained file
```

Or call the tools directly:

```bash
npx @redocly/cli@latest lint openapi.yaml
npx @redocly/cli@latest bundle openapi.yaml -o dist/openapi.bundled.yaml
npx @stoplight/spectral-cli@latest lint dist/openapi.bundled.yaml
npx @redocly/cli@latest build-docs openapi.yaml -o dist/index.html
```

> Note: Spectral is run against the **bundled** spec.
> Its external-`$ref` resolver mis-flags multi-file 3.1 path items; the bundle is semantically identical and lints clean.
> `make lint` and CI handle this for you.

CI runs the same checks on every push and PR, see [`.github/workflows/lint.yml`](./.github/workflows/lint.yml).

---

## 6. Contributing & roadmap

This repo is a **community proposal**, and contributions that sharpen it are welcome:

- Extend or clarify the spec via pull request; keep it lint-clean (`make lint` → 0 errors) and every operation fully documented (`operationId`, `summary`, `tags`, responses with schemas + an example).
- **Settle the rating scale.** Bot ratings are relative; whether and how they anchor to a wider scale is an open question, see [`OPEN-QUESTIONS.md`](./OPEN-QUESTIONS.md).
- Coordinate new variants or fields with the server's registry; the `Variant` and `Side` keys here must match what `hexo.did.science` accepts.
- **Implement it.** This is a proposal; the endpoints still need to be built on the server side, and a reference **bridge** (a ready-to-run bot adapter that speaks this protocol) is planned as a **separate** repository. This repo stays spec-only.
- **Add a quickstart.** A step-by-step walkthrough (register an instance → receive its token → stream events → accept a challenge → play), built on the files in [`examples/`](./examples), is planned; it was left out of this first proposal to keep the focus on the contract itself.

---

## 7. Thanks

Thanks to the **HeXO community**:

---

## 8. License

[MIT](./LICENSE)
