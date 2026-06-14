from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import test_transitions_multi_executable as engine

REPORT_PATH = Path("verification_report_bridge.md")
START_SCENE = engine.START_SCENE
MAX_EPISODE_STEPS = 5
RANDOM_SEED = 2026


def resolve_library_paths() -> None:
    """Point the existing engine config to Excel files that exist in this checkout.

    The older scene engine constants may reference scene libraries without the
    `_executable.xlsx` suffix, while the repository currently stores the
    executable scene libraries with that suffix. This function does not rename,
    copy, or transform Excel files. It only resolves config paths before the
    existing loader runs.
    """
    for config in [*engine.SCENE_LIBRARIES, *engine.TRANSITION_LIBRARIES]:
        current = ROOT / str(config["file"])
        if current.exists():
            config["file"] = str(current)
            continue

        if current.suffix == ".xlsx":
            candidate = current.with_name(f"{current.stem}_executable{current.suffix}")
            if candidate.exists():
                config["file"] = str(candidate)
                continue

        raise FileNotFoundError(f"Required library file not found: {config['file']}")


@dataclass
class MatchState:
    minute: int = 12
    score_a: int = 0
    score_b: int = 0
    possession: str = "A"
    pressure_a: float = 0.50
    pressure_b: float = 0.50
    risk: float = 1.00
    event_type: str = "half"
    match_context: Dict[str, object] = field(
        default_factory=lambda: {
            "match_importance": "early_high_stakes",
            "motivation_a": 1.10,
            "motivation_b": 1.00,
            "strength_diff": 0,
            "late_game": False,
        }
    )


@dataclass
class SceneStep:
    source_scene_id: str
    action: str
    outcome: str
    transition_id: str
    next_scene_id: str
    owner_before: str
    owner_after: str
    source_tier: int
    next_tier: int


@dataclass
class EpisodeResult:
    start_scene_id: str
    end_scene_id: str
    steps_played: int
    actions_taken: List[str]
    final_ball_owner: str
    field_tier_delta: int
    created_chance: bool
    goal_delta_a: int
    goal_delta_b: int
    turnover: bool
    pressure_delta_a: float
    pressure_delta_b: float
    significance_tags: List[str]
    scene_steps: List[SceneStep]


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


def choose_start_scene(match_state: MatchState, scenes: Dict[str, engine.Scene]) -> str:
    if START_SCENE not in scenes:
        raise ValueError(f"Verified default start scene is missing: {START_SCENE}")
    return START_SCENE


def classify_episode(scene_steps: List[SceneStep]) -> Tuple[bool, bool, List[str]]:
    tags: List[str] = []

    turnover = any(
        step.owner_before != "OPPONENT_WITH_BALL"
        and step.owner_after == "OPPONENT_WITH_BALL"
        for step in scene_steps
    )
    player_regain = any(
        step.owner_before == "OPPONENT_WITH_BALL"
        and step.owner_after == "PLAYER_WITH_BALL"
        for step in scene_steps
    )

    max_tier = max(step.next_tier for step in scene_steps)
    created_chance = max_tier >= 3 and not turnover

    if turnover:
        tags.append("dangerous_turnover")
    if player_regain:
        tags.append("defensive_recovery")
    if created_chance:
        tags.append("chance_created")
    if any(step.next_tier > step.source_tier for step in scene_steps):
        tags.append("progressive_action")
    if not tags:
        tags.append("safe_reset")

    return created_chance, turnover, tags


