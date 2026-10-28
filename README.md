# Manga audiobook studio

A uv/npm monorepo for reviewed manga-to-audio production and local shared audiobook playback. Humans approve cast and scripts before synthesis. Export, audio review, and publication remain separate decisions.

## Start developing

Install uv **0.11.16** and Node **22.22.3** (npm **10.9.8**). Runtime pins are checked in.

```bash
uv sync --frozen
npm ci
npm run check:repo
npm test
npm run dev
```

Configure Firebase login and a trusted admin account before using the studio. Copy `apps/web/.env.example` to `apps/web/.env.local` when first configuring your environment. See [developer setup](docs/development.md) for credentials, optional vision installs, and troubleshooting. The default environment downloads no PyTorch or model weights.

## Ownership

| Workspace | Responsibility |
| --- | --- |
| `apps/web` | Next.js routes and studio, identity, library/reader, requests features |
| `apps/worker` | Local workflow/OCR workers and private HTTP adapters |
| `packages/engine` | Reviewed production state, operations, persistence, synthesis, and CLI |
| `packages/vision` | Image utilities, pinned model adapter, and inference CLI |
| `tests/unit`, `tests/integration` | Domain tests and cross-process/HTTP acceptance |
| `tools` | Workspace checks and disposable onboarding verification |

Dependency direction: worker imports engine and vision; engine imports vision utilities; vision imports no application package. Features own browser behavior; Next.js route files are adapters. Architecture checks run in CI.

## Commands

Run commands from the root unless explicitly selecting an installed CLI:

```bash
npm run dev             # local web app
npm test                # Python and web tests
npm run check           # boundaries, lint, tests, typecheck, production build
npm run test:http       # disposable production HTTP checks
uv run manga-tts --help
uv run manga-vision --help
uv run manga-worker --help
```

[Documentation index](docs/README.md) routes developer, domain, operational, and agent guidance. [Contribution guide](CONTRIBUTING.md) defines the review workflow. Saved projects and local shared publications remain under `results/web` by default; preserve them during cleanup. Shared state coordinates one host only; distributed processing and cloud storage remain future migration scopes.
