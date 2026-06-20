from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import test_transitions_multi_executable as engine

CANONICAL_SCENE_FILES = {
    "ball_at_player_normalized_prototype_v7.xlsx": "ball_at_player_normalized_prototype_v7_executable.xlsx",
    "ball_at_teammate_normalized_prototype_v1.xlsx": "ball_at_teammate_normalized_prototype_v1_executable.xlsx",
    "ball_at_opponent_normalized_prototype_v2.xlsx": "ball_at_opponent_normalized_prototype_v2_executable.xlsx",
}

STATIC_ACTION = "CONTINUE"
STATIC_OUTCOME = "SUCCESS"


def resolve_canonical_files() -> None:
    for config in engine.SCENE_LIBRARIES:
        configured = str(config["file"])
        current = ROOT / configured
        if current.exists():
            config["file"] = str(current)
            continue

        canonical_name = CANONICAL_SCENE_FILES.get(configured)
        if canonical_name:
            canonical_path = ROOT / canonical_name
            if canonical_path.exists():
                config["file"] = str(canonical_path)
                continue

        raise FileNotFoundError(
            f"Scene library not found for configured file {configured!r}. "
            f"Expected canonical file in repository root."
        )

    for config in engine.TRANSITION_LIBRARIES:
        current = ROOT / str(config["file"])
        if current.exists():
            config["file"] = str(current)
            continue
        raise FileNotFoundError(f"Transition library not found: {config['file']!r}")


def enrich_scene_types(scenes: Dict[str, engine.Scene]) -> None:
    for scene in scenes.values():
        scene["scene_type"] = "dynamic"

    for config in engine.SCENE_LIBRARIES:
        df = pd.read_excel(config["file"], sheet_name=config["sheet"], dtype=str, keep_default_na=False)
        if "scene_type" not in df.columns:
            continue
        for _, row in df.iterrows():
            scene_id = engine.safe_str(row.get("scene_id"))
            if not scene_id or scene_id not in scenes:
                continue
            scene_type = engine.safe_str(row.get("scene_type")).lower() or "dynamic"
            if scene_type not in {"dynamic", "static"}:
                raise ValueError(f"Unsupported scene_type {scene_type!r} for {scene_id}")
            scenes[scene_id]["scene_type"] = scene_type


def print_scene_static_aware(scene_id: str, scene: engine.Scene, step: int, max_steps: int) -> None:
    scene_type = str(scene.get("scene_type", "dynamic"))
    print("\n" + "=" * 72)
    print(f"Step: {step}/{max_steps}")
    print(f"Scene ID: {scene_id}")
    print(f"Scene type: {scene_type}")
    print(f"Ball ownership: {scene['owner']}")
    print("\nScene:")
    print(f"  {scene.get('narrative') or '(no narrative_scene)'}")
    if scene_type == "dynamic":
        print("\nAvailable player actions:")
        for index, action in enumerate(scene["available_player_actions"], start=1):
            print(f"  {index}. {action}")
    else:
        print("\nStatic scene: no player choice.")
    print("=" * 72)


def run_interactive_match_static_aware(
    scenes: Dict[str, engine.Scene],
    transitions: Dict[engine.TransitionKey, List[engine.Transition]],
    start_scene_id: str,
    max_steps: int,
) -> int:
    current_scene_id = start_scene_id
    match_log: List[Dict[str, object]] = []

    print("\nInteractive player mode")
    print("You make decisions only in dynamic scenes. Static scenes show match events.")
    print("Enter q at any dynamic action prompt to finish the match.")

    for step in range(1, max_steps + 1):
        scene = scenes.get(current_scene_id)
        if not scene:
            print(f"ERROR: scene not found: {current_scene_id}")
            engine.print_match_log(match_log)
            return 1

        scene_type = str(scene.get("scene_type", "dynamic"))
        print_scene_static_aware(current_scene_id, scene, step, max_steps)

        if scene_type == "static":
            input("\nPress Enter to continue...")
            action = STATIC_ACTION
            outcome = STATIC_OUTCOME
        else:
            actions = scene["available_player_actions"]
            if not actions:
                print(f"Match stopped: dynamic scene has no available actions: {current_scene_id}")
                engine.print_match_log(match_log)
                return 1
            action = engine.choose_player_action(actions)
            if action is None:
                print("Match finished by player.")
                engine.print_match_log(match_log)
                return 0
            outcome = random.choice(["SUCCESS", "FAIL"])

        key = (current_scene_id, action, outcome)
        transition_options = transitions.get(key, [])
        if not transition_options:
            print(f"ERROR: no transition for {key}")
            engine.print_match_log(match_log)
            return 1

        transition = random.choice(transition_options)
        next_scene_id, resolver = engine.resolve_next_scene(scenes, current_scene_id, transition)
        if not next_scene_id:
            print(f"ERROR: no next scene from {current_scene_id}")
            engine.print_match_log(match_log)
            return 1

        next_scene = scenes[next_scene_id]
        if scene_type == "dynamic":
            print("\nAction result:")
            print(f"  Action: {action}")
            print(f"  Outcome: {outcome}")
            print(f"  Transition: {transition.get('transition_id') or '(no transition_id)'}")
            print(f"  Resolver: {resolver}")
            print(f"  New scene: {next_scene_id}")
            print(f"  New ball ownership: {next_scene['owner']}")
        else:
            print("\nStatic transition:")
            print(f"  Transition: {transition.get('transition_id') or '(no transition_id)'}")
            print(f"  Resolver: {resolver}")
            print(f"  New scene: {next_scene_id}")
            print(f"  New ball ownership: {next_scene['owner']}")

        match_log.append(
            {
                "step": step,
                "source_scene_id": current_scene_id,
                "owner_before": scene["owner"],
                "action": action,
                "outcome": outcome,
                "transition_id": transition.get("transition_id", ""),
                "next_scene_id": next_scene_id,
                "owner_after": next_scene["owner"],
            }
        )
        current_scene_id = next_scene_id

    print(f"Match finished after reaching max steps: {max_steps}")
    engine.print_match_log(match_log)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run interactive episode simulation using canonical repository Excel files."
    )
    parser.add_argument(
        "--start-scene",
        default=engine.START_SCENE,
        help=f"Scene ID to start from. Default: {engine.START_SCENE}",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=engine.MAX_STEPS,
        help=f"Maximum interactive steps. Default: {engine.MAX_STEPS}",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=engine.RANDOM_SEED,
        help=f"Random seed. Default: {engine.RANDOM_SEED}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    resolve_canonical_files()
    scenes = engine.load_scenes()
    enrich_scene_types(scenes)
    transitions, _ = engine.load_transitions()

    start_scene = args.start_scene
    if start_scene not in scenes:
        sorted_ids = sorted(scenes)
        start_scene = sorted_ids[0]
        print(f"WARNING: configured start scene {args.start_scene} not found; using {start_scene}")

    return run_interactive_match_static_aware(
        scenes=scenes,
        transitions=transitions,
        start_scene_id=start_scene,
        max_steps=args.max_steps,
    )


if __name__ == "__main__":
    raise SystemExit(main())
