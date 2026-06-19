from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import test_transitions_multi_executable as engine

CANONICAL_SCENE_FILES = {
    "ball_at_player_normalized_prototype_v7.xlsx": "ball_at_player_normalized_prototype_v7_executable.xlsx",
    "ball_at_teammate_normalized_prototype_v1.xlsx": "ball_at_teammate_normalized_prototype_v1_executable.xlsx",
    "ball_at_opponent_normalized_prototype_v2.xlsx": "ball_at_opponent_normalized_prototype_v2_executable.xlsx",
}


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
    transitions, _ = engine.load_transitions()

    start_scene = args.start_scene
    if start_scene not in scenes:
        sorted_ids = sorted(scenes)
        start_scene = sorted_ids[0]
        print(f"WARNING: configured start scene {args.start_scene} not found; using {start_scene}")

    return engine.run_interactive_match(
        scenes=scenes,
        transitions=transitions,
        start_scene_id=start_scene,
        max_steps=args.max_steps,
    )


if __name__ == "__main__":
    raise SystemExit(main())
