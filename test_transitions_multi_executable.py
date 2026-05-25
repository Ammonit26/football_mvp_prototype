from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


# ------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------
N_RUNS = 20
MAX_STEPS = 50
RANDOM_SEED = 42
START_SCENE = "fb_player_0002"
REPORT_PATH = Path("verification_report_executable.md")

if RANDOM_SEED is not None:
    random.seed(RANDOM_SEED)


SCENE_LIBRARIES = [
    {
        "file": "ball_at_player_normalized_prototype_v7.xlsx",
        "sheet": "normalized_player_scenes",
        "owner": "PLAYER_WITH_BALL",
    },
    {
        "file": "ball_at_teammate_normalized_prototype_v1.xlsx",
        "sheet": "normalized_teammate_scenes",
        "owner": "TEAMMATE_WITH_BALL",
    },
    {
        "file": "ball_at_opponent_normalized_prototype_v2.xlsx",
        "sheet": "normalized_opponent_scenes",
        "owner": "OPPONENT_WITH_BALL",
    },
]

TRANSITION_LIBRARIES = [
    {
        "file": "transitions_player_complete_graph_v2_executable.xlsx",
        "sheet": 0,
        "name": "player",
    },
    {
        "file": "transitions_teammate_complete_graph_v4_executable.xlsx",
        "sheet": 0,
        "name": "teammate",
    },
    {
        "file": "transitions_opponent_complete_graph_v1_executable.xlsx",
        "sheet": 0,
        "name": "opponent",
    },
]

OUTCOMES = {"SUCCESS", "FAIL"}
MAX_POOL_SIZE = 4
MAX_POOL_TIER_SPREAD = 1

OWN_ATTACK_TIER = {
    "перед своей штрафной": 0,
    "в своей штрафной": 0,
    "на левом фланге на своей половине": 0,
    "на правом фланге на своей половине": 0,
    "в центре поля": 1,
    "на левом фланге в центре поля": 1,
    "на правом фланге в центре поля": 1,
    "перед чужой штрафной": 2,
    "на углу чужой штрафной": 3,
    "на фланге у чужой штрафной": 3,
    "внутри чужой штрафной": 4,
}

OPPONENT_DANGER_TIER = {
    "в своей штрафной": 0,
    "перед своей штрафной": 1,
    "на фланге возле своей штрафной": 1,
    "в центре поля": 2,
    "на фланге в центре поля": 2,
    "перед нашей штрафной": 3,
    "на фланге у нашей штрафной": 3,
    "в нашей штрафной": 4,
}

PLAYER_PASS_SUCCESS_ACTIONS = {
    "отдать пас назад",
    "Отдать пас вперед",
    "Отдать пас на фланг",
    "сыграть через центр",
    "Забросить мяч на ход на фланг",
    "Навесить в штрафную",
    "Пас под удар",
    "вынести мяч далеко вперед",
}

PLAYER_RETAIN_SUCCESS_ACTIONS = {
    "Вести мяч вперед",
    "Пройти соперника дриблингом",
    "Развернуться и пытаться тащить мяч самому",
    "Ударить по воротам",
    "придержать мяч, ожидая открываний",
}

OPPONENT_REGAIN_SUCCESS_ACTIONS = {
    "остаться в зоне, мяч может вернуться",
    "отобрать мяч любой ценой",
    "постараться чисто отобрать мяч",
    "рывок вперед, постараться накрыть чисто",
    "свалить его, тактический фол!",
    "сместиться на перехват мяча",
    "оттянуться назад, занять позицию ниже",
}


Scene = Dict[str, object]
Transition = Dict[str, object]
TransitionKey = Tuple[str, str, str]


def safe_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def split_actions(raw: object) -> List[str]:
    return [part.strip() for part in safe_str(raw).split("||") if part.strip()]


def split_scene_pool(raw: object) -> List[str]:
    return [part.strip() for part in safe_str(raw).split("||") if part.strip()]


def scene_tier(owner: str, player_position: str, ball_holder_position: str) -> int:
    if owner == "OPPONENT_WITH_BALL":
        return OPPONENT_DANGER_TIER.get(ball_holder_position, 2)
    if owner == "TEAMMATE_WITH_BALL":
        return OWN_ATTACK_TIER.get(ball_holder_position, 1)
    return OWN_ATTACK_TIER.get(player_position, 1)


