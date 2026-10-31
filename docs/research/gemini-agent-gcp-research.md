# ADK and Google managed-agent feasibility

**Status:** Research memo updated 2026-10-31. The direct Google Gen AI SDK migration
is implemented; this memo remains research about ADK and managed-agent options. No
ADK dependency or runtime is installed, and none is needed for the current workflow.
No cloud resources were changed; no live or paid provider calls were performed.

## Current implementation and rollout state

- The engine uses Google Gen AI SDK 2.33+ with enterprise mode, explicit
  `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION=us`, and ADC. Gemini API keys
  are not a fallback.
- Planning and TTS use `gemini-3.8-flash` and `gemini-3.8-flash-tts` through
  `generate_content`. The TTS adapter preserves exact text and speech metadata and
  validates complete unary WAV bytes; it does not downgrade models or add WAV
  headers. Offline fixtures verify request mapping and WAV handling, not live
  project access, model quality, or cost.
- `provider_configured` indicates project configuration only; it does not inspect
  ADC or verify provider readiness.
- The new hosted API, jobs and GCS target `us-central1`. The existing frontend
  remains in `us-east4`; its `us-central1` move is future work. Existing Firestore
  remains `nam5`. Phase-5 live or paid validation has not run.

The earlier provider-migration recommendation and TTS uncertainty below describe
the research state before that SDK migration. Treat them as historical context,
not as current implementation guidance.

## Recommendation

Do not replace the hosted production workflow with a conversational agent runtime. Keep the existing API, Firestore operation and budget ledgers, GCS artifacts, and finite Cloud Run Jobs authoritative. The direct SDK migration to an enterprise ADC client is implemented and offline-verified; live validation remains gated. Evaluate an ADK wrapper only for a bounded, non-authoritative planning-assistant experiment if evaluation or agent-level observability provides measurable value. Keep every cast/script result a proposal requiring the existing human review and approval path.

