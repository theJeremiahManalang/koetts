# Active task context

Updated 19 October 2026.

## Assignment and decisions

Consolidate project documentation and agent context after the confirmed alignment
interview. Documentation/harness only; runtime implementation is outside this task.
Accepted product, access boundaries, target stack, and unresolved inputs are recorded
in `docs/target-design.md`. Document authority is indexed by `docs/README.md`.
Project skills stay in `.agents/skills/`; other agent docs stay in `docs/`, except
`AGENTS.md` and `CONTEXT.md`.

## Work and verification

Consolidated current architecture, target design, and scope invocation. Preserved
historical handoff/prompts/walkthrough in `docs/archive/`; removed the root audio
workflow duplicate after confirming differences were only obsolete setup links.
Repaired instruction routing and baseline links. No runtime changes, provider calls,
cloud mutations, dependency installation, or application test execution.
Verification: local Markdown links resolve across 28 documents; manga-workflow
skill format validation passes; `git diff --check` passes. Historical application
checks remain historical. Existing user changes were preserved.

## Next action

Assign S0 explicitly to reproduce baseline checks and stabilize local execution.
S0 is not started or completed. No `docs/alignment-status.md` exists yet; create it
when recording implementation-scope evidence. Resolve dependent open decisions
before later production behavior; do not infer cloud policy from archived documents.