def expected_ball_owner_after(source_owner: str, action: str, outcome: str) -> Optional[str]:
    if source_owner == "PLAYER_WITH_BALL":
        if outcome == "FAIL":
            return "OPPONENT_WITH_BALL"
        if action in PLAYER_PASS_SUCCESS_ACTIONS:
            return "TEAMMATE_WITH_BALL"
        if action in PLAYER_RETAIN_SUCCESS_ACTIONS:
            return "PLAYER_WITH_BALL"
    if source_owner == "TEAMMATE_WITH_BALL":
        if outcome == "FAIL":
            return "OPPONENT_WITH_BALL"
        if action == "отдать пас назад":
            return "PLAYER_WITH_BALL"
        return "TEAMMATE_WITH_BALL"
    if source_owner == "OPPONENT_WITH_BALL":
        if outcome == "FAIL":
            return "OPPONENT_WITH_BALL"
        if action in OPPONENT_REGAIN_SUCCESS_ACTIONS:
            return "PLAYER_WITH_BALL"
    return None


def find_column(df: pd.DataFrame, possible_names: Iterable[str]) -> Optional[str]:
    cols_lower = {str(col).strip().lower(): col for col in df.columns}
    for name in possible_names:
        if name.lower() in cols_lower:
            return cols_lower[name.lower()]
    return None


def read_excel(file_name: str, sheet_name: object) -> pd.DataFrame:
    return pd.read_excel(file_name, sheet_name=sheet_name, dtype=str, keep_default_na=False)


def load_scenes() -> Dict[str, Scene]:
    print("Loading scene libraries...")
    scenes: Dict[str, Scene] = {}
    duplicates: List[str] = []

    for config in SCENE_LIBRARIES:
        df = read_excel(config["file"], config["sheet"])
        for _, row in df.iterrows():
            scene_id = safe_str(row.get("scene_id"))
            if not scene_id:
                continue
            if scene_id in scenes:
                duplicates.append(scene_id)
            owner = safe_str(row.get("scene_owner")) or config["owner"]
            player_position = safe_str(row.get("player_position"))
            ball_holder_position = safe_str(row.get("ball_holder_position"))
            scenes[scene_id] = {
                "owner": owner,
                "player_position": player_position,
                "player_direction": safe_str(row.get("player_direction")),
                "ball_holder_position": ball_holder_position,
                "ball_holder_direction": safe_str(row.get("ball_holder_direction")),
                "ball_holder_action": safe_str(row.get("ball_holder_action")),
                "available_player_actions": split_actions(row.get("available_player_actions")),
                "narrative": safe_str(row.get("narrative_scene")),
                "library_file": config["file"],
                "tier": scene_tier(owner, player_position, ball_holder_position),
            }

    if duplicates:
        print(f"WARNING: duplicate scene IDs remain: {duplicates[:10]}")
    print(f"Loaded scenes: {len(scenes)}")
    return scenes


