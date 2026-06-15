# MVP Match Loop Contract

## Purpose

This document defines the current MVP contract for the multi-episode match loop.

It records the decisions that must guide the next implementation step after the single-episode bridge proof.

This document does not introduce observer, reputation, career, tournament, or runtime LLM systems.

---

## Current Confirmed Foundation

The project already has:

* an executable scene/transition engine;
* verified scene graph execution;
* a single-episode bridge from match state to scene chain and back;
* bridge path resolution fixed so the bridge can run against the repository Excel files without temporary local copies.

The next unfinished MVP block is the multi-episode match loop.

---

## Match Scope for MVP

For this MVP layer, the match is a normal football match.

Included:

* 90 minutes of regular time;
* added time;
* final whistle after regular time plus added time.

Out of scope for this MVP layer:

* extra time;
* penalty shootout;
* cup formats requiring a winner;
* tournament rules;
* aggregate scores;
* replay rules.

Those belong to later competition/tournament format layers.

---

## Playable Episode Count

A match contains a bounded number of playable episodes.

Target range:

* minimum: 4 playable episodes;
* usual: 6-8 playable episodes;
* maximum: 10 playable episodes.

This is a distribution target across the whole match, not a match-ending condition.

The match does not end because the maximum number of playable episodes has been reached.

Instead, playable episodes must be distributed within the match timeline.

---

## Episode Timing

Playable episodes must occur inside the match timeline.

The late phase must not feel empty.

MVP rule:

* at least 2 playable episodes must occur after minute 60.

This rule applies even to low-importance or quiet matches.

The generator must avoid using all playable episodes too early.

---

## Playable Episode Types

A playable episode is shown only when the player can make a decision.

Playable episodes may come from all existing ownership states:

* `PLAYER_WITH_BALL`;
* `TEAMMATE_WITH_BALL`;
* `OPPONENT_WITH_BALL`.

This means MVP episodes are not limited to situations where the player has the ball.

Off-ball attacking and defensive participation are part of the MVP match loop.

---

## Start Ownership Selection

Playable episodes must not always start from the same scene.

The start ownership state must depend on match pressure.

Pressure means match-level pressure by team, currently represented as:

* `pressure_a`;
* `pressure_b`.

MVP rule:

* when team A pressure is higher, playable episodes should more often start from a team-A possession state;
* when team B pressure is higher, playable episodes should more often start from a team-B possession state;
* when pressure is balanced, start ownership distribution should remain mixed.

For the player-side MVP model, team-A possession can produce:

* `PLAYER_WITH_BALL` starts;
* `TEAMMATE_WITH_BALL` starts.

Team-B possession can produce:

* `OPPONENT_WITH_BALL` starts.

This must be a weighted dependency, not a hard deterministic rule.

High pressure should increase probability, not force every episode into the same ownership state.

The selector must avoid trivial repetition such as every playable episode starting from `fb_player_0002`.

A safe first implementation may use audited start-scene pools per ownership state.

It must not infer start-scene suitability from scene text without verification.

---

## Non-Playable Critical Match Events

The match may contain critical events where the player character is not directly involved.

These are shown as short text updates without player choice.

Allowed MVP non-playable critical events:

* goal;
* penalty;
* red card.

Other team events are out of scope for this MVP layer.

Examples of out-of-scope non-playable events:

* ordinary yellow cards;
* injuries;
* substitutions;
* generic momentum shifts;
* ordinary pressure changes;
* routine attacks without a critical outcome.

The purpose is to show that the match world continues outside the player character, without turning the game into passive match viewing.

---

## Relationship Between Playable Episodes and Critical Events

Playable episodes and non-playable critical events are separate match-level outputs.

Playable episodes:

* use the executable scene graph;
* require player choice;
* return an `EpisodeResult`;
* update match state.

Non-playable critical events:

* do not use the scene graph;
* do not ask for player choice;
* may update match state directly;
* must be logged clearly.

Example:

```text
63' Goal. Opponent scores from a corner. Score: 0-1.
```

This is a match event, not a playable scene.

---

## Match State Responsibilities

The multi-episode match loop must keep match state across episodes.

Minimum state:

* current minute;
* added time;
* final whistle minute;
* score;
* possession;
* pressure;
* risk;
* episode count;
* playable episode log;
* non-playable critical event log.

---

## Verification Requirements

The first multi-episode match loop implementation must verify:

* total playable episodes are between 4 and 10;
* usual run profile tends toward 6-8 playable episodes;
* at least 2 playable episodes occur after minute 60;
* playable episodes do not all occur too early;
* every playable episode starts from an existing scene;
* every playable episode uses existing executable transitions;
* match state persists across episodes;
* score can be changed by playable episode results;
* score can be changed by non-playable critical goal events;
* penalty and red-card events can be logged without player choice;
* start ownership varies across playable episodes when pressure conditions justify it;
* higher team pressure increases the probability of that team's possession ownership starting an episode;
* audited start-scene pools are used instead of text inference;
* observer, reputation, relationship and career memory are not modified;
* existing scene graph verification still passes before match loop execution;
* bridge verification still passes before or during match loop execution.

---

## Current Decision

The next MVP implementation target is:

```text
match initialization
-> scheduled playable episodes across 90 minutes + added time
-> pressure-weighted start ownership selection
-> playable episode execution through the bridge
-> match state updates
-> critical non-playable event logging
-> final whistle
-> match loop verification report
```

The next code artifact should extend the small multi-episode match loop with audited pressure-based start ownership selection, not add a new gameplay layer.