def run_episode(
    scenes: Dict[str, engine.Scene],
    transitions: Dict[engine.TransitionKey, List[engine.Transition]],
    start_scene_id: str,
    max_steps: int = MAX_EPISODE_STEPS,
) -> EpisodeResult:
    current_scene_id = start_scene_id
    scene_steps: List[SceneStep] = []
    actions_taken: List[str] = []
    start_tier = int(scenes[start_scene_id]["tier"])

    for _ in range(max_steps):
        scene = scenes.get(current_scene_id)
        if scene is None:
            raise ValueError(f"Scene not found during bridge episode: {current_scene_id}")

        actions = executable_actions(current_scene_id, scene, transitions)
        if not actions:
            raise ValueError(f"No executable actions at scene: {current_scene_id}")

        action = random.choice(actions)
        outcome = random.choice(["SUCCESS", "FAIL"])
        options = transitions.get((current_scene_id, action, outcome), [])
        if not options:
            raise ValueError(f"No transition for {(current_scene_id, action, outcome)}")

        transition = random.choice(options)
        next_scene_id, resolver = engine.resolve_next_scene(scenes, current_scene_id, transition)

        if resolver != "allowed_next_scene_ids":
            raise ValueError(f"Bridge must use allowed_next_scene_ids resolver, got: {resolver}")
        if not next_scene_id or next_scene_id not in scenes:
            raise ValueError(f"Invalid next scene from {current_scene_id}: {next_scene_id}")

        next_scene = scenes[next_scene_id]
        step = SceneStep(
            source_scene_id=current_scene_id,
            action=action,
            outcome=outcome,
            transition_id=str(transition.get("transition_id", "")),
            next_scene_id=next_scene_id,
            owner_before=str(scene["owner"]),
            owner_after=str(next_scene["owner"]),
            source_tier=int(scene["tier"]),
            next_tier=int(next_scene["tier"]),
        )
        scene_steps.append(step)
        actions_taken.append(action)
        current_scene_id = next_scene_id

    end_scene = scenes[current_scene_id]
    end_tier = int(end_scene["tier"])
    created_chance, turnover, tags = classify_episode(scene_steps)

    goal_delta_a = 1 if created_chance and not turnover and random.random() < 0.25 else 0
    if goal_delta_a:
        tags.append("goal_scored")
    elif created_chance:
        tags.append("missed_big_chance")

    pressure_delta_a = 0.10 if created_chance else 0.0
    pressure_delta_b = 0.10 if turnover else 0.0

    return EpisodeResult(
        start_scene_id=start_scene_id,
        end_scene_id=current_scene_id,
        steps_played=len(scene_steps),
        actions_taken=actions_taken,
        final_ball_owner=str(end_scene["owner"]),
        field_tier_delta=end_tier - start_tier,
        created_chance=created_chance,
        goal_delta_a=goal_delta_a,
        goal_delta_b=0,
        turnover=turnover,
        pressure_delta_a=pressure_delta_a,
        pressure_delta_b=pressure_delta_b,
        significance_tags=tags,
        scene_steps=scene_steps,
    )


def apply_episode_result(match_state: MatchState, result: EpisodeResult) -> MatchState:
    match_state.score_a += result.goal_delta_a
    match_state.score_b += result.goal_delta_b
    match_state.pressure_a = min(1.0, max(0.1, match_state.pressure_a + result.pressure_delta_a))
    match_state.pressure_b = min(1.0, max(0.1, match_state.pressure_b + result.pressure_delta_b))
    match_state.risk = 0.0 if result.created_chance or result.turnover else match_state.risk

    if result.final_ball_owner == "OPPONENT_WITH_BALL":
        match_state.possession = "B"
    else:
        match_state.possession = "A"

    return match_state


def verify_bridge(
    scenes: Dict[str, engine.Scene],
    transitions: Dict[engine.TransitionKey, List[engine.Transition]],
    start_scene_id: str,
    result: EpisodeResult,
) -> Dict[str, object]:
    errors: List[str] = []

    if start_scene_id not in scenes:
        errors.append(f"selected start scene missing: {start_scene_id}")

    if result.steps_played != MAX_EPISODE_STEPS:
        errors.append(f"unexpected episode length: {result.steps_played}")

    for step in result.scene_steps:
        if step.source_scene_id not in scenes:
            errors.append(f"missing source scene: {step.source_scene_id}")
        if step.next_scene_id not in scenes:
            errors.append(f"missing next scene: {step.next_scene_id}")
        if not transitions.get((step.source_scene_id, step.action, "SUCCESS")):
            errors.append(f"missing SUCCESS transition: {(step.source_scene_id, step.action)}")
        if not transitions.get((step.source_scene_id, step.action, "FAIL")):
            errors.append(f"missing FAIL transition: {(step.source_scene_id, step.action)}")
        if not transitions.get((step.source_scene_id, step.action, step.outcome)):
            errors.append(f"missing selected transition: {(step.source_scene_id, step.action, step.outcome)}")

    forbidden_outputs = {
        "relationship_delta",
        "reputation_delta",
        "memory_update",
        "career_memory",
        "opportunity_change",
    }
    result_fields = set(result.__dataclass_fields__)
    leaked_fields = sorted(result_fields & forbidden_outputs)
    if leaked_fields:
        errors.append(f"bridge leaked downstream observer fields: {leaked_fields}")

    return {
        "passed": not errors,
        "errors": errors,
        "start_scene_id": start_scene_id,
        "end_scene_id": result.end_scene_id,
        "steps_played": result.steps_played,
        "significance_tags": result.significance_tags,
    }


