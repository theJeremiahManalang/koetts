# Prompt-approval validation

Validation record for the harness documentation change, 19 October 2026.
This record is evidence, not an additional procedure.

## Scope and baseline

The baseline is the working tree immediately before this task's edits, including
pre-existing tracked edits and untracked guides; it is not Git HEAD. Four existing
files were updated: root `AGENTS.md`, the documentation index, the architecture
assignment prompt, and the issue-tracker guide. Four files were added: the approval
guide, the project-local skill and its mechanics reference, and this record.

The shared `writing-for-agents/SKILL.md` matches the supplied personal skill byte
for byte. Its bundled mechanics reference uses Codex's `allow_implicit_invocation`
policy instead of the source reference's `disable-model-invocation` setting. No
personal-path dependency, skill installer, lockfile update, or runtime change is
required. Automatic skill discovery remains enabled by default.

## Checks actually executed

- The skill-creator `scripts/quick_validate.py` validator passed for
  `.agents/skills/writing-for-agents` using `python3`.
- A temporary Python checker resolved all 54 Markdown-link and root/template path
  occurrences in the seven operative changed documents. The validation record's
  pointer is included. Optional generated `agents/openai.yaml` and placeholder skill
  paths in the packaging reference are configuration examples, not load targets.
- SHA-256 comparison against the initial working-tree snapshot verified all 109
  files outside the task's changed paths remained intact. This includes existing
  `CONTEXT.md`, test, web setup, glossary, and alignment-evidence changes.
- The copied skill matched its supplied source using `git diff --no-index`.
- Manual instruction review checked root routing, web routing, authority references,
  assignment guidance, and existing agent guides. The tracker claim now follows
  approval; the architecture prompt derives eligibility from evidence instead of
  claiming S0 is next. Existing publication, cast/script, paid-generation, deployment,
  preservation, and verification safeguards remain. No conflicting execution
  instruction was found in the inspected active guidance.
- `git diff --check` passed; added files were also checked for trailing whitespace.

No application tests, live providers, cloud operations, or actual model evaluations
were run. Documentation validation does not establish future agent compliance.

## Static scenario walkthroughs

These are instruction-based walkthroughs, not model evaluations.

| Scenario | Input and expected observable behavior | Walkthrough result |
| --- | --- | --- |
| Substantial new task | “Investigate interrupted renders and fix recovery.” Inspect targeted instructions/source/state read-only; identify rigor; present one bounded rewrite; wait before broader investigation or edits. | Preparation and wait steps cover the boundary; passed. |
| Quick question | “Which Python command runs the tests?” Read the relevant instruction and answer directly. | Direct-path rule avoids a rewrite; passed. |
| Approved follow-up | After approving a recovery fix, “Run the relevant offline checks and clarify the failure message.” Continue within the approved recovery scope. | Execution step reuses approval; passed. |
| Changed scope | During that fix, “Also migrate rendering to a distributed scheduler.” Present an updated rewrite and wait for approval of the changed scope; independent approved work may continue. | Material-change branch preserves the boundary; passed. |
| Explicit bypass | “Skip rewriting; fix the recovery bug and run offline checks.” Execute that scope directly; preserve separate paid/deployment/publication authorization. | Bypass and separate-authorization rules apply; passed. |

For the substantial-task walkthrough, a complete original request and silence do
not constitute approval of the rewrite. An explicit “yes” in response does. Routine
implementation choices do not reopen the gate.

## Measured context cost

Words are whitespace-delimited (`len(text.split())`), including Markdown and code.
Tokens are exact counts from the locally available
`all-MiniLM-L6-v2/onnx/tokenizer.json` WordPiece tokenizer through Python `tokenizers`,
with truncation, padding, and special tokens disabled. These are **MiniLM tokenizer
counts, not Codex token counts**. No estimate or model-inference run is involved.

### Changed operative guides

New repository files have a zero baseline. The personal skill previously existed
outside the repository; its external cost is excluded from repository totals.
This evidence record is excluded from instruction-reading costs.

