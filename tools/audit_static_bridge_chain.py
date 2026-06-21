from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "verification_report_static_bridge_chain.md"
CSV = ROOT / "verification_report_static_bridge_chain.csv"

SCENE_FILES = [
    ("player", ROOT / "ball_at_player_normalized_prototype_v7_executable.xlsx"),
    ("teammate", ROOT / "ball_at_teammate_normalized_prototype_v1_executable.xlsx"),
    ("opponent", ROOT / "ball_at_opponent_normalized_prototype_v2_executable.xlsx"),
]
TRANSITION_FILES = [
    ("player", ROOT / "transitions_player_complete_graph_v2_executable.xlsx"),
    ("teammate", ROOT / "transitions_teammate_complete_graph_v4_executable.xlsx"),
    ("opponent", ROOT / "transitions_opponent_complete_graph_v1_executable.xlsx"),
]
TARGET_TRANSITIONS = ROOT / "transitions_teammate_complete_graph_v4_executable.xlsx"


def clean(value):
    return str(value or "").strip()


def norm(value):
    return clean(value).lower().replace("ё", "е")


def split_ids(value):
    return [part.strip() for part in clean(value).split("||") if part.strip()]


def choose_outcome_column(columns):
    if "player_action_outcome" in columns:
        return "player_action_outcome"
    if "teammate_action_outcome" in columns:
        return "teammate_action_outcome"
    if "outcome" in columns:
        return "outcome"
    return None


def load_scenes():
    scenes = {}
    for library, path in SCENE_FILES:
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            scene_id = clean(row.get("scene_id"))
            if not scene_id:
                continue
            scenes[scene_id] = {
                "library": library,
                "scene_id": scene_id,
                "scene_type": clean(row.get("scene_type")) or "dynamic",
                "scene_owner": clean(row.get("scene_owner")),
                "player_position": clean(row.get("player_position")),
                "player_direction": clean(row.get("player_direction")),
                "ball_holder_position": clean(row.get("ball_holder_position")),
                "ball_holder_direction": clean(row.get("ball_holder_direction")),
            }
    return scenes


def load_continue_edges():
    edges = {}
    duplicate_sources = Counter()
    outcome_columns_used = Counter()

    for library, path in TRANSITION_FILES:
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
        outcome_col = choose_outcome_column(df.columns)
        outcome_columns_used[f"{library}:{outcome_col or 'NONE'}"] += 1

        for _, row in df.iterrows():
            source = clean(row.get("source_scene_id"))
            action = clean(row.get("player_action"))
            outcome = clean(row.get(outcome_col)).upper() if outcome_col else ""

            if not source or action != "CONTINUE" or outcome != "SUCCESS":
                continue

            pool = split_ids(row.get("allowed_next_scene_ids")) or split_ids(row.get("next_scene_id"))
            if not pool:
                continue

            if source in edges:
                duplicate_sources[source] += 1

            edges[source] = {
                "library": library,
                "transition_id": clean(row.get("transition_id")),
                "targets": pool,
            }

    return edges, duplicate_sources, outcome_columns_used


def expand_chain(start_ids, scenes, continue_edges, max_depth=3):
    dynamic_targets = []
    chain_flags = []
    frontier = [(scene_id, 0, [scene_id]) for scene_id in start_ids]
    seen = set()

    while frontier:
        scene_id, depth, path = frontier.pop(0)
        state = (scene_id, depth)
        if state in seen:
            continue
        seen.add(state)

        scene = scenes.get(scene_id)
        if scene is None:
            chain_flags.append(f"missing_scene:{scene_id}")
            continue

        if norm(scene.get("scene_type")) != "static":
            dynamic_targets.append((scene_id, path))
            continue

        if depth >= max_depth:
            chain_flags.append(f"max_depth_static:{scene_id}")
            continue

        edge = continue_edges.get(scene_id)
        if not edge:
            chain_flags.append(f"static_without_continue:{scene_id}")
            continue

        for next_id in edge["targets"]:
            frontier.append((next_id, depth + 1, path + [next_id]))

    unique = []
    seen_ids = set()
    for scene_id, path in dynamic_targets:
        if scene_id not in seen_ids:
            unique.append((scene_id, path))
            seen_ids.add(scene_id)
    return unique, chain_flags


def consensus(values):
    unique = sorted({clean(value) for value in values if clean(value)})
    return unique[0] if len(unique) == 1 else ""


