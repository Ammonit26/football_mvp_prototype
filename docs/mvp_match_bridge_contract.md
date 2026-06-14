# MVP Match Bridge Contract

## Purpose

This document defines the minimal contract between the existing executable scene/transition engine and the existing match simulator.

It does not introduce a new game system.

Its purpose is to make the current unfinished MVP block explicit: connecting playable scene episodes to match state.

---

## Verified Current State

### Executable scene/transition engine

Current implementation: `test_transitions_multi_executable.py`.

Verified responsibilities:

* loads three scene libraries;
* loads three transition libraries;
* stores scenes by `scene_id`;
* exposes player-facing scene text and available player actions;
* resolves transitions by `(source_scene_id, player_action, outcome)`;
* selects the next scene from `allowed_next_scene_ids`;
* verifies graph completeness, ownership consistency, dead ends, orphan scenes and reachability;
* supports an interactive console mode.

Current verification report status: `PASS`.

The scene/transition graph is executable, connected and internally valid.

### Match simulator

Current implementation: `tools/mvp_simm.py`.

Verified responsibilities:

* simulates match minutes;
* tracks score;
* tracks possession;
* tracks pressure;
* tracks risk accumulation;
* creates match events such as `GOAL`, `MISS` and `GOAL_REBOUND`;
* supports scenario-level parameters such as team strength and motivation.

The match simulator does not currently read Excel scene libraries and does not use `scene_id`.

---

## Confirmed MVP Gap

The current MVP has two valid but separate layers:

1. Scene graph layer: player decisions, scene text and transitions.
2. Match state layer: minute, score, pressure, possession, risk and goals.

The unfinished MVP block is the bridge between these layers.

Until this bridge exists, the player can execute scene chains, but those chains do not meaningfully exist inside match state.

The match simulator can produce goals and match statistics, but it does not use the scene libraries or player decisions.

---

## Existing Conceptual Constraint

The bridge must follow the existing project model:

* a match is not a full 90-minute action simulation;
* a match consists of key episodes;
* an episode is a sequence of connected scenes;
* decisions inside the match must create readable consequences;
* match decisions and results must be able to feed later observer/reputation processing.

Therefore the bridge should connect match state to episodes, not replace the scene graph and not simulate every football action in real time.

---

## Minimal Terms

### Match State

The match-level state owned by the match simulator.

Minimum fields:

* `minute`
* `score_a`
* `score_b`
* `possession`
* `pressure_a`
* `pressure_b`
* `risk`
* `event_type`
* `match_context`

`match_context` must stay minimal for MVP. It may include:

* match importance;
* motivation;
* strength difference;
* current score difference;
* late-game flag;
* coach instruction tag, if later verified as present.

### Episode

A local playable situation inside the match.

An episode starts when match state requires a playable decision moment.

An episode contains one or more executable scenes.

An episode ends when it returns a compact outcome to match state.

### Scene Step

One transition inside the existing scene graph:

* current `scene_id`;
* player action;
* action outcome;
* selected transition;
* selected next scene.

### Episode Result

The compact output returned from the scene graph to match state.

Minimum fields:

* `start_scene_id`
* `end_scene_id`
* `steps_played`
* `actions_taken`
* `final_ball_owner`
* `field_tier_delta`
* `created_chance`
* `goal_delta_a`
* `goal_delta_b`
* `turnover`
* `pressure_delta_a`
* `pressure_delta_b`
* `significance_tags`

`significance_tags` are not reputation changes. They are raw event descriptors for later observer evaluation.

Examples:

* `safe_reset`
* `progressive_action`
* `dangerous_turnover`
* `chance_created`
* `goal_scored`
* `missed_big_chance`
* `defensive_recovery`

---

## Direction: Match State -> Episode

The match simulator may request an episode when accumulated match state reaches a playable threshold.

Minimum trigger inputs:

* current minute;
* score difference;
* possession;
* pressure difference;
* risk level;
* event type, if generated;
* match importance / motivation context.

The bridge should then choose a valid starting scene from the existing scene graph.

For MVP, start-scene selection must be conservative.

Allowed first implementation:

* use explicit mapped start scenes for a small number of match situations;
* avoid automatic semantic inference over all scenes until the mapping is audited;
* preserve `fb_player_0002` as the known verified default start scene unless a more specific audited mapping exists.

---

## Direction: Episode -> Match State

After the player completes an episode, the scene graph returns an `Episode Result`.

The match simulator applies only compact effects:

* score change;
* possession change;
* pressure change;
* risk reset or risk increase;
* match log entry;
* raw significant event tags.

The scene graph must not directly update reputation, relationship, opportunities or career memory.

Those belong to later observer processing.

---

## Boundary With Observer System

For MVP bridge work, observer/reputation logic is downstream.

The bridge may emit raw event descriptors.

It must not decide:

* how the coach interprets the event;
* how teammates interpret the event;
* how fans or press react;
* relationship changes;
* reputation changes;
* new opportunities or restrictions.

Those decisions must remain in the documented chain:

`Event -> Observer Evaluation -> Interpretation -> Memory Update -> Relationship Update -> Reputation Change -> Opportunities / Restrictions`.

---

## What Must Not Be Done Yet

Do not add a new runtime LLM layer.

Do not replace Excel scene libraries.

Do not rewrite the current scene graph before the bridge contract is tested.

Do not design a full tactical simulator.

Do not create observer/reputation implementation before match event output is stable.

Do not infer scene semantics from text until a verification pass exists.

---

## First Implementation Target

Create a small integration module or mode that proves one loop:

1. initialize match state;
2. trigger one playable episode;
3. run existing scene/transition logic for a bounded number of scene steps;
4. produce an `Episode Result`;
5. apply the result back to match state;
6. write a verification report for the bridge.

This is the next executable MVP block.

---

## Verification Requirements

The first bridge implementation must verify:

* every selected start scene exists;
* every selected action has both `SUCCESS` and `FAIL` transitions;
* every transition result resolves through `allowed_next_scene_ids`;
* no episode ends in a dead end;
* match state updates are deterministic under a fixed seed;
* no reputation, relationship or career memory is changed by the bridge;
* existing scene graph verification still passes after integration work.

---

## Current Decision

The next MVP block is not a new gameplay layer.

The next MVP block is the integration bridge:

`match state -> playable episode -> scene chain -> episode result -> match state`.
