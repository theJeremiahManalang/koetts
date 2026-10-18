"""Script stage implementation; public workflow commands live in PipelineRouter."""
from __future__ import annotations
import copy
import math
import re
from typing import Any
from .config import UNKNOWN, NARRATOR, DELIVERIES, MAX_SILENCE_SEC, TEXT_POLICY_VERSION, CACHE_REVISION
from .cleaner import require_reviewed_text
from .schemas import Scene, Proposal, validate_contract
from .storage import digest
import uuid



def cast_signature(p: dict[str, Any]) -> str:
    """Return the approval fingerprint of cast profiles and appearance assignments in p."""
    return digest({"cast": p["cast"], "appearances": p["appearances"]})


def sync_cast_speakers(p: dict[str, Any]) -> None:
    """Use unambiguous detection links without replacing manual/proposed choices."""
    appearances = {(a["page_id"], a["char_id"]): a for a in p["appearances"]}
    changed_scenes = set()

    def assign(item, speaker, scene_id):
        origin = item.get("speaker_origin", "")
        managed = origin == "cast" and item["speaker_id"] == item.get("cast_speaker_id")
        unresolved = item["speaker_id"] == UNKNOWN and origin not in {"manual", "proposal"}
        if not managed and not unresolved:
            return
        if speaker == UNKNOWN and not managed:
            return
        if item["speaker_id"] != speaker:
            changed_scenes.add(scene_id)
        item.update(speaker_id=speaker, speaker_origin="cast", cast_speaker_id=speaker)

    for source in p["sources"]:
        linked = [appearances.get((source["page_id"], link.get("char_id"))) if isinstance(link.get("char_id"), str) else None for link in source.get("magi_links", [])]
        valid = linked and all(a and not a["rejected"] and a["speaker_id"] in p["cast"] and a["speaker_id"] != NARRATOR for a in linked)
        speakers = {a["speaker_id"] for a in linked} if valid else set()
        assign(source, next(iter(speakers)) if len(speakers) == 1 else UNKNOWN, source["scene_id"])

    sources = {s["source_id"]: s for s in p["sources"]}
    for scene in p["scenes"]:
        for turn in scene["turns"]:
            if turn["kind"] != "dialogue" or not turn["source_ids"]:
                continue
            linked = [sources.get(sid) for sid in turn["source_ids"]]
            valid = all(s and s["speaker_id"] in p["cast"] for s in linked)
            speakers = {s["speaker_id"] for s in linked} if valid else set()
            assign(turn, next(iter(speakers)) if len(speakers) == 1 else UNKNOWN, scene["scene_id"])
    for scene_id in changed_scenes:
        p["approvals"].pop(scene_id, None)


def approve_cast(p: dict[str, Any]) -> None:
    """Validate mapped/rejected appearances and record the current cast fingerprint in p.

    Returns None; raises ValueError for unresolved appearances or missing cast.
    Does not save to disk or make API calls; relevant edits invalidate the fingerprint."""
    for a in p["appearances"]:
        if not a["rejected"] and a["speaker_id"] not in p["cast"]:
            raise ValueError(f"Resolve or reject appearance {a['char_id']}")
    if len(p["cast"]) < 2:
        raise ValueError("Add character references before approving the cast")
    sync_cast_speakers(p)
    p["cast_approval"] = cast_signature(p)


