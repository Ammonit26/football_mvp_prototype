from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
for path in (ROOT, TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import test_transitions_multi_executable as engine
import mvp_match_bridge as bridge

REPORT_PATH = Path("verification_report_invalid_start_candidates.md")
OWNERS = ["PLAYER_WITH_BALL", "TEAMMATE_WITH_BALL", "OPPONENT_WITH_BALL"]
STANDARD_ACTIONS = {"стандарт (аут, угловой)"}
TERMINAL_ACTION_HINTS = [
    "выносит мяч за пределы поля",
    "выносит за пределы поля",
    "мяч за пределы поля",
]


def executable_actions(
    scene_id: str,
    scene: engine.Scene,
    transitions: Dict[engine.TransitionKey, List[engine.Transition]],
) -> List[str]:
    return [
        action
        for action in scene["available_player_actions"]
        if transitions.get((scene_id, action, "SUCCESS"))
        and transitions.get((scene_id, action, "FAIL"))
    ]


def lower_text(value: object) -> str:
    return str(value or "").strip().lower()


def invalid_start_reasons(scene: engine.Scene, actions: List[str]) -> List[str]:
    reasons: List[str] = []
    normalized_actions = [action.strip() for action in actions]
    action_set = set(normalized_actions)
    ball_holder_action = lower_text(scene.get("ball_holder_action", ""))
    narrative = lower_text(scene.get("narrative", ""))
    combined_text = f"{ball_holder_action} {narrative}"

    if len(normalized_actions) == 1 and action_set <= STANDARD_ACTIONS:
        reasons.append("single_standard_action_only")

    for hint in TERMINAL_ACTION_HINTS:
        if hint in combined_text:
            reasons.append(f"terminal_text_hint:{hint}")

    if action_set and action_set <= STANDARD_ACTIONS:
        reasons.append("only_standard_actions")

    return sorted(set(reasons))


def build_invalid_candidates(
    scenes: Dict[str, engine.Scene],
    transitions: Dict[engine.TransitionKey, List[engine.Transition]],
) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []

    for scene_id, scene in scenes.items():
        owner = str(scene["owner"])
        if owner not in OWNERS:
            continue

        actions = executable_actions(scene_id, scene, transitions)
        if not actions:
            continue

        reasons = invalid_start_reasons(scene, actions)
        if not reasons:
            continue

        candidates.append({
            "scene_id": scene_id,
            "owner": owner,
            "tier": int(scene["tier"]),
            "player_position": scene.get("player_position", ""),
            "ball_holder_position": scene.get("ball_holder_position", ""),
            "ball_holder_action": scene.get("ball_holder_action", ""),
            "actions": actions,
            "narrative": scene.get("narrative", ""),
            "reasons": reasons,
        })

    candidates.sort(key=lambda item: (str(item["owner"]), int(item["tier"]), str(item["scene_id"])))
    return candidates


def write_report(candidates: List[Dict[str, object]]) -> None:
    by_owner: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for item in candidates:
        by_owner[str(item["owner"])].append(item)

    lines = [
        "# Invalid Start Candidate Audit Report",
        "",
        "Status: PASS",
        "",
        "## Scope",
        "",
        "- Purpose: exhaustive audit for scenes that may be invalid as episode starts.",
        "- This report does not modify Excel scene libraries.",
        "- This report does not automatically remove scenes from selection pools.",
        "- It flags scenes for review by explicit mechanical/textual patterns.",
        "",
        "## Detection Rules",
        "",
        "A scene is flagged if at least one of these is true:",
        "",
        "- the only executable action is `стандарт (аут, угловой)`;",
        "- all executable actions are standard actions;",
        "- `ball_holder_action` or `narrative` contains terminal hints such as `выносит мяч за пределы поля`.",
        "",
        "These are candidate flags, not final classifications.",
        "",
        "## Summary",
        "",
        f"- total_invalid_start_candidates: {len(candidates)}",
    ]

    for owner in OWNERS:
        lines.append(f"- {owner}: {len(by_owner.get(owner, []))}")

    lines += ["", "## Candidates", ""]
    if not candidates:
        lines.append("- none")
    else:
        for owner in OWNERS:
            owner_items = by_owner.get(owner, [])
            lines += [f"### {owner}", ""]
            if not owner_items:
                lines.append("- none")
                lines.append("")
                continue
            for item in owner_items:
                actions = " || ".join(str(action) for action in item["actions"])
                reasons = ", ".join(str(reason) for reason in item["reasons"])
                lines += [
                    f"#### {item['scene_id']}",
                    "",
                    f"- owner: {item['owner']}",
                    f"- tier: {item['tier']}",
                    f"- reasons: {reasons}",
                    f"- player_position: {item['player_position']}",
                    f"- ball_holder_position: {item['ball_holder_position']}",
                    f"- ball_holder_action: {item['ball_holder_action']}",
                    f"- actions: {actions}",
                    f"- narrative: {item['narrative']}",
                    "",
                    "Review: INVALID_START / RARE_START / GOOD_START / UNSURE",
                    "Notes:",
                    "",
                ]

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    bridge.resolve_library_paths()
    scenes = engine.load_scenes()
    transitions, _ = engine.load_transitions()
    candidates = build_invalid_candidates(scenes, transitions)
    write_report(candidates)

    by_owner = defaultdict(int)
    for item in candidates:
        by_owner[str(item["owner"])] += 1

    print("Invalid start candidate audit status: PASS")
    print(f"total_invalid_start_candidates: {len(candidates)}")
    for owner in OWNERS:
        print(f"{owner}: {by_owner[owner]}")
    print(f"Report written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
