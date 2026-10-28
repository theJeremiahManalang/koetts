export const requestStatuses = ["submitted", "approved", "processing", "ready", "rejected"] as const;
export type RequestStatus = typeof requestStatuses[number];
export type AdminRequest = {
  id: string;
  userId: string;
  requesterName: string;
  mangaTitle: string;
  chapter: number;
  notes: string;
  status: RequestStatus;
  createdAt: string;
};

export const requestActions: Record<RequestStatus, { status: RequestStatus; label: string }[]> = {
  submitted: [{ status: "approved", label: "Approve" }, { status: "rejected", label: "Reject" }],
  approved: [{ status: "processing", label: "Mark processing" }, { status: "rejected", label: "Reject" }],
  processing: [{ status: "ready", label: "Mark ready" }],
  ready: [],
  rejected: [{ status: "submitted", label: "Reopen request" }],
};

export function isRequestStatus(value: unknown): value is RequestStatus {
  return typeof value === "string" && requestStatuses.includes(value as RequestStatus);
}

/** Submitted requests are awaiting the same admin review as pending requests. */
export function normalizeRequestStatus(value: unknown): RequestStatus | null {
  const status = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (status === "submitted") return "submitted";
  return isRequestStatus(status) ? status : null;
}

export function isAdminRequest(value: unknown): value is AdminRequest {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return ["id", "userId", "requesterName", "mangaTitle", "notes", "createdAt"].every(key => typeof item[key] === "string")
    && typeof item.chapter === "number" && Number.isInteger(item.chapter) && isRequestStatus(item.status);
}