def rebuild_turns(p: dict[str, Any], narration: dict[str, list[dict[str, Any]]] | None = None) -> None:
    """Rebuild p scenes from ordered source groups and clear scene approvals.

    Optional narration maps scene IDs to narration turns; otherwise existing narration
    is retained with source anchors. Consecutive groups must share speaker and acting
    attributes. Final turn text is the sole render transcript: source rebuilds replace
    manual dialogue-turn edits. Returns None; invalid grouping raises ValueError.
    Mutates p; callers save explicitly. No API calls."""
    by_scene = {s["scene_id"]: s for s in p["scenes"]}
    if narration is None:
        narration = {}
        for scene in p["scenes"]:
            items = []
            for index, turn in enumerate(scene["turns"]):
                if turn.get("kind") == "narration":
                    item = copy.deepcopy(turn)
                    following = [sid for t in scene["turns"][index+1:] for sid in t["source_ids"]]
                    item["anchor_source_id"] = following[0] if following else None
                    items.append(item)
            narration[scene["scene_id"]] = items
    for scene in p["scenes"]:
        scene["turns"] = []
    previous, current, used_groups = None, None, set()
    for source in sorted(p["sources"], key=lambda x: x["order"]):
        if source["scene_id"] not in by_scene:
            raise ValueError("Source refers to an unknown scene")
        pending = narration.get(source["scene_id"], [])
        inserts = [n for n in pending if n.get("anchor_source_id", source["source_id"]) == source["source_id"]]
        if inserts:
            by_scene[source["scene_id"]]["turns"].extend(copy.deepcopy(inserts))
            narration[source["scene_id"]] = [n for n in pending if n not in inserts]
            previous = None
        key = (source["scene_id"], source["turn_group"], source["speaker_id"], source["delivery"],
               source["emotion"], source["style"], source["pacing"], source["include"])
        if key != previous:
            group = (source["scene_id"], source["turn_group"])
            if group in used_groups:
                raise ValueError("A turn group must be consecutive and share speaker, delivery, emotion, style, pacing and inclusion")
            used_groups.add(group)
            current = {"turn_id": "turn_" + digest(source["source_id"])[:12], "kind": "dialogue",
                       "speaker_id": source["speaker_id"], "source_ids": [], "text": "",
                       "include": source["include"], "delivery": source["delivery"], "emotion": source["emotion"],
                       "style": source["style"], "pacing": source["pacing"], "silence_sec": 0.0}
            if source.get("speaker_origin"):
                current["speaker_origin"] = source["speaker_origin"]
                if source["speaker_origin"] == "cast":
                    current["cast_speaker_id"] = source["speaker_id"]
            by_scene[source["scene_id"]]["turns"].append(current)
        assert current is not None  # Every new group creates a turn above.
        current["source_ids"].append(source["source_id"])
        if source.get("speaker_origin") in {"manual", "proposal"}:
            current["speaker_origin"] = source["speaker_origin"]
        reaction = source.get("reaction")
        spoken = reaction["text"] if reaction else source["text"]
        if reaction and reaction.get("silence_sec"):
            current["silence_sec"] += reaction["silence_sec"]
        current["text"] = " ".join(x for x in (current["text"], spoken.strip()) if x)
        previous = key
    for sid, pending in narration.items():
        if pending:
            by_scene[sid]["turns"].extend(copy.deepcopy(pending))
    p["approvals"] = {}


def apply_proposal(p: dict[str, Any], proposal: dict[str, Any]) -> None:
    """Validate and transactionally load proposal into p as an unapproved working script.

    Requires complete, unique source/appearance coverage and valid scenes/cast references.
    Proposed groups split at nonconsecutive or incompatible speaker/acting/inclusion
    boundaries; compatible consecutive bubbles remain joined. Wording, acting fields
    and upstream inclusion are not rewritten by this grouping normalization.
    Replaces assignments, ordering and scenes; rebuilds turns and clears approvals.
    Returns None. Invalid proposals raise ValueError/KeyError/TypeError without publishing
    partial project changes. No disk writes or API calls; save explicitly after success."""
    validate_contract(proposal, Proposal, "proposal")
    q = copy.deepcopy(p)
    src = {s["source_id"]: s for s in q["sources"]}
    apps = {a["char_id"]: a for a in q["appearances"]}
    def exact_ids(items, field, expected):
        ids = [x[field] for x in items]
        if len(ids) != len(set(ids)) or set(ids) != set(expected):
            raise ValueError(f"Proposal must cover all {field} values exactly once")
    exact_ids(proposal["sources"], "source_id", src)
    exact_ids(proposal["appearances"], "char_id", apps)
    allowed = set(q["cast"]) | {UNKNOWN}
    for a in proposal["appearances"]:
        if a["speaker_id"] not in allowed or a["speaker_id"] == NARRATOR:
            raise ValueError("Invalid appearance speaker")
        apps[a["char_id"]].update({k: a[k] for k in ("speaker_id", "rejected", "reason")})
    q["scenes"] = []
    narration: dict[str, list[dict[str, Any]]] = {}
    scene_ids: set[str] = set()
    for s in proposal["scenes"]:
        sid = s["scene_id"]
        if sid in scene_ids or not sid:
            raise ValueError("Duplicate/empty scene ID")
        scene_ids.add(sid)
        if not set(s["evidence_source_ids"]) <= src.keys():
            raise ValueError("Unknown narration evidence")
        q["scenes"].append({"scene_id": sid, "title": s["title"], "context": s["context"], "turns": []})
        narration[sid] = []
        if s["narration"].strip():
            if not s["evidence_source_ids"]:
                raise ValueError("Narration needs visual evidence references")
            narration[sid] = [{"turn_id": "narration_" + digest(sid)[:12], "kind": "narration", "speaker_id": NARRATOR,
                "text": s["narration"], "source_ids": [], "evidence_source_ids": s["evidence_source_ids"],
                "include": True, "delivery": "narration", "emotion": "neutral", "style": "warm, restrained storyteller",
                "pacing": "measured; allow the listener to picture the setting", "silence_sec": 0.0}]
    previous_turn_key: tuple[Any, ...] | None = None
    active_turn_group = ""

    for order, s in enumerate(proposal["sources"]):
        if (
            s["speaker_id"] not in allowed
            or s["scene_id"] not in scene_ids
            or s["delivery"] not in DELIVERIES
        ):
            raise ValueError("Invalid source speaker/scene/delivery")

        target = src[s["source_id"]]
        target.update({
            k: s[k]
            for k in (
                "text", "speaker_id", "scene_id", "turn_group",
                "delivery", "emotion", "style", "pacing", "reason",
            )
        })

        # Keep a group only while its speaker and performance remain compatible.
        turn_key = (
            s["scene_id"], s["turn_group"], s["speaker_id"],
            s["delivery"], s["emotion"], s["style"], s["pacing"],
            target["include"],
        )
        if turn_key != previous_turn_key:
            active_turn_group = s["source_id"]

        target["speaker_origin"] = "proposal"
        target["turn_group"] = active_turn_group
        previous_turn_key = turn_key
        target["order"] = order
        target["reaction"] = (
            {"text": s["reaction_text"], "silence_sec": 0.0}
            if s["reaction_text"].strip()
            else None
        )
    sequence = [s["scene_id"] for s in proposal["sources"]]
    runs = [s for i, s in enumerate(sequence) if i == 0 or s != sequence[i-1]]
    if runs != [s["scene_id"] for s in q["scenes"] if s["scene_id"] in sequence]:
        raise ValueError("Scene order must match contiguous source reading order")
    rebuild_turns(q, narration)
    q["cast_approval"] = None
    p.clear()
    p.update(q)


