# Web application

Use [root setup](../../resources/DEVELOPMENT.md) and root npm scripts. Next.js `app/` contains route adapters. `features/` owns studio, identity, library/reader, and shared request behavior. `lib/` contains shared server transport.

The admin studio is `/`; `/admin/requests` manages shared chapter work and reviewed publication. Signed-in readers can submit requests, browse published audio and listen locally. Firebase guards protect private assets and admin actions. Hosted frontend-only mode redirects `/` to `/browse` and disables the local shared backend and processing.

The server invokes installed `manga_worker` modules through the root uv environment. See [workflow](../../resources/AUDIO_WORKFLOW.md) for review/recovery and [hosting](../../resources/APP_HOSTING.md) for deployment boundaries.
