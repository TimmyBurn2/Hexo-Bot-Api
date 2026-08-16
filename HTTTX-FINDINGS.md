# htttx findings for BSoD (proposed text)

This is a findings doc produced by the HeXO side. It is **not** a commit into
the htttx-bot-api repo; it is proposed text for BSoD to review and land. Each
item cites the htttx file and line, states the contradiction, and proposes one
resolution.

Grounded in `definitions/basic_websocket/bws-v1-alpha.yaml`,
`definitions/stateless/stateless-v1-alpha.yaml`, and
`definitions/bot-api-v1.yaml` at commit `37d2385`.

## 1. request_id apply-vs-discard contradiction (bws)

**Where.** `bws-v1-alpha.yaml` `MoveRequestPacket.request_id` (lines 142-162)
and `MoveResponsePacket.request_id` (lines 192-199), and the `MoveOption`
illegal-move clause (lines 283-298).

**The contradiction.** `MoveRequestPacket.request_id` says the client "discards,
and does not apply, any move_response whose id is not the outstanding one"
(lines 154-155). `MoveResponsePacket.request_id` repeats this: "A response that
does not echo the outstanding request_id is discarded and not applied to the
board" (lines 196-197). But `MoveOption` (lines 283-298) lists "a response that
does not echo the outstanding request_id" as one of the **illegal-move** cases
and says "On an illegal move a server MAY drop the connection and SHOULD NOT
apply the move." Discard-not-apply and illegal-move-should-not-apply are two
different framings of the same event: one treats a wrong-id answer as silently
dropped (the next move_request supersedes it), the other treats it as a
forfeitable offence. A reader cannot tell which applies.

**Proposed rule (one sentence to add, replacing the ambiguity).** On a session
that assigns `request_id`: an answer that does not echo the outstanding id is
**discarded and not applied to the board**; it is not itself a board-level
illegal move (it is not a placement on an occupied cell, out of range, etc.).
What happens next is the **play layer's** call, not bws's: the play layer may
forfeit the side (HeXO forfeits as `illegal-move`), time it out, or wait for a
re-answer. This keeps `MoveOption`'s illegal-move list to board/turn/range
shape faults and removes the overlap with id-matching. The HeXO profile pins
the play-layer consequence as a forfeit, but that pinning lives in the HeXO
`EngineSession` binding, not in bws; bws should only state the discard.

Concretely: delete the "a response that does not echo the outstanding
request_id" bullet from `MoveOption`'s illegal-move list (lines 293-294), and
leave the discard rule in `MoveRequestPacket.request_id` / `MoveResponsePacket.request_id`
as the single authority for the discard. The play-layer consequence stays out
of bws.

## 2. Reverse-connection capabilities (bot-api-v1 / bws)

**Where.** `bot-api-v1.yaml` `capabilities.json` (the GET fetch model), and the
bws capability flags referenced as `"basic_websocket.v1-alpha.*" in the bot's
capabilities.json`.

**The issue.** `capabilities.json` is specified as fetched by GET on the bot,
which assumes the client dials the bot (the canonical htttx deployment: the
server dials a bot-hosted `/game` websocket and GETs `capabilities.json`). In
the HeXO session the direction is inverted: the bot dials out to the server's
`socketUrl` (reverse connection), so the server never GETs the bot. Capabilities
therefore arrive out-of-band, declared at register time on the HeXO side, not by
GET. The current bws text assumes the GET path and does not acknowledge the
reverse-connection case.

**Proposed acknowledgement (a short note in bot-api-v1 / bws).** Add a note
that a deployment where the bot dials out (reverse connection) MUST deliver the
bot's `capabilities.json` out-of-band, not by GET; the server treats the
declared capabilities as authoritative for the session. The GET fetch remains
the canonical path for the dial-in deployment. This does not change the
capability object shape, only the delivery channel.

## 3. First-request shape: opening delivery

**Where.** `bws-v1-alpha.yaml` `GameSetupPacket` (lines 74-93) and
`MoveRequestPacket.previous` (lines 115-134).

**The issue.** The HeXO server auto-places the opening at the origin as a
single-stone turn (the opener places one cross, then the turn passes to the
other side with a two-stone budget). The opening is delivered in the `setup`
packet's `board.cells` (exactly one cross at the origin), and the first
`move_request` a bot receives carries `previous: []` (the opening is not in the
move ledger as a two-stone move). This is consistent with the bws spec as
written: `GameSetupPacket` carries the initial board, and `previous` is "moves
made since the last move request." No bws change is required for the HeXO
profile; this item is recorded only to document the delivery shape so a reader
does not assume the opening appears in `previous`.

**Proposed text (a short note in `GameSetupPacket`).** Add: "On a session where
the server auto-plays a single-stone opening (the HeXO profile), the opening
placement is delivered in this `setup` packet's `board.cells`, not in any
`move_request.previous` entry. The first `move_request` carries `previous: []`."
This is a clarification, not a shape change.

## 4. Note for BSoD: these are HeXO-profile pinning, not bws changes

Items 1 and 3 can be resolved two ways: (a) bws acknowledges the HeXO profile
shape and clarifies the text as proposed, or (b) bws stays generic and the
HeXO spec carries the pinning (the HeXO `EngineSession` binding now states
that `request_id` is required on a HeXO session and that the opening is
delivered in `setup`, not `previous`). Our preference is (a) for the discard
rule (it is a bws ambiguity regardless of profile) and (b) for the opening
delivery (it is arguably HeXO-specific and bws already supports it). We defer
to BSoD; the HeXO side has already pinned both in its `EngineSession` binding
so the contradiction is resolved on our side either way.
