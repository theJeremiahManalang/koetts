# Assign one implementation scope

The [implementation plan](architecture-alignment-plan.md) owns scope definitions,
prerequisites, acceptance criteria, and completion-report requirements. Use this
single prompt with the requested scope ID; S0 is the next eligible assignment.

```text
Implement scope <S0–S5> only from docs/architecture-alignment-plan.md.
Read applicable AGENTS.md instructions, docs/architecture.md, and
 docs/target-design.md. Read CONTEXT.md only for relevant task handoff state.
Inspect existing code and working-tree changes before editing.
For scopes after S0, verify prerequisite evidence in docs/alignment-status.md.
Resolve open decisions that block this scope; continue independent authorized work.
Preserve the local studio and existing engine contracts. Run relevant checks and
record exact acceptance evidence and blockers in docs/alignment-status.md.
Stop at the assigned scope boundary. Paid generation, publication, and deployment
require task authorization; existing authorization remains valid.
```

This prompt selects a scope; it does not authorize later scopes or cloud mutations.
Original expanded prompts are retained in [the archive](archive/architecture-alignment-prompt.md).
