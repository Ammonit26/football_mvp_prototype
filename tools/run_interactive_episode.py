from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
DEFAULT_MAX_DYNAMIC_SCENES = 5
RUNTIME_STATIC_PREFIX = "fb_runtime_static_result"

# State Resolver V2:
# dynamic action -> static result bridge -> exact dynamic scene by state_after.
# If no exact dynamic scene exists, the episode stops with STATE_GAP.
STATE_FIELD_PAIRS = [
    ("ball_owner_after", "owner"),
    ("player_position_after", "player_position"),
    ("player_direction_after", "player_direction"),
    ("ball_holder_position_after", "ball_holder_position"),
    ("ball_holder_direction_after", "ball_holder_direction"),
]


def norm(value: object) -> str:
    return str(value or "").strip().lower().replace("ё", "е")


def split_scene_pool(raw: object) -> List[str]:
    return [part.strip() for part in str(raw or "").split("||") if part.strip()]


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


def transition_scene_pool(transition: engine.Transition) -> List[str]:
    pool = split_scene_pool(transition.get("allowed_next_scene_ids", ""))
    if pool:
        return pool
    next_scene = str(transition.get("next_scene_id", "") or transition.get("target_scene_id", "")).strip()
    return [next_scene] if next_scene else []


def scene_matches_state_after(transition: engine.Transition, scene: engine.Scene) -> bool:
    for transition_field, scene_field in STATE_FIELD_PAIRS:
        expected = str(transition.get(transition_field, "") or "").strip()
        if not expected:
            continue
        actual = str(scene.get(scene_field, "") or "").strip()
        if norm(expected) != norm(actual):
            return False
    return True


def find_exact_dynamic_scenes(scenes: Dict[str, engine.Scene], transition: engine.Transition) -> List[str]:
    exact: List[str] = []
    for scene_id, scene in scenes.items():
        if str(scene.get("scene_type", "dynamic")) == "static":
            continue
        if scene_matches_state_after(transition, scene):
            exact.append(scene_id)
    return sorted(exact)


def build_runtime_static_scene(scene_id: str, transition: engine.Transition) -> engine.Scene:
    owner_after = str(transition.get("ball_owner_after", "") or "").strip() or "UNKNOWN"
    return {
        "scene_id": scene_id,
        "owner": owner_after,
        "scene_type": "static",
        "player_position": str(transition.get("player_position_after", "") or "").strip(),
        "player_direction": str(transition.get("player_direction_after", "") or "").strip(),
        "ball_holder_position": str(transition.get("ball_holder_position_after", "") or "").strip(),
        "ball_holder_direction": str(transition.get("ball_holder_direction_after", "") or "").strip(),
        "available_player_actions": [],
        "narrative": "[RUNTIME_STATIC_RESULT] Техническая статическая сцена результата действия. Финальный текст будет написан позже.",
    }


def choose_static_bridge_scene(scenes: Dict[str, engine.Scene], transition: engine.Transition, runtime_index: int) -> Tuple[str, str]:
    pool = transition_scene_pool(transition)
    static_candidates = [
        scene_id
        for scene_id in pool
        if scene_id in scenes and str(scenes[scene_id].get("scene_type", "dynamic")) == "static"
    ]
    if static_candidates:
        chosen = random.choice(sorted(static_candidates))
        return chosen, f"static_bridge_from_transition_pool={len(static_candidates)}"

    runtime_scene_id = f"{RUNTIME_STATIC_PREFIX}_{runtime_index:04d}"
    scenes[runtime_scene_id] = build_runtime_static_scene(runtime_scene_id, transition)
    return runtime_scene_id, "runtime_static_bridge_created"


def resolve_state_v2_dynamic_result(
    scenes: Dict[str, engine.Scene],
    transition: engine.Transition,
    runtime_index: int,
) -> Tuple[Optional[str], Optional[str], str, str]:
    exact = find_exact_dynamic_scenes(scenes, transition)
    if not exact:
        return None, None, "state_resolver_v2_state_gap", "no exact dynamic scene for transition state_after"

    pending_dynamic_scene_id = random.choice(exact)
    static_scene_id, static_detail = choose_static_bridge_scene(scenes, transition, runtime_index)
    detail = f"exact_dynamic_candidates={len(exact)}; pending_next_dynamic={pending_dynamic_scene_id}; {static_detail}"
    return static_scene_id, pending_dynamic_scene_id, "state_resolver_v2_exact_static_bridge", detail


