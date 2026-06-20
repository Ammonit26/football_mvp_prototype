from __future__ import annotations

from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "verification_report_state_resolver_coverage.md"
CSV = ROOT / "verification_report_state_resolver_coverage.csv"

SCENE_FILES = [
    ("PLAYER_WITH_BALL", "ball_at_player_normalized_prototype_v7_executable.xlsx"),
    ("TEAMMATE_WITH_BALL", "ball_at_teammate_normalized_prototype_v1_executable.xlsx"),
    ("OPPONENT_WITH_BALL", "ball_at_opponent_normalized_prototype_v2_executable.xlsx"),
]

TRANSITION_FILES = [
    ("player", "transitions_player_complete_graph_v2_executable.xlsx"),
    ("teammate", "transitions_teammate_complete_graph_v4_executable.xlsx"),
    ("opponent", "transitions_opponent_complete_graph_v1_executable.xlsx"),
]

PAIRS = [
    ("ball_owner_after", "scene_owner"),
    ("player_position_after", "player_position"),
    ("player_direction_after", "player_direction"),
    ("ball_holder_position_after", "ball_holder_position"),
    ("ball_holder_direction_after", "ball_holder_direction"),
]


def clean(x):
    return str(x or "").strip()


def norm(x):
    return clean(x).lower().replace("ё", "е")


def split_ids(x):
    return [p.strip() for p in clean(x).split("||") if p.strip()]


def action_bucket(action):
    t = norm(action)
    if action == "CONTINUE":
        return "CONTINUE"
    if any(x in t for x in ["удар", "бить", "бьет"]):
        return "SHOT"
    if any(x in t for x in ["пас", "передач", "отдать", "заброс", "навес", "прострел"]):
        return "PASS_CROSS"
    if any(x in t for x in ["дриблинг", "пройти", "обыграть", "вести"]):
        return "DRIBBLE_CARRY"
    if any(x in t for x in ["отбор", "отобрать", "накрыть", "закрывать", "перехват", "оттянуться"]):
        return "DEFENSE"
    if any(x in t for x in ["отскок", "рикошет", "подбор"]):
        return "SECOND_BALL"
    if any(x in t for x in ["вынести", "вынос"]):
        return "CLEARANCE"
    return "GENERIC"


