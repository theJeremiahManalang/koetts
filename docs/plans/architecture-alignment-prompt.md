# Assign one implementation scope

The [implementation plan](architecture-alignment-plan.md) owns scope definitions,
prerequisites, acceptance criteria, and completion-report requirements. Use this
single prompt with the requested scope ID; verify eligibility against current
acceptance evidence rather than assuming a fixed next scope.

```text
Implement scope <S0–S5> only from docs/plans/architecture-alignment-plan.md.
Read applicable AGENTS.md instructions, docs/ARCHITECTURE.md, and
 docs/TARGET_DESIGN.md. Read CONTEXT.md only for relevant task handoff state.
Inspect existing code and working-tree changes before editing.
Before implementation, apply docs/agents/prompt-approval.md to this assignment.
For scopes after S0, verify prerequisite evidence in docs/STATUS.md.
Surface blocking decisions during preparation; execute within the approved scope.
Preserve the local studio and existing engine contracts. Run relevant checks and
record exact acceptance evidence and blockers in docs/STATUS.md.
Stop at the assigned scope boundary. Paid generation, publication, and deployment
require task authorization; existing authorization remains valid.
```

This prompt selects a scope; the prompt-approval guide owns the approval procedure.
It does not authorize later scopes or cloud mutations.
Original expanded prompts are retained in [the archive](../archive/architecture-alignment-prompt.md).
