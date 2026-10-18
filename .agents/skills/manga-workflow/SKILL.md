---
name: manga-workflow
description: Change or debug this repository's manga extraction, cast/source/script review, Python worker contracts, audio rendering, or project recovery. Use for studio-to-engine integration; unrelated catalog styling does not need this workflow.
---

# Manga workflow

## Locate the contract

Trace the affected operation until its state owner and validation boundary are clear:

- `web/app/api/workflow/route.ts` and `web/lib/workflow.ts`: transport, staging,
  subprocess launch, persisted jobs, and polling.
- `web_workflow.py`: snapshots, expected-state checks, command dispatch, and jobs.
- `manga_tts/router.py`: typed application operations and validated commits.
- `manga_tts/schemas.py`, `script.py`, and `resolution.py`: commands, approval,
  grouping, and character resolution.
- `manga_tts/extraction.py` and `magi.py`: evidence and model adaptation.
- `manga_tts/tts.py`, `gemini.py`, and `storage.py`: requests, takes, persistence,
  archives, and export.
- `manga_tts/cli.py`: CLI adaptation and workspace writer ownership.

Read [the workflow guide](../../../docs/AUDIO_WORKFLOW.md) for review/render/export
semantics or recovery; read [model setup](../../../docs/MODELS.md) for installation
and inference. Verify details against code before edits.

## Preserve the affected invariants

- Keep evidence separate from human decisions: original recovered text, image
  coordinates, explicit image order, and source identities remain traceable.
- Review cast, then sources, then exact scene scripts. Applying sources rebuilds
  dialogue wording. Loading a proposal does not approve it. Preserve invalidation
  when approval inputs change, including settings and cast edits.
- Expected-state fingerprints reject stale mutations. Refresh a stale review from
  current state rather than rewriting its fingerprint to force acceptance.
- CLI and web writers share workspace locking. Direct router callers require writer
  ownership. Confirm a recorded process has stopped before removing its stale lock.
- Render preflights the selection and checkpoints successful segments. Preserve
  eligible take reuse, selected-take validation, and resume behavior. Inspection
  and export operate without synthesis or creating a provider client.
- Restore validates in staging before publishing to an empty workspace. Export
  replaces fixed filenames and is not a multi-file publication transaction.
- Filesystem jobs and locks provide local execution only. Preserve explicit
  local/cloud boundaries when extending persistence or execution.

## Verify the changed boundary

Use synthetic predictions and injected renderers for normal regression work.
Select existing tests by affected behavior: `test_web_workflow.py` for worker
contracts; `test_project.py` and `test_cast_speakers.py` for review;
`test_audio_pipeline.py` for rendering/export; `test_web_extract.py` and
`test_runners.py` for extraction/adapters. Inspect cases before selecting them.
Run the broader Python suite for shared schema, storage, or router changes.

For web contracts, also run `npm test` and `npm run typecheck` in `web/`; include
`npm run build` for route/runtime configuration changes. Optional HTTP tests require
an existing local server and `MANGA_WEB_TEST_URL`. Optional sample compatibility
uses `MANGA_TTS_SAMPLE_PROJECT` and temporary copies.

Completion requires evidence for every affected contract, with failures/skips
reported accurately. Offline checks establish neither live MAGI accuracy nor Gemini
compatibility/voice quality. Model downloads, paid generation, and cloud mutations
require task authorization; choose the smallest relevant live check when authorized.
