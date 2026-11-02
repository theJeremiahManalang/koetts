import type { Job } from "./types";

export function shouldReconnect(status?: number): boolean {
  return status === undefined || status === 408 || status === 429 || status >= 500;
}

export function takeOperationEvents(buffer: string): { events: Job[]; controls: string[]; remainder: string } {
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const remainder = blocks.pop() ?? "";
  const events: Job[] = [];
  const controls: string[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (["auth-expired", "stream-error", "reconnect"].includes(event)) {
      controls.push(event);
      continue;
    }
    if (event !== "operation" || !data.length) continue;
    const value = JSON.parse(data.join("\n")) as Partial<Job>;
    if (typeof value.id !== "string" || typeof value.project !== "string" || typeof value.message !== "string"
        || !["queued", "running", "complete", "failed", "reconciliation_required"].includes(value.status || "")) {
      throw new Error("Invalid operation event");
    }
    events.push(value as Job);
  }
  return { events, controls, remainder };
}
