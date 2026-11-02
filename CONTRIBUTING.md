# Contributing

Follow [developer setup](resources/DEVELOPMENT.md), then work on a focused branch. Read the affected domain guide before changing a boundary. Reuse existing tests and fixtures; add regression coverage for changed contracts.

## Boundaries and dependency changes

Keep route/HTTP/CLI adapters separate from engine decisions. Keep provider/model dependencies behind optional adapters. Update the owning workspace manifest, regenerate the root lockfile with the pinned tool, and include both manifest and lockfile in review. Use `uv lock` for Python and `npm install --package-lock-only` for Node. Only one lockfile per ecosystem is authoritative.

Preserve saved-project formats, approval invalidation, workspace writer ownership, expected-state checks, and operation recovery. Discuss changes to these contracts explicitly. Intentional demo fixtures belong to their web feature; remove unused scaffolding rather than preserving compatibility aliases without a consumer.

## Before review

Run `npm run check` and include results in the pull request. Run `npm run test:http` for worker transport, route/auth boundaries, data paths, packaging, or runtime changes. Run `uv run python tools/verify_fresh_checkout.py` when changing onboarding or dependency management. Report optional skips and environmental blocks separately.

Describe the problem, resulting behavior, migration effects, and tests. Keep credentials, private uploads, model caches, and generated results out of commits. Deployment, paid generation, human review decisions, and publication need explicit task authorization.

CI runs frozen installs, repository checks, lint, Python/web tests, typecheck, build, and disposable HTTP verification. A passing synthetic suite does not establish live extraction accuracy, provider quality, or production cloud authorization.
