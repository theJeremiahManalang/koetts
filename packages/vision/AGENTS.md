# Vision package guide

Own model identity, image loading, runner selection, inference CLI, and prediction artifacts here. Preserve `manga_vision` imports; import no engine or application package.

Read `../../docs/MODELS.md` before dependency changes or real inference. Keep model imports lazy so lightweight installs and synthetic tests use no weights. Preserve pinned model revision, EXIF orientation, caption validation, and evidence coordinates. CPU/CUDA extras remain mutually exclusive and default installs remain lightweight.

Run vision tests and affected extraction integration tests. Synthetic fixtures establish plumbing, not model accuracy. Live inference and provider calls require task authorization.
