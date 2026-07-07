# HeXO Bot API

> **Status: WIP, not yet implemented.**

> This repository is a *proposed* bot protocol for HeXO, published for review.
> No server currently serves these endpoints; they still need to be implemented.
> Names, shapes, and paths may change before a `1.0.0` release.
> Treat this as a request-for-comment, not a finalized contract.

The **bot protocol contract** for [HeXO](https://hexo.did.science), the [OpenAPI 3.1](./openapi.yaml) spec a bot speaks to play HeXO. The reference host is `https://hexo.did.science`; the contract is implementable by any host serving a HeXO variant.

**Just the contract:** spec + this README.
No server, no bot; those are separate programs that agree only on `openapi.yaml`.
A reference bridge (bot adapter) is planned as its own repo.
Modelled on the [Lichess Bot/Board API](https://github.com/lichess-org/api).

---

## 1. What this is

- **Reference server (proposed):** `https://hexo.did.science`. The contract is implementable by any host serving a HeXO variant.
- **Product:** [`openapi.yaml`](./openapi.yaml) (split into [`paths/`](./paths) and [`components/`](./components)) + this README.
- **Scope:** this spec is the **server and ladder layer** only: identity, registration, matchmaking, challenges, ratings, and game lifecycle. The per-game move exchange is the **[htttx engine protocol](https://github.com/hex-tic-tac-toe/htttx-bot-api)** (pinned at commit `37d2385` for this proposal), reached through the session a `gameStart` event hands you; it is not in this repo.
- **Game:** the reference host serves `httt6`, HeXO's hexagonal tic-tac-toe.
  The board geometry and rules of play (coordinates, legal placement, the opening, win conditions) belong to the **engine protocol**, not this contract; here the variant key is just the label carried on challenges and games.
  The `Variant` field is defined once in [`components/schemas/Variant.yaml`](./components/schemas/Variant.yaml) as an open, server-scoped string; extending the value set is a server-side registry change, not a spec edit.
- **Sides:** the two players are identified by **play order, `p1` and `p2`** (not colours; the game UI renders colours, the protocol does not).
  Defined once in [`components/schemas/Side.yaml`](./components/schemas/Side.yaml).
- **Examples:** runnable-shaped samples in [`examples/`](./examples).

---

## 2. Current API at a glance

What the contract lets a bot do today. Every call is authenticated with a Personal Access Token (`Authorization: Bearer hxo_...`). An operator registers instances with a `bot:register` token; each registered instance gets its own `bot:play` token. `bot:organize` covers bulk pairing.

| Area | Operation | What it does |
| --- | --- | --- |
| **Account** | `POST /api/bot/register` | Register a bot instance and receive its own scoped token, declaring its `capabilities`. Requires `bot:register`. |
| **Account** | `GET /api/account` | Whoami: your id, owner, rating, granted scopes, declared capabilities, and opt-in hardware label. |
| **Account** | `POST /api/bot/{handle}/retire` | Retire an instance you own: tombstones it and reserves the handle forever, forfeits its in-progress games as surrenders (rated normally), and cancels its pending challenges. Requires `bot:register`. |
| **Account** | `DELETE /api/token` | Revoke the calling instance's own `bot:play` token. |
| **Streaming** | `GET /api/stream/event` | Global event stream: challenge lifecycle (`challenge`, `challengeDeclined`, `challengeCanceled`, `challengeExpired`), `gameStart` (carrying the engine dial bootstrap) and `gameFinish`, plus an observe-only `opponentGone`. |
| **Bot** | `POST /api/bot/game/{gameId}/resign` | Resign (concede) a game. |
| **Bot** | `GET /api/bot/games` | List your active (in-progress) games as lightweight pointers, to reconcile after a restart. |
| **Bot** | `POST /api/bot/status` | Advertise whether you are taking challenges. Held only while your event stream is connected; surfaced as `openForChallenge` in the directory. |
| **Directory** | `GET /api/bots` | Browse the public bot roster to find an opponent. Cursor-paged; filter by variant, owner, or `openForChallenge`. |
| **Challenges** | `POST /api/challenge/{handle}` | Challenge an account you know by handle. The authoritative availability check: `409` if the target is not accepting. |
| **Challenges** | `POST /api/challenge/{challengeId}/accept` | Accept a challenge. |
| **Challenges** | `POST /api/challenge/{challengeId}/decline` | Decline a challenge. |
| **Challenges** | `POST /api/challenge/{challengeId}/cancel` | Cancel a challenge you issued (still pending). |
| **Challenges** | `GET /api/challenges` | List your pending incoming and outgoing challenges (only `created`; accepted, declined, canceled, or expired ones drop off). |
| **Challenges** | `GET /api/challenge/{challengeId}/show` | Read one challenge by id, including its terminal status (tells "bad id" apart from "just went terminal", with `declineReason` on a decline). |
| **Organizer** | `POST /api/bulk-pairing` | Seed many games at once for an eval ladder. Requires `bot:organize`. |

Every game carries a time control (`unlimited`, `turn`, or `match`; see section 4). Whether a game is rated is decided by the server, not the caller. Playing a game itself happens over the **engine protocol**: a `gameStart` event hands you a socket URL and a short-lived per-game token to connect with.

---

## 3. How a game works (where this spec stops)

This spec carries a game's **lifecycle**, not its moves. When a challenge is accepted the server creates a game and sends both players a `gameStart` event on their global event stream. That event carries an **engine dial bootstrap**:

```json
"engine": {
  "socketUrl": "wss://hexo.did.science/engine/J9kP2qLm",
  "token": "egs_4c1f9b2a7d3e"
}
```

- **`socketUrl`**: where to connect to play the game.
- **`token`**: a short-lived, per-game bearer to present on connect. It is not your Personal Access Token and is not reusable across games.

Both fields are **server-issued and read-only**. The adapter opens that session and plays over the **engine protocol**; the move exchange, board state, and answer-matching all live there, not in this contract.

When the game ends you get a `gameFinish` on the global stream carrying `finishReason` and `winner`. If an opponent drops mid-game you may see an observe-only `opponentGone` (with its `gameId`) counting down to an auto-forfeit; there is nothing to claim. To concede, `POST /api/bot/game/{gameId}/resign`: `200` on success, `409 game-finished` if it already ended, `404` once the server reaps it, so reconcile the outcome from the `gameFinish` event rather than the status code.

See [`examples/bot-loop.md`](./examples/bot-loop.md) for the full lifecycle loop.

---

## 4. Design philosophy (the ideas behind it)

**The server is the referee.**
It is the single source of truth for pairing, clocks, ratings, and game lifecycle.
Bots never adjudicate; they ask, and the server decides.

**A proposal layered on the server.**
This contract is a proposal over the existing HeXO server, not a parallel design.
It mirrors or exposes concepts the server already implements rather than duplicating server-owned logic, and where the two differ the server is authoritative.

**Bots own everything else.** State, reconnection, search, and time management are the bot's problem.
The contract assumes nothing about how a bot thinks.

**Reconnect-safe lifecycle.**
The global event stream is the one long-lived connection, and it is built to survive a crash.
It sends a blank-line keepalive **at least every 15 seconds**, so a client can set a read timeout at a small multiple of that to spot a dead socket; opening a new global event stream **closes any previous one for the same token**, so a reconnecting bot need not tear down the stale connection first; and on reconnect the server replays your active challenges and games, re-issuing a `gameStart` (with a **fresh** engine dial bootstrap) for each game still in progress so you re-dial and continue. (See [`examples/bot-loop.md`](./examples/bot-loop.md).)
Board and clock state live on the engine session, not here.

**Capabilities are a label and an eligibility marker.**
At registration an instance declares its `capabilities`: which engine modes it speaks, plus a `matchmaking` block whose presence marks it ladder-eligible.
The server treats the declaration as authoritative and echoes it read-only on whoami and the roster.
Like the hardware label, capabilities are **never a rating or pairing-strength input**.

**Bot-agnostic.**
Nothing depends on any particular bot's internals. **KrakenBot** and **SealBot** in the examples are illustrative only.

**One ladder, one time control per game.** Every game carries a time control set
on the challenge: `unlimited`, `turn` (a per-turn budget `turnTimeMs`, fine-grained
and sub-second capable for bots: 500 ms default, 45000 ms ceiling; the server's
current default value is 45000 ms with a 5000 ms player floor, so this proposes
the server accept sub-second budgets for bot games), or `match`
(`mainTimeMs` plus `incrementMs` per side).
Under `turn` or `match`, ratings measure the whole engine, speed included.

**Hardware telemetry is a label.**
A bot may *opt in* to a coarse self-report (`HardwareInfo`:
GPU class, CPU cores, RAM GB) at registration time.
It is shown as a **label only** and is **not used as a rating or pairing input**:
the server never feeds it into the rating formula or pairing.
Under a timed control (`turn` or `match`) faster hardware can still affect
results through how quickly it plays; the label itself carries no rating weight.
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
- **Settle the rating scale.** Bot ratings are relative; whether and how they anchor to a wider scale is an open question.
- Coordinate new variant keys with the serving host's registry; the `Variant` field is open and server-scoped, the `Side` keys (`p1`/`p2`) are fixed by this contract.
- **Implement it.** This is a proposal; the endpoints still need to be built on the server side, and a reference **bridge** (a ready-to-run bot adapter that speaks this protocol) is planned as a **separate** repository. This repo stays spec-only.
- **Add a quickstart.** A step-by-step walkthrough (register an instance → receive its token → stream events → accept a challenge → dial the engine session), built on the files in [`examples/`](./examples), is planned; it was left out of this first proposal to keep the focus on the contract itself.

---

## 7. License

[MIT](./LICENSE)
