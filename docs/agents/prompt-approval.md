# Prompt approval

This guide owns prompt preparation and approval for substantial new implementation,
architecture, and investigation tasks. A task is substantial when it needs coordinated
changes, consequential design choices, or extended investigation. Use the requested
outcome and consequences to judge the boundary, rather than a fixed file count.

## Prepare and obtain approval

1. **Ground the request.** Inspect applicable instructions, document authority,
   working-tree changes, and targeted primary evidence using read-only operations.
   Resolve discoverable facts directly. Ask only questions whose answers materially
   change intent, scope, or tradeoffs. Stop preparation when the objective, boundaries,
   consequential assumptions, and proposed acceptance evidence can be stated.
   Broader investigation belongs to execution and waits for approval.
2. **Identify the rigor needed.** Briefly name expert practice missing from the
   request, primary evidence needed instead of summaries, specific methods and tools,
   and observable acceptance evidence independent of either party's confidence.
   If a category is already covered, say so; add rigor without adding deliverables.
3. **Present one rewrite.** Write a concise, self-contained prompt preserving the
   user's objective, constraints, and scope. Include consequential assumptions,
   task-specific methods, and acceptance evidence. Separate discovered facts from
   decisions still requiring the user's judgment. Ask for explicit approval of this
   specific rewrite through the available question interface or final reply.
4. **Wait.** End the turn or leave the approval question pending. Continue only
   read-only preparation while waiting. File edits, issue claims, external mutations,
   paid calls, and task execution wait. Silence, elapsed time, a complete original
   request, and approval of a different prompt do not approve this rewrite.
5. **Execute the approved scope.** Explicit approval such as “yes” or “proceed” in
   response to the rewrite opens execution. Incorporate compatible clarifications;
   continue routine choices, checks, and follow-ups within that scope without another
   gate. If the objective or scope materially changes, present an updated rewrite
   and obtain approval before executing the changed portion. Continue independent
   work already covered by approval. Record approval status in a required handoff.

## Direct paths and separate authorization

- **Quick question:** answer directly when a brief answer or targeted lookup suffices.
- **Approved follow-up:** reuse the approved scope; clarify only material ambiguity.
- **Explicit bypass:** a request such as “skip rewriting and implement this” opens
  execution for that requested scope. An initial imperative alone is not a bypass.
- **Other approvals:** rewritten-prompt approval or bypass does not replace explicit
  human cast/script decisions, publication approval, or task authorization for paid
  generation and deployment. Existing applicable authorization remains valid.

For harness changes, validate pointers and instruction consistency, walk through
substantial-task, quick-question, approved-follow-up, changed-scope, and explicit-bypass
scenarios, and measure reading costs.
Label walkthroughs separately from actual model evaluations; state the model and
budget before making any context-window fit claim.
