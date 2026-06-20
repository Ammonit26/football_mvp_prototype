from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]

PLAYER_SCENES = ROOT / "ball_at_player_normalized_prototype_v7_executable.xlsx"
PLAYER_TRANSITIONS = ROOT / "transitions_player_complete_graph_v2_executable.xlsx"

STATIC_SCENE_ID = "fb_static_player_0001"
STATIC_TRANSITION_ID = "fb_trans_static_player_000001"
SOURCE_SCENE_ID = "fb_player_0002"
SOURCE_ACTION = "Пройти соперника дриблингом"
SOURCE_OUTCOME = "SUCCESS"
TARGET_DYNAMIC_SCENE_ID = "fb_player_0158"
STATIC_TEXT = "Ты оставляешь соперника позади и протаскиваешь мяч в центр поля. Атака получает продолжение."


def safe(value: object) -> str:
    return "" if value is None else str(value).strip()


def header_map(ws) -> Dict[str, int]:
    return {safe(cell.value): int(cell.column) for cell in ws[1] if safe(cell.value)}


def require(headers: Dict[str, int], names: Iterable[str]) -> int:
    lowered = {name.lower(): col for name, col in headers.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    raise RuntimeError(f"Missing required column. Tried: {list(names)}")


def optional(headers: Dict[str, int], names: Iterable[str]) -> Optional[int]:
    lowered = {name.lower(): col for name, col in headers.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def ensure_column(ws, name: str) -> int:
    headers = header_map(ws)
    if name in headers:
        return headers[name]
    col = ws.max_column + 1
    ws.cell(row=1, column=col).value = name
    return col


def find_rows(ws, col: int, value: str) -> list[int]:
    return [row for row in range(2, ws.max_row + 1) if safe(ws.cell(row=row, column=col).value) == value]


def patch_scene_library() -> None:
    wb = load_workbook(PLAYER_SCENES)
    ws = wb["normalized_player_scenes"]
    headers = header_map(ws)
    scene_id_col = require(headers, ["scene_id"])
    scene_type_col = ensure_column(ws, "scene_type")
    headers = header_map(ws)

    for row in range(2, ws.max_row + 1):
        if not safe(ws.cell(row=row, column=scene_type_col).value):
            ws.cell(row=row, column=scene_type_col).value = "dynamic"

    existing = find_rows(ws, scene_id_col, STATIC_SCENE_ID)
    if existing:
        row = existing[0]
        status = "updated_existing"
    else:
        row = ws.max_row + 1
        status = "created"

    values = {
        "scene_id": STATIC_SCENE_ID,
        "scene_owner": "PLAYER_WITH_BALL",
        "player_position": "в центре поля",
        "player_direction": "лицом к чужим воротам",
        "ball_holder_position": "в центре поля",
        "ball_holder_direction": "лицом к чужим воротам",
        "ball_holder_action": "продвигается после успешного дриблинга",
        "available_player_actions": "",
        "narrative_scene": STATIC_TEXT,
        "scene_type": "static",
    }
    for col_name, value in values.items():
        col = optional(headers, [col_name])
        if col is not None:
            ws.cell(row=row, column=col).value = value

    wb.save(PLAYER_SCENES)
    print(f"SCENE_LIBRARY_PATCHED {PLAYER_SCENES.name}: {STATIC_SCENE_ID} {status}")


def patch_transition_library() -> None:
    wb = load_workbook(PLAYER_TRANSITIONS)
    ws = wb.active
    headers = header_map(ws)
    transition_id_col = optional(headers, ["transition_id"])
    source_col = require(headers, ["source_scene_id", "source_scene", "from_scene", "scene_id"])
    action_col = require(headers, ["player_action", "action", "teammate_action"])
    outcome_col = require(headers, ["player_action_outcome", "teammate_action_outcome", "outcome"])
    owner_col = require(headers, ["ball_owner_after", "ball_owner"])
    next_col = optional(headers, ["next_scene_id", "target_scene_id"])
    allowed_col = require(headers, ["allowed_next_scene_ids"])

    matching_source_rows = []
    template_row = None
    for row in range(2, ws.max_row + 1):
        if (
            safe(ws.cell(row=row, column=source_col).value) == SOURCE_SCENE_ID
            and safe(ws.cell(row=row, column=action_col).value) == SOURCE_ACTION
            and safe(ws.cell(row=row, column=outcome_col).value).upper() == SOURCE_OUTCOME
        ):
            matching_source_rows.append(row)
            if template_row is None:
                template_row = row

    if not matching_source_rows:
        raise RuntimeError("No source transition rows found for the vertical static-scene slice")

    for row in matching_source_rows:
        ws.cell(row=row, column=allowed_col).value = STATIC_SCENE_ID
        if next_col is not None:
            ws.cell(row=row, column=next_col).value = STATIC_SCENE_ID
        ws.cell(row=row, column=owner_col).value = "PLAYER_WITH_BALL"

    static_rows = []
    if transition_id_col is not None:
        static_rows = find_rows(ws, transition_id_col, STATIC_TRANSITION_ID)

    if static_rows:
        static_row = static_rows[0]
        status = "updated_existing"
    else:
        static_row = ws.max_row + 1
        status = "created"
        for col in range(1, ws.max_column + 1):
            ws.cell(row=static_row, column=col).value = ws.cell(row=template_row, column=col).value

    if transition_id_col is not None:
        ws.cell(row=static_row, column=transition_id_col).value = STATIC_TRANSITION_ID
    ws.cell(row=static_row, column=source_col).value = STATIC_SCENE_ID
    ws.cell(row=static_row, column=action_col).value = "CONTINUE"
    ws.cell(row=static_row, column=outcome_col).value = "SUCCESS"
    ws.cell(row=static_row, column=owner_col).value = "PLAYER_WITH_BALL"
    ws.cell(row=static_row, column=allowed_col).value = TARGET_DYNAMIC_SCENE_ID
    if next_col is not None:
        ws.cell(row=static_row, column=next_col).value = TARGET_DYNAMIC_SCENE_ID

    wb.save(PLAYER_TRANSITIONS)
    print(
        f"TRANSITION_LIBRARY_PATCHED {PLAYER_TRANSITIONS.name}: "
        f"{len(matching_source_rows)} source row(s) redirected to {STATIC_SCENE_ID}; "
        f"{STATIC_TRANSITION_ID} {status}"
    )


def main() -> int:
    patch_scene_library()
    patch_transition_library()
    print("Static scene vertical slice patch status: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
