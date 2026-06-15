from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

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

HIGH_CONFIDENCE_TERMINAL_HINTS = [
    "выносит мяч за пределы поля",
    "выносит за пределы поля",
    "мяч за пределы поля",
]

REVIEW_TERMINAL_HINTS = [
    "бьет по воротам",
    "бьёт по воротам",
    "мгновенный удар",
    "удар издали",
    "находит момент для удара",
    "готов откатить под удар",
    "простреливает",
    "навешивает в штрафную",
    "врывается в штрафную",
]

ANOMALY_HINTS = [
    "||",
    "...",
]

LOW_DECISION_ACTIONS = {
    "стандарт (аут, угловой)",
    "караулить отскок, рикошет",
    "продвинуться вперед, караулить отскок, рикошет",
}


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


def classify_start_risk(scene: engine.Scene, actions: List[str]) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    normalized_actions = [action.strip() for action in actions]
    action_set = set(normalized_actions)
    ball_holder_action = lower_text(scene.get("ball_holder_action", ""))
    narrative = lower_text(scene.get("narrative", ""))
    combined_text = f"{ball_holder_action} {narrative}"

    high_confidence = False
    review_needed = False

    if not narrative:
        reasons.append("empty_narrative")
        review_needed = True

    if not ball_holder_action and str(scene.get("owner")) != "PLAYER_WITH_BALL":
        reasons.append("empty_ball_holder_action_non_player_owner")
        review_needed = True

    if len(normalized_actions) == 1:
        reasons.append("single_executable_action")
        review_needed = True

    if len(normalized_actions) == 1 and action_set <= STANDARD_ACTIONS:
        reasons.append("single_standard_action_only")
        high_confidence = True

    if action_set and action_set <= STANDARD_ACTIONS:
        reasons.append("only_standard_actions")
        high_confidence = True

    if action_set and action_set <= LOW_DECISION_ACTIONS:
        reasons.append("only_low_decision_actions")
        review_needed = True

    for hint in HIGH_CONFIDENCE_TERMINAL_HINTS:
        if hint in combined_text:
            reasons.append(f"terminal_text_hint:{hint}")
            high_confidence = True

    for hint in REVIEW_TERMINAL_HINTS:
        if hint in combined_text:
            reasons.append(f"review_terminal_or_late_phase_hint:{hint}")
            review_needed = True

    for hint in ANOMALY_HINTS:
        if hint in ball_holder_action or hint in narrative:
            reasons.append(f"text_anomaly_hint:{hint}")
            review_needed = True

    if high_confidence:
        return "LIKELY_INVALID_START", sorted(set(reasons))
    if review_needed:
        return "REVIEW_START", sorted(set(reasons))
    return "NO_FLAG", []


