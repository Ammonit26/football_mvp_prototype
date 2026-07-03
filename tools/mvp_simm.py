import random
import csv
from collections import Counter

MATCH_DURATION = 90
EXTRA_TIME_RANGE = (1, 7)
GOAL_CHANCE = {
    "tight": 0.18, "half": 0.30, "big": 0.45, "mistake": 0.60
}

CONTEXT_EVENT_COOLDOWN = 5
SET_PIECE_SUBTYPES = ["corner", "free_kick", "penalty"]
SET_PIECE_WEIGHTS = [0.50, 0.40, 0.10]

def get_intensity_modifier(minute, score_diff, strength_diff, motivation_A, motivation_B, extra_time=False):
    if minute <= 15: minute_factor = 0.83
    elif 16 <= minute <= 30: minute_factor = 0.91
    elif 31 <= minute <= 45: minute_factor = 1.30
    elif 46 <= minute <= 60: minute_factor = 1.12
    elif 61 <= minute <= 75: minute_factor = 1.10
    elif 76 <= minute <= 90: minute_factor = 1.13
    else: minute_factor = 1.45

    if score_diff == 0: score_factor = 1.0
    elif score_diff == 1: score_factor = 0.95
    elif score_diff >= 2: score_factor = 0.85
    elif score_diff == -1: score_factor = 1.15
    else: score_factor = 1.25

    if minute > 75 and abs(score_diff) == 1: score_factor *= 1.1

    if strength_diff > 1: strength_factor = 1.05
    elif strength_diff > 0: strength_factor = 1.02
    elif strength_diff == 0: strength_factor = 1.0
    elif strength_diff > -2: strength_factor = 0.98
    else: strength_factor = 0.95

    combined_motivation = (motivation_A + motivation_B) / 2
    intensity_mod = minute_factor * score_factor * strength_factor * combined_motivation
    intensity_mod = max(0.3, min(2.5, intensity_mod))

    finishing_mod = 1.0
    if max(motivation_A, motivation_B) > 1.2:
        finishing_mod = 0.9

    return intensity_mod, finishing_mod


def _context_intensity(intensity_mod):
    if intensity_mod < 0.9:
        return "low"
    if intensity_mod <= 1.3:
        return "medium"
    return "high"


def _cooldown_active(team, cooldown_a, cooldown_b):
    return (team == "A" and cooldown_a > 0) or (team == "B" and cooldown_b > 0)


def _build_context_event(
    minute,
    team,
    event_type,
    subtype,
    intensity_mod,
    pressure_a,
    pressure_b,
    possession,
    score_diff,
):
    return {
        "minute": minute,
        "team": team,
        "event_type": event_type,
        "subtype": subtype,
        "intensity": _context_intensity(intensity_mod),
        "pressure_a": pressure_a,
        "pressure_b": pressure_b,
        "possession": possession,
        "score_diff": score_diff,
    }


def generate_context_event(
    minute,
    possession,
    pressure_a,
    pressure_b,
    score_diff,
    intensity_mod,
    last_possession,
    cooldown_a,
    cooldown_b,
):
    possessing_pressure = pressure_a if possession == "A" else pressure_b
    opponent_pressure = pressure_b if possession == "A" else pressure_a
    team = possession

    if _cooldown_active(team, cooldown_a, cooldown_b):
        return None

    if possessing_pressure >= 0.65:
        if random.random() < 0.25:
            return _build_context_event(
                minute, team, "DANGEROUS_ATTACK", None,
                intensity_mod, pressure_a, pressure_b, possession, score_diff
            )
        return None

    if possession != last_possession and possessing_pressure <= 0.45:
        if random.random() < 0.40:
            return _build_context_event(
                minute, team, "COUNTERATTACK", None,
                intensity_mod, pressure_a, pressure_b, possession, score_diff
            )
        return None

    if random.random() < 0.08:
        subtype = random.choices(SET_PIECE_SUBTYPES, weights=SET_PIECE_WEIGHTS, k=1)[0]
        return _build_context_event(
            minute, team, "SET_PIECE", subtype,
            intensity_mod, pressure_a, pressure_b, possession, score_diff
        )

    if opponent_pressure >= 0.70:
        if random.random() < 0.20:
            return _build_context_event(
                minute, team, "DEFENSIVE_PRESSURE", None,
                intensity_mod, pressure_a, pressure_b, possession, score_diff
            )
        return None

    if opponent_pressure > possessing_pressure:
        if random.random() < 0.15:
            return _build_context_event(
                minute, team, "POSSESSION_UNDER_PRESSURE", None,
                intensity_mod, pressure_a, pressure_b, possession, score_diff
            )
        return None

    return None


