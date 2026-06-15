from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
for path in (ROOT, TOOLS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import test_transitions_multi_executable as engine
import mvp_match_bridge as bridge

REPORT_PATH = Path("start_scene_review_pack.md")
OWNERS = ["PLAYER_WITH_BALL", "TEAMMATE_WITH_BALL", "OPPONENT_WITH_BALL"]
SAMPLES_PER_OWNER_TIER = 3


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


def build_candidates(
    scenes: Dict[str, engine.Scene],
    transitions: Dict[engine.TransitionKey, List[engine.Transition]],
) -> Dict[str, Dict[int, List[Dict[str, object]]]]:
    by_owner_tier: Dict[str, Dict[int, List[Dict[str, object]]]] = defaultdict(lambda: defaultdict(list))

    for scene_id, scene in scenes.items():
        owner = str(scene["owner"])
        if owner not in OWNERS:
            continue

        actions = executable_actions(scene_id, scene, transitions)
        if not actions:
            continue

        tier = int(scene["tier"])
        by_owner_tier[owner][tier].append({
            "scene_id": scene_id,
            "owner": owner,
            "tier": tier,
            "player_position": scene.get("player_position", ""),
            "player_direction": scene.get("player_direction", ""),
            "ball_holder_position": scene.get("ball_holder_position", ""),
            "ball_holder_direction": scene.get("ball_holder_direction", ""),
            "ball_holder_action": scene.get("ball_holder_action", ""),
            "actions": actions,
            "narrative": scene.get("narrative", ""),
        })

    for owner in by_owner_tier:
        for tier in by_owner_tier[owner]:
            by_owner_tier[owner][tier].sort(key=lambda item: str(item["scene_id"]))

    return by_owner_tier


def pick_representative(items: List[Dict[str, object]], limit: int) -> List[Dict[str, object]]:
    if len(items) <= limit:
        return items

    if limit == 1:
        return [items[len(items) // 2]]

    indexes = []
    for index in range(limit):
        raw = round(index * (len(items) - 1) / (limit - 1))
        indexes.append(raw)
    return [items[index] for index in indexes]


def join_actions(actions: Iterable[object]) -> str:
    return " || ".join(str(action) for action in actions)


def write_report(by_owner_tier: Dict[str, Dict[int, List[Dict[str, object]]]]) -> None:
    lines = [
        "# Start Scene Review Pack",
        "",
        "## Purpose",
        "",
        "This is a human-review pack for deciding which scenes can naturally start a playable episode.",
        "",
        "It does not classify scenes automatically as valid or invalid starts.",
        "It samples executable scenes across ownership states and tiers so the design decision can be made from actual scene content.",
        "",
        "## Review Questions",
        "",
        "For each sample, decide:",
        "",
        "* GOOD_START: natural first scene of a playable episode;",
        "* RARE_START: usable only as a high-stakes or late-match start;",
        "* BAD_START: should normally only be reached from previous scene flow, not as an episode start;",
        "* UNSURE: needs later review.",
        "",
        "## Samples",
        "",
    ]

    total_samples = 0
    for owner in OWNERS:
        lines += [f"# {owner}", ""]
        tiers = sorted(by_owner_tier.get(owner, {}).keys())
        if not tiers:
            lines += ["No executable scenes found.", ""]
            continue

        for tier in tiers:
            items = by_owner_tier[owner][tier]
            picked = pick_representative(items, SAMPLES_PER_OWNER_TIER)
            total_samples += len(picked)
            lines += [f"## Tier {tier}", "", f"Total executable scenes in this group: {len(items)}", ""]

            for item in picked:
                lines += [
                    f"### {item['scene_id']}",
                    "",
                    f"- owner: {item['owner']}",
                    f"- tier: {item['tier']}",
                    f"- player_position: {item['player_position']}",
                    f"- player_direction: {item['player_direction']}",
                    f"- ball_holder_position: {item['ball_holder_position']}",
                    f"- ball_holder_direction: {item['ball_holder_direction']}",
                    f"- ball_holder_action: {item['ball_holder_action']}",
                    f"- actions: {join_actions(item['actions'])}",
                    f"- narrative: {item['narrative']}",
                    "",
                    "Review: GOOD_START / RARE_START / BAD_START / UNSURE",
                    "Notes:",
                    "",
                ]

    lines += [
        "## Summary",
        "",
        f"Total sampled scenes: {total_samples}",
        "",
        "This pack is intentionally small. It is for validating the start-scene classification approach before any bulk curation.",
    ]

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    bridge.resolve_library_paths()
    scenes = engine.load_scenes()
    transitions, _ = engine.load_transitions()
    by_owner_tier = build_candidates(scenes, transitions)
    write_report(by_owner_tier)

    print("Start scene review pack status: PASS")
    for owner in OWNERS:
        count = sum(len(items) for items in by_owner_tier.get(owner, {}).values())
        tiers = sorted(by_owner_tier.get(owner, {}).keys())
        print(f"{owner}: executable={count} tiers={tiers}")
    print(f"Report written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