def load_scenes():
    scenes = {}
    for default_owner, name in SCENE_FILES:
        df = pd.read_excel(ROOT / name, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            scene_id = clean(row.get("scene_id"))
            if not scene_id:
                continue
            scenes[scene_id] = {
                "scene_id": scene_id,
                "scene_owner": clean(row.get("scene_owner")) or default_owner,
                "scene_type": (clean(row.get("scene_type")) or "dynamic").lower(),
                "player_position": clean(row.get("player_position")),
                "player_direction": clean(row.get("player_direction")),
                "ball_holder_position": clean(row.get("ball_holder_position")),
                "ball_holder_direction": clean(row.get("ball_holder_direction")),
            }
    return scenes


def scene_matches_transition(scene, transition):
    for after_col, scene_col in PAIRS:
        expected = clean(transition.get(after_col))
        if expected and norm(expected) != norm(scene.get(scene_col)):
            return False
    return True


def mismatch_counter(scenes, transition):
    counter = Counter()
    owner = clean(transition.get("ball_owner_after"))
    candidates = [s for s in scenes.values() if s["scene_type"] != "static" and (not owner or s["scene_owner"] == owner)]
    for scene in candidates:
        for after_col, scene_col in PAIRS:
            expected = clean(transition.get(after_col))
            if expected and norm(expected) != norm(scene.get(scene_col)):
                counter[after_col] += 1
    return counter


def main():
    scenes = load_scenes()
    dynamic_scenes = {sid: s for sid, s in scenes.items() if s["scene_type"] != "static"}
    static_count = len(scenes) - len(dynamic_scenes)

    rows = []
    status_counts = Counter()
    bucket_counts = Counter()
    examples = []

    for lib, name in TRANSITION_FILES:
        df = pd.read_excel(ROOT / name, dtype=str, keep_default_na=False)
        outcome_col = "player_action_outcome" if "player_action_outcome" in df.columns else "outcome"
        for idx, row in df.iterrows():
            action = clean(row.get("player_action"))
            if not action or action == "CONTINUE":
                status_counts["SKIP_CONTINUE"] += 1
                continue
            transition = {k: clean(row.get(k)) for k, _ in PAIRS}
            owner = transition.get("ball_owner_after")
            candidates = [s for s in dynamic_scenes.values() if not owner or s["scene_owner"] == owner]
            exact = [s["scene_id"] for s in candidates if scene_matches_transition(s, transition)]
            allowed = split_ids(row.get("allowed_next_scene_ids")) or split_ids(row.get("next_scene_id"))
            allowed_exact = [sid for sid in allowed if sid in exact]
            bucket = action_bucket(action)

            if len(exact) == 0:
                status = "NO_EXACT_SCENE_IN_LIBRARY"
                reasons = mismatch_counter(scenes, transition).most_common(3)
                diagnostic = ", ".join(f"{k}:{v}" for k, v in reasons)
            elif len(allowed_exact) == 0:
                status = "EXACT_EXISTS_BUT_NOT_ALLOWED"
                diagnostic = "exact_examples=" + "||".join(exact[:5])
            else:
                status = "PASS_ALLOWED_EXACT_EXISTS"
                diagnostic = "allowed_exact=" + "||".join(allowed_exact[:5])

            status_counts[status] += 1
            bucket_counts[(bucket, status)] += 1
            item = {
                "status": status,
                "library": lib,
                "excel_row": idx + 2,
                "transition_id": clean(row.get("transition_id")),
                "source_scene_id": clean(row.get("source_scene_id")),
                "action_bucket": bucket,
                "action": action,
                "outcome": clean(row.get(outcome_col)).upper(),
                "ball_owner_after": transition.get("ball_owner_after"),
                "player_position_after": transition.get("player_position_after"),
                "player_direction_after": transition.get("player_direction_after"),
                "ball_holder_position_after": transition.get("ball_holder_position_after"),
                "ball_holder_direction_after": transition.get("ball_holder_direction_after"),
                "allowed_count": len(allowed),
                "exact_library_count": len(exact),
                "allowed_exact_count": len(allowed_exact),
                "exact_examples": "||".join(exact[:10]),
                "allowed_exact_examples": "||".join(allowed_exact[:10]),
                "diagnostic": diagnostic,
            }
            rows.append(item)
            if status != "PASS_ALLOWED_EXACT_EXISTS" and len(examples) < 80:
                examples.append(item)

    pd.DataFrame(rows).to_csv(CSV, index=False, encoding="utf-8-sig")

    lines = ["# State Resolver Coverage Audit", "", "Status: READ_ONLY", ""]
    lines += [
        f"- scenes_total: {len(scenes)}",
        f"- dynamic_scenes: {len(dynamic_scenes)}",
        f"- static_scenes: {static_count}",
        f"- transition_rows_checked: {len(rows)}",
        f"- detailed_csv: {CSV.name}",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in status_counts.most_common():
        lines.append(f"- {key}: {value}")
    lines += ["", "## Status by Action Bucket", ""]
    for (bucket, status), value in sorted(bucket_counts.items()):
        lines.append(f"- {bucket} / {status}: {value}")
    lines += ["", "## Examples", ""]
    for item in examples:
        lines.append(f"- {item['library']} row {item['excel_row']} {item['transition_id']}")
        lines.append(f"  action: {item['action']} / {item['outcome']}")
        lines.append(f"  status: {item['status']}")
        lines.append(f"  state_after: owner={item['ball_owner_after']}; player=({item['player_position_after']}, {item['player_direction_after']}); ball_holder=({item['ball_holder_position_after']}, {item['ball_holder_direction_after']})")
        lines.append(f"  exact_library_count: {item['exact_library_count']}")
        lines.append(f"  allowed_exact_count: {item['allowed_exact_count']}")
        lines.append(f"  diagnostic: {item['diagnostic']}")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("State resolver coverage audit status: PASS")
    print(f"Report written: {REPORT.name}")
    print(f"CSV written: {CSV.name}")


if __name__ == "__main__":
    main()
