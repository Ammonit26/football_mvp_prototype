from __future__ import annotations

import argparse
import ast
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

# Local Static Pool Resolver:
# dynamic action -> static result scene from transition.allowed_next_scene_ids
# static CONTINUE -> dynamic scene from that static transition.allowed_next_scene_ids
# No global state search. No topology fallback. No runtime static bridge.

SHOT_NARRATIVE_MARKERS = [
    "бьёт",
    "бьет",
    "пробивает",
    "пробил",
    "наносит удар",
    "ударил",
    "добивает",
]

SHOT_TERMINAL_OUTCOMES = [
    {
        "code": "GOAL",
        "label": "Гол",
        "narrative": "Мяч оказывается в сетке. Эпизод завершается голом.",
        "next_owner": "CENTER_RESTART",
    },
    {
        "code": "MISS_GOAL_KICK",
        "label": "Мимо / удар от ворот",
        "narrative": "Удар проходит мимо ворот. Игра будет продолжена ударом от ворот.",
        "next_owner": "OPPONENT_WITH_BALL",
    },
    {
        "code": "KEEPER_HELD",
        "label": "Вратарь фиксирует мяч",
        "narrative": "Вратарь забирает мяч намертво. Атака закончена.",
        "next_owner": "OPPONENT_WITH_BALL",
    },
    {
        "code": "SAVE_CORNER",
        "label": "Сейв / угловой",
        "narrative": "Вратарь отбивает удар за лицевую. Будет угловой.",
        "next_owner": "SET_PIECE_CORNER",
    },
    {
        "code": "SAVE_REBOUND_PLAYER",
        "label": "Сейв / отскок к персонажу",
        "narrative": "Вратарь отбивает перед собой. Ты первым оказываешься на отскоке.",
        "next_owner": "PLAYER_WITH_BALL",
    },
    {
        "code": "SAVE_REBOUND_TEAMMATE",
        "label": "Сейв / отскок к партнёру",
        "narrative": "Вратарь отбивает мяч в сторону. На подборе первым оказывается партнёр.",
        "next_owner": "TEAMMATE_WITH_BALL",
    },
    {
        "code": "SAVE_REBOUND_OPPONENT",
        "label": "Сейв / вынос соперником",
        "narrative": "После сейва защитник первым успевает к мячу и выносит его из опасной зоны.",
        "next_owner": "OPPONENT_WITH_BALL",
    },
    {
        "code": "POST_CORNER",
        "label": "Штанга / угловой",
        "narrative": "Мяч попадает в каркас ворот и уходит за лицевую. Будет угловой.",
        "next_owner": "SET_PIECE_CORNER",
    },
    {
        "code": "POST_REBOUND_PLAYER",
        "label": "Штанга / отскок к персонажу",
        "narrative": "Мяч звенит о штангу и отскакивает в твою зону.",
        "next_owner": "PLAYER_WITH_BALL",
    },
    {
        "code": "POST_REBOUND_TEAMMATE",
        "label": "Штанга / отскок к партнёру",
        "narrative": "Мяч попадает в штангу и отскакивает к партнёру.",
        "next_owner": "TEAMMATE_WITH_BALL",
    },
    {
        "code": "POST_REBOUND_OPPONENT",
        "label": "Штанга / отскок к сопернику",
        "narrative": "Мяч отскакивает от штанги, и соперник первым играет на подборе.",
        "next_owner": "OPPONENT_WITH_BALL",
    },
    {
        "code": "DEFLECTION_GOAL",
        "label": "Рикошет / гол",
        "narrative": "После рикошета мяч меняет траекторию и влетает в ворота.",
        "next_owner": "CENTER_RESTART",
    },
    {
        "code": "DEFLECTION_CORNER",
        "label": "Рикошет / угловой",
        "narrative": "Мяч задевает соперника и уходит за лицевую. Будет угловой.",
        "next_owner": "SET_PIECE_CORNER",
    },
    {
        "code": "DEFLECTION_POST",
        "label": "Рикошет / штанга",
        "narrative": "Рикошет меняет траекторию, мяч попадает в штангу и остаётся в игре.",
        "next_owner": "LOOSE_BALL",
    },
]


def split_scene_pool(raw: object) -> List[str]:
    """Parse scene pools stored as either scene1||scene2 or ['scene1', 'scene2']."""
    if isinstance(raw, (list, tuple, set)):
        return [str(part).strip() for part in raw if str(part).strip()]

    text = str(raw or "").strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, (list, tuple, set)):
            return [str(part).strip() for part in parsed if str(part).strip()]
        if isinstance(parsed, str) and parsed.strip():
            return [parsed.strip()]

    return [part.strip().strip("'\"") for part in text.split("||") if part.strip().strip("'\"")]


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
    return split_scene_pool(next_scene) if next_scene else []


