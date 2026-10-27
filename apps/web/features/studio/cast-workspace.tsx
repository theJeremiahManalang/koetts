"use client";

import { useEffect, useState, type ButtonHTMLAttributes, type ComponentType } from "react";
import { toast } from "sonner";
import type { Appearance, CastMember, Page, Project } from "./types";

type Props = {
  project: Project;
  voices: string[];
  pages: Page[];
  currentPageId: string;
  dirty: boolean;
  approved: boolean;
  asset: (path: string) => string;
  edit: (change: (project: Project) => void) => void;
  save: (approve?: boolean) => void;
  importReferences: (file: File) => void;
  showPage: (page: string) => void;
  Button: ComponentType<ButtonHTMLAttributes<HTMLButtonElement> & { reason?: string }>;
};

export function CastWorkspace({ project, voices, pages, currentPageId, dirty, approved, asset, edit, save, importReferences, showPage, Button }: Props) {
  const [view, setView] = useState<"characters" | "appearances">("appearances");
  const [characterId, setCharacterId] = useState("");
  const [appearanceId, setAppearanceId] = useState(() => (project.appearances.find(a => !a.rejected && !project.cast[a.speaker_id]) ?? project.appearances[0])?.char_id || "");
  const [appearanceCharacter, setAppearanceCharacter] = useState<string | null>(null);
  const [onlyUnresolved, setOnlyUnresolved] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchCharacter, setBatchCharacter] = useState("");
  const [name, setName] = useState("");
  const [voice, setVoice] = useState("Kore");
  const characters = Object.entries(project.cast);
  const unresolved = project.appearances.filter(a => !a.rejected && !project.cast[a.speaker_id]);
  const pageId = pages.some(p => p.page_id === currentPageId) ? currentPageId : pages[0]?.page_id;
  const pageAppearances = project.appearances.filter(a => a.page_id === pageId);
  const pageUnresolved = unresolved.filter(a => a.page_id === pageId);
  const pageIndex = pages.findIndex(p => p.page_id === pageId);
  const appearances = (onlyUnresolved ? pageUnresolved : pageAppearances).filter(a => !appearanceCharacter || a.speaker_id === appearanceCharacter);
  const selection = selectedIds.filter(id => pageAppearances.some(a => a.char_id === id));
  const appearance = pageAppearances.find(a => a.char_id === appearanceId) ?? pageUnresolved[0] ?? pageAppearances[0];
  const selectedId = view === "appearances" ? appearance && !appearance.rejected && project.cast[appearance.speaker_id] ? appearance.speaker_id : "" : project.cast[characterId] ? characterId : characters[0]?.[0];
  const character = selectedId ? project.cast[selectedId] : undefined;
  useEffect(() => { setSelectedIds([]); setCreating(false); }, [pageId]);

  function selectAppearance(item: Appearance) {
    setAppearanceId(item.char_id);
    setCreating(false);
    showPage(item.page_id);
  }
  function assignAppearance(charId: string, speakerId: string) {
    edit(p => { Object.assign(p.appearances.find(a => a.char_id === charId)!, { speaker_id: speakerId, rejected: false }); });
  }
  function changePage(id: string) {
    setSelectedIds([]); setCreating(false); setAppearanceCharacter(null); showPage(id);
  }
  function addDraftCharacter() {
    if (!appearance || !name.trim()) return;
    if (characters.some(([, c]) => c.name.trim().toLowerCase() === name.trim().toLowerCase())) {
      toast.error("Character already exists", { description: "Choose the existing character from the identity dropdown." }); return;
    }
    const speakerId = `CHARACTER_${crypto.randomUUID().replaceAll("-", "")}`;
    const targets = selection.includes(appearance.char_id) ? selection : [appearance.char_id];
    edit(p => {
      p.cast[speakerId] = { name: name.trim(), voice, pronunciation: "", acting_notes: "", references: [`input/${appearance.crop_path}`] };
      p.pending_characters = [...(p.pending_characters ?? []), { speaker_id: speakerId, char_id: appearance.char_id }];
      for (const a of p.appearances) if (targets.includes(a.char_id)) Object.assign(a, { speaker_id: speakerId, rejected: false });
    });
    setCreating(false); setName(""); setSelectedIds([]); setBatchCharacter(speakerId);
    toast.success("Character added to your draft", { description: "Keep assigning identities. Save all changes when you finish reviewing your pages." });
  }
  function updateCharacter(patch: Partial<CastMember>) {
    if (selectedId) edit(p => { Object.assign(p.cast[selectedId], patch); });
  }
  function voiceSelect(value: string, update: (voice: string) => void) {
    return <select value={value} onChange={e => update(e.target.value)}>{!voices.includes(value) && <option value={value} disabled>{value || "Choose a voice"} — select a supported voice</option>}{voices.map(v => <option key={v} value={v}>{v}</option>)}</select>;
  }

  return <div className="cast-workspace">
    <div className="cast-workspace-heading"><div><h2>Cast workspace</h2><p className="control-note">Assign identities page by page. Save once after reviewing as many pages as you like.</p></div><span aria-live="polite" className={`badge ${unresolved.length ? "" : "cast-complete"}`}>{!project.appearances.length ? "No detections" : unresolved.length ? `${unresolved.length} need identity` : "✓ All appearances reviewed"}</span></div>
    <p className="control-note">Saving Cast also fills dialogue speakers wherever a speech bubble has a clear link to an assigned appearance. Manual speaker choices are kept; unlinked or ambiguous dialogue still needs review.</p>
    <details className="cast-import"><summary>Import cast references <span>Optional · ZIP</span></summary><p className="control-note">Already have character references? Import them here, then assign the matching appearances.</p><label className="field-label">Reference ZIP<input type="file" accept=".zip" disabled={dirty} onChange={e => { const file = e.target.files?.[0]; if (file) importReferences(file); e.target.value = ""; }} /></label>{dirty && <div className="cast-inline-save"><span>Save your changes before importing references.</span><Button className="button small" onClick={() => save()}>Save changes</Button></div>}</details>
    <div className="segmented-control cast-view-switch" aria-label="Cast workspace view"><Button aria-pressed={view === "appearances"} onClick={() => { setView("appearances"); setCreating(false); }}>Identify appearances · {project.appearances.length}</Button><Button aria-pressed={view === "characters"} onClick={() => { setView("characters"); setCreating(false); }}>Characters & voices · {characters.length}</Button></div>

    {view === "appearances" ? <>
      <div className="cast-page-navigation"><Button className="button small" disabled={pageIndex <= 0} reason="This is the first image." aria-label="Previous image" onClick={() => changePage(pages[pageIndex - 1].page_id)}>←</Button><label className="field-label">Manga image<select value={pageId || ""} onChange={e => changePage(e.target.value)}>{pages.map((p, index) => <option key={p.page_id} value={p.page_id}>Image {index + 1} · {p.page_id}</option>)}</select></label><Button className="button small" disabled={pageIndex >= pages.length - 1} reason="This is the last image." aria-label="Next image" onClick={() => changePage(pages[pageIndex + 1].page_id)}>→</Button></div>
      <div className="cast-queue-toolbar"><label className="check-label"><input type="checkbox" checked={onlyUnresolved} onChange={e => { setOnlyUnresolved(e.target.checked); setAppearanceCharacter(null); setSelectedIds([]); }} /> Needs identity only</label><span className="control-note" aria-live="polite">{pageAppearances.length - pageUnresolved.length}/{pageAppearances.length} reviewed on this image</span></div>
      {appearanceCharacter && <div className="cast-scope"><span>Showing {project.cast[appearanceCharacter]?.name || "character"}’s appearances</span><Button className="button small" onClick={() => setAppearanceCharacter(null)}>Show all</Button></div>}
      <div className="cast-page-grid" role="group" aria-label="Assign identities on this manga image">{appearances.map(a => <div key={a.char_id} className={`cast-page-card ${selection.includes(a.char_id) ? "batch-selected" : ""}`}><label className="check-label"><input type="checkbox" checked={selection.includes(a.char_id)} onChange={e => setSelectedIds(ids => e.target.checked ? [...ids.filter(id => id !== a.char_id), a.char_id] : ids.filter(id => id !== a.char_id))} /> Select {a.char_id}</label><Button className="cast-page-crop" aria-label={`Inspect ${a.char_id}`} onClick={() => selectAppearance(a)}><img src={asset(`input/${a.crop_path}`)} alt={a.char_id} /></Button><label className="field-label">Identity<select value={a.rejected ? "REJECTED" : project.cast[a.speaker_id] ? a.speaker_id : "UNKNOWN"} onChange={e => {
        const value = e.target.value;
        if (value === "REJECTED") edit(p => { p.appearances.find(item => item.char_id === a.char_id)!.rejected = true; });
        else assignAppearance(a.char_id, value);
      }}><option value="UNKNOWN">Needs identity</option>{characters.filter(([id]) => id !== "NARRATOR").map(([id, c]) => <option key={id} value={id}>{c.name}</option>)}<option value="REJECTED">Not a character</option></select></label><Button className="button small" onClick={() => { selectAppearance(a); setCreating(true); }}>+ New character</Button></div>)}</div>
      {!appearances.length && <p className="control-note">{pageUnresolved.length === 0 && pageAppearances.length ? "This image is reviewed. Show all identities or move to the next image; saving is not required between images." : "No matching appearances on this image. Try another image or turn off the filters."}</p>}
      <div className="cast-batch-actions"><div className="action-row"><Button className="button small" disabled={!appearances.length} reason="No visible appearances to select." onClick={() => setSelectedIds(appearances.map(a => a.char_id))}>Select visible</Button><Button className="button small" disabled={!selection.length} reason="No appearances are selected." onClick={() => setSelectedIds([])}>Clear selection</Button><span className="control-note">{selection.length} selected</span></div><label className="field-label">Assign selected to<select value={batchCharacter} onChange={e => setBatchCharacter(e.target.value)}><option value="">Choose a character</option>{characters.filter(([id]) => id !== "NARRATOR").map(([id, c]) => <option key={id} value={id}>{c.name}</option>)}</select></label><Button className="button" disabled={!selection.length || !project.cast[batchCharacter]} reason={!selection.length ? "Select appearances of the same character first." : "Choose a character to assign."} onClick={() => {
        edit(p => { for (const a of p.appearances) if (selection.includes(a.char_id)) Object.assign(a, { speaker_id: batchCharacter, rejected: false }); });
        setSelectedIds([]);
        toast.success(`${selection.length} appearances assigned`, { description: "Changes stay in your draft. Continue to the next image and save when finished." });
      }}>Assign selected</Button></div>
      <p className="control-note">Page changes keep your draft. Save changes saves assignments and new characters across the whole chapter.</p>
    </> : <div className="cast-character-picker"><label className="field-label">Character to edit<select value={selectedId || ""} onChange={e => { setCharacterId(e.target.value); setCreating(false); }}>{characters.map(([id, c]) => <option value={id} key={id}>{c.name} · {c.voice}</option>)}</select></label><Button className="button small" disabled={!project.appearances.length} reason="No detected appearances are available. Import a reference ZIP instead." onClick={() => { setView("appearances"); setAppearanceCharacter(null); setOnlyUnresolved(false); setCreating(true); }}>+ Add character</Button></div>}

    {creating && appearance ? <section className="cast-character-detail"><div className="dialogue-heading"><h3>New character</h3><Button className="button small" onClick={() => setCreating(false)}>Cancel</Button></div><p className="control-note">Reference image: {appearance.char_id}. This crop becomes the character’s reference.</p><div className="field-grid"><label className="field-label">Character name<input value={name} maxLength={120} placeholder="Enter character name" onChange={e => setName(e.target.value)} /></label><label className="field-label">Gemini voice{voiceSelect(voice, setVoice)}</label></div><p className="control-note">This character will be added to your draft{selection.includes(appearance.char_id) && selection.length > 1 ? ` and assigned to ${selection.length} selected appearances` : ""}. Save with the rest of your changes when finished.</p><Button className="button primary" disabled={!name.trim() || appearance.rejected} reason={appearance.rejected ? "Restore this detection first." : "Enter a character name."} onClick={addDraftCharacter}>Add character to draft</Button></section>
      : character ? <section className="cast-character-detail" aria-label={`Edit ${character.name}`}><div className="cast-detail-heading">{view === "characters" && character.references?.[0] && <img src={asset(character.references[0])} alt={`${character.name} reference`} />}<div><h3>{view === "appearances" ? "Assigned character & voice" : "Character & voice"}</h3><p className="control-note">Changes apply to every appearance assigned to this character.</p></div></div><div className="field-grid"><label className="field-label">Character name<input value={character.name} maxLength={120} onChange={e => updateCharacter({ name: e.target.value })} /></label><label className="field-label">Gemini voice{voiceSelect(character.voice, value => updateCharacter({ voice: value }))}</label></div><details className="cast-extra-details" key={selectedId}><summary>Pronunciation & acting notes</summary><label className="field-label">Pronunciation<input value={character.pronunciation} onChange={e => updateCharacter({ pronunciation: e.target.value })} /></label><label className="field-label">Base acting notes<textarea value={character.acting_notes || ""} onChange={e => updateCharacter({ acting_notes: e.target.value })} /></label></details>{view === "characters" && selectedId !== "NARRATOR" && <Button className="button small" disabled={!project.appearances.some(a => a.speaker_id === selectedId)} reason="No appearances are assigned to this character yet." onClick={() => { const match = project.appearances.find(a => a.speaker_id === selectedId); if (match) { selectAppearance(match); setAppearanceCharacter(selectedId); setOnlyUnresolved(false); setSelectedIds([]); setView("appearances"); } }}>Review this character’s appearances</Button>}</section>
        : <p className="control-note">{view === "appearances" ? "Choose an existing character or create one from the selected image. Reject false detections with Not a character." : "Create a character from an appearance or import your cast references above."}</p>}

    <div className="cast-save-bar"><span className={dirty ? "unsaved" : "control-note"} role="status">{dirty ? "Unsaved cast changes" : approved ? "✓ Cast approved" : "Review and approve your cast"}</span><div className="action-row"><Button className="button" disabled={!dirty} reason="Your cast changes are already saved." onClick={() => save()}>Save changes</Button><Button className="button primary" disabled={unresolved.length > 0 || characters.length < 2} reason={unresolved.length ? `Assign or reject ${unresolved.length} unresolved appearance(s) first.` : "Create at least one character in addition to the narrator."} onClick={() => save(true)}>Save & approve cast</Button></div></div>
  </div>;
}
