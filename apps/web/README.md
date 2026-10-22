# Web application

Use [root setup](../../docs/development.md) and root npm scripts. Next.js `app/` contains route adapters. `features/` owns studio, identity, library/reader, and browser-local request behavior; demo catalog/request fixtures are explicit feature data. `lib/` contains only shared server transport.

The admin studio is `/`. Reader/catalog/request routes intentionally demonstrate product flows; shared publication and requests remain future work. Firebase guards protect local processing and private assets. Hosted frontend-only mode redirects `/` to `/browse` and disables processing.

The server invokes installed `manga_worker` modules through the root uv environment. See [workflow](../../docs/AUDIO_WORKFLOW.md) for review/recovery and [hosting](../../docs/APP_HOSTING.md) for deployment boundaries.