def resolve_next_scene_random(scenes: Dict[str, engine.Scene], current_scene_id: str, transition: engine.Transition) -> Tuple[str, str, str]:
    next_scene_id, resolver = engine.resolve_next_scene(scenes, current_scene_id, transition)
    return next_scene_id, resolver, "legacy random/allowed_next_scene_ids resolver"


def print_scene_static_aware(scene_id: str, scene: engine.Scene, step: int, max_steps: int, dynamic_count: int, max_dynamic_scenes: int) -> None:
    scene_type = str(scene.get("scene_type", "dynamic"))
    print("\n" + "=" * 72)
    print(f"Step: {step}/{max_steps}")
    print(f"Scene ID: {scene_id}")
    print(f"Scene type: {scene_type}")
    print(f"Ball ownership: {scene['owner']}")
    print(f"Dynamic scene budget: {dynamic_count}/{max_dynamic_scenes}")
    print("\nScene:")
    print(f"  {scene.get('narrative') or '(no narrative_scene)'}")
    if scene_type == "dynamic":
        print("\nAvailable player actions:")
        for index, action in enumerate(scene["available_player_actions"], start=1):
            print(f"  {index}. {action}")
    else:
        print("\nStatic scene: no player choice.")
    print("=" * 72)


def print_forced_episode_end(next_scene_id: str, next_scene: engine.Scene, dynamic_count: int) -> None:
    print("\n" + "=" * 72)
    print("Episode end: forced static scene")
    print(f"Dynamic scene limit reached: {dynamic_count}")
    print("\nScene:")
    print("  Эпизод исчерпывает себя. Игра уходит в следующую фазу матча, а новая важная ситуация будет начата отдельным эпизодом.")
    print("\nNext episode candidate:")
    print(f"  Scene ID: {next_scene_id}")
    print(f"  Ball ownership: {next_scene['owner']}")
    print("=" * 72)


def should_force_episode_end(next_scene: engine.Scene, dynamic_count: int, max_dynamic_scenes: int) -> bool:
    return dynamic_count >= max_dynamic_scenes and str(next_scene.get("scene_type", "dynamic")) == "dynamic"


def print_state_gap(current_scene_id: str, action: str, outcome: str, transition: engine.Transition, detail: str) -> None:
    print("\n" + "=" * 72)
    print("STATE_GAP: no exact dynamic scene for transition state_after")
    print(f"Source scene: {current_scene_id}")
    print(f"Action: {action}")
    print(f"Outcome: {outcome}")
    print(f"Transition: {transition.get('transition_id') or '(no transition_id)'}")
    print("State after:")
    for field, _ in STATE_FIELD_PAIRS:
        print(f"  {field}: {transition.get(field, '')}")
    print(f"Detail: {detail}")
    print("Episode stopped for diagnosis.")
    print("=" * 72)


