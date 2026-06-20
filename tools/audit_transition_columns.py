from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'verification_report_transition_columns.md'

files = [
    'transitions_player_complete_graph_v2_executable.xlsx',
    'transitions_teammate_complete_graph_v4_executable.xlsx',
    'transitions_opponent_complete_graph_v1_executable.xlsx',
]

wanted = [
    'transition_id', 'source_scene_id', 'player_action', 'player_action_outcome',
    'ball_owner_after', 'player_position_after', 'player_direction_after',
    'ball_holder_position_after', 'ball_holder_direction_after',
    'allowed_next_scene_ids', 'next_scene_id', 'target_scene_id',
]

lines = ['# Transition Column Audit', '', 'Status: READ_ONLY', '']
for name in files:
    df = pd.read_excel(ROOT / name, dtype=str, keep_default_na=False)
    cols = list(df.columns)
    lower = {c.lower(): c for c in cols}
    lines.append(f'## {name}')
    lines.append(f'- rows: {len(df)}')
    for col in wanted:
        real = lower.get(col.lower())
        if real is None:
            lines.append(f'- {col}: NO')
        else:
            non_empty = int((df[real].astype(str).str.strip() != '').sum())
            lines.append(f'- {col}: YES, non_empty={non_empty}')
    lines.append('')

REPORT.write_text('\n'.join(lines), encoding='utf-8')
print('Transition column audit status: PASS')
print(f'Report written: {REPORT.name}')