def merge_event_logs(log, context_log):
    """
    Merge baseline and context logs into one minute-sorted timeline.
    Baseline tuples are converted to dictionaries with event_source="baseline".
    Context dictionaries are copied with event_source="context".
    """
    merged = []
    for minute, possession, event_type, subtype in log:
        merged.append({
            "minute": minute,
            "team": possession,
            "possession": possession,
            "event_type": event_type,
            "subtype": subtype,
            "event_source": "baseline",
        })
    for event in context_log:
        item = dict(event)
        item["event_source"] = "context"
        merged.append(item)
    return sorted(
        merged,
        key=lambda item: (item["minute"], 0 if item["event_source"] == "baseline" else 1),
    )


def simulate_match(strength_diff=0, motivation_A=1.0, motivation_B=1.0, include_context_log=False):
    score_a = 0; score_b = 0
    minute = 0
    possession = random.choice(["A", "B"])

    pressure_A = 0.5; pressure_B = 0.5
    risk = 0.0
    risk_threshold = 1.0

    log = []
    context_log = []
    cooldown_a = 0
    cooldown_b = 0
    last_possession = possession
    boost_until_A = 0; boost_until_B = 0
    boost_multiplier_A = 1.5; boost_multiplier_B = 1.5

    extra_minutes = random.randint(*EXTRA_TIME_RANGE)
    total_duration = MATCH_DURATION + extra_minutes

    # Проверка на финальный режим (сумма мотиваций > 2.4)
    high_stakes = (motivation_A + motivation_B) > 2.4

    def record_context_for_minute(intensity_mod):
        nonlocal cooldown_a, cooldown_b, last_possession
        if not include_context_log:
            return

        random_state = random.getstate()
        ctx = generate_context_event(
            minute, possession, pressure_A, pressure_B,
            score_a - score_b, intensity_mod,
            last_possession, cooldown_a, cooldown_b
        )
        random.setstate(random_state)

        if ctx:
            context_log.append(ctx)
            if ctx["team"] == "A":
                cooldown_a = CONTEXT_EVENT_COOLDOWN
            else:
                cooldown_b = CONTEXT_EVENT_COOLDOWN
        else:
            if cooldown_a > 0:
                cooldown_a -= 1
            if cooldown_b > 0:
                cooldown_b -= 1

        last_possession = possession

    while minute < total_duration:
        minute += 1
        extra_time = (minute > MATCH_DURATION)
        score_diff = score_a - score_b

        if risk_threshold > 1.0:
            risk_threshold = max(1.0, risk_threshold - 0.1)

        intensity_mod, finishing_mod = get_intensity_modifier(
            minute, score_diff, strength_diff, motivation_A, motivation_B, extra_time
        )

        def compute_risk_coeff(minute, score_diff, motivation, is_team_a=True):
            if not is_team_a: score_diff = -score_diff
            if score_diff < 0: coeff = 1.3
            elif score_diff == 0: coeff = 1.0
            elif score_diff == 1: coeff = 0.9
            else: coeff = 0.7
            if motivation > 1.1 and score_diff <= 1:
                coeff = max(coeff, 1.1)
            elif motivation < 0.95:
                coeff = min(coeff, 0.9)
            if minute > 75:
                if score_diff < 0 or (score_diff == 0 and motivation > 1.0):
                    coeff = max(coeff, 1.3)
                elif score_diff == 1 and motivation > 1.1:
                    coeff = max(coeff, 1.1)
            return max(0.5, min(1.5, coeff))

        risk_coeff_A = compute_risk_coeff(minute, score_diff, motivation_A, True)
        risk_coeff_B = compute_risk_coeff(minute, score_diff, motivation_B, False)

        base_growth = 0.035
        base_decay = 0.020

        if possession == "A":
            pressure_A = min(1.0, pressure_A + base_growth * risk_coeff_A)
            pressure_B = max(0.1, pressure_B - base_decay * (2 - risk_coeff_B))
        else:
            pressure_B = min(1.0, pressure_B + base_growth * risk_coeff_B)
            pressure_A = max(0.1, pressure_A - base_decay * (2 - risk_coeff_A))

        if minute <= boost_until_A:
            pressure_A = min(1.0, pressure_A + base_growth * 0.5 * boost_multiplier_A)
        if minute <= boost_until_B:
            pressure_B = min(1.0, pressure_B + base_growth * 0.5 * boost_multiplier_B)

        if possession == "A":
            if score_diff < 0: base_risk = random.uniform(0.08, 0.18)
            elif score_diff > 1: base_risk = random.uniform(0.03, 0.10)
            elif score_diff > 0: base_risk = random.uniform(0.06, 0.14)
            else: base_risk = random.uniform(0.06, 0.14)
        else:
            if score_diff > 0: base_risk = random.uniform(0.03, 0.10)
            elif score_diff < 0: base_risk = random.uniform(0.08, 0.18)
            else: base_risk = random.uniform(0.06, 0.14)

        delta = pressure_A - pressure_B if possession == "A" else pressure_B - pressure_A
        conflict_increment = 0.0
        if delta > 0:
            conflict_increment = delta * random.uniform(0.04, 0.12)

        risk += (base_risk + conflict_increment) * intensity_mod

        switch_base = 0.10 + (1 - (pressure_A + pressure_B) / 2) * 0.08
        if score_diff > 0: switch_base *= 0.9
        elif score_diff < 0: switch_base *= 1.1

        if random.random() < switch_base:
            possession = "B" if possession == "A" else "A"
            risk *= 0.5
            record_context_for_minute(intensity_mod)
            continue

        if risk < risk_threshold:
            record_context_for_minute(intensity_mod)
            continue

        # Событие
        risk = 0.0
        # Повышаем порог: в финале до 1.8, иначе до 1.5
        risk_threshold = 1.8 if high_stakes else 1.5

        roll = random.random()
        if roll < 0.60: event_type = "half"
        elif roll < 0.85: event_type = "big"
        elif roll < 0.95: event_type = "tight"
        else: event_type = "mistake"

        if random.random() < GOAL_CHANCE[event_type] * finishing_mod:
            if possession == "A":
                score_a += 1
                pressure_A = min(1.0, pressure_A + 0.15)
                pressure_B = max(0.1, pressure_B - 0.15)
                if motivation_B >= 0.95:
                    boost_until_B = minute + random.randint(2, 4)
                    if abs(score_a - score_b) >= 2:
                        boost_multiplier_B = 1.2
                    else:
                        boost_multiplier_B = 1.5
                else:
                    boost_until_B = 0
            else:
                score_b += 1
                pressure_B = min(1.0, pressure_B + 0.15)
                pressure_A = max(0.1, pressure_A - 0.15)
                if motivation_A >= 0.95:
                    boost_until_A = minute + random.randint(2, 4)
                    if abs(score_a - score_b) >= 2:
                        boost_multiplier_A = 1.2
                    else:
                        boost_multiplier_A = 1.5
                else:
                    boost_until_A = 0

            log.append((minute, possession, "GOAL", event_type))
            possession = "B" if possession == "A" else "A"
        else:
            log.append((minute, possession, "MISS", event_type))
            pressure_A *= 0.95
            pressure_B *= 0.95
            if random.random() < 0.20:
                if random.random() < GOAL_CHANCE[event_type] * 0.6 * finishing_mod:
                    if possession == "A":
                        score_a += 1
                        pressure_A = min(1.0, pressure_A + 0.15)
                        pressure_B = max(0.1, pressure_B - 0.15)
                        if motivation_B >= 0.95:
                            boost_until_B = minute + random.randint(2, 4)
                            boost_multiplier_B = 1.2 if abs(score_a - score_b) >= 2 else 1.5
                    else:
                        score_b += 1
                        pressure_B = min(1.0, pressure_B + 0.15)
                        pressure_A = max(0.1, pressure_A - 0.15)
                        if motivation_A >= 0.95:
                            boost_until_A = minute + random.randint(2, 4)
                            boost_multiplier_A = 1.2 if abs(score_a - score_b) >= 2 else 1.5
                    log.append((minute, possession, "GOAL_REBOUND", event_type))
                    possession = "B" if possession == "A" else "A"

        record_context_for_minute(intensity_mod)

    if include_context_log:
        return score_a, score_b, log, context_log
    return score_a, score_b, log