def run_interactive_match_static_aware(
    scenes: Dict[str, engine.Scene],
    transitions: Dict[engine.TransitionKey, List[engine.Transition]],
    start_scene_id: str,
    max_steps: int,
    max_dynamic_scenes: int,
    resolver_mode: str,
) -> int:
    current_scene_id = start_scene_id
    match_log: List[Dict[str, object]] = []
    dynamic_count = 0
    runtime_static_counter = 0
    pending_next_dynamic_scene_id: Optional[str] = None
    pending_resolver_detail = ""

    print("\nInteractive player mode")
    print("PEFL-style event flow: static match events plus occasional player decisions.")
    print("You make decisions only in dynamic scenes. Static scenes show match events.")
    print(f"Episode dynamic-scene limit: {max_dynamic_scenes}")
    print(f"Next-scene resolver: {resolver_mode}")
    print("Enter q at any dynamic action prompt to finish the match.")

    for step in range(1, max_steps + 1):
        scene = scenes.get(current_scene_id)
        if not scene:
            print(f"ERROR: scene not found: {current_scene_id}")
            engine.print_match_log(match_log)
            return 1

        scene_type = str(scene.get("scene_type", "dynamic"))
        if scene_type == "dynamic":
            dynamic_count += 1

        print_scene_static_aware(current_scene_id, scene, step, max_steps, dynamic_count, max_dynamic_scenes)

        if scene_type == "static" and pending_next_dynamic_scene_id is not None:
            input("\nPress Enter to continue...")
            next_scene_id = pending_next_dynamic_scene_id
            pending_next_dynamic_scene_id = None
            next_scene = scenes[next_scene_id]
            print("\nStatic transition:")
            print("  Transition: pending_static_bridge")
            print("  Resolver: state_resolver_v2_pending_next_dynamic")
            print(f"  Resolver detail: {pending_resolver_detail}")
            print(f"  New scene: {next_scene_id}")
            print(f"  New ball ownership: {next_scene['owner']}")
            match_log.append({"step": step, "source_scene_id": current_scene_id, "owner_before": scene["owner"], "scene_type": scene_type, "action": STATIC_ACTION, "outcome": STATIC_OUTCOME, "transition_id": "pending_static_bridge", "resolver": "state_resolver_v2_pending_next_dynamic", "next_scene_id": next_scene_id, "owner_after": next_scene["owner"]})
            if should_force_episode_end(next_scene, dynamic_count, max_dynamic_scenes):
                print_forced_episode_end(next_scene_id, next_scene, dynamic_count)
                engine.print_match_log(match_log)
                return 0
            current_scene_id = next_scene_id
            continue

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

        if resolver_mode == "random" or scene_type == "static":
            next_scene_id, resolver, resolver_detail = resolve_next_scene_random(scenes, current_scene_id, transition)
            if not next_scene_id:
                print(f"ERROR: no next scene from {current_scene_id}")
                print(f"Resolver: {resolver}")
                print(f"Resolver detail: {resolver_detail}")
                engine.print_match_log(match_log)
                return 1
        else:
            runtime_static_counter += 1
            next_scene_id, pending_dynamic, resolver, resolver_detail = resolve_state_v2_dynamic_result(scenes, transition, runtime_static_counter)
            if not next_scene_id or not pending_dynamic:
                print_state_gap(current_scene_id, action, outcome, transition, resolver_detail)
                engine.print_match_log(match_log)
                return 1
            pending_next_dynamic_scene_id = pending_dynamic
            pending_resolver_detail = resolver_detail

        next_scene = scenes[next_scene_id]
        if scene_type == "dynamic":
            print("\nAction result:")
            print(f"  Action: {action}")
            print(f"  Outcome: {outcome}")
            print(f"  Transition: {transition.get('transition_id') or '(no transition_id)'}")
            print(f"  Resolver: {resolver}")
            print(f"  Resolver detail: {resolver_detail}")
            print(f"  New scene: {next_scene_id}")
            print(f"  New ball ownership: {next_scene['owner']}")
        else:
            print("\nStatic transition:")
            print(f"  Transition: {transition.get('transition_id') or '(no transition_id)'}")
            print(f"  Resolver: {resolver}")
            print(f"  Resolver detail: {resolver_detail}")
            print(f"  New scene: {next_scene_id}")
            print(f"  New ball ownership: {next_scene['owner']}")

        match_log.append({"step": step, "source_scene_id": current_scene_id, "owner_before": scene["owner"], "scene_type": scene_type, "action": action, "outcome": outcome, "transition_id": transition.get("transition_id", ""), "resolver": resolver, "next_scene_id": next_scene_id, "owner_after": next_scene["owner"]})

        if should_force_episode_end(next_scene, dynamic_count, max_dynamic_scenes):
            print_forced_episode_end(next_scene_id, next_scene, dynamic_count)
            engine.print_match_log(match_log)
            return 0

        current_scene_id = next_scene_id

    print(f"Match finished after reaching max steps: {max_steps}")
    engine.print_match_log(match_log)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PEFL-style interactive episode simulation using canonical repository Excel files.")
    parser.add_argument("--start-scene", default=engine.START_SCENE, help=f"Scene ID to start from. Default: {engine.START_SCENE}")
    parser.add_argument("--max-steps", type=int, default=engine.MAX_STEPS, help=f"Maximum total scene steps. Default: {engine.MAX_STEPS}")
    parser.add_argument("--max-dynamic-scenes", type=int, default=DEFAULT_MAX_DYNAMIC_SCENES, help=f"Maximum dynamic decision scenes per episode. Default: {DEFAULT_MAX_DYNAMIC_SCENES}")
    parser.add_argument("--resolver", choices=["state", "random"], default="state", help="Next-scene resolver mode. state = State Resolver V2 static bridge flow; random = legacy resolver.")
    parser.add_argument("--seed", type=int, default=engine.RANDOM_SEED, help=f"Random seed. Default: {engine.RANDOM_SEED}")
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

    return run_interactive_match_static_aware(scenes=scenes, transitions=transitions, start_scene_id=start_scene, max_steps=args.max_steps, max_dynamic_scenes=args.max_dynamic_scenes, resolver_mode=args.resolver)


if __name__ == "__main__":
    raise SystemExit(main())
