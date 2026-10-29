# API documentation tools: repository fit

Research date: 2026-10-29. Scope: tool selection and adoption proposal only; no runtime, dependency, authentication, or deployment changes.

## Recommendation

Use **OpenAPI 3.1 contracts, Scalar API Reference for presentation, and Redocly CLI for contract linting and bundling**. Add a breaking-change comparison such as oasdiff when the initial contracts are reliable. Keep the existing Markdown guides for architecture and production workflow.

This is a repository-fit judgment, not a performance benchmark. Scalar offers a direct Next.js integration, while a portable OpenAPI artifact can describe both the browser-facing Next.js API and the private worker API. Redocly CLI addresses specification quality separately from presentation. The most urgent work is describing the actual contracts: installing a renderer alone would display incomplete or misleading worker documentation.

Choose **FastAPI's Swagger UI instead** if the immediate requirement is only local worker debugging with minimum integration work. Choose **ReDoc Community Edition** if a static reading reference is sufficient. Defer a hosted documentation platform until there is a clear external developer audience, editorial workflow, or portal requirement.

## Repository evidence

Runtime source and manifests establish these findings; migration documents do not establish implemented capabilities.

| Area | Implemented evidence | Documentation consequence |
| --- | --- | --- |
| Browser API | Eleven `route.ts` files under `apps/web/app/api`; Next.js 16 and React 19 in [web manifest](../../apps/web/package.json) | Worker-generated documentation cannot cover the browser API. |
| Private worker | Six paths in [http_api.py](../../apps/worker/src/manga_worker/http_api.py); FastAPI 0.156.6 in [worker manifest](../../apps/worker/pyproject.toml) | Generate or enrich a separate worker contract. |
| Disabled docs | `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` | Do not assume `/docs` or `/openapi.json` is available. An offline schema export can preserve this deployment behavior. |
| Manual contracts | Worker operations read raw `Request`, parse JSON manually, and return untyped objects | Automatic schema generation does not discover the request body, response shape, custom errors, or authentication rules. |
| Browser workflow | [Workflow route](../../apps/web/app/api/workflow/route.ts) has GET branches for job, key, project, and listing; POST accepts JSON or multipart uploads | Document action variants, response variants, idempotency, upload limits, and polling behavior explicitly. |
| Authentication | [Worker boundary](../../apps/worker/src/manga_worker/http_auth.py) separates service and user credentials; [session route](../../apps/web/app/api/auth/session/route.ts) establishes an HttpOnly browser session | Worker and browser security descriptions must remain separate. |
| Runtime modes | Worker workspace operations return 503 outside local mode; frontend-only routes reject processing | A documented endpoint is not a promise of hosted processing availability. |
| Media | [Asset route](../../apps/web/app/api/asset/route.ts), [playback route](../../apps/web/app/api/shared/playback/route.ts), [audio route](../../apps/web/app/api/shared/audio/route.ts), and [audio serving](../../apps/web/features/requests/server/audio-file.ts) | Describe binary media, signed playback links, expiration, byte ranges, and 200/206/416 responses. |

The browser workflow requires same-origin requests and `x-manga-workflow: 1` for POST, plus an idempotency key. Upload and JSON size rules differ from the worker's 5 MiB operation limit. These rules need examples and prose alongside schemas. Existing TypeScript wire types in [studio/types.ts](../../apps/web/features/studio/types.ts) are useful evidence, but types alone do not describe headers, authorization, content types, response codes, or runtime validation.

### Offline schema inspection

During research, an offline call to `create_app(BoundaryConfig('docs-research', 'https://example.invalid', {})).openapi()` produced OpenAPI 3.1.0 with six paths. It contained no security schemes, no operation security requirements, no request body for POST `/operations`, and empty success schemas. The asset operation advertised a default 200 even though its handler unconditionally raises 503. No provider, credentials, workspace operation, or live HTTP service was used.

