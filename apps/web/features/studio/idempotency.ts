export const pendingOperationStorageKey = "manga-tts-pending-operation";

type IntentStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export type PendingOperationIntent = { key: string; fingerprint: string; conflicted?: boolean };

function readPendingIntents(storage: IntentStorage): PendingOperationIntent[] {
  try {
    const stored = storage.getItem(pendingOperationStorageKey);
    if (!stored) return [];
    const value: unknown = JSON.parse(stored);
    if (Array.isArray(value)) {
      return value.filter((entry): entry is PendingOperationIntent =>
        !!entry && typeof entry.key === "string" && typeof entry.fingerprint === "string",
      );
    }
    // Recover the single-intent format used by the first local UI implementation.
    if (
      value &&
      typeof value === "object" &&
      "key" in value &&
      typeof value.key === "string" &&
      "fingerprint" in value &&
      typeof value.fingerprint === "string"
    ) {
      return [{ key: value.key, fingerprint: value.fingerprint }];
    }
  } catch {
    // Discard invalid local recovery state.
  }
  return [];
}

function writePendingIntents(intents: PendingOperationIntent[], storage: IntentStorage): void {
  if (intents.length) storage.setItem(pendingOperationStorageKey, JSON.stringify(intents));
  else storage.removeItem(pendingOperationStorageKey);
}

export function idempotencyKeyForIntent(
  fingerprint: string,
  storage: IntentStorage = localStorage,
): string {
  const intents = readPendingIntents(storage);
  const existing = [...intents].reverse().find(
    (intent) => intent.fingerprint === fingerprint && !intent.conflicted,
  );
  if (existing) return existing.key;
  const key = crypto.randomUUID();
  intents.push({ key, fingerprint });
  writePendingIntents(intents, storage);
  return key;
}

export function clearConflictedOperationKey(
  code: string | undefined,
  key: string | undefined,
  storage: IntentStorage = localStorage,
): void {
  if (code !== "idempotency_conflict" || !key) return;
  const intents = readPendingIntents(storage).map((intent) =>
    intent.key === key ? { ...intent, conflicted: true } : intent,
  );
  writePendingIntents(intents, storage);
}

export function pendingOperationIntents(
  storage: IntentStorage = localStorage,
): PendingOperationIntent[] {
  return readPendingIntents(storage);
}

export function removePendingOperationKey(
  key: string,
  storage: IntentStorage = localStorage,
): void {
  writePendingIntents(readPendingIntents(storage).filter((intent) => intent.key !== key), storage);
}