def scene_type_of(scenes: Dict[str, engine.Scene], scene_id: str) -> str:
    scene = scenes.get(scene_id)
    if not scene:
        return "missing"
    return str(scene.get("scene_type", "dynamic"))


def choose_static_bridge_scene(
    scenes: Dict[str, engine.Scene],
    transition: engine.Transition,
) -> Tuple[Optional[str], str, str]:
    pool = transition_scene_pool(transition)
    if not pool:
        return None, "STATE_GAP", "dynamic transition has empty next-scene pool"

    missing = [scene_id for scene_id in pool if scene_id not in scenes]
    static_candidates = [
        scene_id
        for scene_id in pool
        if scene_id in scenes and scene_type_of(scenes, scene_id) == "static"
    ]

    if not static_candidates:
        pool_types = ", ".join(f"{scene_id}:{scene_type_of(scenes, scene_id)}" for scene_id in pool)
        detail = f"dynamic transition did not provide static bridge; pool=[{pool_types}]"
        if missing:
            detail += f"; missing={missing}"
        return None, "STATE_GAP", detail

    chosen = random.choice(sorted(static_candidates))
    detail = f"static_candidates={len(static_candidates)}; local_pool_size={len(pool)}"
    if missing:
        detail += f"; missing={missing}"
    return chosen, "local_static_bridge", detail


def choose_dynamic_from_static_continue(
    scenes: Dict[str, engine.Scene],
    transition: engine.Transition,
) -> Tuple[Optional[str], str, str]:
    pool = transition_scene_pool(transition)
    if not pool:
        return None, "STATE_GAP", "static CONTINUE transition has empty next-scene pool"

    missing = [scene_id for scene_id in pool if scene_id not in scenes]
    dynamic_candidates = [
        scene_id
        for scene_id in pool
        if scene_id in scenes and scene_type_of(scenes, scene_id) == "dynamic"
    ]

    if not dynamic_candidates:
        pool_types = ", ".join(f"{scene_id}:{scene_type_of(scenes, scene_id)}" for scene_id in pool)
        detail = f"static CONTINUE transition did not provide dynamic target; pool=[{pool_types}]"
        if missing:
            detail += f"; missing={missing}"
        return None, "STATE_GAP", detail

    chosen = random.choice(sorted(dynamic_candidates))
    detail = f"dynamic_candidates={len(dynamic_candidates)}; local_pool_size={len(pool)}"
    if missing:
        detail += f"; missing={missing}"
    return chosen, "local_static_continue_pool", detail


def resolve_next_scene_random(
    scenes: Dict[str, engine.Scene],
    current_scene_id: str,
    transition: engine.Transition,
) -> Tuple[str, str, str]:
    next_scene_id, resolver = engine.resolve_next_scene(scenes, current_scene_id, transition)
    return next_scene_id, resolver, "legacy random/allowed_next_scene_ids resolver"


def is_shot_static_scene(scene: engine.Scene) -> bool:
    if str(scene.get("scene_type", "dynamic")) != "static":
        return False
    narrative = str(scene.get("narrative") or "").lower().replace("ё", "е")
    markers = [marker.replace("ё", "е") for marker in SHOT_NARRATIVE_MARKERS]
    return any(marker in narrative for marker in markers)


def resolve_shot_terminal_outcome() -> Dict[str, str]:
    return random.choice(SHOT_TERMINAL_OUTCOMES)


def print_shot_terminal_event(current_scene_id: str, outcome: Dict[str, str]) -> None:
    print("\n" + "=" * 72)
    print("Shot terminal outcome")
    print(f"Source static scene: {current_scene_id}")
    print(f"Outcome: {outcome['code']} — {outcome['label']}")
    print("\nScene:")
    print(f"  {outcome['narrative']}")
    print("\nEpisode end: shot outcome")
    print(f"Next phase owner/context: {outcome['next_owner']}")
    if outcome["code"] in {"GOAL", "DEFLECTION_GOAL"}:
        print("Match event: GOAL. Score update layer is not implemented yet.")
    print("=" * 72)


def print_scene_static_aware(
    scene_id: str,
    scene: engine.Scene,
    step: int,
    max_steps: int,
    dynamic_count: int,
    max_dynamic_scenes: int,
) -> None:
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


