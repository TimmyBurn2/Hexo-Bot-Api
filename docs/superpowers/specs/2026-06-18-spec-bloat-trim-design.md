# Spec bloat trim - medium pass

**Scope:** All YAML schema and property descriptions. Operation descriptions untouched. README/SERVER-NOTES untouched.

## Rules

1. **Repeated disclaimers.** "Label only, never a rating or pairing input" and "server-authoritative and read-only" appear in 8+ places each. Keep once at the parent schema `description`; drop from every property that repeats it.

2. **Property descriptions capped at 2 short sentences.** Anything longer that elaborates on constraints already visible in the YAML (type, pattern, enum, required) is cut to the essential part.

3. **Self-evident names.** A description that only restates the field name is dropped entirely or reduced to a one-clause phrase covering the non-obvious part.

4. **Cross-file prose.** A property description that re-explains lifecycle rules owned by an operation description shrinks to a one-liner; the full rule stays where it belongs.

5. **Never touch.** Examples, `pattern`/`enum`/`format`/`required` constraints, error response descriptions, and any unique behavioral rule not expressed elsewhere.

## What stays at medium

Operation-level descriptions in `paths/*.yaml` are left alone.

## Branch setup

Work on a new `development` branch from `main`. After lint clean + red-team: cherry-pick onto `chore/shed-gameplay-to-htttx` (resolve any conflicts from the cleanup-2 delta there).

## Approach

3 parallel agents by file group, then a read-only red-team agent.

- Agent 1: `components/schemas/*.yaml` (heaviest: Capabilities, BotListing, BotInstance, GameEventInfo, Challenge, TimeControl, Player)
- Agent 2: `paths/*.yaml` schema blocks only - inline request/response body property descriptions (not the operation description itself)
- Agent 3: `openapi.yaml` info.description subsections and tag descriptions (medium applies here too)