def build_candidates(
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

        classification, reasons = classify_start_risk(scene, actions)
        if classification == "NO_FLAG":
            continue

        candidates.append({
            "scene_id": scene_id,
            "owner": owner,
            "tier": int(scene["tier"]),
            "classification": classification,
            "player_position": scene.get("player_position", ""),
            "player_direction": scene.get("player_direction", ""),
            "ball_holder_position": scene.get("ball_holder_position", ""),
            "ball_holder_direction": scene.get("ball_holder_direction", ""),
            "ball_holder_action": scene.get("ball_holder_action", ""),
            "actions": actions,
            "narrative": scene.get("narrative", ""),
            "reasons": reasons,
        })

    candidates.sort(key=lambda item: (str(item["classification"]), str(item["owner"]), int(item["tier"]), str(item["scene_id"])))
    return candidates


def write_report(candidates: List[Dict[str, object]]) -> None:
    by_owner: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    by_classification = Counter(str(item["classification"]) for item in candidates)
    by_owner_classification = Counter((str(item["owner"]), str(item["classification"])) for item in candidates)
    by_reason = Counter(reason for item in candidates for reason in item["reasons"])

    for item in candidates:
        by_owner[str(item["owner"])].append(item)

    lines = [
        "# Invalid Start Candidate Audit Report",
        "",
        "Status: PASS",
        "",
        "## Scope",
        "",
        "- Purpose: exhaustive audit for scenes that may be invalid or suspicious as episode starts.",
        "- This report does not modify Excel scene libraries.",
        "- This report does not automatically remove scenes from selection pools.",
        "- It separates high-confidence likely invalid starts from broader review candidates.",
        "",
        "## Classification Meaning",
        "",
        "- `LIKELY_INVALID_START`: strong mechanical evidence that the scene is an outcome/terminal state, not a playable start.",
        "- `REVIEW_START`: suspicious or late-phase/anomalous scene that needs design review before being used as a start.",
        "",
        "## Detection Rules",
        "",
        "High-confidence likely invalid examples:",
        "",
        "- the only executable action is `стандарт (аут, угловой)`;",
        "- all executable actions are standard actions;",
        "- `ball_holder_action` or `narrative` contains terminal out-of-play hints such as `выносит мяч за пределы поля`.",
        "",
        "Review-needed examples:",
        "",
        "- empty narrative;",
        "- empty ball-holder action for non-player ownership states;",
        "- only one executable action;",
        "- only low-decision actions such as rebound waiting;",
        "- late-phase hints such as shot/cross/cutback already happening;",
        "- text anomalies such as embedded `||` or unfinished ellipsis.",
        "",
        "These are audit flags, not final classifications.",
        "",
        "## Summary",
        "",
        f"- total_flagged_start_candidates: {len(candidates)}",
    ]

    for classification, count in sorted(by_classification.items()):
        lines.append(f"- {classification}: {count}")

    lines += ["", "## By Owner", ""]
    for owner in OWNERS:
        total = len(by_owner.get(owner, []))
        lines.append(f"- {owner}: total_flagged={total}")
        for classification in ["LIKELY_INVALID_START", "REVIEW_START"]:
            lines.append(f"  - {classification}: {by_owner_classification[(owner, classification)]}")

    lines += ["", "## Reason Counts", ""]
    for reason, count in by_reason.most_common():
        lines.append(f"- {reason}: {count}")

    lines += ["", "## Candidates", ""]
    if not candidates:
        lines.append("- none")
    else:
        for classification in ["LIKELY_INVALID_START", "REVIEW_START"]:
            class_items = [item for item in candidates if item["classification"] == classification]
            lines += [f"### {classification}", ""]
            if not class_items:
                lines.append("- none")
                lines.append("")
                continue

            for owner in OWNERS:
                owner_items = [item for item in class_items if item["owner"] == owner]
                lines += [f"#### {owner}", ""]
                if not owner_items:
                    lines.append("- none")
                    lines.append("")
                    continue
                for item in owner_items:
                    actions = " || ".join(str(action) for action in item["actions"])
                    reasons = ", ".join(str(reason) for reason in item["reasons"])
                    lines += [
                        f"##### {item['scene_id']}",
                        "",
                        f"- owner: {item['owner']}",
                        f"- tier: {item['tier']}",
                        f"- reasons: {reasons}",
                        f"- player_position: {item['player_position']}",
                        f"- player_direction: {item['player_direction']}",
                        f"- ball_holder_position: {item['ball_holder_position']}",
                        f"- ball_holder_direction: {item['ball_holder_direction']}",
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
    candidates = build_candidates(scenes, transitions)
    write_report(candidates)

    by_owner = defaultdict(int)
    by_classification = defaultdict(int)
    for item in candidates:
        by_owner[str(item["owner"])] += 1
        by_classification[str(item["classification"])] += 1

    print("Invalid start candidate audit status: PASS")
    print(f"total_flagged_start_candidates: {len(candidates)}")
    for classification in ["LIKELY_INVALID_START", "REVIEW_START"]:
        print(f"{classification}: {by_classification[classification]}")
    for owner in OWNERS:
        print(f"{owner}: {by_owner[owner]}")
    print(f"Report written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