Google's Agent Development Kit (ADK) is technically usable here: Python ADK 2.0 is GA, ADK targets Gemini, and it can deploy to Cloud Run or Gemini Enterprise Agent Platform's managed Agent Runtime. The linked “Migrate to ADK” guide is an Agents CLI-assisted migration method: it maps current loops, tools, state, and tests, then recommends incremental conversion and evaluation. It is not a requirement to rewrite this application, a production migration command, or evidence that migration preserves its contracts. The repo does not currently use ADK, so its v1-to-v2 compatibility notes are not a direct migration step here; pin and evaluate a v2 version only if an ADK prototype is approved. [ADK migration guide](https://adk.dev/get-started/migrate/), [ADK 2.0 guide](https://adk.dev/2.0/)

The repository already has the valuable orchestration properties this product needs: a validated planning schema and evidence-keyed cache; proposal-only output; reviewed TTS request validation; and Cloud Run jobs that execute one fenced operation at a time. Firestore owns the shared durable state, transactional operation/quota admission, and budget reservations. The repo plan explicitly keeps human cast/script choices and publication approved by a person. ADK could structure a future LLM interaction, but its conversation history/session service must not become the production ledger or approval authority.

## Architecture options

1. **Direct Google Gen AI SDK with enterprise ADC — implemented.** Keep current router, planning/resolution and TTS contracts. The engine now creates an enterprise client with explicit project and location, and uses ADC without a Gemini API-key path. Offline fixtures cover request mapping and WAV handling; live compatibility, access, and cost remain unverified pending authorization.
2. **ADK planning assistant inside existing operation boundary — conditional experiment.** Model one chapter proposal as a bounded ADK workflow invoked by the existing worker job. Give it only necessary read access to staged chapter evidence and a typed proposal result. Do not give it Firestore approval, project revision, budget, publication, or arbitrary tool-write authority. Existing operation admission, budget checks, persistence, retries, and human approvals stay outside ADK. Keep the existing path available until replay evaluation proves comparable or better results.
3. **Move the production service to managed Agent Runtime — defer.** Agent Runtime supports ADK deployments and managed sessions; `us-central1` is a supported GA region. This could suit a future user-facing conversational helper, but it does not supply the app's Firestore transaction, job-fencing, budget, artifact, or human-approval contracts. It adds a second lifecycle/state system and changes the execution and billing boundary. It is not a drop-in replacement for current Cloud Run Jobs or API. [Agent Runtime ADK deployment](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk), [locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/agent-locations)

Cloud Run is also a possible ADK host if a future use case justifies it. Google distinguishes request-driven services (can scale to zero), long-lived instances, worker pools, and run-to-completion jobs. The hosted target uses finite jobs for work; the existing frontend remains in `us-east4`, while the new API, jobs and artifacts target `us-central1`. An ADK HTTP endpoint would be an additional service, not a reason to move work out of the durable job path. Minimum instances incur idle cost; zero-minimum request-based services can scale to zero. [Cloud Run agent resource choices](https://docs.cloud.google.com/run/docs/ai-agents), [minimum instances and billing](https://docs.cloud.google.com/run/docs/configuring/min-instances)

## Historical auth, model, region, and cost research

Before the direct SDK migration, the research identified enterprise ADC as the intended auth path and treated it as a backend/configuration switch. That migration is now implemented as described above. Gemini Developer API billing and Vertex/Agent Platform billing are distinct services; historical Developer API allowances do not establish a Vertex budget. [ADK Google Cloud setup](https://adk.dev/get-started/google-cloud/), [ADC](https://docs.cloud.google.com/docs/authentication/application-default-credentials), [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing)

`us-central1` supports GA Agent Runtime/Sessions and is documented for Gemini TTS models. This confirms regional product availability, not access to every model ID in this repo or quality/latency for manga workloads. Agent Runtime compute is listed at $0.085/vCPU-hour and memory at $0.009/GiB-hour; its pricing page says idle time waiting between prompts is not billed. Managed Sessions storage and operations became billable September 1, 2026. These are service rates, not an estimate for this project's workload. The repo's $10 monthly target and desired <$20 infrastructure spend remain goals, not a guarantee; a separately managed provider allowance and reservations remain necessary. Do not assume the old Agent Engine free-runtime allowances still apply. [Agent Platform pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing)

Before migration, TTS compatibility was the main risk. The current adapter instead calls `generate_content` and handles complete unary WAV bytes; offline fixtures verify that mapping and preserve the reviewed request contract. This does not prove live access, model quality, or cost for `gemini-3.8-flash-tts`; those checks remain gated. The older Vertex TTS docs cited here described PCM output without WAV headers for a different API/model path, so they do not describe the implemented transport. [Gemini-TTS APIs, models and regions](https://docs.cloud.google.com/text-to-speech/docs/gemini-tts)

## Remaining gates and phased evaluation

1. **SDK compatibility:** request mapping and unary WAV handling have offline fixture coverage. Real model access, output quality, IAM, time and cost remain unverified. No phase-5 live or paid calls have run.
2. **Offline replay and evaluation design:** construct a small, rights-cleared fixture set with known reviewed cast, source text, and scripts. Replay saved provider responses or use injected model/tool doubles without new network inference. These checks prove contract preservation, not candidate model quality. After separate paid-test authorization, compare fresh baseline and candidate outputs on schema validity, source coverage/order, exact text fidelity, speaker attribution, scene continuity, false identity creation, safety/instruction handling, cache determinism, and reviewer correction rate. Freeze model/version, prompts, and evaluation data; report uncertainty and failure cases. Do not count a model-generated answer as a human approval.
3. **ADK-only gated trial if justified:** isolate a planning workflow with no mutating business tools. Wire callbacks/guards before every model request, tool call, retry, and parallel fan-out; one top-level “before job” hook is insufficient. Audit ADK, Gen AI SDK, transport, and tool retry layers so hidden retries cannot exceed Firestore reservations or replay uncertain paid calls. Enforce the current durable operation attempt ceiling and reconcile ambiguous external results before retry. Confirm callback execution order and failure behavior against the pinned ADK version.
4. **Separate live validation authorization:** only after offline review, seek the existing project gate for tightly bounded paid calls/deployment. Test the exact target in `us-central1`, IAM, ADC, Firestore/GCS durability, model/TTS support, measured time and cost, rollback, and production pause. No result here authorizes a cloud mutation, paid call, deployment, human decision, or publication.

The existing durable operation/budget and approval controls stay authoritative in all options. In particular, ADK sessions are conversational state, not the ledger for approved scripts, revisions, attempts, provider debits, chapter quotas, or publication.

## Open compatibility questions

- If an ADK experiment is proposed, does the pinned ADK version preserve structured multimodal request semantics with the enterprise Gen AI client?
- Does the configured `gemini-3.8-flash-tts` model have the required live project access and quality for this workload? Offline fixtures do not answer this.
- What service-account permissions and quotas are required for the selected model endpoints, ADK runtime, and TTS API? Derive least privilege from the chosen path; do not copy tutorial roles wholesale.
- Do ADK callbacks cover each lower-level SDK retry and every parallel tool invocation in the exact version? Treat this as a measured release gate, not an assumption.

## Primary sources

- [Migrate existing agent codebases to ADK](https://adk.dev/get-started/migrate/)
- [ADK 2.0](https://adk.dev/2.0/)
- [ADK and Google Cloud auth](https://adk.dev/get-started/google-cloud/)
- [Host AI agents on Cloud Run](https://docs.cloud.google.com/run/docs/ai-agents)
- [Deploy ADK on managed Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk)
- [Agent Runtime/Sessions regions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/agent-locations)
- [Agent Platform pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing)
- [Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing)
- [Gemini TTS API/model/region guide](https://docs.cloud.google.com/text-to-speech/docs/gemini-tts)
