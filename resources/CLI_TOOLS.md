# Project CLI tools

Run commands from the repository root. For exact flags, run each command with
`--help`. `uv run --locked` must be run from this root so uv finds the pinned
workspace lockfile.

## Local checks

| Tool | Use |
| --- | --- |
| `uv run --locked python tools/check_repo.py --help` | Check workspace boundaries, imports, and active documentation links. No flags beyond `--help`. |
| `uv run --locked python tools/verify_fresh_checkout.py --help` | Recreate the frozen install and test flow in a disposable checkout. No flags beyond `--help`; installs dependencies and runs tests. |
| `uv run --locked python tools/verify_shared_firestore.py --help` | Run integration suites against the pinned local Firestore emulator. Supports suite selection, repetition, and a retained emulator log path. Requires Java and may download the checksum-pinned emulator. Never points at live Firestore. |

## Hosted preparation and review

| Tool | Use |
| --- | --- |
| `uv run --locked python tools/prepare_apphosting_source.py --help` | Create a sanitized App Hosting staging tree at a new output directory. It does not deploy. |
| `uv run --locked python tools/hosted_rollout_record.py --help` | Create an offline rollout evidence record at a new file path. It does not call Google Cloud. |
| `uv run --locked python tools/capture_hosted_logs.py --help` | Capture logs for one explicit UTC time window and project/region. This is read-only, but output can contain private operational data. |
| `uv run --locked python tools/manage_hosted_budget.py --help` | Prompt for USD stage caps, save a private caps JSON, and print a budget configuration plan. Live ledger writes require `--execute`. It does not start jobs or resume production. |

The existing operator handles the actual budget ledger operations:

```bash
uv run --locked python -m manga_worker.cloud_operator --help
```

It requires explicit cloud settings. Mutating actions print a plan by default;
`--execute` applies the action and requires an audit actor, reason, and evidence
reference. `status --execute` performs a read-only live ledger read. A production
resume may dispatch already queued operations immediately.

For a hosted Cloud Run start with no recorded execution name, use the operator
command `resolve-operation`. It checks the operation's submission state,
waits five minutes after uncertainty, and exhaustively searches the configured
Cloud Run job before it can resolve as `fail` or `retry`. The default prints a
plan; `--execute` performs the Firestore resolution. A retry can start a CPU job.
The `manga-worker reconcile` command instead targets the local SQLite operation
store; do not use it for hosted Firestore operations.

```bash
uv run --locked python -m manga_worker.cloud_operator resolve-operation --help
```

The package entry points also support their standard help flags:

```bash
uv run --locked manga-worker --help
uv run --locked manga-vision --help
c
```

`npm run` lists the workspace scripts, including checks, tests, build, and HTTP
acceptance. See [developer setup](DEVELOPMENT.md) for environment configuration.