def scene_signature(p: dict[str, Any], scene: dict[str, Any]) -> str:
    """Return the fingerprint of scene plus relevant project cast, sources and settings."""
    ids = {sid for t in scene["turns"] for sid in t["source_ids"]}
    return digest({"cache_revision": CACHE_REVISION, "text_policy": TEXT_POLICY_VERSION, "scene": scene, "sources": [s for s in p["sources"] if s["source_id"] in ids],
                   "cast": p["cast"], "settings": p["settings"], "cast_approval": p["cast_approval"]})


def validate_scene(p: dict[str, Any], scene: dict[str, Any]) -> None:
    """Validate scene against p, including current cast approval and included turn rules.

    Returns None or raises ValueError for unresolved speakers, invalid source/evidence
    links, encoding repairs requiring review, lost replacement characters, unsupported
    tags, punctuation-only speech or invalid silence. Excluded turn text is not spoken
    or encoding-checked. No mutation/I/O."""
    validate_contract(scene, Scene, "scene")
    if p["cast_approval"] != cast_signature(p):
        raise ValueError("Approve the current cast first")
    sources = {s["source_id"]: s for s in p["sources"]}
    expected = [s["source_id"] for s in sorted(p["sources"], key=lambda s: s["order"]) if s["scene_id"] == scene["scene_id"]]
    actual = [sid for t in scene["turns"] for sid in t["source_ids"]]
    if actual != expected:
        raise ValueError("Scene turns must cover source bubbles once, in reviewed order")
    turn_ids = [t["turn_id"] for t in scene["turns"]]
    if len(turn_ids) != len(set(turn_ids)):
        raise ValueError("Duplicate turn IDs")
    for t in scene["turns"]:
        if not t["include"]:
            continue
        if t["speaker_id"] not in p["cast"]:
            raise ValueError(f"Resolve or exclude {t['turn_id']}")
        require_reviewed_text(t["text"], "Turn text")
        for value in (scene["context"], t["emotion"], t["style"], t["pacing"],
                      p["cast"][t["speaker_id"]]["name"], p["cast"][t["speaker_id"]].get("acting_notes", ""),
                      p["cast"][t["speaker_id"]].get("pronunciation", "")):
            require_reviewed_text(value, "Acting metadata")
        if t["delivery"] not in DELIVERIES:
            raise ValueError("Unsupported delivery")
        if any(not sources[sid]["include"] for sid in t["source_ids"]):
            raise ValueError("Excluded source is in an included turn: rebuild turns")
        if t.get("kind") == "narration" and (t["speaker_id"] != NARRATOR or not t.get("evidence_source_ids")):
            raise ValueError("Narration needs narrator and visual evidence references")
        if not set(t.get("evidence_source_ids", [])) <= sources.keys():
            raise ValueError("Unknown narration evidence source")
        tags = re.findall(r"<[^>]*>", t["text"])
        if any(tag not in {"<gasp>", "<breath>", "<sigh>", "<laugh>", "<cough>", "<short pause>"} for tag in tags):
            raise ValueError("Use supported momentary vocal tags; sustained instructions belong in Acting/Pacing")
        if not math.isfinite(float(t.get("silence_sec", 0))) or not 0 <= float(t.get("silence_sec", 0)) <= MAX_SILENCE_SEC:
            raise ValueError("Silence must be between 0 and 30 seconds")
        if not t["text"].strip() and not t.get("silence_sec", 0):
            raise ValueError("Included turn has neither speech nor intentional silence")
        if t["text"].strip() and not re.search(r"[\w<>]", t["text"], re.UNICODE):
            raise ValueError("Punctuation-only turn needs an approved vocalization, silence, or exclusion")


