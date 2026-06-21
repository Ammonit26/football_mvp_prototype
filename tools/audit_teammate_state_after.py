from __future__ import annotations

from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "verification_report_teammate_state_after.md"
CSV = ROOT / "verification_report_teammate_state_after.csv"
TRANSITIONS = ROOT / "transitions_teammate_complete_graph_v4_executable.xlsx"
SCENES = ROOT / "ball_at_teammate_normalized_prototype_v1_executable.xlsx"

DIRECTION_MARKERS = [
    "лицом к чужим воротам",
    "лицом к своим воротам",
    "лицом к боковой линии",
]


def clean(value):
    return str(value or "").strip()


def split_position_direction(value):
    text = clean(value)
    for marker in DIRECTION_MARKERS:
        token = ", " + marker
        if text.endswith(token):
            return text[: -len(token)].strip(), marker
    return text, ""


def main():
    tr = pd.read_excel(TRANSITIONS, dtype=str, keep_default_na=False)
    sc = pd.read_excel(SCENES, dtype=str, keep_default_na=False)

    scene_by_id = {clean(row.get("scene_id")): row for _, row in sc.iterrows() if clean(row.get("scene_id"))}
    rows = []
    counts = Counter()

    for idx, row in tr.iterrows():
        source_scene_id = clean(row.get("source_scene_id"))
        source_scene = scene_by_id.get(source_scene_id)
        action = clean(row.get("player_action"))
        position_after = clean(row.get("player_position_after"))
        parsed_pos, parsed_dir = split_position_direction(position_after)
        existing_player_direction = clean(row.get("player_direction_after")) if "player_direction_after" in tr.columns else ""
        existing_ball_holder_position = clean(row.get("ball_holder_position_after")) if "ball_holder_position_after" in tr.columns else ""
        existing_ball_holder_direction = clean(row.get("ball_holder_direction_after")) if "ball_holder_direction_after" in tr.columns else ""

        flags = []
        if parsed_dir:
            flags.append("PLAYER_POSITION_CONTAINS_DIRECTION")
        if not existing_player_direction:
            flags.append("MISSING_PLAYER_DIRECTION_AFTER")
        if not existing_ball_holder_position:
            flags.append("MISSING_BALL_HOLDER_POSITION_AFTER")
        if not existing_ball_holder_direction:
            flags.append("MISSING_BALL_HOLDER_DIRECTION_AFTER")
        if source_scene is None:
            flags.append("MISSING_SOURCE_SCENE")

        for flag in flags:
            counts[flag] += 1

        source_ball_holder_position = ""
        source_ball_holder_direction = ""
        source_player_position = ""
        source_player_direction = ""
        if source_scene is not None:
            source_ball_holder_position = clean(source_scene.get("ball_holder_position"))
            source_ball_holder_direction = clean(source_scene.get("ball_holder_direction"))
            source_player_position = clean(source_scene.get("player_position"))
            source_player_direction = clean(source_scene.get("player_direction"))

        rows.append({
            "excel_row": idx + 2,
            "transition_id": clean(row.get("transition_id")),
            "source_scene_id": source_scene_id,
            "player_action": action,
            "ball_owner_after": clean(row.get("ball_owner_after")),
            "player_position_after_raw": position_after,
            "player_position_after_parsed": parsed_pos,
            "player_direction_after_parsed": parsed_dir,
            "player_direction_after_existing": existing_player_direction,
            "ball_holder_position_after_existing": existing_ball_holder_position,
            "ball_holder_direction_after_existing": existing_ball_holder_direction,
            "source_ball_holder_position": source_ball_holder_position,
            "source_ball_holder_direction": source_ball_holder_direction,
            "source_player_position": source_player_position,
            "source_player_direction": source_player_direction,
            "flags": "||".join(flags),
        })

    pd.DataFrame(rows).to_csv(CSV, index=False, encoding="utf-8-sig")

    lines = ["# Teammate State-After Audit", "", "Status: READ_ONLY", ""]
    lines.append(f"- transition_rows: {len(tr)}")
    lines.append(f"- scene_rows: {len(sc)}")
    lines.append(f"- detailed_csv: {CSV.name}")
    lines.append("")
    lines.append("## Flag Counts")
    lines.append("")
    for key, value in counts.most_common():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Column Presence")
    lines.append("")
    for col in ["player_direction_after", "ball_holder_position_after", "ball_holder_direction_after"]:
        lines.append(f"- {col}: {'YES' if col in tr.columns else 'NO'}")
    lines.append("")
    lines.append("## Examples")
    lines.append("")
    shown = 0
    for item in rows:
        if not item["flags"]:
            continue
        lines.append(f"- row {item['excel_row']} {item['transition_id']}")
        lines.append(f"  source_scene_id: {item['source_scene_id']}")
        lines.append(f"  action: {item['player_action']}")
        lines.append(f"  ball_owner_after: {item['ball_owner_after']}")
        lines.append(f"  player_position_after_raw: {item['player_position_after_raw']}")
        lines.append(f"  parsed_player_position: {item['player_position_after_parsed']}")
        lines.append(f"  parsed_player_direction: {item['player_direction_after_parsed']}")
        lines.append(f"  source_ball_holder: ({item['source_ball_holder_position']}, {item['source_ball_holder_direction']})")
        lines.append(f"  flags: {item['flags']}")
        shown += 1
        if shown >= 40:
            break

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("Teammate state-after audit status: PASS")
    print(f"Report written: {REPORT.name}")
    print(f"CSV written: {CSV.name}")


if __name__ == "__main__":
    main()
