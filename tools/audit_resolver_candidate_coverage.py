from __future__ import annotations

from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "verification_report_resolver_candidate_coverage.md"

SCENE_FILES = [
    ("PLAYER_WITH_BALL", "ball_at_player_normalized_prototype_v7_executable.xlsx"),
    ("TEAMMATE_WITH_BALL", "ball_at_teammate_normalized_prototype_v1_executable.xlsx"),
    ("OPPONENT_WITH_BALL", "ball_at_opponent_normalized_prototype_v2_executable.xlsx"),
]

TRANSITION_FILES = [
    ("player", "transitions_player_complete_graph_v2_executable.xlsx"),
    ("opponent", "transitions_opponent_complete_graph_v1_executable.xlsx"),
]

FIELDS = [
    ("ball_owner_after", "scene_owner"),
    ("player_position_after", "player_position"),
    ("player_direction_after", "player_direction"),
    ("ball_holder_position_after", "ball_holder_position"),
    ("ball_holder_direction_after", "ball_holder_direction"),
]


def norm(value):
    return str(value or "").strip().lower().replace("ё", "е")


def load_scenes():
    scenes = []
    for default_owner, name in SCENE_FILES:
        df = pd.read_excel(ROOT / name, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            scene_id = str(row.get("scene_id", "")).strip()
            if not scene_id:
                continue
            scene_type = str(row.get("scene_type", "dynamic") or "dynamic").strip().lower() or "dynamic"
            scenes.append({
                "scene_id": scene_id,
                "scene_owner": str(row.get("scene_owner", "") or default_owner).strip() or default_owner,
                "scene_type": scene_type,
                "player_position": str(row.get("player_position", "")).strip(),
                "player_direction": str(row.get("player_direction", "")).strip(),
                "ball_holder_position": str(row.get("ball_holder_position", "")).strip(),
                "ball_holder_direction": str(row.get("ball_holder_direction", "")).strip(),
            })
    return scenes


def scene_matches_transition(scene, row):
    mismatches = []
    checked = 0
    for t_col, s_col in FIELDS:
        expected = str(row.get(t_col, "")).strip()
        if not expected:
            continue
        checked += 1
        actual = str(scene.get(s_col, "")).strip()
        if norm(expected) != norm(actual):
            mismatches.append(t_col)
    return checked, mismatches


def action_bucket(action):
    low = norm(action)
    if any(x in low for x in ["удар", "бить", "бьет"]):
        return "SHOT"
    if any(x in low for x in ["пас", "передач", "отдать", "заброс", "навес", "прострел"]):
        return "PASS_CROSS"
    if any(x in low for x in ["дриблинг", "пройти", "вести", "обыграть"]):
        return "DRIBBLE_CARRY"
    if any(x in low for x in ["отбор", "накрыть", "перехват", "закрывать", "позицию", "рывок"]):
        return "DEFENSE"
    if any(x in low for x in ["отскок", "рикошет", "подбор"]):
        return "SECOND_BALL"
    if any(x in low for x in ["вынести", "вынос"]):
        return "CLEARANCE"
    return "GENERIC"


def audit():
    scenes = load_scenes()
    dynamic_scenes = [s for s in scenes if s["scene_type"] != "static"]
    static_scenes = [s for s in scenes if s["scene_type"] == "static"]

    counts = Counter()
    bucket_counts = Counter()
    zero_examples = []
    many_examples = []
    one_examples = []
    reason_counts = Counter()

    for lib, name in TRANSITION_FILES:
        df = pd.read_excel(ROOT / name, dtype=str, keep_default_na=False)
        outcome_col = "player_action_outcome" if "player_action_outcome" in df.columns else "outcome"
        for idx, row in df.iterrows():
            action = str(row.get("player_action", "")).strip()
            outcome = str(row.get(outcome_col, "")).strip().upper()
            if action == "CONTINUE":
                counts["SKIP_CONTINUE"] += 1
                continue
            bucket = action_bucket(action)
            bucket_counts[bucket] += 1
            matches = []
            near_reason = Counter()
            for scene in dynamic_scenes:
                checked, mismatches = scene_matches_transition(scene, row)
                if checked == 0:
                    continue
                if not mismatches:
                    matches.append(scene["scene_id"])
                else:
                    for item in mismatches:
                        near_reason[item] += 1
            match_count = len(matches)
            if match_count == 0:
                counts["ZERO_MATCH"] += 1
                top_reason = near_reason.most_common(1)[0][0] if near_reason else "NO_STATE_FIELDS"
                reason_counts[top_reason] += 1
                if len(zero_examples) < 40:
                    zero_examples.append((lib, idx + 2, row, bucket, top_reason))
            elif match_count == 1:
                counts["ONE_MATCH"] += 1
                if len(one_examples) < 20:
                    one_examples.append((lib, idx + 2, row, bucket, matches[:5]))
            else:
                counts["MULTI_MATCH"] += 1
                if len(many_examples) < 40:
                    many_examples.append((lib, idx + 2, row, bucket, match_count, matches[:10]))

    lines = ["# Resolver Candidate Coverage Audit", "", "Status: READ_ONLY", ""]
    lines.append("## Loaded scenes")
    lines.append(f"- dynamic_scenes: {len(dynamic_scenes)}")
    lines.append(f"- static_scenes: {len(static_scenes)}")
    lines.append("")
    lines.append("## Candidate coverage counts")
    for k, v in counts.most_common():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Action bucket counts")
    for k, v in bucket_counts.most_common():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## ZERO_MATCH likely blocking fields")
    for k, v in reason_counts.most_common():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## ZERO_MATCH examples")
    for lib, excel_row, row, bucket, top_reason in zero_examples:
        lines.append(f"- library: {lib}")
        lines.append(f"  excel_row: {excel_row}")
        lines.append(f"  transition_id: {row.get('transition_id', '')}")
        lines.append(f"  source_scene_id: {row.get('source_scene_id', '')}")
        lines.append(f"  action: {row.get('player_action', '')}")
        lines.append(f"  outcome: {row.get('player_action_outcome', row.get('outcome', ''))}")
        lines.append(f"  bucket: {bucket}")
        lines.append(f"  blocker: {top_reason}")
        lines.append(f"  state_after: owner={row.get('ball_owner_after', '')}; player=({row.get('player_position_after', '')}, {row.get('player_direction_after', '')}); ball_holder=({row.get('ball_holder_position_after', '')}, {row.get('ball_holder_direction_after', '')})")
    lines.append("")

    lines.append("## ONE_MATCH examples")
    for lib, excel_row, row, bucket, matches in one_examples:
        lines.append(f"- library: {lib}")
        lines.append(f"  excel_row: {excel_row}")
        lines.append(f"  transition_id: {row.get('transition_id', '')}")
        lines.append(f"  action: {row.get('player_action', '')}")
        lines.append(f"  bucket: {bucket}")
        lines.append(f"  matches: {' || '.join(matches)}")
    lines.append("")

    lines.append("## MULTI_MATCH examples")
    for lib, excel_row, row, bucket, match_count, matches in many_examples:
        lines.append(f"- library: {lib}")
        lines.append(f"  excel_row: {excel_row}")
        lines.append(f"  transition_id: {row.get('transition_id', '')}")
        lines.append(f"  action: {row.get('player_action', '')}")
        lines.append(f"  bucket: {bucket}")
        lines.append(f"  match_count: {match_count}")
        lines.append(f"  sample_matches: {' || '.join(matches)}")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("Resolver candidate coverage audit status: PASS")
    print(f"Report written: {REPORT.name}")


if __name__ == "__main__":
    audit()
