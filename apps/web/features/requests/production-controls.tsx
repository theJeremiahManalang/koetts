"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../identity/auth-provider";
import { getFirebaseAuth } from "../identity/firebase-client";

type ProductionStatus = {
  budget: {
    configured: boolean;
    paused: boolean;
    pause_reason?: string | null;
    provider_allowance_micro?: number;
    provider_reserved_micro?: number;
    provider_used_micro?: number;
    infrastructure_reported_micro?: number;
    infrastructure_reserved_micro?: number;
  };
  chapter_quota: { utc_month: string; used: number; limit: 5; remaining: number; pages_per_chapter: 40 };
  reader_limits: { pending: number; new_per_utc_day: number };
  artifact_collection: { active: boolean; epoch: number };
};

function validStatus(value: unknown): value is ProductionStatus {
  if (!value || typeof value !== "object") return false;
  const status = value as Partial<ProductionStatus>;
  const budget = status.budget;
  const quota = status.chapter_quota;
  const readers = status.reader_limits;
  const collection = status.artifact_collection;
  const budgetAmounts = [budget?.provider_allowance_micro, budget?.provider_reserved_micro, budget?.provider_used_micro,
    budget?.infrastructure_reported_micro, budget?.infrastructure_reserved_micro];
  return !!budget && typeof budget.configured === "boolean" && typeof budget.paused === "boolean"
    && (budget.configured ? budgetAmounts.every(Number.isSafeInteger) : budgetAmounts.every(value => value === undefined || Number.isSafeInteger(value)))
    && !!quota && typeof quota.utc_month === "string" && Number.isInteger(quota.used)
    && quota.limit === 5 && Number.isInteger(quota.remaining) && quota.pages_per_chapter === 40
    && !!readers && readers.pending === 5 && readers.new_per_utc_day === 10
    && !!collection && typeof collection.active === "boolean" && Number.isSafeInteger(collection.epoch);
}

function usd(microDollars: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(microDollars / 1_000_000);
}

async function responseJson(response: Response): Promise<unknown> {
  let payload: unknown;
  try { payload = await response.json(); } catch { throw new Error("Production status response is invalid."); }
  if (!response.ok) {
    const message = payload && typeof payload === "object" && "error" in payload && typeof payload.error === "string"
      ? payload.error : "Production control request failed. Try again.";
    throw new Error(message);
  }
  return payload;
}

