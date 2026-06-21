from __future__ import annotations

from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "verification_report_teammate_missing_sources.md"
CSV = ROOT / "verification_report_teammate_missing_sources.csv"

TRANSITIONS = ROOT / "transitions_teammate_complete_graph_v4_executable.xlsx"
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


def clean(value):
    return str(value or "").strip()


def scene_prefix(scene_id: str) -> str:
    if scene_id.startswith("fb_static_auto_teammate_"):
        return "static_auto_teammate"
    if scene_id.startswith("fb_static_auto_player_"):
        return "static_auto_player"
    if scene_id.startswith("fb_static_auto_opponent_"):
        return "static_auto_opponent"
    if scene_id.startswith("fb_static_"):
        return "static_manual"
    if scene_id.startswith("fb_teamm_"):
        return "teammate_dynamic_prefix"
    if scene_id.startswith("fb_player_"):
        return "player_dynamic_prefix"
    if scene_id.startswith("fb_opp_"):
        return "opponent_dynamic_prefix"
    return "other"


def load_scene_ids():
    by_file = {}
    all_ids = set()
    for key, path in SCENE_FILES:
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
        ids = {clean(v) for v in df.get("scene_id", []) if clean(v)}
        by_file[key] = ids
        all_ids.update(ids)
    return by_file, all_ids


def load_transition_sources():
    sources = Counter()
    targets = Counter()
    for key, path in TRANSITION_FILES:
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
        if "source_scene_id" in df.columns:
            for value in df["source_scene_id"]:
                sid = clean(value)
                if sid:
                    sources[(key, sid)] += 1
        for col in ["allowed_next_scene_ids", "next_scene_id"]:
            if col not in df.columns:
                continue
            for value in df[col]:
                raw = clean(value)
                if not raw:
                    continue
                for sid in [part.strip() for part in raw.split("||") if part.strip()]:
                    targets[(key, sid)] += 1
    return sources, targets


def main():
    teammate_tr = pd.read_excel(TRANSITIONS, dtype=str, keep_default_na=False)
    scene_ids_by_file, all_scene_ids = load_scene_ids()
    transition_sources, transition_targets = load_transition_sources()

    rows = []
    counts = Counter()

    for idx, row in teammate_tr.iterrows():
        source_scene_id = clean(row.get("source_scene_id"))
        if not source_scene_id:
            continue
        exists_anywhere = source_scene_id in all_scene_ids
        exists_teammate = source_scene_id in scene_ids_by_file["teammate"]
        if exists_teammate:
            continue

        appears_as_source = sum(count for (_, sid), count in transition_sources.items() if sid == source_scene_id)
        appears_as_target = sum(count for (_, sid), count in transition_targets.items() if sid == source_scene_id)
        prefix = scene_prefix(source_scene_id)

        if exists_anywhere:
            classification = "EXISTS_IN_OTHER_SCENE_LIBRARY"
        elif prefix.startswith("static"):
            classification = "MISSING_STATIC_SOURCE_ID"
        elif appears_as_target:
            classification = "MISSING_BUT_REFERENCED_AS_TARGET"
        else:
            classification = "MISSING_UNREFERENCED_SOURCE_ID"

        counts[classification] += 1
        counts[f"prefix:{prefix}"] += 1

        rows.append({
            "excel_row": idx + 2,
            "transition_id": clean(row.get("transition_id")),
            "source_scene_id": source_scene_id,
            "source_prefix": prefix,
            "classification": classification,
            "exists_player_scene": source_scene_id in scene_ids_by_file["player"],
            "exists_teammate_scene": exists_teammate,
            "exists_opponent_scene": source_scene_id in scene_ids_by_file["opponent"],
            "appears_as_transition_source_total": appears_as_source,
            "appears_as_transition_target_total": appears_as_target,
            "player_action": clean(row.get("player_action")),
            "ball_owner_after": clean(row.get("ball_owner_after")),
            "allowed_next_scene_ids": clean(row.get("allowed_next_scene_ids")),
            "next_scene_id": clean(row.get("next_scene_id")),
        })

    out = pd.DataFrame(rows)
    out.to_csv(CSV, index=False, encoding="utf-8-sig")

    lines = ["# Teammate Missing Source Audit", "", "Status: READ_ONLY", ""]
    lines.append(f"- teammate_transition_rows: {len(teammate_tr)}")
    lines.append(f"- missing_source_rows: {len(rows)}")
    lines.append(f"- unique_missing_source_ids: {out['source_scene_id'].nunique() if len(out) else 0}")
    lines.append(f"- detailed_csv: {CSV.name}")
    lines.append("")
    lines.append("## Classification Counts")
    lines.append("")
    for key, value in counts.most_common():
        if key.startswith("prefix:"):
            continue
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Prefix Counts")
    lines.append("")
    for key, value in counts.most_common():
        if key.startswith("prefix:"):
            lines.append(f"- {key.removeprefix('prefix:')}: {value}")
    lines.append("")
    lines.append("## Unique Missing Source IDs")
    lines.append("")
    if len(out):
        grouped = out.groupby(["source_scene_id", "source_prefix", "classification"], dropna=False).size().reset_index(name="rows")
        for _, item in grouped.head(80).iterrows():
            lines.append(f"- {item['source_scene_id']} | {item['source_prefix']} | {item['classification']} | rows={item['rows']}")
    lines.append("")
    lines.append("## Examples")
    lines.append("")
    for _, item in out.head(60).iterrows():
        lines.append(f"- row {item['excel_row']} {item['transition_id']}")
        lines.append(f"  source_scene_id: {item['source_scene_id']}")
        lines.append(f"  classification: {item['classification']}")
        lines.append(f"  action: {item['player_action']}")
        lines.append(f"  ball_owner_after: {item['ball_owner_after']}")
        lines.append(f"  appears_as_target_total: {item['appears_as_transition_target_total']}")
        lines.append(f"  allowed_next_scene_ids: {item['allowed_next_scene_ids']}")
        lines.append(f"  next_scene_id: {item['next_scene_id']}")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("Teammate missing source audit status: PASS")
    print(f"Report written: {REPORT.name}")
    print(f"CSV written: {CSV.name}")


if __name__ == "__main__":
    main()