This confirms a contract-quality gap independently of renderer choice. FastAPI documents that data read directly from `Request` does not receive automatic validation or OpenAPI documentation. It supports schema extension through `openapi_extra` and a custom `app.openapi()` implementation. Preserve the current strict parser when adding documentation; replacing it with ordinary body parsing could change duplicate-key, size, and non-finite-number rejection. Sources: [direct Request access](https://fastapi.tiangolo.com/advanced/using-request-directly/), [operation schema extension](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/), [custom OpenAPI](https://fastapi.tiangolo.com/how-to/extending-openapi/).

## Tool comparison

The fit ratings below are qualitative judgments based on this repository's two HTTP surfaces, private access, existing tooling, and small documentation footprint.

| Candidate | Verified capabilities | Repository fit and tradeoff |
| --- | --- | --- |
| **Scalar API Reference** | OpenAPI renderer with Next.js standalone handler and React embedding; MIT-licensed source; configurable request testing | **Best overall presentation fit.** Can display either contract within the existing web application. Requires a real specification and explicit server-side access checks. |
| **Swagger UI through FastAPI** | Built-in FastAPI documentation integration; accepts OpenAPI documents; request interception and configurable execution | **Best minimum-work worker option.** Does not automatically document Next.js. A combined reference needs additional hosting/integration. |
| **ReDoc Community Edition** | OpenAPI reference delivered through HTML, React, or a generated HTML artifact; MIT license | **Best reading-only artifact option.** Avoid confusing the community renderer with commercial Redocly features such as Replay and RBAC. |
| **Redocly CLI** | Open-source specification linting, bundling, transformations, and documentation tooling | **Recommended companion.** Improves the contract rather than replacing Scalar. More useful now than buying a portal. |
| **Mintlify** | Hosted documentation, OpenAPI endpoint generation, Git-based content, API playground, authentication options | **Conditional future fit.** Useful for a maintained developer portal; introduces a separate publication and access workflow. It still consumes specifications rather than discovering these handlers. |

Primary sources: [Scalar integration](https://github.com/scalar/scalar/blob/main/documentation/integrations/nextjs.md), [Scalar license](https://github.com/scalar/scalar/blob/main/LICENSE), [Scalar configuration](https://github.com/scalar/scalar/blob/main/documentation/configuration.md), [FastAPI documentation settings](https://fastapi.tiangolo.com/tutorial/metadata/#docs-urls), [Swagger configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/), [ReDoc source and product distinction](https://github.com/Redocly/redoc), [Redocly CLI](https://redocly.com/docs/cli), [Mintlify OpenAPI setup](https://www.mintlify.com/docs/api-playground/openapi-setup).

### Integration and maintenance details

Scalar's current Next.js guide documents Next.js 15/16, React 19, and Node 22 or newer. These match the repository's framework generation. The standalone handler keeps documentation styling separate from application layout; embedding React requires application CSS integration. Start with the standalone approach for a small reference. It does not generate a specification from route handlers. Its default browser renderer follows a CDN release independently of the npm package, so pin or self-host the renderer as well as pinning the integration package. These are documented capabilities, not a compatibility test against this checkout. [Scalar integration guide](https://github.com/scalar/scalar/blob/main/documentation/integrations/nextjs.md).

Redocly CLI v2 currently requires Node 22.12.0 or newer, compatible with the repository's Node 22.22.3 pin. Its lint command supports configurable rule sets; bundle resolves a modular source into a consumable artifact. Pin the selected CLI release in the existing npm tooling. A linter cannot establish that a specification matches custom runtime behavior. [CLI requirements](https://redocly.com/docs/cli), [lint command](https://redocly.com/docs/cli/commands/lint).

## Private access and request execution

Protect both the reference page and the specification response. A private page loading a public JSON file still exposes the contract. Prefer local development access first; if integrated into the studio, reuse server-side identity checks and private, non-cacheable responses. Do not place private specifications in Next.js `public/`. Scalar's guide explicitly describes this distinction. [Private documentation guidance](https://github.com/scalar/scalar/blob/main/documentation/integrations/nextjs.md).

For browser endpoints, document the existing session cookie and origin/header restrictions. An HttpOnly cookie cannot be filled from JavaScript. Same-origin testing must use the application's existing session flow; a separate documentation domain does not automatically satisfy that boundary.

For worker endpoints, model service Bearer authentication **AND** one user credential. The alternatives are `(service AND user token) OR (service AND user session)`. `/ready` requires only the service credential. In OpenAPI, put schemes required together into the same Security Requirement Object and alternatives into separate array entries. Document separately that supplying both user headers is rejected; the security alternatives do not express every exclusivity rule. [OpenAPI security semantics](https://spec.openapis.org/oas/v3.1.0.html#security-requirement-object), [implemented credential checks](../../apps/worker/src/manga_worker/http_auth.py).

Start the reference with request execution disabled, especially for worker and synthesis operations. Scalar exposes `hideTestRequestButton`; Swagger UI exposes `supportedSubmitMethods`, which can be empty. UI settings are presentation controls; the API must retain its own authorization. Never place service tokens in browser configuration. Do not introduce a service-credential proxy merely to make documentation interactive. Review proxy configuration before any later interactive deployment. Sources: [Scalar configuration](https://github.com/scalar/scalar/blob/main/documentation/configuration.md), [Swagger configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/).

## Cost and hosting

Scalar's renderer and ReDoc CE use MIT licenses; Swagger UI uses Apache 2.0. They can avoid documentation SaaS subscription costs, but still require hosting, dependency maintenance, and contract authoring. Redocly CLI is open source. The largest initial cost here is describing and checking the two existing APIs, common to all candidates. Sources: [Scalar license](https://github.com/scalar/scalar/blob/main/LICENSE), [ReDoc license](https://github.com/Redocly/redoc), [Swagger license](https://github.com/swagger-api/swagger-ui/blob/main/LICENSE), [Redocly CLI](https://redocly.com/docs/cli).

Mintlify's current pricing page lists a free Starter plan and paid Pro/Enterprise options. Authentication and self-hosting have plan-specific details; verify the exact required method and quote before selecting a private portal. No subscription purchase is needed for the recommended stack. Prices and entitlements can change, so this report does not use them as a durable architectural assumption. [Mintlify pricing](https://www.mintlify.com/pricing).

## Proposed adoption sequence

1. **Establish two contracts.** Keep browser and worker descriptions separate, with explicit ownership. Use OpenAPI 3.1 to match the worker's observed output. Describe existing behavior without exposing new endpoints or changing validation. For the worker, enrich generated metadata or maintain a checked overlay for manual parsing and security. For Next.js, begin with a reviewed specification beside the adapters; consider schema-first runtime definitions only in a separately approved refactor.
2. **Cover difficult behavior first.** Include workflow action variants, multipart input, 202 operation receipts, idempotency conflicts, polling, authentication alternatives, mode-dependent 503 responses, and media range responses. Use synthetic examples. Do not present future cloud processing or disabled asset delivery as working functionality.
3. **Add quality checks.** Lint and bundle each contract. Check route/method inventory against source, including the eleven Next.js route files and six worker paths. Validate representative request/response fixtures against schemas. Regenerate worker metadata and fail on unexplained contract differences. A successful lint alone is not drift protection.
4. **Render locally with Scalar.** Display the contracts as separate references, with request execution disabled. Check that action variants, uploads, errors, and authentication explanations are understandable. Pin all renderer assets. Only add authenticated hosted access when needed.
5. **Detect compatibility changes.** Compare reviewed baseline contracts with proposed contracts using oasdiff's breaking-change support. Keep HTTP acceptance tests for real origin, credential, size, and range behavior; specification diffing cannot prove runtime conformance. [oasdiff project](https://github.com/oasdiff/oasdiff).

Acceptance for a later implementation should include: complete route inventory, explicit security schemes, nonempty request/response schemas where applicable, representative errors, documented local/hosted availability, schema lint success, deterministic generation, and verified access control on both HTML and JSON. Transport or authentication changes require the repository's `npm run test:http` in addition to normal acceptance checks. Rendering should receive a browser smoke test before adopting the exact package version.

## Evidence limits

Research used repository source, an offline FastAPI schema inspection, Context7 documentation for Scalar and FastAPI, and first-party web sources. No packages were installed, no renderer was launched, no live authentication was exercised, and no deployment or paid call occurred. Relative maintenance estimates and recommendations are judgments. Current upstream documentation does not establish compatibility of an unselected package release with the repository's lockfiles. This report proposes tooling; it does not change documentation authority or approve implementation.