def write_report(
    match_state_before: MatchState,
    match_state_after: MatchState,
    result: EpisodeResult,
    verification: Dict[str, object],
) -> None:
    lines = [
        "# MVP Match Bridge Verification Report",
        "",
        f"Status: {'PASS' if verification['passed'] else 'FAIL'}",
        "",
        "## Scope",
        "",
        "- Source scene engine: test_transitions_multi_executable.py",
        "- Bridge script: tools/mvp_match_bridge.py",
        "- Purpose: prove match state -> playable episode -> scene chain -> episode result -> match state",
        "- Observer/reputation systems are not modified by this bridge.",
        "",
        "## Match State Before",
        "",
        f"- minute: {match_state_before.minute}",
        f"- score: {match_state_before.score_a}-{match_state_before.score_b}",
        f"- possession: {match_state_before.possession}",
        f"- pressure: A={match_state_before.pressure_a:.2f}, B={match_state_before.pressure_b:.2f}",
        f"- risk: {match_state_before.risk:.2f}",
        f"- event_type: {match_state_before.event_type}",
        "",
        "## Episode Result",
        "",
        f"- start_scene_id: {result.start_scene_id}",
        f"- end_scene_id: {result.end_scene_id}",
        f"- steps_played: {result.steps_played}",
        f"- final_ball_owner: {result.final_ball_owner}",
        f"- field_tier_delta: {result.field_tier_delta}",
        f"- created_chance: {result.created_chance}",
        f"- turnover: {result.turnover}",
        f"- goal_delta: A={result.goal_delta_a}, B={result.goal_delta_b}",
        f"- pressure_delta: A={result.pressure_delta_a:.2f}, B={result.pressure_delta_b:.2f}",
        f"- significance_tags: {', '.join(result.significance_tags)}",
        "",
        "## Scene Steps",
        "",
    ]

    for index, step in enumerate(result.scene_steps, start=1):
        lines.append(
            f"{index}. {step.source_scene_id} [{step.owner_before}, tier {step.source_tier}] "
            f"-- {step.action} => {step.outcome} -> "
            f"{step.next_scene_id} [{step.owner_after}, tier {step.next_tier}]"
        )

    lines += [
        "",
        "## Match State After",
        "",
        f"- minute: {match_state_after.minute}",
        f"- score: {match_state_after.score_a}-{match_state_after.score_b}",
        f"- possession: {match_state_after.possession}",
        f"- pressure: A={match_state_after.pressure_a:.2f}, B={match_state_after.pressure_b:.2f}",
        f"- risk: {match_state_after.risk:.2f}",
        "",
        "## Verification",
        "",
        f"- selected start scene exists: {verification['start_scene_id']}",
        f"- bounded episode steps: {verification['steps_played']}",
        "- observer/reputation fields emitted: no",
    ]

    if verification["errors"]:
        lines += ["", "## Errors", ""]
        lines.extend(f"- {error}" for error in verification["errors"])

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    random.seed(RANDOM_SEED)
    resolve_library_paths()

    scenes = engine.load_scenes()
    transitions, transition_rows = engine.load_transitions()
    start_scene_id = choose_start_scene(MatchState(), scenes)

    graph_verification = engine.verify_graph(scenes, transitions, transition_rows, start_scene_id)
    graph_blockers = [
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
    if any(graph_verification[name] for name in graph_blockers) or graph_verification["weak_component_count"] != 1:
        raise RuntimeError("Existing scene graph verification failed before bridge execution")

    match_state_before = MatchState()
    match_state_after = MatchState()
    result = run_episode(scenes, transitions, start_scene_id)
    match_state_after = apply_episode_result(match_state_after, result)
    bridge_verification = verify_bridge(scenes, transitions, start_scene_id, result)
    write_report(match_state_before, match_state_after, result, bridge_verification)

    print(f"Bridge status: {'PASS' if bridge_verification['passed'] else 'FAIL'}")
    print(f"Report written: {REPORT_PATH}")
    return 0 if bridge_verification["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
