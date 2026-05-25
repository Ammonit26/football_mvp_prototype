# Football Match Generator Verification Report

Status: PASS

## Scope

- Source of truth: 3 canonical scene libraries, 3 executable transition libraries, test_transitions_multi_executable.py
- Start scene: fb_player_0002
- Simulation runs: 20
- Max steps per run: 50

## Counts

- Scenes: 482
- Transition rows: 3360
- Transition keys: 3360
- Max pool size allowed: 4
- Max pool tier spread allowed: 1

## Verification

- Missing transitions: 0
- Broken source links: 0
- Broken next_scene_id links: 0
- Empty allowed_next_scene_ids pools: 0
- Broken pool links: 0
- Pool ownership contradictions: 0
- Expected ownership semantic violations: 0
- Excessive semantic spread inside pools: 0
- Invalid outcomes: 0
- Actions not present in source scene: 0
- Scenes without actions: 0
- Orphan scenes: 0
- Dead-end scenes: 0
- Dead-end pools: 0
- Disconnected scenes from start: 0
- Weak connected graph parts: 1
- Weak component sizes: [482]

## Simulation

- Successful runs: 20 / 20
- Average executed steps: 50.00
- Non-pool resolver uses: 0

## Example Chains

- fb_player_0007 [PLAYER_WITH_BALL, tier 0] -> Отдать пас на фланг -> SUCCESS -> selected fb_teamm_0045 [TEAMMATE_WITH_BALL, tier 1]
  Pool: fb_teamm_0045||fb_teamm_0027||fb_teamm_0036||fb_teamm_0033
  Semantic continuity: successful flank pass: ball ownership transfers to teammate, then the next scene is selected only from TEAMMATE_WITH_BALL pool
- fb_player_0002 [PLAYER_WITH_BALL, tier 0] -> Пройти соперника дриблингом -> SUCCESS -> selected fb_player_0158 [PLAYER_WITH_BALL, tier 1]
  Pool: fb_player_0305||fb_player_0096||fb_player_0158||fb_player_0015
  Semantic continuity: successful dribble forward: retained ball and moved from defensive third into a more advanced possession state
- fb_player_0002 [PLAYER_WITH_BALL, tier 0] -> отдать пас назад -> SUCCESS -> selected fb_teamm_0004 [TEAMMATE_WITH_BALL, tier 0]
  Pool: fb_teamm_0004||fb_teamm_0017||fb_teamm_0008||fb_teamm_0001
  Semantic continuity: successful pass backward: ball moves to teammate for a safer deep buildup reset
- fb_player_0002 [PLAYER_WITH_BALL, tier 0] -> Пройти соперника дриблингом -> FAIL -> selected fb_opp_0062 [OPPONENT_WITH_BALL, tier 4]
  Pool: fb_opp_0060||fb_opp_0062||fb_opp_0061||fb_opp_0063
  Semantic continuity: failed dribble near own box: immediate dangerous turnover / opponent pressure near our goal
- fb_opp_0001 [OPPONENT_WITH_BALL, tier 0] -> рывок вперед, постараться накрыть чисто -> SUCCESS -> selected fb_player_0212 [PLAYER_WITH_BALL, tier 4]
  Pool: fb_player_0216||fb_player_0218||fb_player_0215||fb_player_0212
  Semantic continuity: successful defensive pressure high up: regain near opponent goal with attacking initiative
- fb_opp_0001 [OPPONENT_WITH_BALL, tier 0] -> остаться в зоне, мяч может вернуться -> FAIL -> selected fb_opp_0018 [OPPONENT_WITH_BALL, tier 1]
  Pool: fb_opp_0021||fb_opp_0013||fb_opp_0010||fb_opp_0018
  Semantic continuity: failed defensive pressure: opponent escapes first line and progresses one danger band
- fb_teamm_0001 [TEAMMATE_WITH_BALL, tier 0] -> открыться навстречу под пас -> SUCCESS -> selected fb_teamm_0016 [TEAMMATE_WITH_BALL, tier 0]
  Pool: fb_teamm_0002||fb_teamm_0015||fb_teamm_0011||fb_teamm_0016
  Semantic continuity: supporting run while teammate has ball: possession remains with teammate in nearby buildup states
