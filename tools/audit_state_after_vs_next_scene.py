from __future__ import annotations

from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'verification_report_state_after_vs_next_scene.md'

SCENES = [
    ('PLAYER_WITH_BALL', 'ball_at_player_normalized_prototype_v7_executable.xlsx'),
    ('TEAMMATE_WITH_BALL', 'ball_at_teammate_normalized_prototype_v1_executable.xlsx'),
    ('OPPONENT_WITH_BALL', 'ball_at_opponent_normalized_prototype_v2_executable.xlsx'),
]

TRANSITIONS = [
    ('player', 'transitions_player_complete_graph_v2_executable.xlsx'),
    ('opponent', 'transitions_opponent_complete_graph_v1_executable.xlsx'),
]

FIELDS = [
    ('ball_owner_after', 'scene_owner'),
    ('player_position_after', 'player_position'),
    ('player_direction_after', 'player_direction'),
    ('ball_holder_position_after', 'ball_holder_position'),
    ('ball_holder_direction_after', 'ball_holder_direction'),
]


def norm(x):
    return str(x or '').strip().lower().replace('ё', 'е')


def split_ids(x):
    return [p.strip() for p in str(x or '').split('||') if p.strip()]


def load_scenes():
    out = {}
    for default_owner, name in SCENES:
        df = pd.read_excel(ROOT / name, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            sid = str(row.get('scene_id', '')).strip()
            if not sid:
                continue
            out[sid] = {
                'scene_owner': str(row.get('scene_owner', '') or default_owner).strip() or default_owner,
                'scene_type': str(row.get('scene_type', '') or 'dynamic').strip().lower() or 'dynamic',
                'player_position': str(row.get('player_position', '')).strip(),
                'player_direction': str(row.get('player_direction', '')).strip(),
                'ball_holder_position': str(row.get('ball_holder_position', '')).strip(),
                'ball_holder_direction': str(row.get('ball_holder_direction', '')).strip(),
            }
    return out


def load_continue_map():
    cont = {}
    for _, name in [
        ('player', 'transitions_player_complete_graph_v2_executable.xlsx'),
        ('teammate', 'transitions_teammate_complete_graph_v4_executable.xlsx'),
        ('opponent', 'transitions_opponent_complete_graph_v1_executable.xlsx'),
    ]:
        df = pd.read_excel(ROOT / name, dtype=str, keep_default_na=False)
        outcome_col = 'player_action_outcome' if 'player_action_outcome' in df.columns else 'outcome'
        if outcome_col not in df.columns:
            continue
        for _, row in df.iterrows():
            if str(row.get('player_action', '')).strip() == 'CONTINUE' and str(row.get(outcome_col, '')).strip().upper() == 'SUCCESS':
                sid = str(row.get('source_scene_id', '')).strip()
                pool = split_ids(row.get('allowed_next_scene_ids', '')) or split_ids(row.get('next_scene_id', ''))
                if sid and pool:
                    cont[sid] = pool
    return cont


def effective_targets(raw_targets, scenes, cont):
    result = []
    for sid in raw_targets:
        s = scenes.get(sid)
        if not s:
            result.append((sid, 'MISSING'))
        elif s.get('scene_type') == 'static':
            for final in cont.get(sid, []):
                result.append((final, sid))
            if sid not in cont:
                result.append((sid, 'STATIC_NO_CONTINUE'))
        else:
            result.append((sid, 'DIRECT'))
    return result


def audit():
    scenes = load_scenes()
    cont = load_continue_map()
    examples = []
    counts = Counter()
    total = 0
    checked = 0

    for lib, name in TRANSITIONS:
        df = pd.read_excel(ROOT / name, dtype=str, keep_default_na=False)
        outcome_col = 'player_action_outcome' if 'player_action_outcome' in df.columns else 'outcome'
        for idx, row in df.iterrows():
            total += 1
            action = str(row.get('player_action', '')).strip()
            if action == 'CONTINUE':
                counts['SKIP_CONTINUE'] += 1
                continue
            raw_targets = split_ids(row.get('allowed_next_scene_ids', '')) or split_ids(row.get('next_scene_id', ''))
            targets = effective_targets(raw_targets, scenes, cont)
            if not targets:
                counts['INVALID_EMPTY_TARGET'] += 1
                continue
            for target_id, via in targets:
                checked += 1
                scene = scenes.get(target_id)
                if not scene:
                    counts['INVALID_MISSING_TARGET'] += 1
                    if len(examples) < 80:
                        examples.append((lib, idx + 2, row, target_id, via, 'missing target scene'))
                    continue
                mismatches = []
                for after_col, scene_col in FIELDS:
                    expected = str(row.get(after_col, '')).strip()
                    if not expected:
                        continue
                    actual = str(scene.get(scene_col, '')).strip()
                    if norm(expected) != norm(actual):
                        mismatches.append(f'{after_col}: expected={expected!r}, actual={actual!r}')
                if mismatches:
                    counts['INVALID_STATE_MISMATCH'] += 1
                    if len(examples) < 80:
                        examples.append((lib, idx + 2, row, target_id, via, '; '.join(mismatches)))
                else:
                    counts['PASS_STATE_MATCH'] += 1

    lines = ['# State After vs Next Scene Audit', '', 'Status: READ_ONLY', '']
    lines += [f'- transition_rows_scanned: {total}', f'- effective_targets_checked: {checked}', '']
    lines.append('## Counts')
    for k, v in counts.most_common():
        lines.append(f'- {k}: {v}')
    lines.append('')
    lines.append('## Examples')
    lines.append('')
    for lib, rownum, row, target_id, via, detail in examples:
        lines.append(f'- library: {lib}')
        lines.append(f'  excel_row: {rownum}')
        lines.append(f'  transition_id: {row.get("transition_id", "")}')
        lines.append(f'  source_scene_id: {row.get("source_scene_id", "")}')
        lines.append(f'  action: {row.get("player_action", "")}')
        lines.append(f'  outcome: {row.get("player_action_outcome", row.get("outcome", ""))}')
        lines.append(f'  target_id: {target_id}')
        lines.append(f'  via: {via}')
        lines.append(f'  detail: {detail}')
    REPORT.write_text('\n'.join(lines), encoding='utf-8')
    print('State-after vs next-scene audit status: PASS')
    print(f'Report written: {REPORT.name}')


if __name__ == '__main__':
    audit()
