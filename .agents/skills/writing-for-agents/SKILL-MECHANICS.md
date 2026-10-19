# Skill mechanics

Read this reference when creating or editing a skill. The parent [writing guide](SKILL.md)
owns document-writing principles; this file covers Codex skill packaging.

## Discovery and invocation

Put project-shared skills in `.agents/skills/<name>/SKILL.md`. Include YAML
frontmatter with `name` and `description`; use lowercase letters, digits, and
hyphens for names. The description is an always-loaded context pointer: state the
capability and the actual branches that should select it.

Automatic selection is the default and still permits explicit user invocation.
When the user requests explicit-only invocation, set the following in
`agents/openai.yaml`, preserving other metadata:

```yaml
policy:
  allow_implicit_invocation: false
```

Use the installed skill-creator guidance when available for packaging or validator
commands. Keep required references in the project so teammates need no personal
home-directory files. Read each supporting reference only for its stated branch.

## Split only when useful

Create a separate skill when a distinct capability needs independent discovery.
Keep shared writing principles in one authoritative reference; route to them rather
than copying them into each consumer. A short self-contained skill needs no extra
router or optional UI metadata.

For a router, state each branch and its target explicitly. Explicit-only skills
require user invocation; a router can describe that choice without assuming that
another agent can invoke them automatically.

## Validation

Check frontmatter, names, relative pointers, and invocation policy. Exercise realistic
requests when behavior needs evaluation; label static walkthroughs separately from
actual model runs. Measure the description's always-loaded cost as well as the
body and any supporting references loaded on each branch.
