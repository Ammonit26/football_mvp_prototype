from __future__ import annotations

import sys
from collections import Counter, defaultdict
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
SAFE_TIER_RULES = {
    "PLAYER_WITH_BALL": {0, 1, 2},
    "TEAMMATE_WITH_BALL": {0, 1, 2},
    "OPPONENT_WITH_BALL": {1, 2, 3},
}


def executable_actions(scene_id: str, scene: engine.Scene, transitions: Dict[engine.TransitionKey, List[engine.Transition]]) -> List[str]:
    return [
        action
        for action in scene["available_player_actions"]
        if transitions.get((scene_id, action, "SUCCESS"))
        and transitions.get((scene_id, action, "FAIL"))
    ]


def is_safe_start_candidate(owner: str, tier: int) -> bool:
    return tier in SAFE_TIER_RULES[owner]


def build_candidates(scenes: Dict[str, engine.Scene], transitions: Dict[engine.TransitionKey, List[engine.Transition]]) -> Dict[str, List[Dict[str, object]]]:
    candidates: Dict[str, List[Dict[str, object]]] = defaultdict(list)

    for scene_id, scene in scenes.items():
        owner = str(scene["owner"])
        if owner not in OWNERS:
            continue

        actions = executable_actions(scene_id, scene, transitions)
        if not actions:
            continue

        tier = int(scene["tier"])
        candidates[owner].append({
            "scene_id": scene_id,
            "tier": tier,
            "safe_start_pool": is_safe_start_candidate(owner, tier),
            "action_count": len(actions),
            "actions": actions,
            "player_position": scene.get("player_position", ""),
            "ball_holder_position": scene.get("ball_holder_position", ""),
            "narrative": scene.get("narrative", ""),
        })

    for owner in candidates:
        candidates[owner].sort(key=lambda item: (not bool(item["safe_start_pool"]), int(item["tier"]), str(item["scene_id"])))

    return candidates


def safe_candidates(candidates: Dict[str, List[Dict[str, object]]], owner: str) -> List[Dict[str, object]]:
    return [item for item in candidates.get(owner, []) if bool(item["safe_start_pool"])]


def tier_counts(items: List[Dict[str, object]]) -> Dict[int, int]:
    return dict(sorted(Counter(int(item["tier"]) for item in items).items()))


def verify_candidates(candidates: Dict[str, List[Dict[str, object]]]) -> Dict[str, object]:
    errors: List[str] = []
    counts = {owner: len(candidates.get(owner, [])) for owner in OWNERS}
    safe_counts = {owner: len(safe_candidates(candidates, owner)) for owner in OWNERS}
    all_tier_counts = {owner: tier_counts(candidates.get(owner, [])) for owner in OWNERS}
    safe_tier_counts = {owner: tier_counts(safe_candidates(candidates, owner)) for owner in OWNERS}

    for owner in OWNERS:
        if counts[owner] == 0:
            errors.append(f"no executable start candidates for owner: {owner}")
        if safe_counts[owner] == 0:
            errors.append(f"no safe start-pool candidates for owner: {owner}")

    return {
        "passed": not errors,
        "errors": errors,
        "counts": counts,
        "safe_counts": safe_counts,
        "all_tier_counts": all_tier_counts,
        "safe_tier_counts": safe_tier_counts,
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
        "- Safe start pool criterion is tier-based, not narrative-text-based.",
        "- Excel scene libraries are not modified.",
        "- Transition libraries are not modified.",
        "",
        "## Safe Start Pool Tier Rules",
        "",
    ]

    for owner in OWNERS:
        tiers = ", ".join(str(tier) for tier in sorted(SAFE_TIER_RULES[owner]))
        lines.append(f"- {owner}: tier {tiers}")

    lines += ["", "## Candidate Counts", ""]
    for owner in OWNERS:
        lines.append(
            f"- {owner}: executable={verification['counts'][owner]} | "
            f"safe_start_pool={verification['safe_counts'][owner]}"
        )

    lines += ["", "## Tier Distribution", ""]
    for owner in OWNERS:
        lines.append(f"### {owner}")
        lines.append(f"- executable_by_tier: {verification['all_tier_counts'][owner]}")
        lines.append(f"- safe_start_pool_by_tier: {verification['safe_tier_counts'][owner]}")
        lines.append("")

    lines += ["## Safe Start Pool Samples", ""]
    for owner in OWNERS:
        lines += [f"### {owner}", ""]
        owner_candidates = safe_candidates(candidates, owner)[:MAX_SAMPLE_PER_OWNER]
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

    lines += ["## Excluded High-Risk Samples", ""]
    for owner in OWNERS:
        lines += [f"### {owner}", ""]
        excluded = [item for item in candidates.get(owner, []) if not bool(item["safe_start_pool"])]
        if not excluded:
            lines.append("- none")
            lines.append("")
            continue
        for item in excluded[:MAX_SAMPLE_PER_OWNER]:
            lines.append(
                f"- {item['scene_id']} | tier={item['tier']} | "
                f"player_position={item['player_position']} | ball_holder_position={item['ball_holder_position']}"
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
        "The safe start pool is still mechanical and tier-based; it is not final manual curation.",
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
        print(f"{owner}: executable={verification['counts'][owner]} safe_start_pool={verification['safe_counts'][owner]}")
    print(f"Report written: {REPORT_PATH}")
    return 0 if verification["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
