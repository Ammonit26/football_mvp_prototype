import random
import csv
from collections import Counter

MATCH_DURATION = 90
EXTRA_TIME_RANGE = (1, 7)
GOAL_CHANCE = {
    "tight": 0.18, "half": 0.30, "big": 0.45, "mistake": 0.60
}

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


def simulate_match(strength_diff=0, motivation_A=1.0, motivation_B=1.0):
    score_a = 0; score_b = 0
    minute = 0
    possession = random.choice(["A", "B"])

    pressure_A = 0.5; pressure_B = 0.5
    risk = 0.0
    risk_threshold = 1.0

    log = []
    boost_until_A = 0; boost_until_B = 0
    boost_multiplier_A = 1.5; boost_multiplier_B = 1.5

    extra_minutes = random.randint(*EXTRA_TIME_RANGE)
    total_duration = MATCH_DURATION + extra_minutes

    # Проверка на финальный режим (сумма мотиваций > 2.4)
    high_stakes = (motivation_A + motivation_B) > 2.4

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
            continue

        if risk < risk_threshold:
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
