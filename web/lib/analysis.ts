export type Character = { id: string; name: string; voice: string };
export type Appearance = { id: string; bbox: number[]; cluster: number | null; group_id: string; crop: string; character_id: string | null };
export type Line = { id: string; page_id: string; sequence: number; text: string; bbox: number[]; detection_index: number | null; speaker_candidates: string[]; appearance_id: string | null; included: boolean; warning: string; character_id?: string | null };
export type Page = { id: string; filename: string; image_hash: string; width: number; height: number; panels: number[][]; appearances: Appearance[]; lines: Line[] };
export type Analysis = { schema_version: string; reading_direction: "rtl" | "ltr"; model_id: string; model_revision: string; pages: Page[] };
export function scriptFor(analysis: Analysis, characters: Character[], lines: Line[], appearances: Appearance[]) {
  return { ...analysis, characters, appearances: appearances.map(({ crop, ...a }) => a),
    pages: analysis.pages.map(({ appearances: _a, lines: _l, ...p }) => p),
    lines: lines.map((line, i) => {
      const characterId = line.appearance_id ? appearances.find(a => a.id === line.appearance_id)?.character_id : line.character_id;
      return { ...line, sequence: i + 1, source_image: analysis.pages.find(p => p.id === line.page_id)?.filename,
        character_id: characterId ?? null, voice: characters.find(c => c.id === characterId)?.voice ?? null };
    }) };
}
export function playbackErrors(script: ReturnType<typeof scriptFor>, voices: string[]) {
  const selected = script.lines.filter(l => l.included);
  if (!selected.length) return ["Include at least one dialogue line."];
  return selected.flatMap(line => !line.text.trim() ? [`Line ${line.sequence}: enter dialogue or exclude it.`]
    : !line.character_id ? [`Line ${line.sequence}: assign a character.`]
    : !line.voice || !voices.includes(line.voice) ? [`Line ${line.sequence}: select an available voice.`] : []);
}
