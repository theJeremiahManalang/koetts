"use client";

import { createContext, useContext, useEffect, useId, useRef, useState, type ButtonHTMLAttributes } from "react";
import { Toaster, toast } from "sonner";
import { ImageOrder } from "./image-order";
import { CastWorkspace } from "./cast-workspace";
import { SourceWorkspace } from "./source-workspace";
import { ScriptWorkspace } from "./script-workspace";
import { LoadingState } from "./loading-state";
import {
  clearConflictedOperationKey,
  idempotencyKeyForIntent,
  pendingOperationIntents,
  removePendingOperationKey,
} from "./idempotency";
import type { Acting, Job, Project, Segment, Snapshot } from "./types";
import { getFirebaseAuth } from "../identity/firebase-client";
import { useAuth } from "../identity/auth-provider";
import { RequireSignIn } from "../identity/require-sign-in";
import { AdminNav } from "../identity/admin-nav";
import { StudioRequestContext } from "./studio-request-context";
import { AccountNav } from "../identity/account-nav";

type Tab = "cast" | "proposal" | "sources" | "script" | "audio";
const tabs: [Tab, string][] = [["cast", "Cast"], ["proposal", "AI proposal"], ["sources", "Source & order"], ["script", "Script approval"], ["audio", "Audio & export"]];
const actingFields = (v: Acting) => ({ include: v.include, speaker_id: v.speaker_id, text: v.text, delivery: v.delivery, emotion: v.emotion, style: v.style, pacing: v.pacing });
const assetUrl = (id: string, path: string, download = false) => `/api/asset?project=${encodeURIComponent(id)}&path=${encodeURIComponent(path)}${download ? "&download=1" : ""}`;