def load_transitions() -> Tuple[Dict[TransitionKey, List[Transition]], List[Transition]]:
    print("Loading transition libraries...")
    transitions: Dict[TransitionKey, List[Transition]] = defaultdict(list)
    transition_rows: List[Transition] = []

    for config in TRANSITION_LIBRARIES:
        df = read_excel(config["file"], config["sheet"])
        print(f"  {config['file']}: {len(df)} rows")

        src_col = find_column(df, ["source_scene_id", "source_scene", "from_scene", "scene_id"])
        action_col = find_column(df, ["player_action", "action", "teammate_action"])
        outcome_col = find_column(df, ["player_action_outcome", "teammate_action_outcome", "outcome"])
        owner_col = find_column(df, ["ball_owner_after", "ball_owner"])
        next_col = find_column(df, ["next_scene_id", "target_scene_id"])
        allowed_pool_col = find_column(df, ["allowed_next_scene_ids"])
        player_pos_after_col = find_column(df, ["player_position_after"])
        player_dir_after_col = find_column(df, ["player_direction_after"])
        ball_holder_pos_after_col = find_column(df, ["ball_holder_position_after"])
        ball_holder_dir_after_col = find_column(df, ["ball_holder_direction_after"])
        transition_id_col = find_column(df, ["transition_id"])

        required = {
            "source_scene_id": src_col,
            "player_action/action": action_col,
            "outcome": outcome_col,
            "ball_owner_after": owner_col,
        }
        missing = [name for name, column in required.items() if column is None]
        if missing:
            print(f"  WARNING: skipped {config['file']} because columns are missing: {missing}")
            continue

        for _, row in df.iterrows():
            source = safe_str(row[src_col])
            action = safe_str(row[action_col])
            outcome = safe_str(row[outcome_col]).upper()
            trans_info: Transition = {
                "transition_id": safe_str(row[transition_id_col]) if transition_id_col else "",
                "library_file": config["file"],
                "source_scene_id": source,
                "player_action": action,
                "outcome": outcome,
                "ball_owner_after": safe_str(row[owner_col]) if owner_col else "",
                "player_position_after": safe_str(row[player_pos_after_col]) if player_pos_after_col else "",
                "player_direction_after": safe_str(row[player_dir_after_col]) if player_dir_after_col else "",
                "ball_holder_position_after": safe_str(row[ball_holder_pos_after_col]) if ball_holder_pos_after_col else "",
                "ball_holder_direction_after": safe_str(row[ball_holder_dir_after_col]) if ball_holder_dir_after_col else "",
                "next_scene_id": safe_str(row[next_col]) if next_col else "",
                "allowed_next_scene_ids": split_scene_pool(row[allowed_pool_col]) if allowed_pool_col else [],
            }
            transitions[(source, action, outcome)].append(trans_info)
            transition_rows.append(trans_info)

    print(f"Loaded transition rows: {len(transition_rows)}")
    print(f"Loaded transition keys: {len(transitions)}")
    return transitions, transition_rows


def find_next_scene_by_topology(
    scenes: Dict[str, Scene],
    ball_owner: str,
    player_pos: str,
    player_dir: str,
    ball_holder_pos: str,
    ball_holder_dir: str,
    exclude_id: Optional[str] = None,
) -> Optional[str]:
    candidates = []
    for scene_id, scene in scenes.items():
        if scene["owner"] != ball_owner:
            continue
        if scene["player_position"] != player_pos:
            continue
        if player_dir and scene["player_direction"] != player_dir:
            continue
        if ball_owner != "PLAYER_WITH_BALL":
            if ball_holder_pos and scene["ball_holder_position"] != ball_holder_pos:
                continue
            if ball_holder_dir and scene["ball_holder_direction"] != ball_holder_dir:
                continue
        if exclude_id and scene_id == exclude_id:
            continue
        candidates.append(scene_id)
    return random.choice(candidates) if candidates else None


def resolve_next_scene(
    scenes: Dict[str, Scene],
    current_scene_id: str,
    transition: Transition,
) -> Tuple[Optional[str], str]:
    pool = [
        scene_id
        for scene_id in transition.get("allowed_next_scene_ids", [])
        if isinstance(scene_id, str) and scene_id in scenes
    ]
    if not pool:
        return None, "empty_allowed_next_scene_ids"
    return random.choice(pool), "allowed_next_scene_ids"


def build_adjacency(
    scenes: Dict[str, Scene],
    transition_rows: List[Transition],
) -> Dict[str, Set[str]]:
    adjacency: Dict[str, Set[str]] = {scene_id: set() for scene_id in scenes}
    for row in transition_rows:
        source = row["source_scene_id"]
        for target in row.get("allowed_next_scene_ids", []):
            if source in scenes and target in scenes:
                adjacency[source].add(target)
    return adjacency


