# Manga text web proof of concept

Local Next.js App Router + TypeScript + Tailwind CSS interface for the existing MAGI runner.

From the repository root, install the Python dependencies using the main README first. Then:

```powershell
cd web
npm install
npm run dev
```

Open http://127.0.0.1:3000. Upload a PNG, JPEG or WebP (10 MB maximum, 25 megapixels maximum), then click **MAGI v3 · Extract text**. Nothing runs on upload. The API runs real MAGI OCR, returns `{ "texts": ["..."] }`, and the page displays only the transcriptions. CTD is not offered as an OCR model because it only detects regions.

The server uses the repository's `.venv` Python automatically. Override with `PYTHON_EXECUTABLE` in `web/.env.local` if needed. No API key is needed. The first extraction downloads the pinned model; each request loads it in a fresh process. One extraction runs at a time, with a 15-minute timeout. Uploaded files are temporary and removed after processing. Text order is the model's output order.

This is a local proof of concept: run it on a machine with the Python environment and sufficient memory for MAGI. It is not a static website or a serverless deployment. Keep the server local; there is no authentication or shared job queue.

Checks: `npm run typecheck` and `npm run build`.

Verified locally: production build, TypeScript check, all 11 Python tests, and a
real sample-image upload returning HTTP 200 with nine transcriptions on CPU.
Missing-image and unsupported-model requests return 400; overlapping requests
return 429. The initial page was visually checked in the browser. Automated
browser file selection was unavailable, so the upload was verified over HTTP.

Framework references: [Next.js setup](https://nextjs.org/docs/app/getting-started/installation), [Tailwind CSS](https://tailwindcss.com/docs/installation/framework-guides/nextjs).
