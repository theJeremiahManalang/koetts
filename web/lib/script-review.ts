import type { Project, Scene } from "./types";

export type SceneReview = {
  scene_id: string; title: string; context: string; approve: boolean;
  turns: { speaker_origin?: "manual"; turn_id: string; include: boolean; speaker_id: string; text: string; delivery: string; emotion: string; style: string; pacing: string; silence_sec: number }[];
};
export const sceneDraftKey = (scene: Scene) => JSON.stringify(scene);
export function turnReviewIssue(turn: Scene["turns"][number], project: Project): string | null {
  if (!turn.include) return null;
  if (!project.cast[turn.speaker_id]) return "Choose a speaker or uncheck Include.";
  if (turn.source_ids.some(id => project.sources.some(s => s.source_id === id && !s.include)))
    return "Uses an excluded source. Uncheck Include or include the source in Source & order.";
  const vocalTags = new Set(["<gasp>", "<breath>", "<sigh>", "<laugh>", "<cough>", "<short pause>"]);
  if ((turn.text.match(/<[^>]*>/g) ?? []).some(tag => !vocalTags.has(tag)))
    return "Unsupported vocal tag. Use <gasp>, <breath>, <sigh>, <laugh>, <cough>, or <short pause>. Put action directions in Acting direction.";
  if (!turn.text.trim() && !turn.silence_sec)
    return "Enter spoken wording, set silence after turn, or uncheck Include.";
  if (turn.text.trim() && !/[\p{L}\p{N}_<>]/u.test(turn.text))
    return "Punctuation only. Use <gasp>, clear the text and add silence, or uncheck Include.";
  return null;
}
export function sceneChanged(scene: Scene, saved: Project) {
  const original = saved.scenes.find(s => s.scene_id === scene.scene_id);
  return !original || sceneDraftKey(scene) !== sceneDraftKey(original);
}
export function sceneReviews(project: Project, saved: Project, reviewed: Record<string, string>): SceneReview[] {
  return project.scenes.filter(s => sceneChanged(s, saved) || reviewed[s.scene_id] === sceneDraftKey(s)).map(s => ({
    scene_id: s.scene_id, title: s.title, context: s.context, approve: reviewed[s.scene_id] === sceneDraftKey(s),
    turns: s.turns.map(t => ({ turn_id: t.turn_id, ...(t.speaker_origin === "manual" ? { speaker_origin: "manual" as const } : {}), include: t.include, speaker_id: t.speaker_id, text: t.text, delivery: t.delivery, emotion: t.emotion, style: t.style, pacing: t.pacing, silence_sec: t.silence_sec })),
  }));
}