def approve_scene(p: dict[str, Any], scene: dict[str, Any]) -> None:
    """Validate scene and record its exact fingerprint in p approvals.

    Returns None; validation errors propagate. Does not save or render. Relevant later
    source, scene, cast or settings edits require reapproval."""
    validate_scene(p, scene)
    p["approvals"][scene["scene_id"]] = scene_signature(p, scene)


def exact_review(items: list[dict[str, Any]], field: str, expected: set[str]) -> None:
    """Require complete unique command coverage without exposing rejected values."""
    ids = [item[field] for item in items]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("Review must cover every record exactly once")


def review_cast(data: dict[str, Any], command: dict[str, Any]) -> dict[str, Any]:
    """Return a complete cast/gallery edit candidate; optional approval is transactional. No I/O."""
    result = copy.deepcopy(data)
    for entry in command.get("new_characters", []):
        sid = entry["speaker_id"]
        if sid in result["cast"]:
            raise ValueError("New character identifiers must be unique")
        appearance = next((a for a in result["appearances"] if a["char_id"] == entry["char_id"]), None)
        if appearance is None:
            raise ValueError("Choose an existing appearance for each new character")
        result["cast"][sid] = {"name": "", "voice": "", "pronunciation": "", "acting_notes": "", "references": ["input/" + appearance["crop_path"]]}
    exact_review(command["cast"], "speaker_id", set(result["cast"]))
    exact_review(command["appearances"], "char_id", {a["char_id"] for a in result["appearances"]})
    for edit in command["cast"]:
        if not edit["name"].strip() or not edit["voice"].strip():
            raise ValueError("Cast names and voices cannot be empty")
        result["cast"][edit["speaker_id"]].update({key: edit[key].strip() for key in ("name", "voice", "pronunciation", "acting_notes")})
    for entry in command.get("new_characters", []):
        name = result["cast"][entry["speaker_id"]]["name"].casefold()
        if sum(c["name"].casefold() == name for c in result["cast"].values()) > 1:
            raise ValueError("This character name already exists; assign its existing entry instead")
    appearances = {item["char_id"]: item for item in result["appearances"]}
    for edit in command["appearances"]:
        if edit["speaker_id"] not in (set(result["cast"]) | {UNKNOWN}) - {NARRATOR}:
            raise ValueError("Invalid appearance speaker")
        appearances[edit["char_id"]].update(speaker_id=edit["speaker_id"], rejected=edit["rejected"])
    result.update(cast_approval=None, approvals={})
    sync_cast_speakers(result)
    if command.get("approve", False):
        approve_cast(result)
    return result