| File | Words before | Words after | Tokens before | Tokens after |
| --- | ---: | ---: | ---: | ---: |
| `AGENTS.md` | 491 | 433 | 933 | 898 |
| `docs/README.md` | 208 | 244 | 439 | 528 |
| `docs/architecture-alignment-prompt.md` | 143 | 163 | 260 | 293 |
| `docs/agents/issue-tracker.md` | 553 | 581 | 1261 | 1304 |
| `docs/agents/prompt-approval.md` | 0 | 444 | 0 | 664 |
| `.agents/skills/writing-for-agents/SKILL.md` | 0 | 1777 | 0 | 2548 |
| `.agents/skills/writing-for-agents/SKILL-MECHANICS.md` | 0 | 250 | 0 | 375 |

### Always-loaded instructions and representative paths

The new skill's name and description add 16 words / 27 MiniLM tokens. The table
conservatively charges that discovery text even when a user's environment already
exposes the personal copy. Existing skill catalogs, global instructions, tool
schemas, conversation history, runtime source, and task evidence are excluded;
those costs depend on the environment and task. Concatenated document counts use
one newline between documents.

| Reading path | Words before | Words after | Tokens before | Tokens after |
| --- | ---: | ---: | ---: | ---: |
| Root instructions | 491 | 433 | 933 | 898 |
| Root plus new skill discovery | 491 | 449 | 933 | 925 |
| Always-loaded web instructions plus new skill discovery | 695 | 653 | 1328 | 1320 |
| Quick question / approved follow-up | 699 | 693 | 1372 | 1453 |
| Approved web follow-up | 903 | 897 | 1767 | 1848 |
| New substantial web task | 903 | 1341 | 1767 | 2512 |
| New substantial worker task | 1352 | 1790 | 2634 | 3379 |
| New architecture scope | 3208 | 3666 | 5332 | 6110 |
| New agent-document task | 699 | 2914 | 1372 | 4665 |

Root instructions plus added discovery text remain below the baseline in both
measures; the same holds when unchanged web instructions are always loaded.
No always-loaded size exception is needed. Task-specific reading increases where
the approval procedure or writing skill applies. Quick-question and follow-up
paths avoid loading the approval guide, although the larger index increases their
MiniLM token counts. No universal context-window fit is claimed: no target model
or total context budget was specified.

Path definitions:

- Root instructions: `AGENTS.md` only. Discovery rows add the skill name/description;
  the web row also includes unchanged `web/AGENTS.md`.
- Quick question / approved follow-up: root instructions and `docs/README.md`.
- Approved web follow-up: the preceding path plus `web/AGENTS.md`.
- New substantial web task: approved web path plus `docs/agents/prompt-approval.md`.
- New substantial worker task: new web path plus
  `.agents/skills/manga-workflow/SKILL.md`.
- New architecture scope: root instructions, index, assignment prompt,
  `docs/architecture.md`, `docs/target-design.md`, and
  `docs/architecture-alignment-plan.md`; after the change, also the approval guide.
- New agent-document task: root instructions and index; after the change, also
  the approval guide and local writing skill. For skill creation/editing, additionally
  load the 250-word / 375-token mechanics reference. The baseline assumes no
  externally supplied writing skill; it does not assert equivalent prior guidance.

## Example interaction

**User:** “Investigate why interrupted renders lose completed audio and fix it.”

**Agent:** “Needed rigor: reproduce interruption and verify checkpoint preservation.
Primary evidence: worker code, persistence paths, and a disposable failing fixture.
Methods: targeted source inspection and an offline process-interruption test.
Acceptance: retain completed audio bytes, generate only unfinished segments, and
pass affected regressions.

Proposed prompt: Diagnose and fix completed-audio loss after render interruption.
Preserve existing worker contracts and supplied results. Inspect current checkpoint
and recovery paths; reproduce the failure using disposable projects and offline
rendering. Make the smallest supported fix. Verify completed audio remains unchanged
and restart renders only unfinished segments; run affected checks and report limits.
Assume live-provider behavior and cloud hosting are outside scope.

Approve this rewrite?”

**User:** “Yes.”

**Agent:** Executes the approved investigation and fix; routine choices and relevant
follow-ups continue without another rewrite.