export function ProductionControls() {
  const { user, authorizationReady } = useAuth();
  const identity = useRef({ uid: user?.uid ?? "", ready: authorizationReady });
  identity.current = { uid: user?.uid ?? "", ready: authorizationReady };
  const [status, setStatus] = useState<ProductionStatus | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const authorization = useCallback(async () => {
    const uid = identity.current.uid;
    if (!uid || !identity.current.ready) throw new Error("Verify your administrator account before continuing.");
    const current = getFirebaseAuth().currentUser;
    if (!current || current.uid !== uid) throw new Error("Verify your administrator account before continuing.");
    const token = await current.getIdToken();
    if (!identity.current.ready || identity.current.uid !== uid || getFirebaseAuth().currentUser?.uid !== uid) {
      throw new Error("Verify your administrator account before continuing.");
    }
    return { uid, headers: { Authorization: `Bearer ${token}` } };
  }, []);

  const refresh = useCallback(async () => {
    if (!identity.current.ready) return;
    setError("");
    try {
      const { headers } = await authorization();
      const result = await responseJson(await fetch("/api/production", { headers, cache: "no-store" }));
      if (!validStatus(result)) throw new Error("Production status response is invalid.");
      setStatus(result);
      setMessage("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Production status could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [authorization]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function setPaused(paused: boolean) {
    if (busy || !reason.trim() || !status) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const { headers } = await authorization();
      const response = await fetch("/api/production", {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ paused, reason: reason.trim() }),
        cache: "no-store",
      });
      const result = await responseJson(response);
      if (!validStatus(result)) throw new Error("Production status response is invalid.");
      setStatus(result);
      setMessage(paused ? "Production paused." : "Production resumed.");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Production control request failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const budget = status?.budget;
  const quota = status?.chapter_quota;
  const cleanup = status?.artifact_collection;
  const hasBudgetAmounts = !!budget && [budget.provider_allowance_micro, budget.provider_reserved_micro, budget.provider_used_micro,
    budget.infrastructure_reported_micro, budget.infrastructure_reserved_micro].every(Number.isSafeInteger);
  const allowanceAvailable = hasBudgetAmounts ? budget!.provider_allowance_micro! - budget!.provider_reserved_micro! - budget!.provider_used_micro! : null;

  return <section className="production-controls" aria-labelledby="production-controls-title">
    <div className="production-controls-heading">
      <div><p className="browse-eyebrow">Hosted production</p><h2 id="production-controls-title">Production status</h2></div>
      <button type="button" className="button" disabled={busy || loading} onClick={() => void refresh()}>Refresh status</button>
    </div>
    {error && <p className="notice error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {loading && !status ? <p role="status">Loading production status…</p> : status ? <>
      <div className="production-status-list" aria-live="polite">
        <p><strong>Production:</strong> {!budget?.configured ? "Unconfigured" : budget.paused ? "Paused" : "Active"}{budget?.paused && budget.pause_reason ? ` · ${budget.pause_reason}` : ""}</p>
        {!budget?.configured && <p className="production-status-warning">Provider budget is not configured. Generation stays unavailable.</p>}
        <p><strong>Chapter quota:</strong> {quota?.utc_month} UTC · {quota?.used}/{quota?.limit} chapters used · {quota?.remaining} remaining · up to {quota!.remaining * quota!.pages_per_chapter} pages remaining</p>
        <p><strong>Reader limits:</strong> {status.reader_limits.pending} pending requests per reader · {status.reader_limits.new_per_utc_day} new requests per UTC day</p>
        {hasBudgetAmounts ? <>
          <p><strong>Provider allowance available:</strong> {usd(allowanceAvailable!)} ({usd(budget!.provider_allowance_micro!)} allowance − {usd(budget!.provider_reserved_micro!)} reserved − {usd(budget!.provider_used_micro!)} used)</p>
          <p><strong>Infrastructure cost estimate:</strong> {usd(budget!.infrastructure_reported_micro!)} reported · {usd(budget!.infrastructure_reserved_micro!)} reserved</p>
        </> : <p><strong>Cost estimates:</strong> Unavailable until the provider budget is configured.</p>}
        {cleanup?.active && <p className="production-status-warning" role="status">Artifact cleanup is running (epoch {cleanup.epoch}).</p>}
        {!cleanup?.active && <p><strong>Artifact cleanup:</strong> idle (epoch {cleanup!.epoch})</p>}
      </div>
      <p className="control-note">USD values are maximum-cost estimates, not an actual bill. Billing can be delayed; estimates do not guarantee a spending ceiling.</p>
      <div className="production-pause-controls">
        <label htmlFor="production-pause-reason">Reason for pause or resume</label>
        <textarea id="production-pause-reason" value={reason} maxLength={500} rows={2} onChange={event => setReason(event.target.value)} aria-describedby="production-reason-help" />
        <p id="production-reason-help" className="control-note">A reason is recorded with each operator action.</p>
        {budget?.paused
          ? <button type="button" className="button primary" disabled={busy || !reason.trim() || !budget.configured} onClick={() => void setPaused(false)}>{busy ? "Saving…" : "Resume production"}</button>
          : <button type="button" className="button" disabled={busy || !reason.trim() || !budget?.configured} onClick={() => void setPaused(true)}>{busy ? "Saving…" : "Pause production"}</button>}
      </div>
    </> : <p role="status">Production status is unavailable. Refresh to try again.</p>}
  </section>;
}