def simulate_many(n, strength_diff=0, motivation_A=1.0, motivation_B=1.0):
    results = []
    total_goals = 0; zero_zero = 0
    for _ in range(n):
        a, b, _ = simulate_match(strength_diff, motivation_A, motivation_B)
        results.append((a, b))
        total_goals += a + b
        if a == 0 and b == 0: zero_zero += 1
    avg_goals = total_goals / n
    return {"avg_goals": avg_goals, "0-0_rate": zero_zero / n, "results": results}


def _result_stats(results):
    total_goals = sum(a + b for a, b in results)
    zero_zero = sum(1 for a, b in results if a == 0 and b == 0)
    goals_a = sum(a for a, _ in results)
    goals_b = sum(b for _, b in results)
    return {
        "avg_goals": total_goals / len(results),
        "0-0_rate": zero_zero / len(results),
        "score_distribution": Counter(results),
        "goals_a": goals_a,
        "goals_b": goals_b,
    }


def _print_result_comparison(title, stats):
    print(title)
    print(f"avg goals per match: {stats['avg_goals']:.3f}")
    print(f"0-0 rate: {stats['0-0_rate']:.3%}")
    print(f"A/B goal balance: {stats['goals_a']} / {stats['goals_b']}")
    print("score distribution (top-10):")
    for score, count in stats["score_distribution"].most_common(10):
        print(f"  {score[0]}-{score[1]}: {count}")