def reachable_from(start: str, adjacency: Dict[str, Set[str]]) -> Set[str]:
    if start not in adjacency:
        return set()
    seen = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in adjacency[current]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def weak_components(adjacency: Dict[str, Set[str]]) -> List[Set[str]]:
    undirected: Dict[str, Set[str]] = {node: set(edges) for node, edges in adjacency.items()}
    for source, targets in adjacency.items():
        for target in targets:
            undirected.setdefault(target, set()).add(source)
    components: List[Set[str]] = []
    remaining = set(undirected)
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor in undirected[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def verify_graph(
    scenes: Dict[str, Scene],
    transitions: Dict[TransitionKey, List[Transition]],
    transition_rows: List[Transition],
    start_scene: str,
) -> Dict[str, object]:
    scene_ids = set(scenes)
    missing_transitions = []
    scenes_without_actions = []

    for scene_id, scene in scenes.items():
        actions = scene["available_player_actions"]
        if not actions:
            scenes_without_actions.append(scene_id)
            continue
        for action in actions:
            for outcome in sorted(OUTCOMES):
                if not transitions.get((scene_id, action, outcome)):
                    missing_transitions.append((scene_id, action, outcome))

    broken_sources = [
        (row["transition_id"], row["source_scene_id"])
        for row in transition_rows
        if row["source_scene_id"] not in scene_ids
    ]
    broken_next_links = [
        (row["transition_id"], row["source_scene_id"], row.get("next_scene_id", ""))
        for row in transition_rows
        if row.get("next_scene_id", "") not in scene_ids
    ]
    empty_pools = [
        (row["transition_id"], row["source_scene_id"])
        for row in transition_rows
        if not row.get("allowed_next_scene_ids", [])
    ]
    broken_pool_links = [
        (row["transition_id"], row["source_scene_id"], scene_id)
        for row in transition_rows
        for scene_id in row.get("allowed_next_scene_ids", [])
        if scene_id not in scene_ids
    ]
    pool_ownership_contradictions = [
        (
            row["transition_id"],
            row["source_scene_id"],
            scene_id,
            row["ball_owner_after"],
            scenes[scene_id]["owner"],
        )
        for row in transition_rows
        for scene_id in row.get("allowed_next_scene_ids", [])
        if scene_id in scenes and scenes[scene_id]["owner"] != row["ball_owner_after"]
    ]
    expected_ownership_violations = []
    for row in transition_rows:
        source_id = row["source_scene_id"]
        if source_id not in scenes:
            continue
        expected_owner = expected_ball_owner_after(
            str(scenes[source_id]["owner"]),
            str(row["player_action"]),
            str(row["outcome"]),
        )
        if expected_owner and row["ball_owner_after"] != expected_owner:
            expected_ownership_violations.append(
                (
                    row["transition_id"],
                    source_id,
                    row["player_action"],
                    row["outcome"],
                    row["ball_owner_after"],
                    expected_owner,
                )
            )
    excessive_pool_spread = []
    for row in transition_rows:
        pool = [scene_id for scene_id in row.get("allowed_next_scene_ids", []) if scene_id in scenes]
        if not pool:
            continue
        tiers = [int(scenes[scene_id]["tier"]) for scene_id in pool]
        tier_spread = max(tiers) - min(tiers)
        if len(pool) > MAX_POOL_SIZE or tier_spread > MAX_POOL_TIER_SPREAD:
            excessive_pool_spread.append(
                (row["transition_id"], row["source_scene_id"], len(pool), tier_spread, pool)
            )
    invalid_outcomes = [
        (row["transition_id"], row["source_scene_id"], row["outcome"])
        for row in transition_rows
        if row["outcome"] not in OUTCOMES
    ]
    actions_not_in_scene = [
        (row["transition_id"], row["source_scene_id"], row["player_action"])
        for row in transition_rows
        if row["source_scene_id"] in scenes
        and row["player_action"] not in scenes[row["source_scene_id"]]["available_player_actions"]
    ]

    incoming = defaultdict(int)
    outgoing = defaultdict(int)
    for row in transition_rows:
        source = row["source_scene_id"]
        if source in scene_ids:
            outgoing[source] += 1
        for target in row.get("allowed_next_scene_ids", []):
            if target in scene_ids:
                incoming[target] += 1

    orphan_scenes = sorted(scene_id for scene_id in scene_ids if incoming[scene_id] == 0 and scene_id != start_scene)
    dead_end_scenes = sorted(
        scene_id
        for scene_id, scene in scenes.items()
        if not scene["available_player_actions"] or outgoing[scene_id] == 0
    )
    dead_end_pools = [
        (row["transition_id"], row["source_scene_id"], scene_id)
        for row in transition_rows
        for scene_id in row.get("allowed_next_scene_ids", [])
        if scene_id in scenes
        and (
            not scenes[scene_id]["available_player_actions"]
            or outgoing[scene_id] == 0
        )
    ]

    adjacency = build_adjacency(scenes, transition_rows)
    reachable = reachable_from(start_scene, adjacency)
    disconnected_from_start = sorted(scene_ids - reachable)
    components = weak_components(adjacency)

    return {
        "scene_count": len(scenes),
        "transition_row_count": len(transition_rows),
        "transition_key_count": len(transitions),
        "missing_transitions": missing_transitions,
        "broken_sources": broken_sources,
        "broken_next_links": broken_next_links,
        "empty_pools": empty_pools,
        "broken_pool_links": broken_pool_links,
        "pool_ownership_contradictions": pool_ownership_contradictions,
        "expected_ownership_violations": expected_ownership_violations,
        "excessive_pool_spread": excessive_pool_spread,
        "invalid_outcomes": invalid_outcomes,
        "actions_not_in_scene": actions_not_in_scene,
        "scenes_without_actions": scenes_without_actions,
        "orphan_scenes": orphan_scenes,
        "dead_end_scenes": dead_end_scenes,
        "dead_end_pools": dead_end_pools,
        "disconnected_from_start": disconnected_from_start,
        "weak_component_count": len(components),
        "weak_component_sizes": sorted((len(component) for component in components), reverse=True),
    }


def run_single_simulation(
    scenes: Dict[str, Scene],
    transitions: Dict[TransitionKey, List[Transition]],
    start_scene_id: str,
    max_steps: int = MAX_STEPS,
) -> Tuple[int, bool, str, int]:
    current_scene_id = start_scene_id
    fallback_count = 0

    for step in range(max_steps):
        scene = scenes.get(current_scene_id)
        if not scene:
            return step, False, f"scene not found: {current_scene_id}", fallback_count
        actions = [
            action
            for action in scene["available_player_actions"]
            if transitions.get((current_scene_id, action, "SUCCESS"))
            and transitions.get((current_scene_id, action, "FAIL"))
        ]
        if not actions:
            return step, False, f"no executable actions at {current_scene_id}", fallback_count

        action = random.choice(actions)
        outcome = random.choice(["SUCCESS", "FAIL"])
        transition = random.choice(transitions[(current_scene_id, action, outcome)])
        next_scene_id, resolver = resolve_next_scene(scenes, current_scene_id, transition)
        if resolver != "allowed_next_scene_ids":
            fallback_count += 1
        if not next_scene_id:
            return step, False, f"no next scene from {current_scene_id}", fallback_count
        current_scene_id = next_scene_id

    return max_steps, True, "ok", fallback_count


def run_simulations(
    scenes: Dict[str, Scene],
    transitions: Dict[TransitionKey, List[Transition]],
    start_scene: str,
    max_steps: int = MAX_STEPS,
) -> Dict[str, object]:
    results = [
        run_single_simulation(scenes, transitions, start_scene, max_steps)
        for _ in range(N_RUNS)
    ]
    successful_runs = sum(1 for _, ok, _, _ in results if ok)
    avg_steps = sum(steps for steps, _, _, _ in results) / len(results)
    fallback_count = sum(fallbacks for _, _, _, fallbacks in results)
    failures = [(steps, reason) for steps, ok, reason, _ in results if not ok]
    return {
        "runs": len(results),
        "successful_runs": successful_runs,
        "avg_steps": avg_steps,
        "fallback_count": fallback_count,
        "failures": failures,
    }


def choose_player_action(actions: List[str]) -> Optional[str]:
    while True:
        choice = input("Choose action number, or q to finish match: ").strip().lower()
        if choice in {"q", "quit", "exit", "end"}:
            return None
        if choice.isdigit():
            action_index = int(choice) - 1
            if 0 <= action_index < len(actions):
                return actions[action_index]
        print(f"Please enter a number from 1 to {len(actions)}, or q.")


def print_scene(scene_id: str, scene: Scene, step: int, max_steps: int) -> None:
    print("\n" + "=" * 72)
    print(f"Step: {step}/{max_steps}")
    print(f"Scene ID: {scene_id}")
    print(f"Ball ownership: {scene['owner']}")
    print("\nScene:")
    print(f"  {scene.get('narrative') or '(no narrative_scene)'}")
    print("\nAvailable player actions:")
    for index, action in enumerate(scene["available_player_actions"], start=1):
        print(f"  {index}. {action}")
    print("=" * 72)


def print_match_log(match_log: List[Dict[str, object]]) -> None:
    print("\n=== Match log ===")
    if not match_log:
        print("No actions played.")
        return
    for entry in match_log:
        print(
            f"{entry['step']:02d}. {entry['source_scene_id']} "
            f"[{entry['owner_before']}] -- {entry['action']} => {entry['outcome']} "
            f"-> {entry['next_scene_id']} [{entry['owner_after']}]"
        )


def run_interactive_match(
    scenes: Dict[str, Scene],
    transitions: Dict[TransitionKey, List[Transition]],
    start_scene_id: str,
    max_steps: int,
) -> int:
    current_scene_id = start_scene_id
    match_log: List[Dict[str, object]] = []

    print("\nInteractive player mode")
    print("You make decisions for the player. Outcome is randomly SUCCESS or FAIL.")
    print("Enter q at any action prompt to finish the match.")

    for step in range(1, max_steps + 1):
        scene = scenes.get(current_scene_id)
        if not scene:
            print(f"ERROR: scene not found: {current_scene_id}")
            print_match_log(match_log)
            return 1

        actions = scene["available_player_actions"]
        if not actions:
            print(f"Match stopped: scene has no available actions: {current_scene_id}")
            print_match_log(match_log)
            return 1

        print_scene(current_scene_id, scene, step, max_steps)
        action = choose_player_action(actions)
        if action is None:
            print("Match finished by player.")
            print_match_log(match_log)
            return 0

        outcome = random.choice(["SUCCESS", "FAIL"])
        key = (current_scene_id, action, outcome)
        transition_options = transitions.get(key, [])
        if not transition_options:
            print(f"ERROR: no transition for {key}")
            print_match_log(match_log)
            return 1

        transition = random.choice(transition_options)
        next_scene_id, resolver = resolve_next_scene(scenes, current_scene_id, transition)
        if not next_scene_id:
            print(f"ERROR: no next scene from {current_scene_id}")
            print_match_log(match_log)
            return 1

        next_scene = scenes[next_scene_id]
        print("\nAction result:")
        print(f"  Action: {action}")
        print(f"  Outcome: {outcome}")
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
    print_match_log(match_log)
    return 0


def build_example_chains(
    scenes: Dict[str, Scene],
    transitions: Dict[TransitionKey, List[Transition]],
) -> List[Dict[str, object]]:
    requests = [
        (
            "fb_player_0007",
            "Отдать пас на фланг",
            "SUCCESS",
            "successful flank pass: ball ownership transfers to teammate, then the next scene is selected only from TEAMMATE_WITH_BALL pool",
        ),
        (
            "fb_player_0002",
            "Пройти соперника дриблингом",
            "SUCCESS",
            "successful dribble forward: retained ball and moved from defensive third into a more advanced possession state",
        ),
        (
            "fb_player_0002",
            "отдать пас назад",
            "SUCCESS",
            "successful pass backward: ball moves to teammate for a safer deep buildup reset",
        ),
        (
            "fb_player_0002",
            "Пройти соперника дриблингом",
            "FAIL",
            "failed dribble near own box: immediate dangerous turnover / opponent pressure near our goal",
        ),
        (
            "fb_opp_0001",
            "рывок вперед, постараться накрыть чисто",
            "SUCCESS",
            "successful defensive pressure high up: regain near opponent goal with attacking initiative",
        ),
        (
            "fb_opp_0001",
            "остаться в зоне, мяч может вернуться",
            "FAIL",
            "failed defensive pressure: opponent escapes first line and progresses one danger band",
        ),
        (
            "fb_teamm_0001",
            "открыться навстречу под пас",
            "SUCCESS",
            "supporting run while teammate has ball: possession remains with teammate in nearby buildup states",
        ),
    ]
    rng = random.Random(2026)
    examples = []
    for source_id, action, outcome, explanation in requests:
        options = transitions.get((source_id, action, outcome), [])
        if not options or source_id not in scenes:
            continue
        transition = options[0]
        pool = list(transition.get("allowed_next_scene_ids", []))
        valid_pool = [scene_id for scene_id in pool if scene_id in scenes]
        if not valid_pool:
            continue
        selected = rng.choice(valid_pool)
        examples.append(
            {
                "source_scene_id": source_id,
                "source_owner": scenes[source_id]["owner"],
                "source_tier": scenes[source_id]["tier"],
                "action": action,
                "outcome": outcome,
                "selected_next_scene": selected,
                "selected_owner": scenes[selected]["owner"],
                "selected_tier": scenes[selected]["tier"],
                "pool": valid_pool,
                "explanation": explanation,
            }
        )
    return examples


def sample(items: List[object], limit: int = 10) -> str:
    if not items:
        return "none"
    lines = [f"  - {item}" for item in items[:limit]]
    if len(items) > limit:
        lines.append(f"  - ... {len(items) - limit} more")
    return "\n".join(lines)


def write_report(
    verification: Dict[str, object],
    simulations: Dict[str, object],
    examples: List[Dict[str, object]],
    start_scene: str,
    max_steps: int,
) -> None:
    blockers = [
        "missing_transitions",
        "broken_sources",
        "broken_next_links",
        "empty_pools",
        "broken_pool_links",
        "pool_ownership_contradictions",
        "expected_ownership_violations",
        "excessive_pool_spread",
        "invalid_outcomes",
        "actions_not_in_scene",
        "scenes_without_actions",
        "orphan_scenes",
        "dead_end_scenes",
        "dead_end_pools",
        "disconnected_from_start",
    ]
    passed = all(not verification[name] for name in blockers) and verification["weak_component_count"] == 1
    passed = passed and simulations["successful_runs"] == simulations["runs"]
    passed = passed and simulations["fallback_count"] == 0

    lines = [
        "# Football Match Generator Verification Report",
        "",
        f"Status: {'PASS' if passed else 'FAIL'}",
        "",
        "## Scope",
        "",
        "- Source of truth: 3 canonical scene libraries, 3 executable transition libraries, test_transitions_multi_executable.py",
        f"- Start scene: {start_scene}",
        f"- Simulation runs: {N_RUNS}",
        f"- Max steps per run: {max_steps}",
        "",
        "## Counts",
        "",
        f"- Scenes: {verification['scene_count']}",
        f"- Transition rows: {verification['transition_row_count']}",
        f"- Transition keys: {verification['transition_key_count']}",
        f"- Max pool size allowed: {MAX_POOL_SIZE}",
        f"- Max pool tier spread allowed: {MAX_POOL_TIER_SPREAD}",
        "",
        "## Verification",
        "",
        f"- Missing transitions: {len(verification['missing_transitions'])}",
        f"- Broken source links: {len(verification['broken_sources'])}",
        f"- Broken next_scene_id links: {len(verification['broken_next_links'])}",
        f"- Empty allowed_next_scene_ids pools: {len(verification['empty_pools'])}",
        f"- Broken pool links: {len(verification['broken_pool_links'])}",
        f"- Pool ownership contradictions: {len(verification['pool_ownership_contradictions'])}",
        f"- Expected ownership semantic violations: {len(verification['expected_ownership_violations'])}",
        f"- Excessive semantic spread inside pools: {len(verification['excessive_pool_spread'])}",
        f"- Invalid outcomes: {len(verification['invalid_outcomes'])}",
        f"- Actions not present in source scene: {len(verification['actions_not_in_scene'])}",
        f"- Scenes without actions: {len(verification['scenes_without_actions'])}",
        f"- Orphan scenes: {len(verification['orphan_scenes'])}",
        f"- Dead-end scenes: {len(verification['dead_end_scenes'])}",
        f"- Dead-end pools: {len(verification['dead_end_pools'])}",
        f"- Disconnected scenes from start: {len(verification['disconnected_from_start'])}",
        f"- Weak connected graph parts: {verification['weak_component_count']}",
        f"- Weak component sizes: {verification['weak_component_sizes']}",
        "",
        "## Simulation",
        "",
        f"- Successful runs: {simulations['successful_runs']} / {simulations['runs']}",
        f"- Average executed steps: {simulations['avg_steps']:.2f}",
        f"- Non-pool resolver uses: {simulations['fallback_count']}",
    ]

    if examples:
        lines += ["", "## Example Chains", ""]
        for example in examples:
            lines += [
                (
                    f"- {example['source_scene_id']} [{example['source_owner']}, tier {example['source_tier']}]"
                    f" -> {example['action']} -> {example['outcome']}"
                    f" -> selected {example['selected_next_scene']} [{example['selected_owner']}, tier {example['selected_tier']}]"
                ),
                f"  Pool: {'||'.join(example['pool'])}",
                f"  Semantic continuity: {example['explanation']}",
            ]

    if simulations["failures"]:
        lines += ["", "## Simulation Failures", "", sample(simulations["failures"])]

    for key in blockers:
        values = verification[key]
        if values:
            lines += ["", f"## Sample: {key}", "", sample(values)]

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executable football match generator prototype."
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Run playable console mode where the player chooses actions.",
    )
    parser.add_argument(
        "--start-scene",
        default=START_SCENE,
        help=f"Scene ID to start from. Default: {START_SCENE}",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=MAX_STEPS,
        help=f"Maximum steps for simulation or interactive match. Default: {MAX_STEPS}",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=RANDOM_SEED,
        help=f"Random seed for reproducible outcomes. Default: {RANDOM_SEED}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    scenes = load_scenes()
    start_scene = args.start_scene if args.start_scene in scenes else sorted(scenes)[0]
    if start_scene != args.start_scene:
        print(f"WARNING: configured start scene {args.start_scene} not found; using {start_scene}")

    transitions, transition_rows = load_transitions()
    if args.interactive:
        return run_interactive_match(scenes, transitions, start_scene, args.max_steps)

    verification = verify_graph(scenes, transitions, transition_rows, start_scene)
    simulations = run_simulations(scenes, transitions, start_scene, args.max_steps)
    examples = build_example_chains(scenes, transitions)
    write_report(verification, simulations, examples, start_scene, args.max_steps)

    print("\n=== Verification ===")
    print(f"Missing transitions: {len(verification['missing_transitions'])}")
    print(f"Broken source links: {len(verification['broken_sources'])}")
    print(f"Broken next_scene_id links: {len(verification['broken_next_links'])}")
    print(f"Empty allowed_next_scene_ids pools: {len(verification['empty_pools'])}")
    print(f"Broken pool links: {len(verification['broken_pool_links'])}")
    print(f"Pool ownership contradictions: {len(verification['pool_ownership_contradictions'])}")
    print(f"Expected ownership semantic violations: {len(verification['expected_ownership_violations'])}")
    print(f"Excessive semantic spread inside pools: {len(verification['excessive_pool_spread'])}")
    print(f"Orphan scenes: {len(verification['orphan_scenes'])}")
    print(f"Disconnected scenes from start: {len(verification['disconnected_from_start'])}")
    print(f"Dead-end pools: {len(verification['dead_end_pools'])}")
    print(f"Weak connected graph parts: {verification['weak_component_count']}")

    print("\n=== Simulations ===")
    print(
        f"Successful runs: {simulations['successful_runs']} / {simulations['runs']} "
        f"({simulations['successful_runs'] / simulations['runs'] * 100:.1f}%)"
    )
    print(f"Average executed steps: {simulations['avg_steps']:.2f}")
    print(f"Non-pool resolver uses: {simulations['fallback_count']}")
    print(f"Report written: {REPORT_PATH}")

    failed = (
        verification["missing_transitions"]
        or verification["broken_sources"]
        or verification["broken_next_links"]
        or verification["empty_pools"]
        or verification["broken_pool_links"]
        or verification["pool_ownership_contradictions"]
        or verification["expected_ownership_violations"]
        or verification["excessive_pool_spread"]
        or verification["invalid_outcomes"]
        or verification["actions_not_in_scene"]
        or verification["scenes_without_actions"]
        or verification["orphan_scenes"]
        or verification["dead_end_scenes"]
        or verification["dead_end_pools"]
        or verification["disconnected_from_start"]
        or verification["weak_component_count"] != 1
        or simulations["successful_runs"] != simulations["runs"]
        or simulations["fallback_count"] != 0
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
