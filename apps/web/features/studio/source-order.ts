import type { Project, Source } from "./types";

export function moveTo<T>(items: T[], from: number, to: number): T[] {
  if (from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
  const result = [...items];
  result.splice(to, 0, result.splice(from, 1)[0]);
  return result;
}

export function orderedSources(project: Project) {
  return [...project.sources].sort((a, b) => a.order - b.order);
}

// Replace only the selected slots; sources outside a filtered view keep their positions.
export function replaceSourceSlots(project: Project, ids: string[]) {
  const byId = new Map(project.sources.map(s => [s.source_id, s]));
  const included = new Set(ids);
  let index = 0;
  project.sources = orderedSources(project).map(s => included.has(s.source_id) ? byId.get(ids[index++])! : s);
  project.sources.forEach((s, order) => { s.order = order; });
}

const turnKey = (s: Source) => JSON.stringify([s.scene_id, s.turn_group, s.speaker_id, s.delivery, s.emotion, s.style, s.pacing, s.include]);
export function orderIssues(project: Project): string[] {
  const seenScenes = new Set<string>(), seenGroups = new Set<string>();
  let previousScene = "", previousTurn = "";
  const problems = new Set<string>();
  for (const source of orderedSources(project)) {
    if (source.scene_id !== previousScene) {
      if (seenScenes.has(source.scene_id)) problems.add("A scene is split across separate parts of the reading order.");
      seenScenes.add(source.scene_id); previousScene = source.scene_id;
    }
    const key = turnKey(source), group = JSON.stringify([source.scene_id, source.turn_group]);
    if (key !== previousTurn) {
      if (seenGroups.has(group)) problems.add("A speaking group is split or has conflicting speakers or delivery.");
      seenGroups.add(group); previousTurn = key;
    }
  }
  return [...problems];
}

// Explicit user action: keep the chosen order, split only revisited scenes/groups.
export function splitOrderConflicts(project: Project) {
  const allSceneIds = new Set(project.sources.map(s => s.scene_id));
  const usedScenes = new Set<string>(), usedGroups = new Set<string>();
  let originalScene = "", activeScene = "", previousTurn = "", activeGroup = "";
  for (const s of orderedSources(project)) {
    const originalKey = turnKey(s);
    if (s.scene_id !== originalScene) {
      originalScene = s.scene_id; activeScene = originalScene;
      if (usedScenes.has(activeScene)) {
        let suffix = 2;
        while (allSceneIds.has(`${originalScene}_part_${suffix}`)) suffix++;
        activeScene = `${originalScene}_part_${suffix}`; allSceneIds.add(activeScene);
      }
      usedScenes.add(activeScene);
    }
    s.scene_id = activeScene;
    if (originalKey !== previousTurn) {
      activeGroup = s.turn_group;
      let suffix = 2;
      while (usedGroups.has(JSON.stringify([activeScene, activeGroup]))) activeGroup = `${s.turn_group}_part_${suffix++}`;
      usedGroups.add(JSON.stringify([activeScene, activeGroup])); previousTurn = originalKey;
    }
    s.turn_group = activeGroup;
  }
}