def audit_context_extension(n=1000, strength_diff=0, motivation_A=1.0, motivation_B=1.0):
    """
    Runs paired simulations with and without context events.
    Context generation preserves the baseline random state, so scores should match.
    """
    baseline_results = []
    context_results = []
    context_counts = []
    context_types = Counter()
    context_teams = Counter()
    context_intensity = Counter()

    for _ in range(n):
        random_state = random.getstate()
        score_a, score_b, _ = simulate_match(strength_diff, motivation_A, motivation_B)
        baseline_results.append((score_a, score_b))

        random.setstate(random_state)
        score_a_ctx, score_b_ctx, _, context_log = simulate_match(
            strength_diff, motivation_A, motivation_B, include_context_log=True
        )
        context_results.append((score_a_ctx, score_b_ctx))
        context_counts.append(len(context_log))
        for event in context_log:
            context_types[event["event_type"]] += 1
            context_teams[event["team"]] += 1
            context_intensity[event["intensity"]] += 1

    baseline_stats = _result_stats(baseline_results)
    context_stats = _result_stats(context_results)
    avg_context = sum(context_counts) / len(context_counts)
    avg_goal_delta = context_stats["avg_goals"] - baseline_stats["avg_goals"]
    zero_context = sum(1 for count in context_counts if count == 0)
    ten_plus_context = sum(1 for count in context_counts if count >= 10)

    print("=== Result comparison: before / after ===")
    _print_result_comparison("Before context events:", baseline_stats)
    _print_result_comparison("After context events:", context_stats)
    print(f"avg goals delta: {avg_goal_delta:+.3f}")

    print("\n=== Context event statistics ===")
    print(f"avg context events per match: {avg_context:.3f}")
    print(f"min / max context events per match: {min(context_counts)} / {max(context_counts)}")
    print(f"distribution by event_type: {dict(context_types)}")
    print(f"distribution by team: {dict(context_teams)}")
    print(f"distribution by intensity: {dict(context_intensity)}")
    print(f"matches with 0 context events: {zero_context} ({zero_context / n:.3%})")
    print(f"matches with 10+ context events: {ten_plus_context} ({ten_plus_context / n:.3%})")

    print("\n=== Success criteria ===")
    print(f"avg goals unchanged within +/-0.1: {abs(avg_goal_delta) <= 0.1}")
    print(f"avg context events between 8 and 15: {8 <= avg_context <= 15}")
    print(f"matches with 0 context events below 5%: {zero_context / n < 0.05}")

    return {
        "baseline": baseline_stats,
        "with_context": context_stats,
        "avg_goal_delta": avg_goal_delta,
        "avg_context_events": avg_context,
        "context_event_counts": context_counts,
        "context_types": context_types,
        "context_teams": context_teams,
        "context_intensity": context_intensity,
        "zero_context_rate": zero_context / n,
        "ten_plus_context_rate": ten_plus_context / n,
    }