def print_state_gap(
    current_scene_id: str,
    action: str,
    outcome: str,
    transition: engine.Transition,
    detail: str,
) -> None:
    print("\n" + "=" * 72)
    print("STATE_GAP: local static pool resolver could not continue episode")
    print(f"Source scene: {current_scene_id}")
    print(f"Action: {action}")
    print(f"Outcome: {outcome}")
    print(f"Transition: {transition.get('transition_id') or '(no transition_id)'}")
    print(f"Transition pool: {transition_scene_pool(transition)}")
    print(f"Detail: {detail}")
    print("Episode stopped for diagnosis.")
    print("=" * 72)


def choose_random_start_scene(scenes: Dict[str, engine.Scene]) -> str:
    candidates = [
        scene_id
        for scene_id, scene in scenes.items()
        if str(scene.get("scene_type", "dynamic")) == "dynamic" and scene.get("available_player_actions")
    ]
    if not candidates:
        raise ValueError("No dynamic start-scene candidates with available actions")
    return random.choice(sorted(candidates))


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

    if resolver_mode == "state":
        resolver_mode = "local"
        print("WARNING: --resolver state is deprecated; using --resolver local.")

    print("\nInteractive player mode")
    print("PEFL-style event flow: dynamic decision -> static consequence -> dynamic continuation.")
    print("You make decisions only in dynamic scenes. Static scenes show match events.")
    print(f"Episode dynamic-scene limit: {max_dynamic_scenes}")
    print(f"Next-scene resolver: {resolver_mode}")
    print(f"Start scene: {start_scene_id}")
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

        if scene_type == "static":
            input("\nPress Enter to continue...")
            if resolver_mode != "random" and is_shot_static_scene(scene):
                terminal = resolve_shot_terminal_outcome()
                print_shot_terminal_event(current_scene_id, terminal)
                match_log.append(
                    {
                        "step": step,
                        "source_scene_id": current_scene_id,
                        "owner_before": scene["owner"],
                        "scene_type": scene_type,
                        "action": "SHOT_TERMINAL",
                        "outcome": terminal["code"],
                        "transition_id": "shot_terminal_resolver",
                        "resolver": "shot_terminal_resolver",
                        "next_scene_id": "",
                        "owner_after": terminal["next_owner"],
                    }
                )
                engine.print_match_log(match_log)
                return 0
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

        if resolver_mode == "random":
            next_scene_id, resolver, resolver_detail = resolve_next_scene_random(scenes, current_scene_id, transition)
            if not next_scene_id:
                print(f"ERROR: no next scene from {current_scene_id}")
                print(f"Resolver: {resolver}")
                print(f"Resolver detail: {resolver_detail}")
                engine.print_match_log(match_log)
                return 1
        elif scene_type == "dynamic":
            next_scene_id, resolver, resolver_detail = choose_static_bridge_scene(scenes, transition)
            if not next_scene_id:
                print_state_gap(current_scene_id, action, outcome, transition, resolver_detail)
                engine.print_match_log(match_log)
                return 1
        else:
            next_scene_id, resolver, resolver_detail = choose_dynamic_from_static_continue(scenes, transition)
            if not next_scene_id:
                print_state_gap(current_scene_id, action, outcome, transition, resolver_detail)
                engine.print_match_log(match_log)
                return 1

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

        match_log.append(
            {
                "step": step,
                "source_scene_id": current_scene_id,
                "owner_before": scene["owner"],
                "scene_type": scene_type,
                "action": action,
                "outcome": outcome,
                "transition_id": transition.get("transition_id", ""),
                "resolver": resolver,
                "next_scene_id": next_scene_id,
                "owner_after": next_scene["owner"],
            }
        )

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
    parser.add_argument("--random-start", action="store_true", help="Start from a random dynamic scene with available actions.")
    parser.add_argument("--max-steps", type=int, default=engine.MAX_STEPS, help=f"Maximum total scene steps. Default: {engine.MAX_STEPS}")
    parser.add_argument("--max-dynamic-scenes", type=int, default=DEFAULT_MAX_DYNAMIC_SCENES, help=f"Maximum dynamic decision scenes per episode. Default: {DEFAULT_MAX_DYNAMIC_SCENES}")
    parser.add_argument("--resolver", choices=["local", "state", "random"], default="local", help="Next-scene resolver mode. local = dynamic->static->local static pool; state = deprecated alias for local; random = legacy resolver.")
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

    if args.random_start:
        start_scene = choose_random_start_scene(scenes)
    else:
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
        max_dynamic_scenes=args.max_dynamic_scenes,
        resolver_mode=args.resolver,
    )


if __name__ == "__main__":
    raise SystemExit(main())
