# Developer resources

Developer-oriented project guides and the GCP architecture diagram live here.
Use [the documentation guide](../docs/README.md) for agent contracts, plans,
operational references, research and historical evidence.

| Task | Resource |
| --- | --- |
| Install tooling, configure GCP ADC and run locally | [Development](DEVELOPMENT.md) |
| Configure Firebase authentication and trusted admins | [Firebase Auth](FIREBASE_AUTH.md) |
| Review, synthesize, export and recover audio | [Audio workflow](AUDIO_WORKFLOW.md) |
| Install optional vision models and select CPU/CUDA | [Models](MODELS.md) |
| Configure frontend hosting and later region migration | [App Hosting](APP_HOSTING.md) |
| Visualize GCP services, regional boundaries, identity, data and billing flows | [GCP architecture diagrams](GCP_ARCHITECTURE.md) |

The diagrams use Google Cloud service names, project/region boundaries and labeled
connections in Mermaid. They show intended phase 5 architecture and staged frontend
migration; they do not establish live deployment. Current implementation and
acceptance are recorded in [status](../docs/STATUS.md).