def review_sources(data: dict[str, Any], command: dict[str, Any]) -> dict[str, Any]:
    """Return reviewed source ordering/grouping and rebuilt turns; preserve evidence and narration. No I/O."""
    result = copy.deepcopy(data)
    pages = {page["page_id"]: page for page in result["chapter"]["pages"]}
    if command.get("page_order") is not None:
        order = command["page_order"]
        if len(order) != len(set(order)) or set(order) != set(pages):
            raise ValueError("Image order must contain every image exactly once")
        result["page_order"] = order
    if command.get("panel_order") is not None:
        for page_id, order in command["panel_order"].items():
            if page_id not in pages:
                raise ValueError("Unknown image in panel order")
            expected = {panel["panel_id"] for panel in pages[page_id].get("panels", [])}
            if len(order) != len(set(order)) or set(order) != expected:
                raise ValueError("Panel order must contain every detected panel exactly once")
        result["panel_order"] = command["panel_order"]
    exact_review(command["sources"], "source_id", {s["source_id"] for s in result["sources"]})
    sources = {s["source_id"]: s for s in result["sources"]}
    for edit in command["sources"]:
        if not edit["scene_id"].strip() or not edit["turn_group"].strip():
            raise ValueError("Scene/group IDs cannot be empty")
        if edit["speaker_id"] not in set(result["cast"]) | {UNKNOWN} or edit["delivery"] not in DELIVERIES:
            raise ValueError("Invalid source speaker/delivery")
        reaction = edit["reaction"]
        if reaction and not 0 <= reaction["silence_sec"] <= MAX_SILENCE_SEC:
            raise ValueError("Silence must be between 0 and 30 seconds")
        target = sources[edit["source_id"]]
        manual = edit.get("speaker_origin") == "manual" or edit["speaker_id"] != target["speaker_id"]
        target.update({k: copy.deepcopy(v) for k, v in edit.items() if k != "speaker_origin"})
        if manual:
            target["speaker_origin"] = "manual"
    ordered = sorted(result["sources"], key=lambda source: source["order"])
    if len({source["order"] for source in ordered}) != len(ordered):
        raise ValueError("Order values must be unique")
    ids = [source["scene_id"] for source in ordered]
    runs = [sid for index, sid in enumerate(ids) if index == 0 or sid != ids[index - 1]]
    if len(runs) != len(set(runs)):
        raise ValueError("Each scene must be consecutive in source order")
    previous = {scene["scene_id"]: scene for scene in result["scenes"]}
    result["scenes"] = [previous.get(sid, {"scene_id": sid, "title": sid, "context": "", "turns": []}) for sid in runs]
    rebuild_turns(result)
    return result


def review_scene(data: dict[str, Any], command: dict[str, Any], *, sync_speakers: bool = True) -> dict[str, Any]:
    """Return an exact scene edit candidate; combined apply/approval either succeeds completely or raises."""
    result = copy.deepcopy(data)
    scene = next((scene for scene in result["scenes"] if scene["scene_id"] == command["scene_id"]), None)
    if scene is None:
        raise ValueError("Unknown scene")
    exact_review(command["turns"], "turn_id", {turn["turn_id"] for turn in scene["turns"]})
    turns = {turn["turn_id"]: turn for turn in scene["turns"]}
    for edit in command["turns"]:
        if edit["speaker_id"] not in set(result["cast"]) | {UNKNOWN} or edit["delivery"] not in DELIVERIES:
            raise ValueError("Invalid turn speaker/delivery")
        target = turns[edit["turn_id"]]
        manual = edit.get("speaker_origin") == "manual" or edit["speaker_id"] != target["speaker_id"]
        target.update({k: copy.deepcopy(v) for k, v in edit.items() if k != "speaker_origin"})
        if manual:
            target["speaker_origin"] = "manual"
    scene.update(title=command["title"], context=command["context"])
    result["approvals"].pop(scene["scene_id"], None)
    if sync_speakers:
        sync_cast_speakers(result)
    if command.get("approve", False):
        approve_scene(result, scene)
    return result


def add_narration(data: dict[str, Any], command: dict[str, Any]) -> dict[str, Any]:
    """Return a narration-insertion candidate with valid source evidence and cleared scene approval. No I/O."""
    result = copy.deepcopy(data)
    scene = next((scene for scene in result["scenes"] if scene["scene_id"] == command["scene_id"]), None)
    if scene is None or not 0 <= command["position"] <= len(scene["turns"]):
        raise ValueError("Unknown scene or invalid narration position")
    if not command["text"].strip() or not command["evidence_source_ids"] or not set(command["evidence_source_ids"]) <= {s["source_id"] for s in result["sources"]}:
        raise ValueError("Narration requires text and valid evidence source IDs")
    scene["turns"].insert(command["position"], {"turn_id": "narration_" + uuid.uuid4().hex[:12],
        "kind": "narration", "speaker_id": NARRATOR, "source_ids": [], "evidence_source_ids": command["evidence_source_ids"],
        "text": command["text"].strip(), "include": True, "delivery": "narration", "emotion": "neutral",
        "style": "restrained, warm storyteller", "pacing": "measured", "silence_sec": 0.0})
    result["approvals"].pop(scene["scene_id"], None)
    return result
