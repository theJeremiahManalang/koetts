# ADK and Google managed-agent feasibility

**Status:** Research memo, 2026-10-31. No dependencies, code, cloud resources, or provider calls changed.

## Recommendation

Do not replace the hosted production workflow with a conversational agent runtime. Keep the existing API, Firestore operation and budget ledgers, GCS artifacts, and finite Cloud Run Jobs authoritative. First migrate the existing Gemini calls to an explicitly selected Vertex AI backend with workload identity, as a narrow provider-adapter experiment. Evaluate an ADK wrapper only for a bounded, non-authoritative planning-assistant experiment if evaluation or agent-level observability provides measurable value. Keep every cast/script result a proposal requiring the existing human review and approval path.

Google's Agent Development Kit (ADK) is technically usable here: Python ADK 2.0 is GA, ADK targets Gemini, and it can deploy to Cloud Run or Gemini Enterprise Agent Platform's managed Agent Runtime. The linked “Migrate to ADK” guide is an Agents CLI-assisted migration method: it maps current loops, tools, state, and tests, then recommends incremental conversion and evaluation. It is not a requirement to rewrite this application, a production migration command, or evidence that migration preserves its contracts. The repo does not currently use ADK, so its v1-to-v2 compatibility notes are not a direct migration step here; pin and evaluate a v2 version only if an ADK prototype is approved. [ADK migration guide](https://adk.dev/get-started/migrate/), [ADK 2.0 guide](https://adk.dev/2.0/)

The repository already has the valuable orchestration properties this product needs: a validated planning schema and evidence-keyed cache; proposal-only output; reviewed TTS request validation; and Cloud Run jobs that execute one fenced operation at a time. Firestore owns the shared durable state, transactional operation/quota admission, and budget reservations. The repo plan explicitly keeps human cast/script choices and publication approved by a person. ADK could structure an LLM interaction, but its conversation history/session service must not become the production ledger or approval authority.

## Architecture options

1. **Vertex-backed provider adapter, no ADK — recommended first.** Keep current router, planning/resolution and TTS contracts. Add a separate Vertex AI client/auth configuration and verify each exact model/API call independently. Preserve the Gemini Developer API path as a distinct option if needed. This is the smallest route to GCP workload identity and regional model processing; it avoids a framework migration while the product has no general conversational loop.
2. **ADK planning assistant inside existing operation boundary — conditional experiment.** Model one chapter proposal as a bounded ADK workflow invoked by the existing worker job. Give it only necessary read access to staged chapter evidence and a typed proposal result. Do not give it Firestore approval, project revision, budget, publication, or arbitrary tool-write authority. Existing operation admission, budget checks, persistence, retries, and human approvals stay outside ADK. Keep the existing path available until replay evaluation proves comparable or better results.
3. **Move the production service to managed Agent Runtime — defer.** Agent Runtime supports ADK deployments and managed sessions; `us-central1` is a supported GA region. This could suit a future user-facing conversational helper, but it does not supply the app's Firestore transaction, job-fencing, budget, artifact, or human-approval contracts. It adds a second lifecycle/state system and changes the execution and billing boundary. It is not a drop-in replacement for current Cloud Run Jobs or API. [Agent Runtime ADK deployment](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk), [locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/agent-locations)

Cloud Run is also a valid ADK host. Google distinguishes request-driven services (can scale to zero), long-lived instances, worker pools, and run-to-completion jobs. The existing hosted plan already uses finite jobs for work and keeps the frontend initially in `us-east4`; new backend services and artifacts target `us-central1`. An ADK HTTP endpoint would be an additional service, not a reason to move work out of the durable job path. Minimum instances incur idle cost; zero-minimum request-based services can scale to zero. [Cloud Run agent resource choices](https://docs.cloud.google.com/run/docs/ai-agents), [minimum instances and billing](https://docs.cloud.google.com/run/docs/configuring/min-instances)

## Auth, model, region, and cost constraints

The current engine constructs `google.genai.Client(api_key=GEMINI_API_KEY)` in [gemini.py](../packages/engine/src/manga_tts/gemini.py); its settings default to `gemini-3.8-flash` and `gemini-3.8-flash-tts` in [config.py](../packages/engine/src/manga_tts/config.py). Vertex AI can use Application Default Credentials (ADC), with an attached least-privilege service account preferred in production. ADK's Google Cloud guide documents service-account auth and the Gen AI SDK's `GOOGLE_GENAI_USE_ENTERPRISE` setting (older Vertex setting `GOOGLE_GENAI_USE_VERTEXAI`). This is a deliberate backend/configuration switch, not proof that the existing API-key client, model names, request shapes, or response parsing remain compatible. Gemini Developer API billing and Vertex AI billing are distinct services; a Developer API key's free/paid allowance does not automatically become Vertex credit. [ADK Google Cloud setup](https://adk.dev/get-started/google-cloud/), [ADC](https://docs.cloud.google.com/docs/authentication/application-default-credentials), [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing)

`us-central1` supports GA Agent Runtime/Sessions and is documented for Gemini TTS models. This confirms regional product availability, not access to every model ID in this repo or quality/latency for manga workloads. Agent Runtime compute is listed at $0.085/vCPU-hour and memory at $0.009/GiB-hour; its pricing page says idle time waiting between prompts is not billed. Managed Sessions storage and operations became billable September 1, 2026. These are service rates, not an estimate for this project's workload. The repo's $10 monthly target and desired <$20 infrastructure spend remain goals, not a guarantee; a separately managed provider allowance and reservations remain necessary. Do not assume the old Agent Engine free-runtime allowances still apply. [Agent Platform pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing)

TTS is the main compatibility risk. Current code uses `client.interactions.create(...)` and expects `response.output_audio.data`, then base64-decodes it in [gemini.py](../packages/engine/src/manga_tts/gemini.py). Google's Vertex Gemini-TTS documentation instead demonstrates `generate_content` with speech configuration and inline PCM bytes; it documents PCM as 16-bit/24-kHz data without WAV headers for Vertex API. Therefore expect an explicit adapter, audio container construction/validation, and fixture review if the chosen supported model/API returns that format. Google's current model/region table lists Gemini 2.5 TTS variants in `us-central1`, but that does not establish compatibility of configured `gemini-3.8-flash-tts` with this renderer. Keep TTS unchanged until the exact model, API, voices, speaker modes, and audio output pass compatibility evaluation. [Gemini-TTS APIs, models and regions](https://docs.cloud.google.com/text-to-speech/docs/gemini-tts)

## Required gates and phased evaluation

1. **Provider compatibility spike, offline first:** verify the exact deployed SDK versions and model IDs from primary documentation; implement only behind an injectable client/config boundary. No key migration or default switch until the existing test-double contracts pass. Check structured JSON output, image request handling, cache identity, timeouts, output/audio shape, and error classification.
2. **Offline replay and evaluation design:** construct a small, rights-cleared fixture set with known reviewed cast, source text, and scripts. Replay saved provider responses or use injected model/tool doubles without new network inference. These checks prove contract preservation, not candidate model quality. After separate paid-test authorization, compare fresh baseline and candidate outputs on schema validity, source coverage/order, exact text fidelity, speaker attribution, scene continuity, false identity creation, safety/instruction handling, cache determinism, and reviewer correction rate. Freeze model/version, prompts, and evaluation data; report uncertainty and failure cases. Do not count a model-generated answer as a human approval.
3. **ADK-only gated trial if justified:** isolate a planning workflow with no mutating business tools. Wire callbacks/guards before every model request, tool call, retry, and parallel fan-out; one top-level “before job” hook is insufficient. Audit ADK, Gen AI SDK, transport, and tool retry layers so hidden retries cannot exceed Firestore reservations or replay uncertain paid calls. Enforce the current durable operation attempt ceiling and reconcile ambiguous external results before retry. Confirm callback execution order and failure behavior against the pinned ADK version.
4. **Separate live validation authorization:** only after offline review, seek the existing project gate for tightly bounded paid calls/deployment. Test the exact target in `us-central1`, IAM, ADC, Firestore/GCS durability, model/TTS support, measured time and cost, rollback, and production pause. No result here authorizes a cloud mutation, paid call, deployment, human decision, or publication.

The existing durable operation/budget and approval controls stay authoritative in all options. In particular, ADK sessions are conversational state, not the ledger for approved scripts, revisions, attempts, provider debits, chapter quotas, or publication.

## Open compatibility questions

- Does the pinned ADK version route the current `google.genai` calls through `GOOGLE_GENAI_USE_ENTERPRISE` without changing structured multimodal request semantics? Verify in a narrow spike.
- Are the configured Gemini 3.8 model IDs exposed in Vertex AI in the selected region and supported by the current `interactions.create` path? Public TTS docs do not settle this exact pair.
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


## Approved provider migration follow-up

The user approved GCP SDK/service identity implementation with `us` inference
endpoint, separate from `us-central1` compute/storage. The initial TTS uncertainty
above is superseded by the current [Gemini 3.8 TTS overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/text-to-speech/overview):
it documents SDK >=2.33.0, enterprise ADC clients, `generate_content` with exact
text and speech metadata, and complete WAV bytes for unary output. The current
implementation adapts existing reviewed requests to that transport and validates
the returned WAV. It does not downgrade models or automatically add WAV headers.
Offline fixtures establish mapping and preservation, not real model quality or
project access. Live compatibility and paid-cost verification remain gated.
