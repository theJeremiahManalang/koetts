"use client";

import { useRef, useState, type ButtonHTMLAttributes, type ComponentType } from "react";
import { toast } from "sonner";
import type { Project, Scene, Turn } from "./types";
import { sceneChanged, sceneDraftKey, sceneReviews, turnReviewIssue, type SceneReview } from "./script-review";

type Props = {
  project: Project; saved: Project; approvedScenes: string[]; castApproved: boolean; dirty: boolean;
  sceneId: string; selectScene: (id: string) => void;
  edit: (change: (project: Project) => void) => void;
  save: (reviews: SceneReview[]) => Promise<boolean>;
  syncSpeakers: (drafts?: SceneReview[]) => Promise<boolean>;
  reviewCast: () => void; reviewSources: () => void;
  showScene: (id: string) => void; showSource: (id: string) => void;
  addNarration: (command: { scene_id: string; position: number; text: string; evidence_source_ids: string[] }) => Promise<boolean>;
  Button: ComponentType<ButtonHTMLAttributes<HTMLButtonElement> & { reason?: string }>;
};

export function ScriptWorkspace({ project, saved, approvedScenes, castApproved, dirty, sceneId, selectScene, edit, save, syncSpeakers, reviewCast, reviewSources, showScene, showSource, addNarration, Button }: Props) {
  const sceneCards = useRef<HTMLElement>(null);
  const sceneHeading = useRef<HTMLDivElement>(null);
  const [reviewed, setReviewed] = useState<Record<string, string>>({});
  const [narrations, setNarrations] = useState<Record<string, { text: string; evidence: string }>>({});
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const index = Math.max(0, project.scenes.findIndex(s => s.scene_id === sceneId));
  const scene = project.scenes[index];
  const isReviewed = (s: Scene) => reviewed[s.scene_id] === sceneDraftKey(s);
  const isApproved = (s: Scene) => castApproved && approvedScenes.includes(s.scene_id) && !sceneChanged(s, saved);
  const completed = project.scenes.filter(s => isApproved(s) || isReviewed(s)).length;
  const pending = sceneReviews(project, saved, reviewed);
  const approvalCount = pending.filter(s => s.approve).length;
  const staged = project.scenes.filter(isReviewed).length;
  const blockedTurns = (s: Scene) => s.turns.filter(t => turnReviewIssue(t, project));
  const currentBlockers = scene ? blockedTurns(scene).length : 0;
  const narration = scene ? narrations[scene.scene_id] ?? { text: "", evidence: "" } : { text: "", evidence: "" };

  function navigate(id: string) { selectScene(id); showScene(id); requestAnimationFrame(() => { sceneCards.current?.querySelector('[aria-current="step"]')?.scrollIntoView({ block: "nearest", inline: "nearest" }); sceneHeading.current?.scrollIntoView({ block: "start" }); }); }
  function updateScene(patch: Partial<Scene>) { if (scene) edit(p => { Object.assign(p.scenes.find(s => s.scene_id === scene.scene_id)!, patch); }); }
  function updateTurn(id: string, patch: Partial<Turn>) { if (scene) edit(p => { Object.assign(p.scenes.find(s => s.scene_id === scene.scene_id)!.turns.find(t => t.turn_id === id)!, patch); }); }
  function status(s: Scene) {
    const blocked = blockedTurns(s).length;
    if (blocked) return `! ${blocked} turn${blocked === 1 ? "" : "s"} need correction`;
    return isReviewed(s) ? "✓ Reviewed · ready to save" : isApproved(s) ? "✓ Approved" : sceneChanged(s, saved) ? "○ Edited · needs review" : "○ Needs review";
  }
  function markAndNext() {
    if (!scene || !castApproved || currentBlockers) return;
    setReviewed(r => ({ ...r, [scene.scene_id]: sceneDraftKey(scene) }));
    edit(() => {}); // The pending approval is unsaved work too.
    const next = [...project.scenes.slice(index + 1), ...project.scenes.slice(0, index)].find(s => !isApproved(s) && !isReviewed(s));
    if (next) navigate(next.scene_id);
    toast.success(`${scene.title || `Scene ${index + 1}`} marked reviewed`, { id: "script-review", description: next ? "Moved to the next scene needing review. Save all changes when finished." : "All scenes marked reviewed. Save to validate and apply your edits and approvals." });
  }
  async function saveAll() { if (pending.length && await save(pending)) setReviewed({}); }

  return <div className="script-workspace"><div className="script-review-heading"><div><h2>Review the spoken script</h2><p className="control-note">Move freely between scenes. Your edits stay in one draft until you save.</p></div><span className="badge" aria-live="polite">{completed}/{project.scenes.length} reviewed or approved</span></div>
    {project.scenes.some(s => s.turns.some(t => t.include && !project.cast[t.speaker_id])) && <div className="action-guidance"><p>Some dialogue still needs a speaker. Cast assignments fill clear bubble-to-character links automatically when saved. You can also sync an existing project here; ambiguous or unlinked bubbles need a manual speaker choice.</p><p className="control-note">Updating speakers saves any edited scene drafts and clears pending review marks. Review the updated speakers before approving.</p><Button className="button small" onClick={async () => { if (await syncSpeakers(pending.map(s => ({ ...s, approve: false })))) setReviewed({}); }}>{pending.length ? "Save drafts & update speakers" : "Update speakers from Cast"}</Button></div>}
    {!castApproved && <div className="action-guidance"><p>You can edit and save drafts now. Approve the cast before marking scenes reviewed for approval.</p><Button className="button small" onClick={reviewCast}>Review cast</Button></div>}
    {!project.scenes.length ? <div className="action-guidance"><p>No scenes yet. Apply your sources and reading order to build the script.</p><Button className="button small" onClick={reviewSources}>Review sources</Button></div> : <>
      <div className="script-scene-navigation"><label className="check-label"><input type="checkbox" checked={needsReviewOnly} onChange={e => setNeedsReviewOnly(e.target.checked)} /> Show scenes needing review only</label><nav ref={sceneCards} className="script-scene-cards" aria-label="Choose a scene">{project.scenes.map((s, i) => (!needsReviewOnly || (!isApproved(s) && !isReviewed(s)) || s.scene_id === scene?.scene_id) && <Button key={s.scene_id} className={`script-scene-card${blockedTurns(s).length ? " has-correction" : ""}`} aria-current={scene?.scene_id === s.scene_id ? "step" : undefined} onClick={() => navigate(s.scene_id)}><span className="eyebrow">SCENE {i + 1}</span><strong>{s.title || s.scene_id}</strong><span className={blockedTurns(s).length ? "script-correction-label" : undefined}>{status(s)}</span><small>{s.turns.filter(t => t.include).length} spoken turns</small></Button>)}</nav></div>
      {scene && <><div className="script-scene-toolbar"><Button className="button small" disabled={index === 0} reason="This is the first scene." onClick={() => navigate(project.scenes[index - 1].scene_id)}>← Previous</Button><span>Scene {index + 1} of {project.scenes.length}</span><Button className="button small" disabled={index === project.scenes.length - 1} reason="This is the last scene." onClick={() => navigate(project.scenes[index + 1].scene_id)}>Next →</Button></div>
        <div ref={sceneHeading} className="script-scene-heading"><h3>{scene.title || scene.scene_id}</h3><Button className="button small" disabled={!project.sources.some(s => s.scene_id === scene.scene_id)} reason="This scene has no image source." onClick={() => showScene(scene.scene_id)}>Show source image</Button></div>
        <details className="script-scene-context" key={`context-${scene.scene_id}`}><summary>Scene title & context</summary><label className="field-label">Title<input value={scene.title} onChange={e => updateScene({ title: e.target.value })} /></label><label className="field-label">Context<textarea value={scene.context} onChange={e => updateScene({ context: e.target.value })} /></label></details>
        <div className="script-turns" key={scene.scene_id}>{scene.turns.map((turn, i) => <section className={`script-turn ${!turn.include ? "excluded" : ""}${turnReviewIssue(turn, project) ? " has-correction" : ""}`} key={turn.turn_id}><div className="script-turn-heading"><label className="check-label"><input type="checkbox" checked={turn.include} onChange={e => updateTurn(turn.turn_id, { include: e.target.checked })} />Include {turn.kind === "narration" ? "Narration" : `Turn ${i + 1}`}</label>{turn.source_ids[0] && <Button className="button small" onClick={() => showSource(turn.source_ids[0])}>Show bubble</Button>}</div>{turnReviewIssue(turn, project) && <p className="script-correction" role="status" id={`correction-${turn.turn_id}`}><span className="script-correction-icon" aria-hidden="true">!</span><span><strong>Needs correction</strong> {turnReviewIssue(turn, project)}</span></p>}<label className="field-label">Speaker<select aria-invalid={!!turnReviewIssue(turn, project) && !project.cast[turn.speaker_id]} aria-describedby={turnReviewIssue(turn, project) ? `correction-${turn.turn_id}` : undefined} value={turn.speaker_id} onChange={e => updateTurn(turn.turn_id, { speaker_id: e.target.value, speaker_origin: "manual" })}><option value="UNKNOWN">Unresolved speaker</option>{Object.entries(project.cast).map(([id, c]) => <option key={id} value={id}>{c.name}</option>)}</select></label><label className="field-label">Exact spoken wording<textarea aria-invalid={!!turnReviewIssue(turn, project) && !!project.cast[turn.speaker_id] && !turn.source_ids.some(id => project.sources.some(s => s.source_id === id && !s.include))} aria-describedby={turnReviewIssue(turn, project) ? `correction-${turn.turn_id}` : undefined} value={turn.text} onChange={e => updateTurn(turn.turn_id, { text: e.target.value })} /></label><details><summary>Delivery, emotion & pauses</summary><div className="field-grid"><label className="field-label">Delivery<select value={turn.delivery} onChange={e => updateTurn(turn.turn_id, { delivery: e.target.value })}>{["speech", "thought", "shout", "whisper", "narration"].map(d => <option key={d}>{d}</option>)}</select></label>{(["emotion", "style", "pacing"] as const).map(key => <label className="field-label" key={key}>{({ emotion: "Emotion", style: "Acting direction", pacing: "Pacing" })[key]}<input value={turn[key]} onChange={e => updateTurn(turn.turn_id, { [key]: e.target.value })} /></label>)}<label className="field-label">Silence after turn (seconds)<input type="number" min="0" max="30" step="0.1" value={turn.silence_sec} onChange={e => updateTurn(turn.turn_id, { silence_sec: Number(e.target.value) })} /></label></div></details></section>)}</div>
        <details className="script-add-narration" key={`narration-${scene.scene_id}`}><summary>Add evidence-based narration</summary><p className="control-note">Save your scene drafts and pending approvals before inserting a new narration turn.</p><label className="field-label">Narration text<textarea value={narration.text} onChange={e => setNarrations(n => ({ ...n, [scene.scene_id]: { ...narration, text: e.target.value } }))} /></label><label className="field-label">Visual evidence source<select value={narration.evidence} onChange={e => setNarrations(n => ({ ...n, [scene.scene_id]: { ...narration, evidence: e.target.value } }))}><option value="">Choose evidence</option>{project.sources.filter(s => s.scene_id === scene.scene_id).map(s => <option key={s.source_id} value={s.source_id}>{s.source_id}</option>)}</select></label><Button className="button small" disabled={dirty || staged > 0 || !narration.text.trim() || !narration.evidence} reason={dirty || staged ? "Save your scene edits and approvals first." : !narration.text.trim() ? "Enter narration text." : "Choose visual evidence."} onClick={async () => { if (await addNarration({ scene_id: scene.scene_id, position: 0, text: narration.text, evidence_source_ids: [narration.evidence] })) setNarrations(n => ({ ...n, [scene.scene_id]: { text: "", evidence: "" } })); }}>Insert narration</Button></details>
        <div className="script-review-bar"><div><strong className={currentBlockers ? "script-correction-label" : undefined}>{status(scene)}</strong><span>{pending.length} scene{pending.length === 1 ? "" : "s"} pending save · {approvalCount} marked for approval</span></div><div className="action-row"><Button className="button" disabled={!castApproved || currentBlockers > 0} reason={!castApproved ? "Approve the cast first. You can still save scene drafts." : `Correct the ${currentBlockers} flagged turn(s) before marking this scene reviewed.`} onClick={markAndNext}>Mark reviewed & next →</Button><Button className="button primary" disabled={!pending.length || (approvalCount > 0 && !castApproved)} reason={!pending.length ? "Edit a scene or mark it reviewed first." : "Approve the cast before saving approvals."} onClick={() => void saveAll()}>{approvalCount ? `Save & approve ${approvalCount} reviewed` : "Save all changes"}</Button></div><p className="control-note">Marking reviewed is a draft decision. Saving validates all changes together. Editing a reviewed scene makes it need review again.</p></div>
      </>}
    </>}
  </div>;
}
