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

REPORT_PATH = Path("verification_report_start_scene_candidates.md")
OWNERS = ["PLAYER_WITH_BALL", "TEAMMATE_WITH_BALL", "OPPONENT_WITH_BALL"]
MAX_SAMPLE_PER_OWNER = 20


def executable_actions(scene_id: str, scene: engine.Scene, transitions: Dict[engine.TransitionKey, List[engine.Transition]]) -> List[str]:
    return [
        action
        for action in scene["available_player_actions"]
        if transitions.get((scene_id, action, "SUCCESS"))
        and transitions.get((scene_id, action, "FAIL"))
    ]


def build_candidates(scenes: Dict[str, engine.Scene], transitions: Dict[engine.TransitionKey, List[engine.Transition]]) -> Dict[str, List[Dict[str, object]]]:
    candidates: Dict[str, List[Dict[str, object]]] = defaultdict(list)

    for scene_id, scene in scenes.items():
        owner = str(scene["owner"])
        if owner not in OWNERS:
            continue

        actions = executable_actions(scene_id, scene, transitions)
        if not actions:
            continue

        candidates[owner].append({
            "scene_id": scene_id,
            "tier": int(scene["tier"]),
            "action_count": len(actions),
            "actions": actions,
            "player_position": scene.get("player_position", ""),
            "ball_holder_position": scene.get("ball_holder_position", ""),
            "narrative": scene.get("narrative", ""),
        })

    for owner in candidates:
        candidates[owner].sort(key=lambda item: (int(item["tier"]), str(item["scene_id"])))

    return candidates


def verify_candidates(candidates: Dict[str, List[Dict[str, object]]]) -> Dict[str, object]:
    errors: List[str] = []
    for owner in OWNERS:
        if not candidates.get(owner):
            errors.append(f"no executable start candidates for owner: {owner}")
    return {
        "passed": not errors,
        "errors": errors,
        "counts": {owner: len(candidates.get(owner, [])) for owner in OWNERS},
    }


def write_report(candidates: Dict[str, List[Dict[str, object]]], verification: Dict[str, object]) -> None:
    lines = [
        "# Start Scene Candidate Audit Report",
        "",
        f"Status: {'PASS' if verification['passed'] else 'FAIL'}",
        "",
        "## Scope",
        "",
        "- Purpose: audit executable start-scene candidates per ownership state.",
        "- This report does not infer suitability from scene text.",
        "- Candidate criterion: scene has at least one player action with both SUCCESS and FAIL transitions.",
        "- Excel scene libraries are not modified.",
        "- Transition libraries are not modified.",
        "",
        "## Candidate Counts",
        "",
    ]

    for owner in OWNERS:
        lines.append(f"- {owner}: {verification['counts'][owner]}")

    lines += ["", "## Candidate Samples", ""]
    for owner in OWNERS:
        lines += [f"### {owner}", ""]
        owner_candidates = candidates.get(owner, [])[:MAX_SAMPLE_PER_OWNER]
        if not owner_candidates:
            lines.append("- none")
            lines.append("")
            continue
        for item in owner_candidates:
            action_preview = " || ".join(str(action) for action in item["actions"][:4])
            lines.append(
                f"- {item['scene_id']} | tier={item['tier']} | actions={item['action_count']} | "
                f"player_position={item['player_position']} | ball_holder_position={item['ball_holder_position']} | "
                f"actions_sample={action_preview}"
            )
        lines.append("")

    if verification["errors"]:
        lines += ["## Errors", ""]
        lines.extend(f"- {error}" for error in verification["errors"])
        lines.append("")

    lines += [
        "## Next Use",
        "",
        "This report is an audit input for pressure-based start ownership selection.",
        "It is not yet a final curated start-scene pool.",
    ]

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    bridge.resolve_library_paths()
    scenes = engine.load_scenes()
    transitions, _ = engine.load_transitions()
    candidates = build_candidates(scenes, transitions)
    verification = verify_candidates(candidates)
    write_report(candidates, verification)

    print(f"Start scene candidate audit status: {'PASS' if verification['passed'] else 'FAIL'}")
    for owner in OWNERS:
        print(f"{owner}: {verification['counts'][owner]}")
    print(f"Report written: {REPORT_PATH}")
    return 0 if verification["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
