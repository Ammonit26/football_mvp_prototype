"""
match_state_manager.py
======================
Связывает EpisodeOutcome → MatchState → NextEpisodeStarter.

Встраивается в существующую архитектуру без изменений engine и runner.
Заменяет choose_random_start_scene() на контекстный выбор стартовой сцены.

Использование в smoke_test_episodes.py:
    from match_state_manager import MatchStateManager
    msm = MatchStateManager(scenes)
    ...
    start_scene_id = msm.choose_start_scene()          # вместо choose_random_start_scene
    ...
    msm.update(episode_outcome_code, next_owner, next_scene_owner_from_forced_end)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

# Минут на матч (условных)
MATCH_DURATION = 90

# Диапазон временного прыжка между эпизодами (мин)
EPISODE_TIME_JUMP_MIN = 8
EPISODE_TIME_JUMP_MAX = 15

# Финальный отрезок матча
FINAL_STRETCH_MINUTE = 75

# Целевое число эпизодов за матч
EPISODES_TARGET_MIN = 6
EPISODES_TARGET_MAX = 8

# Вероятность фонового гола соперника или своей команды между эпизодами
BACKGROUND_GOAL_PROB = 0.07  # на каждую сторону за временной прыжок

# EpisodeOutcome-коды, которые завершают матч через гол
GOAL_OUTCOMES = {"GOAL", "DEFLECTION_GOAL"}

# EpisodeOutcome-коды по категории next_owner
OUTCOME_TO_NEXT_OWNER: Dict[str, str] = {
    "GOAL":                   "CENTER_RESTART",
    "MISS_GOAL_KICK":         "OPPONENT_WITH_BALL",
    "KEEPER_HELD":            "OPPONENT_WITH_BALL",
    "SAVE_CORNER":            "SET_PIECE_CORNER",
    "SAVE_REBOUND_PLAYER":    "PLAYER_WITH_BALL",
    "SAVE_REBOUND_TEAMMATE":  "TEAMMATE_WITH_BALL",
    "SAVE_REBOUND_OPPONENT":  "OPPONENT_WITH_BALL",
    "POST_CORNER":            "SET_PIECE_CORNER",
    "POST_REBOUND_PLAYER":    "PLAYER_WITH_BALL",
    "POST_REBOUND_TEAMMATE":  "TEAMMATE_WITH_BALL",
    "POST_REBOUND_OPPONENT":  "OPPONENT_WITH_BALL",
    "DEFLECTION_GOAL":        "CENTER_RESTART",
    "DEFLECTION_CORNER":      "SET_PIECE_CORNER",
    "DEFLECTION_POST":        "LOOSE_BALL",
    "FORCED_END":             None,  # берётся из next_scene["owner"] напрямую
}

# Маппинг next_owner → scene_owner следующего эпизода
# CENTER_RESTART, SET_PIECE_CORNER, LOOSE_BALL — фоновые рестарты,
# эпизод стартует со сцены, соответствующей momentum после рестарта
RESTART_TO_SCENE_OWNER: Dict[str, str] = {
    "CENTER_RESTART":      "OPPONENT_WITH_BALL",   # после гола — соперник давит или мы строимся
    "SET_PIECE_CORNER":    "PLAYER_WITH_BALL",      # угловой — атакующая ситуация
    "LOOSE_BALL":          "OPPONENT_WITH_BALL",    # рикошет/вынос — борьба
    "PLAYER_WITH_BALL":    "PLAYER_WITH_BALL",
    "TEAMMATE_WITH_BALL":  "TEAMMATE_WITH_BALL",
    "OPPONENT_WITH_BALL":  "OPPONENT_WITH_BALL",
}


# ---------------------------------------------------------------------------
# Состояние матча
# ---------------------------------------------------------------------------

@dataclass
class MatchState:
    score_home: int = 0
    score_away: int = 0
    match_minute: int = 0
    episode_count: int = 0
    last_outcome: Optional[str] = None          # последний EpisodeOutcome.code
    restart_type: Optional[str] = None          # next_owner из последнего outcome
    momentum: str = "NEUTRAL"                   # ATTACKING / DEFENDING / NEUTRAL
    is_final_stretch: bool = False              # минута >= FINAL_STRETCH_MINUTE

    def score_diff(self) -> int:
        """Положительное — ведём, отрицательное — проигрываем."""
        return self.score_home - self.score_away

    def is_match_over(self) -> bool:
        return self.match_minute >= MATCH_DURATION

    def episodes_exhausted(self) -> bool:
        return self.episode_count >= EPISODES_TARGET_MAX


# ---------------------------------------------------------------------------
# NextEpisodeStarter
# ---------------------------------------------------------------------------

@dataclass
class NextEpisodeStarter:
    episode_number: int
    match_minute: int
    context: str                    # EpisodeOutcome.code или "MATCH_START"
    score_home: int
    score_away: int
    scene_owner: str                # PLAYER_WITH_BALL / TEAMMATE_WITH_BALL / OPPONENT_WITH_BALL
    start_scene_id: str


# ---------------------------------------------------------------------------
# MatchStateManager
# ---------------------------------------------------------------------------

class MatchStateManager:
    """
    Управляет состоянием матча между эпизодами.

    Параметры
    ----------
    scenes : dict
        Загруженный пул сцен из engine.load_scenes() после enrich_scene_types().
    home_team_is_player : bool
        True — персонаж играет за домашнюю команду.
    """

    def __init__(
        self,
        scenes: Dict[str, object],
        home_team_is_player: bool = True,
    ) -> None:
        self.scenes = scenes
        self.home_team_is_player = home_team_is_player
        self.state = MatchState()

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def choose_start_scene(self) -> str:
        """
        Возвращает scene_id стартовой сцены следующего эпизода.
        Заменяет choose_random_start_scene() из runner.

        При первом вызове (episode_count == 0) — старт матча, нейтральный контекст.
        """
        if self.state.episode_count == 0:
            scene_owner = random.choice([
                "PLAYER_WITH_BALL",
                "TEAMMATE_WITH_BALL",
                "OPPONENT_WITH_BALL",
            ])
        else:
            scene_owner = self._resolve_scene_owner()

        candidates = self._candidates_for_owner(scene_owner)

        # Фолбэк: если нет кандидатов под нужный owner — берём любого dynamic
        if not candidates:
            candidates = self._all_dynamic_candidates()

        if not candidates:
            raise ValueError("No dynamic start-scene candidates available")

        return random.choice(sorted(candidates))

    def update(
        self,
        outcome_code: str,
        next_owner: Optional[str] = None,
        forced_end_scene_owner: Optional[str] = None,
    ) -> None:
        """
        Обновляет MatchState после завершения эпизода.

        Параметры
        ----------
        outcome_code : str
            EpisodeOutcome.code из SHOT_TERMINAL_OUTCOMES или "FORCED_END".
        next_owner : str, optional
            terminal["next_owner"] из resolve_shot_terminal_outcome().
            Для FORCED_END — None.
        forced_end_scene_owner : str, optional
            next_scene["owner"] при FORCED_END.
        """
        self.state.episode_count += 1
        self.state.last_outcome = outcome_code

        # Обновляем счёт
        if outcome_code in GOAL_OUTCOMES:
            self.state.score_home += 1

        # Определяем restart_type
        if outcome_code == "FORCED_END":
            # Владелец мяча берётся из сцены напрямую
            self.state.restart_type = forced_end_scene_owner or "NEUTRAL"
        else:
            self.state.restart_type = next_owner or OUTCOME_TO_NEXT_OWNER.get(outcome_code)

        # Фоновый ход матча: время и случайные голы
        self._advance_match_time()

        # Momentum
        self.state.momentum = self._compute_momentum()

        # Финальный отрезок
        self.state.is_final_stretch = self.state.match_minute >= FINAL_STRETCH_MINUTE

    def get_match_state(self) -> MatchState:
        return self.state

    def is_match_over(self) -> bool:
        return self.state.is_match_over() or self.state.episodes_exhausted()

    def next_episode_starter(self, start_scene_id: str) -> NextEpisodeStarter:
        """Строит NextEpisodeStarter для логирования и карьерных систем."""
        return NextEpisodeStarter(
            episode_number=self.state.episode_count,
            match_minute=self.state.match_minute,
            context=self.state.last_outcome or "MATCH_START",
            score_home=self.state.score_home,
            score_away=self.state.score_away,
            scene_owner=self._resolve_scene_owner(),
            start_scene_id=start_scene_id,
        )

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _resolve_scene_owner(self) -> str:
        """
        Переводит restart_type в scene_owner следующего эпизода.
        CENTER_RESTART / SET_PIECE_CORNER / LOOSE_BALL — фоновые рестарты,
        не требуют специальных сцен.
        """
        restart = self.state.restart_type
        if not restart:
            return "NEUTRAL_FALLBACK"
        return RESTART_TO_SCENE_OWNER.get(restart, "OPPONENT_WITH_BALL")

    def _advance_match_time(self) -> None:
        """Прыжок условного времени + случайные фоновые голы."""
        jump = random.randint(EPISODE_TIME_JUMP_MIN, EPISODE_TIME_JUMP_MAX)
        self.state.match_minute = min(
            self.state.match_minute + jump,
            MATCH_DURATION,
        )

        # Фоновые голы (редко, независимо)
        if random.random() < BACKGROUND_GOAL_PROB:
            self.state.score_home += 1
        if random.random() < BACKGROUND_GOAL_PROB:
            self.state.score_away += 1

    def _compute_momentum(self) -> str:
        """
        Простая эвристика momentum на основе последнего outcome и счёта.
        Используется для выбора стартовой сцены следующего эпизода.
        """
        restart = self.state.restart_type

        # После гола соперника — защита
        if restart == "CENTER_RESTART" and not self.home_team_is_player:
            return "DEFENDING"

        # После гола — атака продолжается или нейтраль
        if restart in {"PLAYER_WITH_BALL", "TEAMMATE_WITH_BALL", "SET_PIECE_CORNER"}:
            return "ATTACKING"

        if restart in {"OPPONENT_WITH_BALL", "CENTER_RESTART"}:
            return "DEFENDING"

        return "NEUTRAL"

    def _candidates_for_owner(self, scene_owner: str) -> List[str]:
        """Динамические сцены с нужным owner и наличием действий."""
        return [
            scene_id
            for scene_id, scene in self.scenes.items()
            if (
                str(scene.get("scene_type", "dynamic")) == "dynamic"
                and scene.get("owner") == scene_owner
                and scene.get("available_player_actions")
            )
        ]

    def _all_dynamic_candidates(self) -> List[str]:
        """Все динамические сцены — фолбэк последней инстанции."""
        return [
            scene_id
            for scene_id, scene in self.scenes.items()
            if (
                str(scene.get("scene_type", "dynamic")) == "dynamic"
                and scene.get("available_player_actions")
            )
        ]
