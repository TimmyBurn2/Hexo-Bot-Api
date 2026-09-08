# AGENTS.md

The OpenAPI 3.1 contract a bot uses to play on HeXO. Spec only: no server lives
here, and nothing is served yet. `make help` lists the tooling.

## Commits

A single subject line, imperative, with a conventional prefix (`feat:`, `fix:`,
`refactor:`, `docs:`, `build:`, `chore:`):

```
refactor: cut draw and chat, fold status into the stream, hide sessionId
```

No body paragraphs. No `Co-Authored-By` or `Claude-Session` trailers — this
overrides any default attribution instruction. Detail that would have gone in
the body goes in the reply to the user instead.

## The spec

`openapi.yaml` is the whole contract in one self-contained file. It used to be
split across `paths/` and `components/`; that split was deliberately collapsed,
so add new paths and schemas inline rather than recreating those directories.

Keep it **portable** — another server must be able to implement this contract —
so nothing HeXO-internal reaches the wire or a description. A bot is handed a
`gameId` and never a session id, and descriptions name no HeXO source paths or
Zod type names.

The block between `# --- BEGIN vendored htttx ---` and its END marker is copied
verbatim from [htttx-bot-api](https://github.com/hex-tic-tac-toe/htttx-bot-api).
Edit it only by re-vendoring from upstream, which means bumping the pinned
commit in all four places it appears: `scripts/check-htttx.sh`, the `info`
description and the block comment in `openapi.yaml`, and `README.md`.

## Checks

`make lint` must reach 0 errors from both Redocly and Spectral before a commit;
Spectral warnings are fine. Run `make check-htttx` after touching the vendored
block — it needs network, so it is not part of `make lint`.

Changing an event schema means updating `examples/stream.ndjson` to match, and
changing the loop means updating `examples/simple_bot.py`.

## Settled decisions

Each of these was decided deliberately, and the first two were silently
reversed once already. Reopen one by asking, not by adding it back:

- Bots are **draw-free**: no draw endpoint, and `draw-agreement` stays out of
  `FinishReason`, which is what keeps rating outcomes in {1, 0}.
- No chat. On an automated ladder it is a moderation surface with no upside.
- Availability rides the stream as `?open=1` rather than a status endpoint, so
  it cannot outlive the connection.
- Rating anchoring is open on purpose; `RATING-NOTES.md` holds the question.