def main():
    scenes = load_scenes()
    continue_edges, duplicate_continue_sources, outcome_columns_used = load_continue_edges()
    df = pd.read_excel(TARGET_TRANSITIONS, dtype=str, keep_default_na=False)

    rows = []
    counts = Counter()
    examples = []

    for index, row in df.iterrows():
        action = clean(row.get("player_action"))
        if action == "CONTINUE":
            counts["skip_continue_rows"] += 1
            continue

        source_scene_id = clean(row.get("source_scene_id"))
        transition_id = clean(row.get("transition_id"))
        ball_owner_after = clean(row.get("ball_owner_after"))
        start_ids = split_ids(row.get("allowed_next_scene_ids")) or split_ids(row.get("next_scene_id"))

        dynamic_targets, chain_flags = expand_chain(start_ids, scenes, continue_edges)
        target_scenes = [scenes[scene_id] for scene_id, _ in dynamic_targets if scene_id in scenes]
        owner_matched = [
            scene
            for scene in target_scenes
            if not ball_owner_after or clean(scene.get("scene_owner")) == ball_owner_after
        ]

        target_count = len(dynamic_targets)
        owner_match_count = len(owner_matched)
        bh_pos_consensus = consensus([scene.get("ball_holder_position") for scene in owner_matched])
        bh_dir_consensus = consensus([scene.get("ball_holder_direction") for scene in owner_matched])

        flags = list(chain_flags)
        if target_count == 0:
            flags.append("NO_DYNAMIC_TARGET")
            status = "NO_DYNAMIC_TARGET"
        elif owner_match_count == 0:
            flags.append("OWNER_MISMATCH_ALL_TARGETS")
            status = "OWNER_MISMATCH"
        elif not bh_pos_consensus or not bh_dir_consensus:
            flags.append("NO_BALL_HOLDER_CONSENSUS")
            status = "NO_CONSENSUS"
        else:
            status = "PATCH_SAFE"

        counts[status] += 1
        counts[f"dynamic_targets:{target_count if target_count < 5 else '5+'}"] += 1
        counts[f"owner_matched:{owner_match_count if owner_match_count < 5 else '5+'}"] += 1
        for flag in flags:
            counts[f"flag:{flag.split(':')[0]}"] += 1

        item = {
            "status": status,
            "excel_row": index + 2,
            "transition_id": transition_id,
            "source_scene_id": source_scene_id,
            "player_action": action,
            "ball_owner_after": ball_owner_after,
            "start_ids": "||".join(start_ids),
            "dynamic_target_count": target_count,
            "owner_match_count": owner_match_count,
            "dynamic_targets": "||".join(scene_id for scene_id, _ in dynamic_targets),
            "ball_holder_position_consensus": bh_pos_consensus,
            "ball_holder_direction_consensus": bh_dir_consensus,
            "flags": "||".join(flags),
            "sample_paths": " ; ".join(" -> ".join(path) for _, path in dynamic_targets[:5]),
        }
        rows.append(item)
        if status != "PATCH_SAFE" and len(examples) < 80:
            examples.append(item)

    pd.DataFrame(rows).to_csv(CSV, index=False, encoding="utf-8-sig")

    lines = ["# Static Bridge Chain Audit", "", "Status: READ_ONLY", ""]
    lines.append(f"- target_transition_file: {TARGET_TRANSITIONS.name}")
    lines.append(f"- non_continue_rows_checked: {len(rows)}")
    lines.append(f"- scenes_loaded: {len(scenes)}")
    lines.append(f"- continue_edges_loaded: {len(continue_edges)}")
    lines.append(f"- duplicate_continue_sources: {sum(duplicate_continue_sources.values())}")
    lines.append(f"- detailed_csv: {CSV.name}")
    lines.append("")
    lines.append("## Outcome Columns Used")
    lines.append("")
    for key, value in sorted(outcome_columns_used.items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Status Counts")
    lines.append("")
    for key, value in counts.most_common():
        if not key.startswith("dynamic_targets:") and not key.startswith("owner_matched:") and not key.startswith("flag:"):
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Dynamic Target Count Distribution")
    lines.append("")
    for key, value in sorted(counts.items()):
        if key.startswith("dynamic_targets:"):
            lines.append(f"- {key.removeprefix('dynamic_targets:')}: {value}")
    lines.append("")
    lines.append("## Owner-Matched Target Count Distribution")
    lines.append("")
    for key, value in sorted(counts.items()):
        if key.startswith("owner_matched:"):
            lines.append(f"- {key.removeprefix('owner_matched:')}: {value}")
    lines.append("")
    lines.append("## Flag Counts")
    lines.append("")
    for key, value in counts.most_common():
        if key.startswith("flag:"):
            lines.append(f"- {key.removeprefix('flag:')}: {value}")
    lines.append("")
    lines.append("## Examples Requiring Attention")
    lines.append("")
    for item in examples:
        lines.append(f"- row {item['excel_row']} {item['transition_id']}")
        lines.append(f"  status: {item['status']}")
        lines.append(f"  source_scene_id: {item['source_scene_id']}")
        lines.append(f"  action: {item['player_action']}")
        lines.append(f"  ball_owner_after: {item['ball_owner_after']}")
        lines.append(f"  dynamic_target_count: {item['dynamic_target_count']}")
        lines.append(f"  owner_match_count: {item['owner_match_count']}")
        lines.append(f"  targets: {item['dynamic_targets']}")
        lines.append(f"  flags: {item['flags']}")
        lines.append(f"  sample_paths: {item['sample_paths']}")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("Static bridge chain audit status: PASS")
    print(f"Report written: {REPORT.name}")
    print(f"CSV written: {CSV.name}")


if __name__ == "__main__":
    main()
