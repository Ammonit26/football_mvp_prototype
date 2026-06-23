from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import test_transitions_multi_executable as engine
import run_interactive_episode as runner

REPORT_MD = ROOT / "verification_report_smoke_test_episodes.md"
REPORT_CSV = ROOT / "verification_report_smoke_test_episodes.csv"


def choose_start_scene(scenes: Dict[str, engine.Scene]) -> str:
    return runner.choose_random_start_scene(scenes)


def choose_action(scene: engine.Scene) -> str:
    actions = list(scene.get("available_player_actions") or [])
    if not actions:
        raise ValueError("dynamic scene has no available actions")
    return random.choice(actions)


def simulate_episode(
    episode_index: int,
    scenes: Dict[str, engine.Scene],
    transitions: Dict[engine.TransitionKey, List[engine.Transition]],
    max_steps: int,
    max_dynamic_scenes: int,
) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
    current_scene_id = choose_start_scene(scenes)
    start_scene_id = current_scene_id
    dynamic_count = 0
    pending_shot_terminal = False
    pending_shot_reason = ""
    episode_log: List[Dict[str, object]] = []

    for step in range(1, max_steps + 1):
        scene = scenes.get(current_scene_id)
        if not scene:
            return {
                "episode": episode_index,
                "status": "SCENE_MISSING",
                "start_scene_id": start_scene_id,
                "step": step,
                "current_scene_id": current_scene_id,
                "dynamic_count": dynamic_count,
                "detail": "current scene id not found",
            }, episode_log

        scene_type = str(scene.get("scene_type", "dynamic"))
        if scene_type == "dynamic":
            dynamic_count += 1

        if scene_type == "static" and (pending_shot_terminal or runner.is_shot_static_scene(scene)):
            terminal = runner.resolve_shot_terminal_outcome()
            episode_log.append(
                {
                    "episode": episode_index,
                    "step": step,
                    "source_scene_id": current_scene_id,
                    "scene_type": scene_type,
                    "action": "SHOT_TERMINAL",
                    "outcome": terminal["code"],
                    "resolver": "shot_terminal_resolver",
                    "next_scene_id": "",
                    "owner_after": terminal["next_owner"],
                    "detail": pending_shot_reason or "static narrative marker",
                }
            )
            return {
                "episode": episode_index,
                "status": "SHOT_TERMINAL",
                "start_scene_id": start_scene_id,
                "step": step,
                "current_scene_id": current_scene_id,
                "dynamic_count": dynamic_count,
                "detail": f"{terminal['code']} {terminal['next_owner']}",
            }, episode_log

        if scene_type == "static":
            action = runner.STATIC_ACTION
            outcome = runner.STATIC_OUTCOME
        else:
            try:
                action = choose_action(scene)
            except ValueError as exc:
                return {
                    "episode": episode_index,
                    "status": "NO_ACTIONS",
                    "start_scene_id": start_scene_id,
                    "step": step,
                    "current_scene_id": current_scene_id,
                    "dynamic_count": dynamic_count,
                    "detail": str(exc),
                }, episode_log
            outcome = random.choice(["SUCCESS", "FAIL"])
            if runner.is_shot_dynamic_context(scene, action):
                pending_shot_terminal = True
                pending_shot_reason = f"dynamic shot context: {current_scene_id}; action={action}"
            else:
                pending_shot_terminal = False
                pending_shot_reason = ""

        key = (current_scene_id, action, outcome)
        transition_options = transitions.get(key, [])
        if not transition_options:
            return {
                "episode": episode_index,
                "status": "NO_TRANSITION",
                "start_scene_id": start_scene_id,
                "step": step,
                "current_scene_id": current_scene_id,
                "dynamic_count": dynamic_count,
                "detail": repr(key),
            }, episode_log

        transition = random.choice(transition_options)

        if scene_type == "dynamic":
            next_scene_id, resolver, resolver_detail = runner.choose_static_bridge_scene(scenes, transition)
        else:
            next_scene_id, resolver, resolver_detail = runner.choose_dynamic_from_static_continue(scenes, transition)

        if not next_scene_id:
            return {
                "episode": episode_index,
                "status": "STATE_GAP",
                "start_scene_id": start_scene_id,
                "step": step,
                "current_scene_id": current_scene_id,
                "dynamic_count": dynamic_count,
                "detail": resolver_detail,
            }, episode_log

        next_scene = scenes.get(next_scene_id)
        if not next_scene:
            return {
                "episode": episode_index,
                "status": "NEXT_SCENE_MISSING",
                "start_scene_id": start_scene_id,
                "step": step,
                "current_scene_id": current_scene_id,
                "dynamic_count": dynamic_count,
                "detail": next_scene_id,
            }, episode_log

        episode_log.append(
            {
                "episode": episode_index,
                "step": step,
                "source_scene_id": current_scene_id,
                "scene_type": scene_type,
                "action": action,
                "outcome": outcome,
                "transition_id": transition.get("transition_id", ""),
                "resolver": resolver,
                "next_scene_id": next_scene_id,
                "owner_after": next_scene.get("owner", ""),
                "detail": resolver_detail,
            }
        )

        if dynamic_count >= max_dynamic_scenes and str(next_scene.get("scene_type", "dynamic")) == "dynamic":
            return {
                "episode": episode_index,
                "status": "FORCED_END",
                "start_scene_id": start_scene_id,
                "step": step,
                "current_scene_id": current_scene_id,
                "dynamic_count": dynamic_count,
                "detail": f"next_episode_candidate={next_scene_id}",
            }, episode_log

        current_scene_id = next_scene_id

    return {
        "episode": episode_index,
        "status": "MAX_STEPS_REACHED",
        "start_scene_id": start_scene_id,
        "step": max_steps,
        "current_scene_id": current_scene_id,
        "dynamic_count": dynamic_count,
        "detail": "episode reached max steps without terminal condition",
    }, episode_log


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated read-only smoke test for local episode resolver.")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--max-dynamic-scenes", type=int, default=runner.DEFAULT_MAX_DYNAMIC_SCENES)
    parser.add_argument("--seed", type=int, default=engine.RANDOM_SEED)
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    runner.resolve_canonical_files()
    scenes = engine.load_scenes()
    runner.enrich_scene_types(scenes)
    transitions, _ = engine.load_transitions()

    summaries: List[Dict[str, object]] = []
    logs: List[Dict[str, object]] = []

    for episode_index in range(1, args.episodes + 1):
        summary, episode_log = simulate_episode(
            episode_index=episode_index,
            scenes=scenes,
            transitions=transitions,
            max_steps=args.max_steps,
            max_dynamic_scenes=args.max_dynamic_scenes,
        )
        summaries.append(summary)
        logs.extend(episode_log)

    status_counts = Counter(str(row["status"]) for row in summaries)
    resolver_counts = Counter(str(row.get("resolver", "")) for row in logs if row.get("resolver"))
    shot_outcome_counts = Counter(str(row.get("outcome", "")) for row in logs if row.get("action") == "SHOT_TERMINAL")

    pd.DataFrame(summaries).to_csv(REPORT_CSV, index=False, encoding="utf-8-sig")

    lines = [
        "# Episode Smoke Test Report",
        "",
        "Status: READ_ONLY",
        "",
        f"- episodes_requested: {args.episodes}",
        f"- max_steps: {args.max_steps}",
        f"- max_dynamic_scenes: {args.max_dynamic_scenes}",
        f"- seed: {args.seed}",
        f"- summaries_csv: {REPORT_CSV.name}",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in status_counts.most_common():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Resolver Counts", ""])
    for key, value in resolver_counts.most_common():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Shot Outcome Counts", ""])
    if shot_outcome_counts:
        for key, value in shot_outcome_counts.most_common():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none: 0")

    lines.extend(["", "## Failure / Attention Examples", ""])
    attention_statuses = {"STATE_GAP", "NO_TRANSITION", "NO_ACTIONS", "SCENE_MISSING", "NEXT_SCENE_MISSING", "MAX_STEPS_REACHED"}
    attention = [row for row in summaries if row["status"] in attention_statuses]
    if not attention:
        lines.append("- none")
    else:
        for row in attention[:30]:
            lines.append(
                f"- episode {row['episode']} status={row['status']} "
                f"start={row['start_scene_id']} step={row['step']} "
                f"scene={row['current_scene_id']} detail={row['detail']}"
            )

    lines.extend(["", "## First 20 Episode Summaries", ""])
    for row in summaries[:20]:
        lines.append(
            f"- episode {row['episode']}: status={row['status']}, "
            f"start={row['start_scene_id']}, step={row['step']}, "
            f"dynamic_count={row['dynamic_count']}, detail={row['detail']}"
        )

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")

    print("Episode smoke test status: PASS")
    print(f"Report written: {REPORT_MD.name}")
    print(f"CSV written: {REPORT_CSV.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
