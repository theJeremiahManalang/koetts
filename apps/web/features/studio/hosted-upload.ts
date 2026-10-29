const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const VALID_ID = /^[a-f0-9]{32}$/;

export function uploadTokenForIntent(idempotencyKey: string): string {
  const token = idempotencyKey.replaceAll("-", "");
  if (!VALID_ID.test(token)) throw new Error("The upload could not be identified. Retry the operation.");
  return token;
}

type SendFile = (name: string, file: File, uploadToken: string) => Promise<unknown>;

function fileFrom(form: FormData, name: string): File | null {
  const value = form.get(name);
  return value instanceof File && value.size > 0 ? value : null;
}

/** Upload each source separately, then return the small workflow request body. */
export async function prepareHostedUpload(
  form: FormData,
  sendFile: SendFile,
  uploadToken: string,
  workId?: string,
) {
  if (!VALID_ID.test(uploadToken)) throw new Error("The upload could not be identified. Retry the operation.");

  const action = String(form.get("action") || "");
  const mode = String(form.get("mode") || "");
  const uploads: { name: string; file: File }[] = [];
  let images: string[] | undefined;

  if (action === "create" && mode === "images") {
    const files = form.getAll("images").filter((value): value is File => value instanceof File && value.size > 0);
    if (files.length < 1 || files.length > 40) throw new Error("Choose 1–40 nonempty manga images.");
    images = files.map((file, index) => {
      const name = `${index}.png`;
      uploads.push({ name, file });
      return name;
    });
  } else if (action === "create" && (mode === "chapter" || mode === "restore")) {
    const file = fileFrom(form, "chapter");
    if (!file) throw new Error("Choose a ZIP file first.");
    uploads.push({ name: "chapter.zip", file });
  } else if (action === "cast-import") {
    const file = fileFrom(form, "cast");
    if (!file) throw new Error("Choose a cast ZIP file first.");
    uploads.push({ name: "cast.zip", file });
  } else {
    throw new Error("This operation cannot upload files in hosted mode.");
  }

  if (action === "create" && mode !== "restore") {
    const cast = fileFrom(form, "cast");
    if (cast) uploads.push({ name: "cast.zip", file: cast });
  }
  for (const { name, file } of uploads) {
    if (file.size > MAX_UPLOAD_BYTES) throw new Error(`${name} must be no larger than 10 MiB.`);
  }

  // Keep memory and in-flight request use bounded, including the 40-page case.
  for (const { name, file } of uploads) await sendFile(name, file, uploadToken);

  const payload: Record<string, unknown> = { action, upload_token: uploadToken };
  if (mode) payload.mode = mode;
  const direction = form.get("direction");
  if (direction) payload.direction = String(direction);
  const project = form.get("project");
  if (typeof project === "string" && VALID_ID.test(project)) payload.project = project;
  const revision = form.get("revision");
  if (typeof revision === "string" && revision) payload.revision = revision;
  if (images) payload.images = images;
  if (typeof workId === "string" && VALID_ID.test(workId)) payload.work_id = workId;
  return payload;
}

export function hostedWorkId(search: string): string | undefined {
  const value = new URLSearchParams(search).get("work");
  return value && VALID_ID.test(value) ? value : undefined;
}