type Operation = { pending: string; success: string; detail: string; section?: Tab | null };
function operationFor(action: string, command: unknown = {}, mode = ""): Operation {
  const values = command as { approve?: boolean; title?: string; name?: string; scene_ids?: string[]; regenerate?: string[]; scenes?: { approve?: boolean }[] };
  const scenes = `${values.scene_ids?.length ?? 0} selected scene(s)`;
  const labels: Record<string, Operation> = {
    create: mode === "restore" ? { pending: "Restoring your saved project…", success: "Project restored", detail: "Saved references, script, approvals and retained audio are ready to review." }
      : { pending: mode === "images" ? "Uploading manga images for panel detection…" : "Importing chapter analysis…", success: "Chapter ready for review", detail: "Open the Annotated view to inspect detections, then review the cast and reading order." },
    "cast-import": { pending: "Importing cast references…", success: "Cast references imported", detail: "Review character assignments and approve the updated cast." },
    "cast-create": { pending: `Creating ${values.name || "character"} from the selected crop…`, success: `${values.name || "Character"} added to cast`, detail: "The selected appearance is assigned. Review and approve the updated cast." },
    cast: { pending: values.approve ? "Saving and approving the cast…" : "Saving cast assignments and voices…", success: values.approve ? "Cast saved and approved" : "Cast changes saved", detail: values.approve ? "Continue to script approval to review each scene." : "Review assignments before approving the cast." },
    plan: { pending: "Generating a visual direction proposal…", success: "Visual proposal generated", detail: "Review the proposal before loading it. Your script has not changed." },
    proposal: { pending: "Applying the proposal to your review workspace…", success: "Proposal loaded for review", detail: "Review cast, sources and script again. Previous approvals have been cleared." },
    sources: { pending: "Saving source text and reading order…", success: "Sources saved and scene turns rebuilt", detail: "Review the rebuilt script and approve the affected scenes." },
    script: { pending: `Saving ${values.title || "scene script"}${values.approve ? " and approval" : ""}…`, success: `${values.title || "Scene script"} saved${values.approve ? " and approved" : ""}`, detail: values.approve ? "This scene is ready for audio once the cast and other selected scenes are approved." : "Review and approve this scene before rendering audio." },
    "script-batch": { pending: `Saving ${values.scenes?.length ?? 0} scene(s) and their review decisions…`, success: `${values.scenes?.length ?? 0} scene(s) saved`, detail: `${values.scenes?.filter(s => s.approve).length ?? 0} explicitly reviewed scene(s) approved. Other saved edits remain drafts for review.` },
    "sync-speakers": { pending: "Matching dialogue speakers to your Cast assignments…", success: "Dialogue speakers updated from Cast", detail: "Clear character links have been applied. Unlinked or ambiguous dialogue still needs speaker review. Manual choices were preserved." },
    narration: { pending: "Adding evidence-based narration…", success: "Narration added to the scene", detail: "Review the narration in the script and approve the updated scene." },
    inspect: { pending: `Inspecting audio segments for ${scenes}…`, success: "Audio segments ready for review", detail: "Inspect the spoken text, synthesis requests and available takes below." },
    render: { pending: `${values.regenerate?.length ? "Regenerating" : "Rendering"} audio for ${scenes}…`, success: "Audio rendering complete", detail: "Listen to the available takes, choose your preferred audio, then export." },
    take: { pending: "Saving your selected audio take…", success: "Audio take selected", detail: "The next export will use this take." },
    export: { pending: `Assembling chapter audio from ${scenes}…`, success: "Chapter audio exported", detail: "Playback and download files are ready in Audio & export." },
    bundle: { pending: "Packaging your saved project…", success: "Project bundle ready", detail: "Use Download resumable project ZIP to save your project and retained audio." },
    rename: { pending: "Saving project title…", success: "Project renamed", detail: "The new title is saved. Chapter identifiers and approvals are unchanged." },
    settings: { pending: "Saving production settings…", success: "Production settings saved", detail: "Future planning and audio requests will use these settings." },
  };
  return labels[action] ?? { pending: "Resuming your saved operation…", success: "Saved operation complete", detail: "The latest project state is ready to review." };
}
const operationToast = "workflow-operation";
function formFingerprint(form: FormData) {
  const entries: unknown[][] = [];
  form.forEach((value, key) => {
    entries.push([key, value instanceof File
      ? { name: value.name, size: value.size, type: value.type, modified: value.lastModified }
      : value]);
  });
  return JSON.stringify(entries);
}
const BusyContext = createContext("");
function ActionButton({ disabled, reason, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { reason?: string }) {
  const busy = useContext(BusyContext);
  const hintId = useId();
  const message = busy ? `Wait for the current operation to finish: ${busy}` : disabled ? reason || "Complete the required fields first." : "";
  if (!message) return <button {...props}>{children}</button>;
  return <span className="disabled-action" tabIndex={0} role="group" aria-label={props["aria-label"] || (typeof children === "string" ? children : "Unavailable action")} aria-describedby={hintId}>
    <button {...props} disabled aria-describedby={hintId}>{children}</button>
    <span className="action-tooltip" role="tooltip" id={hintId}>{message}</span>
  </span>;
}

export default function Home() {
  const { user, isAdmin, loading, error } = useAuth();
  if (loading) return <LoadingState />;
  if (!user || !isAdmin) return <main><h1>Administrator access required</h1><p>{error || "Sign in with an administrator account to use the studio."}</p><a href="/browse">Return to the library</a></main>;
  return <RequireSignIn><StudioWorkspace key={user.uid} /></RequireSignIn>;
}

function StudioWorkspace() {
  const { user: signedInUser, authorizationReady } = useAuth();
  const authorization = useRef({ uid: signedInUser?.uid, ready: authorizationReady });
  authorization.current = { uid: signedInUser?.uid, ready: authorizationReady };
  const [projects, setProjects] = useState<{ id: string; name: string; scenes: number }[]>([]);
  const [projectId, setProjectId] = useState("");
  const [titleDraft, setTitleDraft] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [errorSection, setErrorSection] = useState<Tab | null>(null);
  const operationSection = useRef<Tab | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [draft, setDraft] = useState<Project | null>(null);
  const [tab, setTab] = useState<Tab>("cast");
  const [pageIndex, setPageIndex] = useState(0);
  const [sceneId, setSceneId] = useState("");
  const [imageTab, setImageTab] = useState<"original" | "annotated">("annotated");
  const [zoom, setZoom] = useState(100);
  const artStage = useRef<HTMLDivElement>(null);
  const [viewerSize, setViewerSize] = useState({ width: 0, height: 0 });
  const [imageSize, setImageSize] = useState({ src: "", width: 0, height: 0 });
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const [initialLoading, setInitialLoading] = useState(true);
  function startOperation(operation: Operation) {
    setBusy(operation.pending);
    toast.loading(operation.pending, { id: operationToast, description: "Keep this page open, or reload to reconnect to the saved job." });
  }
  function failOperation(operation: Operation, error: unknown) {
    setErrorSection(operationSection.current);
    toast.error(operation.pending.replace(/…$/, "") + " failed", { id: operationToast, description: error instanceof Error ? error.message : "The connection was interrupted. Reload to reconnect to your saved job.", duration: Infinity, action: projectId ? { label: "Reload saved chapter", onClick: async () => { if (await canLeave()) void openProject(projectId); } } : undefined });
  }
  async function openProject(id: string) {
    operationSection.current = null;
    setErrorSection(null);
    const operation = { pending: "Loading saved chapter…", success: "Saved chapter loaded", detail: "Your saved cast, script, annotations and audio are ready to review." };
    startOperation(operation);
    try { await loadProject(id); toast.success(operation.success, { id: operationToast, description: operation.detail }); }
    catch (e) { failOperation(operation, e); }
    finally { setBusy(""); }
  }
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<Map<File, string>>(new Map());
  const previewUrls = useRef(new Map<File, string>());
  const [mode, setMode] = useState("images");
  const [archive, setArchive] = useState<File | null>(null);
  const [castZip, setCastZip] = useState<File | null>(null);
  const [direction, setDirection] = useState("rtl");
  const [proposal, setProposal] = useState("");
  const [selectedScenes, setSelectedScenes] = useState<string[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [bundleReady, setBundleReady] = useState(false);
  const [hasKey, setHasKey] = useState(false);
  const [focusSource, setFocusSource] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const initialized = useRef(false);
  const leaveDecision = useRef<Promise<boolean> | null>(null);
  const page = snapshot?.pages[pageIndex];
  const orderedPages = snapshot ? (draft?.page_order?.length ? draft.page_order.map(id => snapshot.pages.find(p => p.page_id === id)!).filter(Boolean) : snapshot.pages) : [];
  const pagePosition = page ? Math.max(0, orderedPages.findIndex(p => p.page_id === page.page_id)) : pageIndex;
  const imageCount = snapshot ? orderedPages.length : files.length;
  const imagePosition = snapshot ? pagePosition : pageIndex;
  function stepImage(offset: number) {
    const position = imagePosition + offset;
    if (position < 0 || position >= imageCount) return;
    setPageIndex(snapshot ? snapshot.pages.findIndex(p => p.page_id === orderedPages[position].page_id) : position);
    setZoom(100);
    setFocusSource("");
    artStage.current?.scrollTo(0, 0);
  }
  const activeImageTab = snapshot ? imageTab : "original";
  const imagePath = activeImageTab === "annotated" ? page?.annotated_path : page?.original_path;
  const preview = snapshot ? (imagePath ? assetUrl(projectId, imagePath) : undefined) : previews.get(files[pageIndex]);
  const fitWidth = imageSize.src === preview && imageSize.width && viewerSize.width
    ? Math.min(viewerSize.width, viewerSize.height * imageSize.width / imageSize.height) : 0;
  useEffect(() => {
    setZoom(100);
    const stage = artStage.current;
    if (!stage || !preview) return;
    stage.scrollTo(0, 0);
    const observer = new ResizeObserver(() => setViewerSize({ width: stage.clientWidth, height: stage.clientHeight }));
    observer.observe(stage);
    return () => observer.disconnect();
  }, [preview]);
  const focused = draft?.sources.find(s => s.source_id === focusSource && s.page_id === page?.page_id);

  async function api(url: string, options?: RequestInit, idempotencyKey?: string) {
    const readOnly = !options?.method || options.method === "GET";
    while (true) {
      const user = getFirebaseAuth().currentUser;
      if (!mounted.current || !user || authorization.current.uid !== user.uid) throw new Error("Verify your account before continuing. Your draft is retained.");
      if (!authorization.current.ready) {
        if (!readOnly) throw new Error("Verify your account before continuing. Your draft is retained.");
        // Keep read/poll recovery alive through same-account reauthentication.
        // Mutation requests are never automatically replayed.
        await new Promise(resolve => setTimeout(resolve, 100));
        continue;
      }
      const headers = new Headers(options?.headers);
      headers.set("Authorization", `Bearer ${await user.getIdToken()}`);
      if (!mounted.current || getFirebaseAuth().currentUser?.uid !== user.uid || !authorization.current.ready || authorization.current.uid !== user.uid) {
        if (readOnly) continue;
        throw new Error("Verify your account before continuing. Your draft is retained.");
      }
      const r = await fetch(url, { ...options, headers }); const data = await r.json();
      if (!mounted.current || getFirebaseAuth().currentUser?.uid !== user.uid) throw new Error("Your account changed. Sign in again to resume this operation.");
      if (!r.ok) {
        const code = typeof data.code === "string" ? data.code : undefined;
        clearConflictedOperationKey(code, idempotencyKey);
        const error = new Error(data.error || "Request failed.") as Error & { code?: string };
        error.code = code;
        throw error;
      }
      return data;
    }
  }
  async function refreshList() { const data = await api("/api/workflow"); setProjects(data.projects); setHasKey(data.has_api_key); }
  async function loadProject(id: string) {
    const data: Snapshot = await api(`/api/workflow?project=${id}`);
    setProjectId(id); setTitleDraft(data.project.title || data.project.chapter_id); setRenaming(false); setSnapshot(data); setDraft(structuredClone(data.project)); setDirty(false);
    setHasKey(data.has_api_key); setProposal(JSON.stringify(data.project.proposal?.data ?? null, null, 2));
    setSceneId(previous => data.project.scenes.some(s => s.scene_id === previous) ? previous : data.project.scenes[0]?.scene_id ?? "");
    setSelectedScenes(previous => previous.some(id => data.project.scenes.some(s => s.scene_id === id)) ? previous.filter(id => data.project.scenes.some(s => s.scene_id === id)) : data.project.scenes.map(s => s.scene_id));
    setPageIndex(i => { const selected = snapshot?.pages[i]?.page_id; const next = data.pages.findIndex(p => p.page_id === selected); return next >= 0 ? next : Math.min(i, Math.max(0, data.pages.length - 1)); });
    setSegments([]); setBundleReady(false);
    localStorage.setItem("manga-tts-project", id);
  }
  async function watch(job: { id: string; project: string; operation?: Operation; idempotencyKey?: string }) {
    const operation = job.operation ?? operationFor("resume");
    operationSection.current = operation.section ?? null;
    startOperation(operation);
    let lastProgress = "";
    localStorage.setItem("manga-tts-job", JSON.stringify(job));
    try {
      while (mounted.current) {
        const state: Job = await api(`/api/workflow?job=${job.id}`);
        setBusy(state.message || operation.pending);
        if (state.status === "reconciliation_required") {
          toast.error("Operation needs reconciliation", {
            id: operationToast,
            description: `${state.message} Operation ${job.id}. Resolve locally with web_workflow.py reconcile ${job.id} fail|retry.`,
            duration: Infinity,
          });
          return false;
        }
        if (!["complete", "failed"].includes(state.status) && state.message !== lastProgress) {
          lastProgress = state.message;
          toast.loading(operation.pending, { id: operationToast, description: state.message || "Waiting for processing to begin…" });
        }
        if (["complete", "failed"].includes(state.status)) {
          await refreshList();
          if (state.status === "failed") {
            localStorage.removeItem("manga-tts-job");
            if (job.idempotencyKey) removePendingOperationKey(job.idempotencyKey);
            // Preserve editable drafts on failure; explicit reload recovers partial audio.
            throw new Error(state.message);
          }
          await loadProject(job.project);
          localStorage.removeItem("manga-tts-job");
          if (job.idempotencyKey) removePendingOperationKey(job.idempotencyKey);
          if (state.result?.segments) setSegments(state.result.segments);
          setErrorSection(null);
          toast.success(operation.success, { id: operationToast, description: operation.detail, duration: 6500 });
          return true;
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    } catch (e) { failOperation(operation, e); }
    finally { setBusy(""); }
    return false;
  }
  useEffect(() => {
    mounted.current = true;
    if (initialized.current) return () => { mounted.current = false; };
    initialized.current = true;
    void (async () => {
      try {
        await refreshList();
        const job = localStorage.getItem("manga-tts-job");
        if (job) {
          setInitialLoading(false);
          setBusy("Reconnecting to your job…");
          const savedJob = JSON.parse(job) as { idempotencyKey?: string } & Parameters<typeof watch>[0];
          await watch(savedJob);
        }
        else {
          for (const pending of pendingOperationIntents()) {
            try {
              const operation = await api(`/api/workflow?key=${encodeURIComponent(pending.key)}`);
              const watching = watch({ ...operation, idempotencyKey: pending.key });
              setInitialLoading(false);
              await watching;
              return;
            } catch { /* The POST may not have reached persistence; keep its key for lookup or retry. */ }
          }
          const entry = new URLSearchParams(window.location.search);
          const createForRequest = entry.get("create") === "1" && !!entry.get("request");
          const id = localStorage.getItem("manga-tts-project"); if (id && !createForRequest) await openProject(id);
        }
      } catch (e) { toast.error("Saved projects could not be loaded", { description: e instanceof Error ? e.message : "Check the server connection and reload the page.", duration: Infinity }); }
      finally { setInitialLoading(false); }
    })();
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    const urls = previewUrls.current;
    for (const [file, url] of urls) if (!files.includes(file)) { URL.revokeObjectURL(url); urls.delete(file); }
    for (const file of files) if (!urls.has(file)) urls.set(file, URL.createObjectURL(file));
    setPreviews(new Map(urls));
  }, [files]);
  useEffect(() => () => { for (const url of previewUrls.current.values()) URL.revokeObjectURL(url); previewUrls.current.clear(); }, []);
  function reorderImages(next: File[]) {
    if (busy) return;
    const selected = files[pageIndex];
    setFiles(next);
    setPageIndex(Math.max(0, next.indexOf(selected)));
  }
  useEffect(() => { const handler = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); } }; window.addEventListener("beforeunload", handler); return () => window.removeEventListener("beforeunload", handler); }, [dirty]);
  function edit(change: (p: Project) => void) { setDraft(p => { if (!p) return p; const next = structuredClone(p); change(next); return next; }); setDirty(true); setBundleReady(false); }
  async function canLeave() {
    if (!dirty) return true;
    if (leaveDecision.current) return false;
    leaveDecision.current = new Promise<boolean>(resolve => {
      const finish = (discard: boolean) => { leaveDecision.current = null; resolve(discard); };
      toast.warning(`Unsaved changes in ${tabs.find(([id]) => id === tab)?.[1] || "this section"}`, {
        id: "unsaved-changes", description: "Leaving will discard your edits. Apply them first, or choose Discard edits to continue.",
        duration: Infinity, dismissible: false, closeButton: false,
        action: { label: "Discard edits", onClick: () => finish(true) },
        cancel: { label: "Keep editing", onClick: () => finish(false) },
      });
    });
    return leaveDecision.current;
  }
  async function switchTab(next: Tab) { if (next === tab || !await canLeave()) return; setDraft(structuredClone(snapshot!.project)); setProposal(JSON.stringify(snapshot!.project.proposal?.data ?? null, null, 2)); setDirty(false); setTab(next); }
  async function run(action: string, command: unknown = {}, extra = {}) {
    if (busy || !snapshot) return false;
    operationSection.current = ({ cast: "cast", "cast-create": "cast", "cast-import": "cast", plan: "proposal", proposal: "proposal", sources: "sources", script: "script", "script-batch": "script", "sync-speakers": "script", narration: "script", inspect: "audio", render: "audio", take: "audio", export: "audio", settings: "audio", bundle: "audio" } as Record<string, Tab>)[action] ?? null;
    setErrorSection(null);
    const operation = { ...operationFor(action, command), section: operationSection.current };
    startOperation(operation);
    try {
      const payload = { project: projectId, revision: snapshot.revision, action, command, ...extra };
      const fingerprint = JSON.stringify(payload);
      const key = idempotencyKeyForIntent(fingerprint);
      const job = await api("/api/workflow", { method: "POST", headers: { "Content-Type": "application/json", "X-Manga-Workflow": "1", "Idempotency-Key": key }, body: JSON.stringify(payload) }, key);
      const ok = await watch({ ...job, operation, idempotencyKey: key });
      if (ok && ["take", "export", "bundle"].includes(action)) setSegments(segments);
      if (ok && action === "bundle") setBundleReady(true);
      return ok;
    } catch (e) { failOperation(operation, e); setBusy(""); return false; }
  }
  async function upload(form: FormData) {
    if (busy) return;
    operationSection.current = "cast";
    setErrorSection(null);
    const operation = { ...operationFor(String(form.get("action")), {}, String(form.get("mode") || "")), section: operationSection.current };
    startOperation(operation);
    try {
      const key = idempotencyKeyForIntent(formFingerprint(form));
      const job = await api("/api/workflow", { method: "POST", headers: { "X-Manga-Workflow": "1", "Idempotency-Key": key }, body: form }, key);
      await watch({ ...job, operation, idempotencyKey: key });
    }
    catch (e) { failOperation(operation, e); setBusy(""); }
  }
  function createProject() {
    setTab("cast");
    const form = new FormData(); form.set("action", "create"); form.set("mode", mode); form.set("direction", direction);
    files.forEach(f => form.append("images", f)); if (archive && mode !== "images") form.set("chapter", archive); if (castZip && mode !== "restore") form.set("cast", castZip);
    void upload(form);
  }
  function importCast(file: File | undefined) { if (!file) return; const form = new FormData(); form.set("action", "cast-import"); form.set("project", projectId); form.set("revision", snapshot!.revision); form.set("cast", file); void upload(form); }
  function selectFiles(selected: FileList | null) {
    if (!selected || !selected.length) return;
    const next = Array.from(selected).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    if (next.length > 10 || next.some(f => !["image/png", "image/jpeg", "image/webp"].includes(f.type) || !f.size || f.size > 10 * 1024 * 1024)) { toast.error("Manga images were not selected", { description: "Choose 1–10 nonempty PNG, JPEG or WebP images, no larger than 10 MB each.", duration: 10000 }); return; }
    setFiles(next); setPageIndex(0); toast.success(`${next.length} manga image(s) selected`, { description: "Review their order, then create the chapter to detect panels and annotations." });
  }
  function saveCast(approve = false) { if (!draft) return; void run("cast", { cast: Object.entries(draft.cast).map(([speaker_id, c]) => ({ speaker_id, name: c.name, voice: c.voice, pronunciation: c.pronunciation, acting_notes: c.acting_notes ?? "" })), appearances: draft.appearances.map(({ char_id, speaker_id, rejected }) => ({ char_id, speaker_id, rejected })), new_characters: draft.pending_characters ?? [], approve }); }
  function saveSources() { if (!draft) return; void run("sources", { sources: draft.sources.map(s => ({ ...actingFields(s), source_id: s.source_id, speaker_origin: s.speaker_origin === "manual" ? "manual" : undefined, order: s.order, scene_id: s.scene_id, turn_group: s.turn_group, reaction: s.reaction })), page_order: draft.page_order?.length ? draft.page_order : snapshot!.pages.map(p => p.page_id), panel_order: draft.panel_order ?? {} }); }
  const pendingScenes = snapshot?.project.scenes.filter(s => !snapshot.approved_scenes.includes(s.scene_id)) ?? [];
  const unapprovedSelected = pendingScenes.filter(s => selectedScenes.includes(s.scene_id));
  const unresolved = draft?.appearances.filter(a => !a.rejected && !draft.cast[a.speaker_id]).length ?? 0;
  const audioBlocker = dirty ? "Apply or discard your unsaved edits first. Changed content may need approval again."
    : !snapshot?.cast_approved ? "Approve the cast in the Cast section first."
    : !selectedScenes.length ? "Select at least one scene in Audio & export."
    : unapprovedSelected.length ? `Approve these scenes in Script approval: ${unapprovedSelected.map(s => s.title || s.scene_id).join(", ")}.` : "";
  const selectedAudioMissing = selectedScenes.filter(id => !snapshot?.workflow_status.audio_ready_scenes.includes(id));
  const exportBlocker = audioBlocker || (selectedAudioMissing.length ? "Render audio for all selected scenes before exporting." : "");
  const exportScenes = draft?.scenes.filter(s => selectedScenes.includes(s.scene_id)) ?? [];
  const sectionInstructions: Record<Tab, string> = {
    cast: "Assign detected characters, choose their voices, resolve or reject unknown appearances, then approve the cast.",
    proposal: "Optional: generate and review a proposal, then load it if useful. You can complete the chapter without this step.",
    sources: "Correct detected text, confirm speakers and reading order, then apply sources to rebuild scene turns.",
    script: "Review each scene’s dialogue, narration and delivery. Mark reviewed scenes, then save your edits and approvals together.",
    audio: "Select approved scenes, render audio, listen to and select your preferred takes, then export the chapter.",
  };
  function sectionStatus(id: Tab): { icon: string; label: string; done: boolean } {
    const status = (icon: string, label: string, done = false) => ({ icon, label, done });
    if (busy && operationSection.current === id) return status("◌", "Processing");
    if (errorSection === id) return status("!", "Action needed");
    if (!snapshot) return status("○", "Needs review");
    const affected = dirty && (id === tab || ((id === "script" || id === "audio") && ["cast", "proposal", "sources", "audio"].includes(tab)) || (id === "cast" && tab === "proposal"));
    if (affected) return status("○", "Unsaved · needs review");
    const saved = snapshot.workflow_status;
    if (id === "cast") return snapshot.cast_approved ? status("✓", "Approved", true) : unresolved ? status("!", `${unresolved} unresolved`) : status("○", "Needs approval");
    if (id === "proposal") return saved.proposal_applied ? status("✓", "Applied · optional", true) : status("○", snapshot.project.proposal ? "Ready to review · optional" : "Optional");
    if (id === "sources") return saved.sources_reviewed ? status("✓", "Reviewed", true) : status("○", "Needs review");
    const count = snapshot.project.scenes.length;
    if (id === "script") return count > 0 && !pendingScenes.length && snapshot.cast_approved ? status("✓", `${count}/${count} approved`, true) : status("○", `${snapshot.approved_scenes.length}/${count} approved`);
    if (count > 0 && saved.exported_scenes.length === count && saved.audio_ready_scenes.length === count) return status("✓", "Export complete", true);
    if (count > 0 && saved.audio_ready_scenes.length === count) return status("✓", "Audio ready · export next", true);
    if (saved.exported_scenes.length) return status("○", `${saved.exported_scenes.length}/${count} scenes exported`);
    return status("○", saved.audio_ready_scenes.length ? `${saved.audio_ready_scenes.length}/${count} audio ready` : "Needs audio");
  }
  async function openApproval(target: Tab, id?: string) {
    if (busy || !await canLeave()) return;
    setDraft(structuredClone(snapshot!.project)); setDirty(false); setTab(target);
    if (id) setSceneId(id);
  }

  return <BusyContext.Provider value={busy}><div className="app-shell">
    <Toaster position="top-right" closeButton theme="light" toastOptions={{ duration: 6500, classNames: { toast: "reader-toast" } }} />
    {initialLoading && <LoadingState label={busy || "Preparing your reading space…"} />}
    <div hidden={initialLoading}>
    {busy && !initialLoading && <LoadingState compact label={busy} />}
    <header className="site-header"><a className="brand" href="/" aria-label="KoeTTS home"><span className="brand-icon" aria-hidden="true">▥</span><span><span className="eyebrow">A STORY IN EVERY PANEL</span><span className="brand-title">KoeTTS<span className="brand-dot">.</span></span></span></a><AdminNav active="studio" canNavigate={async () => !busy && await canLeave()} /><div className="header-actions"><ActionButton className="button" disabled={!!busy} onClick={async () => { if (!await canLeave()) return; setSnapshot(null); setDraft(null); setProjectId(""); setDirty(false); setFiles([]); setArchive(null); setPageIndex(0); localStorage.removeItem("manga-tts-project"); }}>＋ New chapter</ActionButton><AccountNav /></div></header>
    <main>
      <section className="studio-generation-panel" aria-label="Audio generation project">
        <div className="studio-generation-details">
          <div className="studio-generation-summary">
            <StudioRequestContext projectTitle={snapshot ? snapshot.project.title || snapshot.project.chapter_id : undefined} projectStatus={snapshot ? `${snapshot.approved_scenes.length}/${snapshot.project.scenes.length} scenes approved` : undefined} />
          </div>
          <div className="studio-project-picker"><p className="studio-active-project" role="status"><span>Project for audio</span><strong>{snapshot ? snapshot.project.title || snapshot.project.chapter_id : "New chapter"}</strong></p><label htmlFor="projects">Use a saved project</label><select id="projects" value={projectId} disabled={!!busy} onChange={async e => { const id = e.target.value; if (id && await canLeave()) { void openProject(id); } }}><option value="" disabled>Choose a saved project</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name} · {p.id.slice(0, 6)}</option>)}</select>{!projects.length && <span className="control-note">No saved chapters yet.</span>}</div>
        </div>
      </section>
      {snapshot && <div className="project-title-row">{renaming ? <form className="action-row" onSubmit={e => { e.preventDefault(); if (titleDraft.trim() && !dirty) void run("rename", { title: titleDraft.trim() }); }}><label className="field-label">Project title<input autoFocus maxLength={120} required value={titleDraft} disabled={!!busy} onChange={e => setTitleDraft(e.target.value)} /></label><ActionButton type="submit" className="button primary" disabled={dirty || !titleDraft.trim()} reason={dirty ? "Apply your section edits before saving a new title." : "Enter a project title."}>Save title</ActionButton><ActionButton type="button" className="button" onClick={() => { setRenaming(false); setTitleDraft(snapshot.project.title || snapshot.project.chapter_id); }}>Cancel</ActionButton></form> : <><strong>{snapshot.project.title || snapshot.project.chapter_id}</strong><ActionButton className="button small" disabled={dirty} reason="Apply or discard your section edits before renaming the project." onClick={() => setRenaming(true)}>Rename project</ActionButton></>}</div>}
      {snapshot && <nav className="workflow-tabs" aria-label="Production steps">{tabs.map(([id, title], i) => <ActionButton key={id} className="button" aria-current={tab === id ? "step" : undefined} disabled={!!busy} onClick={() => switchTab(id)}><span aria-hidden="true">{sectionStatus(id).icon}</span><span className="step-title">{title}<small>{sectionStatus(id).label}</small></span></ActionButton>)}</nav>}
      {snapshot && <div className="section-guidance" aria-live="polite"><div><strong>{tabs.find(([id]) => id === tab)?.[1]} <span className={`step-status ${sectionStatus(tab).done ? "complete" : ""}`}>{sectionStatus(tab).label}</span></strong><p>{sectionInstructions[tab]}</p>{dirty && <p className="unsaved">Unsaved changes. Apply your edits to update section status.</p>}</div></div>}
      {!snapshot && mode === "images" && files.length > 0 && <ImageOrder files={files} previews={previews} selected={pageIndex} disabled={!!busy} onSelect={i => { setPageIndex(i); setZoom(100); }} onReorder={reorderImages} />}
      {snapshot && <div className="page-list" aria-label="Page order">{orderedPages.map((item, i) => <div key={item.page_id}><ActionButton className="button" aria-pressed={page?.page_id === item.page_id} onClick={() => { setPageIndex(snapshot.pages.findIndex(p => p.page_id === item.page_id)); setZoom(100); }}>{i + 1}. {item.page_id}</ActionButton></div>)}</div>}
      <div className="reader-grid">
        <section className="art-card" aria-label="Manga artwork"><div className="art-toolbar"><span>{preview ? `IMAGE ${pagePosition + 1} / ${snapshot?.pages.length ?? files.length}` : "YOUR MANGA"}</span><span>{focused ? "HIGHLIGHTED SOURCE" : "VISUAL EVIDENCE"}</span></div>
          <div className="segmented-control image-tabs" role="tablist" aria-label="Manga image view">{(["original", "annotated"] as const).map(id => <button key={id} id={`image-tab-${id}`} role="tab" aria-selected={activeImageTab === id} aria-controls="manga-image-panel" tabIndex={activeImageTab === id ? 0 : -1} disabled={!snapshot && id === "annotated"} onClick={() => setImageTab(id)} onKeyDown={e => { if (snapshot && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) { e.preventDefault(); const next = e.key === "Home" ? "original" : e.key === "End" ? "annotated" : activeImageTab === "original" ? "annotated" : "original"; setImageTab(next); document.getElementById(`image-tab-${next}`)?.focus(); } }}>{id === "original" ? "Original" : "Annotated"}</button>)}</div>
          <div ref={artStage} id="manga-image-panel" role="tabpanel" aria-labelledby={`image-tab-${activeImageTab}`} className={`art-stage ${preview ? "has-image" : ""}`} tabIndex={preview ? 0 : undefined}>{preview ? <div className="evidence-canvas" style={{ width: fitWidth ? `${fitWidth * zoom / 100}px` : "100%" }}><img src={preview} onLoad={e => setImageSize({ src: preview, width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })} alt={`${activeImageTab === "annotated" ? "Annotated manga" : "Original manga"} page ${pagePosition + 1}`} />{focused && page && <svg className="source-overlay" viewBox={`0 0 ${page.width} ${page.height}`} aria-label="Selected text region"><rect x={focused.bbox[0]} y={focused.bbox[1]} width={focused.bbox[2] - focused.bbox[0]} height={focused.bbox[3] - focused.bbox[1]} /></svg>}</div> : snapshot ? <div className="art-placeholder"><h2>{activeImageTab === "annotated" ? "Annotations unavailable" : "Original unavailable"}</h2><p>{activeImageTab === "annotated" ? "This page has no saved annotated image. Choose Original to view the manga." : "This project has no saved original image for this page. Check the Annotated tab."}</p></div> : <div className="art-placeholder"><span className="panel-symbol" aria-hidden="true"><i /><i /><i /></span><h2>Your story starts here.</h2><p>Upload a panel, a page, or several pages.</p><ActionButton className="button" onClick={() => fileInput.current?.click()} disabled={!!busy || !!snapshot} reason="Start a new chapter to upload different images.">Choose manga images</ActionButton></div>}</div>
          {(preview || imageCount > 0) && <><div className="image-controls">{imageCount > 0 && <nav className="image-pagination" aria-label="Image page navigation"><ActionButton className="button small" aria-label="Previous page" disabled={imagePosition <= 0} reason="This is the first page." onClick={() => stepImage(-1)}>← Previous</ActionButton><span aria-live="polite">{imagePosition + 1} / {imageCount}</span><ActionButton className="button small" aria-label="Next page" disabled={imagePosition >= imageCount - 1} reason="This is the last page." onClick={() => stepImage(1)}>Next →</ActionButton></nav>}{preview && <div className="zoom-toolbar"><ActionButton className="button" aria-label="Zoom out" disabled={zoom <= 50} reason="Minimum zoom is 50%." onClick={() => setZoom(zoom - 25)}>−</ActionButton><output aria-label="Zoom relative to fitted image">{zoom}%</output><ActionButton className="button" aria-label="Zoom in" disabled={zoom >= 300} reason="Maximum zoom is 300%." onClick={() => setZoom(zoom + 25)}>+</ActionButton><ActionButton className="button" aria-pressed={zoom === 100} onClick={() => { setZoom(100); artStage.current?.scrollTo(0, 0); }}>Fit</ActionButton></div>}</div><div className="art-caption">{page?.image_filename ?? files[pageIndex]?.name}</div></>}
          {snapshot && draft && <div className="story-section"><h2 className="eyebrow">CHARACTER APPEARANCES · IMAGE {pagePosition + 1}</h2><p className="control-note">A detection is a visual clue, not a confirmed identity. Review assignments in Cast.</p><div className="appearance-list">{draft.appearances.filter(a => a.page_id === page?.page_id).map(a => <div className={`appearance ${a.rejected ? "rejected" : ""}`} key={a.char_id}><img src={assetUrl(projectId, `input/${a.crop_path}`)} alt={`Detected appearance ${a.char_id}`} /><span>{a.char_id}</span><strong>{a.rejected ? "Rejected detection" : draft.cast[a.speaker_id]?.name ?? "Unresolved"}</strong></div>)}</div></div>}
        </section>
        <section className="reading-card" aria-label="Production workspace">
          {!snapshot || !draft ? <><div className="panel-meta"><span>Start a production</span><span>01 / Upload</span></div><fieldset disabled={!!busy}><div className="story-section"><h2 className="eyebrow">BRING YOUR STORY</h2><div className="segmented-control">{[["images", "Images"], ["chapter", "Chapter ZIP"], ["restore", "Restore ZIP"]].map(([id, label]) => <ActionButton key={id} aria-pressed={mode === id} onClick={() => { setMode(id); setArchive(null); }}>{label}</ActionButton>)}</div><input ref={fileInput} className="visually-hidden" type="file" multiple accept="image/png,image/jpeg,image/webp" aria-label="Upload manga images" onChange={e => { selectFiles(e.target.files); e.target.value = ""; setMode("images"); }} />
            {mode === "images" ? <><p className="control-note">Choose up to 10 images, 10 MB each. Arrange the numbered thumbnails before extracting. Drag to reorder or use the move buttons.</p><ActionButton className="button" onClick={() => fileInput.current?.click()}>＋ Choose images</ActionButton><label className="field-label">Reading direction<select value={direction} onChange={e => setDirection(e.target.value)}><option value="rtl">Right to left · MagiV3 order</option><option value="ltr">Left to right · layout proposal</option></select></label></> : <label className="field-label">{mode === "restore" ? "Saved project bundle" : "Chapter analysis bundle"}<input key={mode} type="file" accept=".zip" onChange={e => setArchive(e.target.files?.[0] ?? null)} /><span className="control-note">{mode === "restore" ? "Restores references, approvals and retained audio without new generation." : "Use the chapter_analysis.zip produced by your extraction workflow."}</span></label>}
            {mode !== "restore" && <label className="field-label">Cast references ZIP <span className="muted">Optional; you can also create characters from panel crops.</span><input type="file" accept=".zip" onChange={e => setCastZip(e.target.files?.[0] ?? null)} /></label>}
            <div className="action-row"><ActionButton className="button primary" disabled={mode === "images" ? !files.length : !archive} reason={mode === "images" ? "Choose manga images first." : "Choose a ZIP file first."} onClick={createProject}>{mode === "images" ? "Extract & create project" : mode === "restore" ? "Restore project" : "Create project"}</ActionButton></div></div></fieldset><div className="story-section"><h2 className="eyebrow">FROM PANEL TO PERFORMANCE</h2><ol className="journey"><li><strong>Read the page</strong><span>Recover text and propose its order.</span></li><li><strong>Find each voice</strong><span>Match appearances to your cast.</span></li><li><strong>Approve the story</strong><span>Review dialogue and delivery before synthesis.</span></li><li><strong>Listen & export</strong><span>Choose takes and download your chapter.</span></li></ol></div></> : <>
            <div className="panel-meta"><span>{tabs.find(([id]) => id === tab)?.[1]}</span><span className={dirty ? "unsaved" : ""}>{dirty ? "Unsaved edits" : "Applied state saved"}</span></div>
            <fieldset disabled={!!busy}>
              {tab === "cast" && <CastWorkspace key={projectId} project={draft} voices={snapshot.voices} pages={snapshot.pages} currentPageId={page?.page_id || ""} dirty={dirty} approved={snapshot.cast_approved} asset={path => assetUrl(projectId, path)} edit={edit} save={saveCast} importReferences={importCast} showPage={id => { const index = snapshot.pages.findIndex(p => p.page_id === id); if (index >= 0) setPageIndex(index); }} Button={ActionButton} />}
              {tab === "proposal" && <><div className="story-section"><h2 className="eyebrow">AI ASSISTED DIRECTION</h2><p>Propose character identities, reading order, scene boundaries and delivery from the chapter evidence.</p><p className="control-note">Generate may use your Gemini quota. Loading a proposal replaces unapproved assignments and script, and clears approvals. Generation alone does not change your script.</p>{!hasKey && <p className="control-note">No API key configured on the server. Existing projects remain available for review and export.</p>}<ActionButton className="button primary" disabled={dirty || Object.keys(draft.cast).length < 2} reason={dirty ? "Apply or discard your edits first." : "Create a character from a crop or import cast references first."} onClick={() => void run("plan")}>Generate visual proposal</ActionButton></div>{draft.proposal && <div className="story-section"><label className="field-label">Review or edit proposal<textarea className="json-editor" value={proposal} spellCheck={false} onChange={e => { setProposal(e.target.value); setDirty(true); }} /></label><ActionButton className="button" onClick={() => { try { void run("proposal", JSON.parse(proposal)); } catch { toast.error("Proposal could not be loaded", { description: "The edited proposal contains invalid JSON. Correct its formatting and try again.", duration: 10000 }); } }}>Load proposal into review</ActionButton><p className="control-note">Then revisit Cast, Sources and Script to approve the changes.</p></div>}</>}
              {tab === "sources" && <SourceWorkspace key={projectId} project={draft} pages={snapshot.pages} dirty={dirty} asset={path => assetUrl(projectId, path)} edit={edit} save={saveSources} showSource={source => { setFocusSource(source.source_id); const index = snapshot.pages.findIndex(p => p.page_id === source.page_id); if (index >= 0) setPageIndex(index); }} showPage={id => { const index = snapshot.pages.findIndex(p => p.page_id === id); if (index >= 0) setPageIndex(index); }} Button={ActionButton} />}
              {tab === "script" && <ScriptWorkspace key={projectId} project={draft} saved={snapshot.project} approvedScenes={snapshot.approved_scenes} castApproved={snapshot.cast_approved} sceneId={sceneId} selectScene={setSceneId} edit={edit} save={scenes => run("script-batch", { scenes })} dirty={dirty} syncSpeakers={scenes => run("sync-speakers", scenes?.length ? { scenes } : {})} reviewCast={() => openApproval("cast")} reviewSources={() => openApproval("sources")} showScene={id => { const source = draft.sources.find(s => s.scene_id === id); if (source) { setFocusSource(source.source_id); const index = snapshot.pages.findIndex(p => p.page_id === source.page_id); if (index >= 0) setPageIndex(index); } }} showSource={id => { const source = draft.sources.find(s => s.source_id === id); if (source) { setFocusSource(id); const index = snapshot.pages.findIndex(p => p.page_id === source.page_id); if (index >= 0) setPageIndex(index); } }} addNarration={command => run("narration", command)} Button={ActionButton} />}
              {tab === "audio" && <><div className="story-section"><h2 className="eyebrow">AUDIO PRODUCTION</h2><p className="control-note">Choose all scenes or select individual scenes below. They will be combined into one MP3 in chapter order.</p><div className="audio-selection-bar"><span>{selectedScenes.length} of {draft.scenes.length} selected</span><div className="action-row"><ActionButton className="button small" disabled={!draft.scenes.length || selectedScenes.length === draft.scenes.length} reason="All scenes are selected." onClick={() => { setSelectedScenes(draft.scenes.map(s => s.scene_id)); setSegments([]); }}>Select all</ActionButton><ActionButton className="button small" disabled={!selectedScenes.length} reason="No scenes are selected." onClick={() => { setSelectedScenes([]); setSegments([]); }}>Clear selection</ActionButton></div></div>{draft.scenes.map(s => <label className="scene-choice" key={s.scene_id}><input type="checkbox" disabled={!!busy} checked={selectedScenes.includes(s.scene_id)} onChange={e => { setSelectedScenes(e.target.checked ? [...selectedScenes, s.scene_id] : selectedScenes.filter(id => id !== s.scene_id)); setSegments([]); }} /><span>{s.title || s.scene_id}</span><span className="badge">{snapshot.approved_scenes.includes(s.scene_id) && !dirty ? "✓ Approved" : "○ Needs review"}</span></label>)}<div className="action-row"><ActionButton className="button" disabled={!!audioBlocker} reason={audioBlocker} onClick={() => void run("inspect", { scene_ids: selectedScenes })}>Inspect segments</ActionButton><ActionButton className="button primary" disabled={!!audioBlocker} reason={audioBlocker} onClick={() => void run("render", { scene_ids: selectedScenes, regenerate: [] })}>Render selected audio</ActionButton></div>{audioBlocker && <div className="action-guidance"><p>{audioBlocker}</p>{!dirty && !snapshot.cast_approved && <ActionButton className="button small" onClick={() => openApproval("cast")}>Review cast</ActionButton>}{!dirty && snapshot.cast_approved && unapprovedSelected.map(s => <ActionButton key={s.scene_id} className="button small" onClick={() => openApproval("script", s.scene_id)}>Review {s.title || s.scene_id}</ActionButton>)}</div>}{!hasKey && <p className="control-note">Audio generation is unavailable until a Gemini API key is configured. Existing current takes can still be played and exported.</p>}<p className="control-note">New audio uses Gemini quota. Inspection and cached playback do not.</p></div>
                {segments.map(seg => <div className="segment-editor" key={seg.segment_id}><div className="dialogue-heading"><h3>{seg.segment_id}</h3><span className="badge">{seg.silence_sec ? `${seg.silence_sec}s silence` : "Speech"}</span></div><p className="segment-transcript">{seg.turns.map(t => t.text).join(" ") || "Deliberate silence"}</p><details><summary>Exact synthesis request</summary><pre>{JSON.stringify(seg.request, null, 2)}</pre></details>{(draft.takes[seg.signature] ?? []).map(take => <div className="take" key={take.take_id}><div className="dialogue-heading"><span>{take.duration_sec.toFixed(2)}s · {take.take_id}</span><ActionButton className="button small" disabled={dirty || draft.selected_takes[`${seg.segment_id}:${seg.signature}`] === take.take_id} reason={dirty ? "Apply your edits first." : "This take is already selected."} onClick={() => void run("take", { segment_id: seg.segment_id, take_id: take.take_id })}>{draft.selected_takes[`${seg.segment_id}:${seg.signature}`] === take.take_id ? "Selected" : "Use this take"}</ActionButton></div><audio controls preload="none" src={assetUrl(projectId, take.path)} />{take.clipped_samples > 0 && <p className="control-note">Clipping detected: {take.clipped_samples} samples.</p>}</div>)}<ActionButton className="button small" disabled={dirty} reason="Apply your edits first." onClick={() => void run("render", { scene_ids: [seg.scene_id], regenerate: [seg.segment_id] })}>Regenerate this segment</ActionButton></div>)}
                <div className="story-section"><h2 className="eyebrow">ASSEMBLE & DOWNLOAD</h2><p className="control-note">One compiled MP3 · {exportScenes.length} selected scene{exportScenes.length === 1 ? "" : "s"} · chapter order</p>{exportScenes.length > 0 && <p className="audio-export-order">{exportScenes.map(s => s.title || s.scene_id).join(" → ")}</p>}<div className="action-row"><ActionButton className="button primary" disabled={!!exportBlocker} reason={exportBlocker} onClick={() => void run("export", { scene_ids: exportScenes.map(s => s.scene_id) }, { mp3: true })}>Compile selected scenes to MP3</ActionButton><ActionButton className="button" disabled={dirty} reason="Apply your edits first." onClick={() => void run("bundle")}>Create project bundle</ActionButton></div>{exportBlocker && <p className="control-note" role="status">{exportBlocker}</p>}{snapshot.exports.length > 0 && <><p className="control-note">Last export. Export again after any script or take change; existing files may reflect an earlier version.</p>{snapshot.exports.includes("chapter_narration.mp3") && <a className="button primary" href={assetUrl(projectId, "exports/chapter_narration.mp3", true) + `&revision=${snapshot.revision}`}>↓ Download compiled MP3</a>}{snapshot.exports.includes("chapter_narration.wav") && <audio controls preload="none" src={assetUrl(projectId, snapshot.exports.includes("chapter_narration.mp3") ? "exports/chapter_narration.mp3" : "exports/chapter_narration.wav") + `&revision=${snapshot.revision}`} />}<div className="download-list">{snapshot.exports.filter(name => name !== "chapter_narration.mp3").map(name => <a className="button" key={name} href={assetUrl(projectId, `exports/${name}`, true)}>{name.replace("chapter_narration", "Chapter")}</a>)}</div></>}{bundleReady && <a className="button" href={assetUrl(projectId, "bundle.zip", true)}>Download resumable project ZIP</a>}</div>
                <details className="story-section"><summary>Models, segment budget & pauses</summary>{(["planning_model", "tts_model"] as const).map(key => <label key={key} className="field-label">{key === "planning_model" ? "Planning model" : "Speech model"}<input value={draft.settings[key]} onChange={e => edit(p => { p.settings[key] = e.target.value; })} /></label>)}{(["max_chars", "scene_pause", "segment_pause"] as const).map(key => <label key={key} className="field-label">{key === "max_chars" ? "Characters per segment" : key === "scene_pause" ? "Pause between scenes (seconds)" : "Pause between segments (seconds)"}<input type="number" min={key === "max_chars" ? 100 : 0} step={key === "max_chars" ? 1 : .01} value={draft.settings[key]} onChange={e => edit(p => { p.settings[key] = Number(e.target.value); })} /></label>)}<p className="control-note">Applying settings clears scene approvals. Review scenes again before rendering.</p><ActionButton className="button" onClick={() => void run("settings", { settings: draft.settings })}>Apply settings</ActionButton></details></>}
            </fieldset>
          </>}
        </section>
      </div>
      <footer className="reader-footer"><span>Original images preserved · Human approval before speech</span><span>Local workspace · Mono 24 kHz WAV · Resumable projects</span></footer>
    </main>
    </div>
  </div></BusyContext.Provider>;
}