def save_results(stats, filename_prefix="match_results"):
    csv_filename = f"{filename_prefix}.csv"
    with open(csv_filename, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Match", "Goals_A", "Goals_B", "Total"])
        for i, (a, b) in enumerate(stats["results"], 1):
            writer.writerow([i, a, b, a + b])
    print(f"Детализация сохранена в {csv_filename}")

    txt_filename = f"{filename_prefix}_summary.txt"
    with open(txt_filename, "w", encoding="utf-8-sig") as f:
        f.write(f"Количество матчей: {len(stats['results'])}\n")
        f.write(f"Среднее голов за матч: {stats['avg_goals']:.3f}\n")
        f.write(f"Доля нулевых ничьих: {stats['0-0_rate']:.3%}\n\n")
        f.write("Распределение тоталов:\n")
        totals = [a + b for (a, b) in stats["results"]]
        dist = Counter(totals)
        for t in sorted(dist):
            count = dist[t]
            percent = count / len(totals) * 100
            f.write(f"  {t} голов: {count} матчей ({percent:.1f}%)\n")
    print(f"Сводка сохранена в {txt_filename}")


if __name__ == "__main__":
    try:
        n = int(input("Сколько матчей на каждый сценарий? (например, 1000): "))
    except ValueError:
        n = 1000
        print("Некорректный ввод, использую 1000 матчей.")

    scenarios = [
        {"name": "regular", "desc": "Рядовая игра, равные силы и мотивация",
         "strength_diff": 0, "motivation_A": 1.0, "motivation_B": 1.0},
        {"name": "final", "desc": "Финал, обе команды максимально мотивированы",
         "strength_diff": 0, "motivation_A": 1.3, "motivation_B": 1.3},
        {"name": "friendly", "desc": "Товарищеский матч, низкая мотивация",
         "strength_diff": 0, "motivation_A": 0.9, "motivation_B": 0.9},
        {"name": "must_win_vs_hold", "desc": "Одной команде нужна победа, другая играет на ничью",
         "strength_diff": 0, "motivation_A": 1.4, "motivation_B": 0.7}
    ]

    print(f"\n=== Автосерия: {n} матчей для каждого сценария ===\n")

    for scenario in scenarios:
        print(f"Сценарий: {scenario['desc']}")
        stats = simulate_many(n, scenario["strength_diff"],
                              scenario["motivation_A"], scenario["motivation_B"])

        avg = stats["avg_goals"]
        zero_rate = stats["0-0_rate"]
        print(f"Среднее голов за матч: {avg:.3f}")
        print(f"Доля 0-0: {zero_rate:.3%}")

        totals = [a + b for (a, b) in stats["results"]]
        dist = Counter(totals)
        print("Тоталы:")
        for t in sorted(dist):
            print(f"  {t} голов: {dist[t]} матчей ({dist[t]/len(totals)*100:.1f}%)")

        save_results(stats, f"match_results_{scenario['name']}")
        print("-" * 40)

    print("Автосерия завершена. Все файлы сохранены.")
