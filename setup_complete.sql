-- ============================================================
-- P2A COACH HUB — COMPLETE SCHEMA
-- Run once against heliumdb in Replit Shell:
--   psql $DATABASE_URL -f schema_complete.sql
-- ============================================================

-- Athletes
CREATE TABLE IF NOT EXISTS athletes (
  id               SERIAL PRIMARY KEY,
  name             TEXT NOT NULL,
  initials         TEXT,
  event_group      TEXT,
  squad            TEXT,
  assessment_code  TEXT UNIQUE,   -- links to speed-assessment.online
  dob              DATE,
  is_active        BOOLEAN DEFAULT true,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Macrocycle blocks (imported from Excel)
CREATE TABLE IF NOT EXISTS macrocycle_blocks (
  id                  SERIAL PRIMARY KEY,
  season              TEXT NOT NULL,
  block_number        INT  NOT NULL,
  block_name          TEXT,
  start_date          DATE,
  end_date            DATE,
  mesocycle_phase     TEXT,
  strength_label      TEXT,
  speed_label         TEXT,
  intensity_level     TEXT,
  volume_level        TEXT,
  sc_phase_code       TEXT,
  UNIQUE (season, block_number)
);

-- Track session library
CREATE TABLE IF NOT EXISTS sessions (
  id              SERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  description     TEXT,
  session_type    TEXT,
  event_group     TEXT,
  training_phase  TEXT,
  intensity_level TEXT,
  tags            TEXT[] DEFAULT '{}',
  source_year     INT,
  is_archived     BOOLEAN DEFAULT false,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Videos attached to sessions
CREATE TABLE IF NOT EXISTS session_videos (
  id            SERIAL PRIMARY KEY,
  session_id    INT REFERENCES sessions(id) ON DELETE CASCADE,
  video_type    TEXT CHECK (video_type IN ('reference','feedback')),
  url           TEXT NOT NULL,
  title         TEXT,
  notes         TEXT,
  athlete_name  TEXT,
  session_date  DATE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Scheduling layer — athlete x session x date
CREATE TABLE IF NOT EXISTS athlete_schedule (
  id             SERIAL PRIMARY KEY,
  athlete_id     INT REFERENCES athletes(id) ON DELETE CASCADE,
  session_id     INT REFERENCES sessions(id),
  scheduled_date DATE NOT NULL,
  block_number   INT,
  status         TEXT DEFAULT 'scheduled',  -- scheduled | completed | skipped
  coach_notes    TEXT,
  athlete_notes  TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (athlete_id, scheduled_date, session_id)
);

-- S&C phases
CREATE TABLE IF NOT EXISTS sc_phases (
  id                    SERIAL PRIMARY KEY,
  name                  TEXT NOT NULL,
  short_code            TEXT NOT NULL,
  bompa_label           TEXT,
  macrocycle_phase      TEXT,
  macrocycle_blocks     TEXT,
  typical_weeks         TEXT,
  sessions_per_week_min INT DEFAULT 2,
  sessions_per_week_max INT DEFAULT 2,
  sets_min              INT,
  sets_max              INT,
  reps_min              INT,
  reps_max              INT,
  load_pct_min          INT,
  load_pct_max          INT,
  rest_seconds_min      INT,
  rest_seconds_max      INT,
  tempo_guidance        TEXT,
  rpe_target_min        INT,
  rpe_target_max        INT,
  primary_goal          TEXT,
  sprint_specific_focus TEXT,
  display_order         INT
);

-- S&C exercise library
CREATE TABLE IF NOT EXISTS sc_exercises (
  id                  SERIAL PRIMARY KEY,
  name                TEXT NOT NULL,
  movement_pattern    TEXT,
  primary_muscles     TEXT[],
  secondary_muscles   TEXT[],
  equipment           TEXT[],
  coaching_cues       TEXT,
  common_errors       TEXT,
  reference_video_url TEXT,
  is_primary          BOOLEAN DEFAULT true,
  suitable_phase_ids  INT[],
  difficulty_level    TEXT,
  sprint_relevance    TEXT,
  tags                TEXT[] DEFAULT '{}'
);

-- S&C workout templates
CREATE TABLE IF NOT EXISTS sc_workout_templates (
  id             SERIAL PRIMARY KEY,
  name           TEXT NOT NULL,
  sc_phase_id    INT REFERENCES sc_phases(id),
  session_label  TEXT,
  session_focus  TEXT,
  warmup_notes   TEXT,
  cooldown_notes TEXT,
  coach_notes    TEXT,
  week_placement TEXT,
  tags           TEXT[] DEFAULT '{}',
  display_order  INT
);

-- Exercises within a template
CREATE TABLE IF NOT EXISTS sc_template_exercises (
  id               SERIAL PRIMARY KEY,
  template_id      INT REFERENCES sc_workout_templates(id) ON DELETE CASCADE,
  exercise_id      INT REFERENCES sc_exercises(id),
  order_index      INT NOT NULL,
  block_label      TEXT,
  sets             INT,
  reps_min         INT,
  reps_max         INT,
  load_pct_1rm     INT,
  load_notes       TEXT,
  rest_seconds     INT,
  tempo            TEXT,
  superset_group   INT,
  coaching_cues    TEXT,
  progression_note TEXT
);

-- Athlete 1RM records
CREATE TABLE IF NOT EXISTS sc_athlete_maxes (
  id           SERIAL PRIMARY KEY,
  athlete_id   INT REFERENCES athletes(id),
  exercise_id  INT REFERENCES sc_exercises(id),
  one_rep_max  NUMERIC(6,2),
  test_date    DATE,
  test_type    TEXT,
  notes        TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- S&C workout logs
CREATE TABLE IF NOT EXISTS sc_workout_logs (
  id                   SERIAL PRIMARY KEY,
  athlete_id           INT REFERENCES athletes(id),
  template_id          INT REFERENCES sc_workout_templates(id),
  sc_phase_id          INT REFERENCES sc_phases(id),
  workout_date         DATE NOT NULL,
  macrocycle_block     TEXT,
  overall_rpe          INT CHECK (overall_rpe BETWEEN 1 AND 10),
  session_duration_min INT,
  coach_notes          TEXT,
  athlete_feedback     TEXT,
  created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Set-by-set logs
CREATE TABLE IF NOT EXISTS sc_set_logs (
  id             SERIAL PRIMARY KEY,
  workout_log_id INT REFERENCES sc_workout_logs(id) ON DELETE CASCADE,
  exercise_id    INT REFERENCES sc_exercises(id),
  set_number     INT,
  reps_completed INT,
  load_kg        NUMERIC(6,2),
  rpe            INT CHECK (rpe BETWEEN 1 AND 10),
  notes          TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Performance testing
CREATE TABLE IF NOT EXISTS performance_tests (
  id               SERIAL PRIMARY KEY,
  athlete_id       INT REFERENCES athletes(id),
  test_date        DATE NOT NULL,
  macrocycle_block INT,
  test_protocol    TEXT,
  conditions       TEXT,
  notes            TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Individual test results
CREATE TABLE IF NOT EXISTS test_results (
  id             SERIAL PRIMARY KEY,
  test_id        INT REFERENCES performance_tests(id) ON DELETE CASCADE,
  metric         TEXT NOT NULL,
  value          NUMERIC(8,3),
  unit           TEXT,
  attempt_number INT DEFAULT 1,
  wind_reading   NUMERIC(4,2),
  is_pb          BOOLEAN DEFAULT false,
  notes          TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Benchmarks (shared with speed-assessment.online)
CREATE TABLE IF NOT EXISTS performance_benchmarks (
  id          SERIAL PRIMARY KEY,
  sport       TEXT,
  event_group TEXT,
  metric      TEXT NOT NULL,
  age_group   TEXT,
  gender      TEXT,
  level       TEXT,
  value       NUMERIC(8,3),
  unit        TEXT,
  source      TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_type     ON sessions (session_type);
CREATE INDEX IF NOT EXISTS idx_sessions_tags     ON sessions USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_schedule_athlete  ON athlete_schedule (athlete_id, scheduled_date);
CREATE INDEX IF NOT EXISTS idx_test_results_test ON test_results (test_id);
CREATE INDEX IF NOT EXISTS idx_sc_template_ex    ON sc_template_exercises (template_id);


-- ============================================================
-- SEED: 79 track sessions from Final Surge library
-- ============================================================
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (1, '100m & 200m start practice', '1 x30m, 1 x40m & 1x 50m Block starts
Rest = 3mins, 4 mins & 5mins
2x50m bend - 5mins break
1 x100m (50m bend + 50m straight) 6mins break
1 x120m sprint', 'Technical', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (2, '100m Race reparation work', '100m work
3 x 30m sprints - 3mins rest between
2 x 60m sprints - 6 mins rest between
2 x 100m - 10 -12mins or Full recovery', 'Speed', '100m', 'Competition', 'Max', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (3, '100m Tempo / Speed Endurance', '5min jog, active warmup
5min running drills
4 x 60m run throughs
2 Sets of 3-4x100m WB +1min to be fresh -
Hold form and run tall, no quicker than 80%
6 mins break between sets', 'Speed_Endurance', '100m', 'Base', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (4, '100m form runs', 'Extended In & Out Warm Up
Stretches, Activation and SMR
4 x 50m run throughs
3 x 10 x Wickets at 5-6 “shoe” spacing - 5min break (20m fast run in)
2 x 3 x 100m relaxed form runs - WB + 1 min
8 mins betweens sets', 'Technical', '100m', 'Base', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (5, '100m or 400m preparation work', '100m / 200m work
3 x 30m sprints - 2mins rest between
2 x 60m sprints - 5 mins rest between
2 x 100m - 10 mins or Full recovery
1 x 150m
200m = FAST 1 x 100 - 150 - 200m (10 mins between reps)
400m work - Split 400s
2 x 60m bend ( Race start setup )
1 x 300m 400m start to top bend - 10-12mins recovery
1 x 200m (200m start to 400 Finish mark) 8mins recovery
1 x 100m to Finish line', 'Speed', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (6, '150-80s', 'Active warmup and running drills
4x60m run throughs
*Short Hill Sprints*
3 x10 sec hill - WB = 60-90secs recovery
2 x13-15sec hill - WB = 2/2:30mins
4 x 150m, WB 80m, run 80m
Walk 250m recovery
#Coach Note# Increase recovery times for next session', 'Speed_Endurance', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (7, '150m speed endurance building session', 'Dynamic warmup + running drills
4 x 60m run throughs
5 x 40m Sprints, 2mins recovery
3 x 3 x 150m - Walk / Jog / Walk Recovery
4mins between sets
Bodyweight circuit x 2', 'Speed_Endurance', 'Multi', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (8, '2 x 2km Tempo', '2 x 2km steady @4 to 4:30min pace - 5mins between reps', 'Aerobic', 'General', 'Base', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (9, '200m Endurance Session 1', '5 mins jog
5 x Running drill circuit
4 x 60m run throughs on track or grass
3-4 x 30 - 40m bend starts
2 x 3 x 200m@90% - walk 200m recovery (5-6mins between reps)
8 mins between sets
Gym session', 'Speed_Endurance', '200m', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (10, '200m endurance Session 2', '5 mins jog
5 x Running drill circuit
4 x 60m run throughs on grass
3-4 x 30 - 40m bend starts
2 x 3 x 200m - walk 200m recovery
8mins after 3
*variation - 2 x 120, 150, 250m - 5mins rest
8mins after each set', 'Speed_Endurance', '200m', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (11, '200m prep work', '2 x 40m bend starts - 4mins
2 x 70m bend starts - 6 mins
2 x 150m - FAST
10mins Break, then 12mins after 2
1 x 250m in 30 secs or under
4 x 60m ease down runs and stretching', 'Speed', '200m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (12, '200m preparation - Split 200', '4 x 20m sprints
3 x 30m sprints
2 x 50m bend,
3 x 120m, 1min break, sprint back 80m
6 mins Break', 'Speed', '200m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (13, '200m preparation work', '3 x 30m sprints
2 x 50m sprints
2 x 40m bend, 2 x 60m bend
2 x 100m - 50m bend, 50m straight
2 x 150m, 1 x 200m, 1 x 250m 6-8mins between reps', 'Speed', '200m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (14, '200m preparation work 2', '3 x 30m sprints
2 x 50m sprints
2 x 60m bend, 2 x 80m (40m & bend into straight)
2 x 120m @90% 6mins between reps
Athletes running at 95% = 8mins Recovery
10mins Break
2 x 200m @90%
10mins between reps', 'Speed', '200m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (15, '250 - 150 (400m session)', '4 x60m RT
2 x 250 / 150m in 35-40sec 3-4mins between 250m
10 min break between sets
4 x 70m Strides
Ab Circuit', 'Speed_Endurance', '400m', 'Competition', 'Max', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (16, '3-5 km at a steady pace', 'can also be done as 2 x 2km, with 5min rest and stretch in between', 'Aerobic', 'General', 'Transition', 'Low', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (17, '3km run', 'Easy run at a pace that you can have a chat', 'Aerobic', 'General', 'Transition', 'Low', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (18, '400+ 150 tempo session', 'After Warmup and Short Sprints
400m 5mins rest
4x150m 2mins rest
400m 5mins rest
Ease down run throughs and stretching', 'Speed_Endurance', '400m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (19, '400m Endurance building session', 'Dynamic warmup and running drills
4 x 60m run throughs
4 x 300m @80% - 6mins recovery
8mins between sets
OR - 4 x 500m with 6mins rest
5 x 80m runs @ 80%- Recovery = WB in 1min
Core workout circuit', 'Speed_Endurance', '400m', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (20, '400m Gut buster', 'In and Out warmup
Active stretching exercises and Core activation
(leg swings, squats, plank, plank with leg left)
3 - 4 x 80m RT''s
2 x 300 - 80 - 70m @90%
Run 300, rest 1min, Run 80m to finish, WB to 70m, run to finish, then walk a slow lap in 6-8mins
Then repeat ( So run 300m etc a total of twice)
4 x 50m Easy Stride Run throughs to help the legs recover', 'Speed_Endurance', '400m', 'Competition', 'Max', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (21, '400m prep - 350 / 250', 'Active Warmup and running drills
4 x 60m run throughs
3 x 40m sprints - Straight
2 x 70m sprints - Bend
1 x 350m , 1 x 250m - 15mins break', 'Speed_Endurance', '400m', 'Competition', 'Max', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (22, '400m prep session - Speed Endurance', '4 x60m run throughs
3 x 50m sprints - 5 mins rest between each
2 x 2 x 200m @90% 8mins rest between reps
15mins break after 1st set
(Target time = 25 secs or under)', 'Speed_Endurance', '400m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (23, '400m race tempo 200s', '4 x60m run throughs
3 x40m sprints - Straight - 3mins rst between each
3 x 200m at 400m race pace
10 - 12 mins break between each', 'Speed_Endurance', '400m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (24, '400m speed endurance', '07:00
3x30m block starts
2x50m block starts
300m @90%
Walk 150m in 3mins recovery
150m @90%
Walk back 70m / 2mins rest
70m hold form
Walk 1 lap in 6mins
Repeat', 'Speed_Endurance', '400m', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (25, '400m speed endurance work 1', '2 Lap jog
Squats, leg swings, Skipping drills
Running drills x 2 each
3-4 x 80m RT''s
4 x 20m fast starts
3 x 50m sprints - 2mins rest between each
2 x 250m @80% effort - walk 80m - sprint 70m to finish.
Rest is walk 1 lap in 5-6mins
5-10 mins Stretching', 'Speed_Endurance', '400m', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (26, '800 - 1500m workout 1', '600m @ 1500m pace 3mins Rest 4x200m @800m pace 90 secs rest, then 3mins break, 600m @1500m pace', 'Speed_Endurance', '800_1500m', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (27, '800m prep & Race sim', 'Active / Skipping warmup
Running drills
4 x 50m Run throughs
Sprint work x 3 reps
300m @90% - 5mins rest
200m @90% - From 300m start - 4mins rest
200m from 200m start - 5mins rest
120m or 150m
1 lap easy jog or 4 x 60 ease down runs
Stretching', 'Speed_Endurance', '800_1500m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (28, 'Acceleration Development 1 (INTRO)', '3 - 4 SETS x Accel Ladder 20 / 30 / 40m = 300 - 400m
RECOVERY = 2'', 3 & 4 mins
3 x Jumping and Bounding Drills over 30 - 40m = 200m
Technical Form Running = 4 x 100m @90% = 400m
Medball Circuit x 3', 'Speed', 'General', 'Pre_season', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (29, 'Acceleration and Speed Endurance', '3x20m sprints :1min break
2x30m Sprints : 2 mins break
2x40m Sprints : 3mins break
2 x 4 x 80m / 45 secs recovery
4 mins between sets', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (30, 'Agility and Speed Endurance 1', '5min jog, active warmup
5 min Balance and Activation
5min running drills
3-4 x 60m run throughs
4 x 4 cone tennis ball drill ( set cones up 4m apart in a square)
1-2mins between reps
4 x Agility / Zig Zag runs over 20-30m
Short Sprints - 3 x 40m
3 x 120m build up runs (40m 50%, 40m 75%, 40m 100% effort)
4mins recovery
1 x 250m Run', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (31, 'Agility and Speed Endurance 2', '5min jog, active warmup
5 min Balance and Activation
5min running drills
3-4 x 60m run throughs
3x30m, 2x50m, 2x80m WB +1min to be fresh
3-4 150m build up runs - 50m@50%, 50m@75%, 50m@100% - 3mins recovery
Ab & Back exercises (print from Resources)', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (32, 'Athletic Performance Testing', 'Using Electronic Timing Gates and Jump Mat
20m Sprint x 2
60m sprint x 2
150m Sprint
300m (for 400m athletes)
Vertical Jump x 3
Standing Long Jump', 'Testing', 'General', 'Base', 'Max', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (33, 'Block Starts + Max V', 'Heavy Sled x 20m
Block Starts x 30m / 40m out to 50m
Flying 30 x 2
Med Ball Throws and Sandpit Jumps', 'Speed', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (34, 'Block Starts and Max V Work', 'Block Starts x 4 x 40m
3 x 75m - In & Outs (15m Accel, 15m Maintain - 3 Accels)
6 mins between reps
3 x120m - hard bend relaxed straight
5 mins recovery', 'Speed', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (35, 'Footy Boys session 1', 'Acceleration, Speed and Form running
In & Outs 20, on, 20m off, 20m on x 4
60m, 80m, 120m x 2
3 - 4 x 250m, walk 150m recovery
Lateral Hurdle jumps', 'Speed', 'Team_Sport', 'Base', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (36, 'Hills + Track', '5 x 10sec hill, 1min WB recovery
5mins break
4x30m sprints, 1 min recovery
4mins
3 x 60m on/off 15m on, 10m off
5x60m Jog/WB/Jog/WB/Jog', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (37, 'Hills + Track (150s)', '5 x 15sec hill, 1min WB recovery
5mins break
10m "roll in" into 4x30m sprints, 1 min recovery
4mins
2 x 2 x 150m - 2 mins rest between sets
4 mins Break between sets', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (38, 'Hills and Track Workout', '5 min jog
Running Drills and Active Warmup
4x60m Run throughs
4 x 30m sprints - WB
400/800m Runners = 4 x 90 sec gravel trail - 3mins rec
100/200m runners = 5 x 20 sec efforts
All = 5 x 10 sec hill - WB + 30 secs
Track
3 x 120 or 150m Reps - WB
Powerband and Mini band strength exercises', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (39, 'Long Speed Endurance - Ladder Down', '2 lap easy jog
Running drills
4 x 60m Run throughs
500m, 400m, 300m, 200m, 100m
Recoveries are 4min,3min,2min,1min, so judge your pace!
1 lap easy jog or 4 x 60 ease down runs
Stretching', 'Speed_Endurance', '400m', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (40, 'Long Speed Endurance - Ladders', '2 lap easy jog
Running drills
4 x 60m Run throughs
500, 300m, 100, 300m, 500m
Recoveries are 5min,3min, 1min, 3min, so judge your pace!
1 lap easy jog or 4 x 60 ease down runs
Stretching', 'Speed_Endurance', '400m', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (41, 'Max V and Speed session', '3 x 30m Accels from 3 point start
2 x 12 wickets with 20m run in and 5 stride gap
6 mins recovery
1 x 60 - 80 - 120
Rest = 6mins between reps', 'Speed', 'General', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (42, 'Plyo Intro + Speed Endurance', 'Dynamic warmup + drills
5 x standing long jumps
4 x 20m bounding
5 x 20m accelerations over low hurdles
(1min rec between reps)
5 x 100m @80%
4mins recovery between reps
4 x 20-30m resisted harness or sled pulls
Bodyweight circuit', 'Plyo_Power', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (43, 'Short Fartlek', '5-6min jog warmup and Active stretches
(squats, leg swings, inchworm & spidermans)
3x60m run throughs
4x30sec run, 30 sec jog - 3mins rest
3x1min run, 1min jog
2x2min run, 2mins rest', 'Aerobic', 'General', 'Transition', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (44, 'Sled PUSH and Max V', '4 x 50m Run throughs
Heavy Sled PUSHES x 20m x 3 reps - Superset with 3 x 30m Sprints
Flying 30m over "wickets" x 3 - 6 mins break
Med Ball Throws -
Underhand throw 2 x10
Ab Slams 2 x 10
Rotation Side throws 2 x 10 each side', 'Speed', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (45, 'Sled Push and Max V', '4 x 50m Run throughs
Sled Push x 20m x 3 reps - Superset with 3 x 30m Sprints
Flying 30m over "wickets" x 3 - 6 mins break
2 x 70 -80 run - 8 mins rest
Med Ball Throws -
Underhand throw 2 x10
Ab Slams 2 x 10
Rotation Side throws 2 x 10 each side', 'Speed', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (46, 'Sled Push, Max V and Wickets', 'Heavy Sled x 20m
Block Starts x 30m / 40m out to 50m
Flying 30 x 2 (Wicket runs?)
Med Ball Throws and Sandpit Jumps', 'Speed', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (47, 'Sled Towing and Max V', '4 x 50m Run throughs
3 Point or Block Starts
Sled towing x 20m x 3 reps - Superset with 3 x 30m Sprints
Flying 30m over "wickets" x 2 - 6 mins break
Med Ball Throws -
Underhand throw 2 x10
Ab Slams 2 x 10
Rotation Side throws 2 x 10 each side', 'Speed', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (48, 'Speed Endurance 2 - Ladder Up & Down', '2 lap easy jog
Running drills
4 x 60m Run throughs
5 x 30m sprints - Wb + 1 min recovery
150 - 200 - 250 - 250 - 200 -150m
Recovery = 4, 5, 6, 8, 6, 4mins between reps
4 x 70m ease down run throughs and stretching', 'Speed_Endurance', 'Multi', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (49, 'Speed Endurance Building Session 1', '5min jog, Active warmup
5 min Balance and Activation
5min running drills
3-4 x 80m run throughs
2 sets of 4 x 100m @ 80% WB recovery
Bodyweight Exercises & Core', 'Speed_Endurance', 'General', 'Base', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (50, 'Speed Endurance Combo session 2', 'Focussed Speed Drills
Medball Push Pass starts - 4 x 20m
2x5x80m @10-12secs, 60 sec break
3mins between sets
2 x 200m, walk 100m, run 100m - 4 mins break', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (51, 'Speed Endurance Ladder', '1 Lap jog, running drills and stretches
4 x 50m Run throughs
3 x 20m Sprint starts - FAST
2 Sets of:
50m @90% - WB + 1 min rest
70m @90% - WB + 90 secs rest
90m @90% - WB + 2mins rest
120m @90% - 5 mins break
Repeat in Reverse order
5mins break then
1 x 250m @80%
4 x 30 sec Hill - WB - 3min rest after 4
4-5 x 1min hill run, jog 30 secs, walk 1 min
4-5 mins rest
Ab & Back exercise circuit', 'Speed_Endurance', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (52, 'Speed Endurance Session 1', '5min jog, Active warmup
5 min Balance and Activation
5min running drills
3-4 x 60m run throughs
1 x 60m, 80m, 100m @ 80% WB recovery +1min
2 Sets of Speedmakers - 5xSprint 50m, Jog 50m, Walk 50m
3 x 5 Double Leg Jumps for distance (measure it)
3 x 6 Jumps onto a bench or stairs ( for height)', 'Speed_Endurance', 'General', 'Base', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (53, 'Speed Endurance Session 2', '5min jog, Active warmup
5 min Balance and Activation
5min running drills
3-4 x 60m run throughs
2 x 4 x 80m @75%- rest 30 secs and run back
2 Sets High bench stepup - 8-10 each leg
2 Set of 5 hops for distance each leg', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (54, 'Speed Endurance Session 3', '5min jog, Active warmup
5 min Balance and Activation
5min running drills
3-4 x 60m run throughs
3 x 30m flying starts - 5m rolling start
2 x 50m flying starts - 5 m rolling start
2 Set of 4 x 80m sprints @70% effort
Jog back, walk back, jog back, walk back Rec
5min break, then do 2nd Set', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (55, 'Speed Endurance Session 4', '5min jog, Active warmup
5 min Balance and Activation
5min running drills
3-4 x 60m run throughs
4 x 30m block starts - WB + 1min
4 x 120m sprints @70% effort
Jog back, walk back, jog back, walk back Rec
5min break
3 x 200m - WB, Jog back, WB recovery', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (56, 'Speed Endurance Session 5', 'In & Out Warm up - Run 100m, jog/skip 50m, walk 50m (Until you have run 3 laps)
Active Stretches
Running drills
3 x 30m stand starts - WB
2 x 60m sprints WB + 1-2mins
6x200m@80%
Rec 3-4 mins rest
Leg Circuit', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (57, 'Speed Session + hills', '5min jog, Active warmup
5 min Balance and Activation
5min running drills
3-4 x 60m run throughs
3 x 30m sprints
2x 60m sprints
4 x 15sec sec hill - WB in 1min
(incline to be steep enough to encourage a strong knee and arm drive up the hill
4 x 100m @ 80% WB recovery +1min if needed', 'Speed', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (58, 'Speed Session 1', '5min jog, Active warmup
5 min Balance and Activation
5min running drills
3-4 x 60m run throughs
3 x 30m Accelerations
2 x 60m sprints
1 x 100 - 120 - 150m 6-8mins between reps
Stretching', 'Speed', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (59, 'Speed and Agility for Team Sport', 'Dynamic warmup + drills
3 x Compass Drill
5 x standing long jumps + 20m sprint
4 x 20m bounding
5 x 20m accelerations over low hurdles
(1min rec between reps)
5 x 100m @80%
Walk back recovery between reps', 'Speed', 'Team_Sport', 'Base', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (60, 'Speed and Power Testing', 'Standing Long jump - 2 attempts
150m sprint - 1 attempt
20mins break
300m run - 1 attempt', 'Testing', 'General', 'Base', 'Max', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (61, 'Speed and Speed Endurance', '5min jog, active warmup
5 min Balance and Activation
5min running drills
4 x 60m run throughs
4x20m fast sprints, block or 3 point start
3x60m blocks or standing start
2 Sets of 4x100m WB +1min to be fresh -
Hold form and run tall, no quicker than 80%
Ab & Back exercises (print from Resources)', 'Speed_Endurance', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (62, 'Speed session for 200m', '5min jog, Active warmup
5 min Balance and Activation
5min running drills
4 x 50m run throughs
3 x 30m Accelerations
2 x 60m sprints
3 x 100m fast 5mins between reps
1 x 200m @90% 8mins
1 x 250m @90%
Stretching', 'Speed', '200m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (63, 'Speed week - Race Sim for 400m', '1 lap jog and skipping warmup
4 sets of each running drill
4 x 60m run throughs
3 x 20-30m block starts or 3 point start
3 x 40m sprints from 400m start
1 x 350m @ 400m Race pace - 10mins rest
1 x 250m @ 400m Race pace - 10mins rest
1 x100m @200m race pace
Walk 5mins and stretch', 'Speed_Endurance', '400m', 'Competition', 'Max', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (64, 'Speedweek Sprint Session', 'In & Out Warmup + Dynamic Stretching
Speed Drills and Activation
3x80m Run throughs
2 x 40m Block Starts, 2 x 60m Bend starts
3 x 150m @ 80%
1 x 300m', 'Speed', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (65, 'Sprint and Plyo Session', 'In & Out Warmup + Dynamic Stretching
Speed Drills and Activation
4x60m Run throughs
Bounding starts - 20m bound, 20 sprint - Grass
3 x50m Block Starts, 4 x100m @ 90% 5mins recovery between reps
3 x 150m - Walk Back recovery
Double leg jumps and Hops for Distance - 2 sets of 20m', 'Plyo_Power', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (66, 'Start Practice and Speed Session 1', '5min jog, Active warmup
5 min Balance and Activation
5min running drills
3-4 x 80m run throughs
Start practice for 100m - 4 x 30m
Start practice for 200m 3 x 50m bend
Form Runs - 80,100,120,150m
Bodyweight Exercises & Core', 'Technical', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (67, 'Starts and 200m work', '4x60m RT,
4 x30 starts,
3x50m,
1 x 150, 200, 250m 5'', 8-10''', 'Speed', '200m', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (68, 'Stawell Grass prep', 'Setup blocks on Grass for start practice
mark out 120m
40m Blocks x 2 : 3 - 4mins break
60m blocks x 2 : 5 mins break
2 x 100m (diagonals) 6mins break', 'Technical', 'Multi', 'Competition', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (69, 'Technical Session - Block set-ups and Start Execution', 'Standing start with Back Block push-off 3 x 20m
Block start 3 x 30m - 3 mins rest
Block Starts 2 x 40m - 4 mins rest
2 x Flying 30m - 20m run in (50m Total)
6 mins between reps
Medball Throws. - 2 sets
Chest pass x 8
Underhand FWD Throw x 8
Overhead FWD Throw x 8', 'Technical', 'Multi', 'Competition', 'High', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (70, 'Tempo Sandwich', '1km warmup run
Active stretches and Running Drills
5min tempo - 2 min rest
4 x 30 sec hard/30sec easy - 3mins rest after the 4 hard efforts
(30 secs easy is an "active" recovery)
5min tempo', 'Aerobic', 'General', 'Transition', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (71, 'Transition Week 1 - Session 1', 'In and Out warm up with skipping drills
Mobility and activation exercises
Extensive running drills - focus on Form and execution
4 x 60m Run throughs
3 x 10m Roll in 40m Accelerations
5 x 80m relaxed runs - WB recovery
Sandpit bear crawls & inchworms
Ab - Flutter kicks and Planks', 'Speed', 'General', 'Transition', 'Low', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (72, 'Transition Week 1 - Session 2', 'In and Out warm up with skipping drills
Mobility and activation exercises
Extensive running drills - focus on Form and execution
4 x 60m Run throughs
2 x 20m Straight leg bound into 30m Accelerations
2 x 20m Speed Bound into 30m Acceleration
2 x 4 x 100m relaxed runs - WB recovery
4mins betweeen Sets
Cool down static stretches - 10mins', 'Speed', 'General', 'Transition', 'Low', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (73, 'Transition Week 2 - Session 1', 'Continuous Warm-up
Extensive running drills - focus on Form and execution
4 x 60m Run throughs
4 x 20m Accel - 20m "Roll", 20m Accel, then coast down
2 x 4 x 80m relaxed runs ( Up and Backs ) 30 secs recovery
5mins between sets
Core x 2 Setsx 10 reps of each: Double leg lifts, Plank with shoulder taps, V-Sit, Side plank
Cool down static stretches - 10mins', 'Speed_Endurance', 'General', 'Transition', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (74, 'Transition Week 2 - Session 2', 'In and Out warm up with skipping drills
Mobility and activation exercises
Extensive running drills - focus on Form and execution
4 x 60m Run throughs
2 x 20m Straight leg bound into 30m Accelerations
2 x 20m B Skip into 20m Acceleration
3 x 120m relaxed runs - WB recovery
4mins Break
2 x Run 200m, walk 200m @70-80%
Cool down static stretches - 10mins', 'Speed', 'General', 'Transition', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (75, 'Transition Week 3 - Session 1', 'Continuous Warm-up
Extensive running drills - focus on Form and execution
4 x 60m Run throughs
5 x 20m Accelerations - WB + 1min
5 x 70m - WB recovery
5mins Break
2 x 250m - walk 200m recovery, run 150m - 4 mins rest & repeatCore x 2 Sets x 10 reps of each: Double leg lifts, Plank with shoulder taps, V-Sit, Side plank', 'Speed_Endurance', 'General', 'Transition', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (76, 'Transition Week 3 - Session 2', 'In and Out warm up with skipping drills
Mobility and activation exercises
Extensive running drills - focus on Form and execution
4 x 60m Run throughs
2 x 3 x 150m relaxed runs - WB recovery
4mins Break
Cool down static stretches - 10mins', 'Speed_Endurance', 'General', 'Transition', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (77, 'Transition Week 4 - Session 1', 'Continuous Warm-up
Extensive running drills - focus on Form and execution
4 x 60m Run throughs
5 x 20m Accelerations - WB + 1min
4 x 100m (or 13-15 sec) Grass or Track runs - 90- secs - 2min WB recovery
5mins Break
2 x 200m - walk 200m recovery in 4-5mins', 'Speed_Endurance', 'General', 'Transition', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (78, 'Transition Week 4 - Session 2', 'In and Out warm up with skipping drills
Mobility and activation exercises
Extensive running drills - focus on Form and execution
4 x 60m Run throughs
Traffic Light Drill for warmup
4-5 x 10-15min 2 point stats with feedback
2 x 4 x 80 / 40m @80% (run 80m, 30sec rest, run back 40m / 1min rest
5 mins Break
Core Circuit x 2 - flutter kicks, Hollow rocks and Plank with alternating leg lifts
Cool down static stretches - 10mins', 'Technical', 'General', 'Transition', 'Moderate', '{}', 2025) ON CONFLICT DO NOTHING;
INSERT INTO sessions (id, name, description, session_type, event_group, training_phase, intensity_level, tags, source_year) VALUES (79, 'Wickets and Max V Session 1', 'Muscle activastion and Active Warmup Drills
4 x 50m Run throughs
18w at 6 step spacing - 4 sets
Speed Bounding over 30m x 3 - 4
3 x Flying 30m (20m run in)
3 x 60 - 80m bend runs', 'Speed', 'General', 'Base', 'High', '{}', 2025) ON CONFLICT DO NOTHING;

-- ============================================================
-- SEED: S&C phases
-- ============================================================
INSERT INTO sc_phases (id, name, short_code, bompa_label, macrocycle_phase, macrocycle_blocks, typical_weeks, sessions_per_week_min, sessions_per_week_max, sets_min, sets_max, reps_min, reps_max, load_pct_min, load_pct_max, rest_seconds_min, rest_seconds_max, tempo_guidance, rpe_target_min, rpe_target_max, primary_goal, sprint_specific_focus, display_order) VALUES (1, 'Anatomical Adaptation', 'AA', 'Introduce', 'Transition', 'Block 13', '3-4', 2, 3, 2, 3, 15, 20, 40, 55, 60, 90, '2-1-2-0 (controlled eccentric, no explosive)', 5, 7, 'Prepare connective tissue, establish movement quality, general conditioning base', 'Posterior chain activation, hip hinge mechanics, ankle and knee stability', 1) ON CONFLICT DO NOTHING;
INSERT INTO sc_phases (id, name, short_code, bompa_label, macrocycle_phase, macrocycle_blocks, typical_weeks, sessions_per_week_min, sessions_per_week_max, sets_min, sets_max, reps_min, reps_max, load_pct_min, load_pct_max, rest_seconds_min, rest_seconds_max, tempo_guidance, rpe_target_min, rpe_target_max, primary_goal, sprint_specific_focus, display_order) VALUES (2, 'Hypertrophy', 'HYP', 'Volume', 'General_Prep', 'Blocks 1-2', '8', 2, 2, 3, 5, 8, 12, 65, 75, 60, 90, '3-1-1-0 (slow eccentric, controlled concentric)', 7, 8, 'Build muscle cross-sectional area, increase maximum force production capacity', 'Glute and hamstring hypertrophy for sprint propulsion. Eccentric hamstring loading for injury prevention.', 2) ON CONFLICT DO NOTHING;
INSERT INTO sc_phases (id, name, short_code, bompa_label, macrocycle_phase, macrocycle_blocks, typical_weeks, sessions_per_week_min, sessions_per_week_max, sets_min, sets_max, reps_min, reps_max, load_pct_min, load_pct_max, rest_seconds_min, rest_seconds_max, tempo_guidance, rpe_target_min, rpe_target_max, primary_goal, sprint_specific_focus, display_order) VALUES (3, 'Maximum Strength', 'MAX', 'Intensity', 'General_Prep', 'Block 3', '4', 2, 2, 4, 5, 3, 6, 80, 90, 180, 300, '2-1-X-0 (controlled down, pause, EXPLOSIVE up)', 8, 9, 'Maximise neural drive and absolute strength. Build the strength ceiling for power phase.', 'Absolute squat and hip hinge strength directly feeds power output in sprint acceleration phase.', 3) ON CONFLICT DO NOTHING;
INSERT INTO sc_phases (id, name, short_code, bompa_label, macrocycle_phase, macrocycle_blocks, typical_weeks, sessions_per_week_min, sessions_per_week_max, sets_min, sets_max, reps_min, reps_max, load_pct_min, load_pct_max, rest_seconds_min, rest_seconds_max, tempo_guidance, rpe_target_min, rpe_target_max, primary_goal, sprint_specific_focus, display_order) VALUES (4, 'Power / Speed-Strength', 'PWR', 'Volume then Intensity', 'Specific_Prep', 'Blocks 4-5', '8', 2, 2, 3, 4, 3, 5, 65, 85, 180, 300, 'X-0-X-0 (EXPLOSIVE both directions — maximum velocity intent)', 7, 9, 'Convert maximum strength into explosive power and rate of force development', 'Triple extension power (hip-knee-ankle) directly mimics sprint push-off mechanics. Power clean is highest transfer exercise.', 4) ON CONFLICT DO NOTHING;
INSERT INTO sc_phases (id, name, short_code, bompa_label, macrocycle_phase, macrocycle_blocks, typical_weeks, sessions_per_week_min, sessions_per_week_max, sets_min, sets_max, reps_min, reps_max, load_pct_min, load_pct_max, rest_seconds_min, rest_seconds_max, tempo_guidance, rpe_target_min, rpe_target_max, primary_goal, sprint_specific_focus, display_order) VALUES (5, 'Maintenance', 'MAINT', 'Maintain / Reduce', 'Competition', 'Blocks 6-12', '24', 1, 2, 2, 3, 3, 5, 78, 83, 180, 240, '2-0-X-0 (quality eccentric, EXPLOSIVE concentric)', 7, 8, 'Maintain strength and neural drive through competition season without accumulating fatigue', 'Keep CNS primed without fatigue accumulation. Schedule gym 3-4 days before competition minimum.', 5) ON CONFLICT DO NOTHING;

-- ============================================================
-- SEED: S&C exercises
-- ============================================================
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (1, 'Back Squat', 'Bilateral_Squat', '{"Quadriceps","Glutes","Erector Spinae"}', '{"Hamstrings","Core","Adductors"}', '{"barbell","rack"}', 'Brace core before unracking. Hip-width stance. Track knees over toes. Depth to parallel minimum. Drive floor away on ascent. Bar stays over mid-foot.', 'Knee cave on ascent. Forward lean. Rising onto toes. Depth cut short.', TRUE, '{1,2,3,4,5}', 'Intermediate', 'Primary bilateral leg strength. Develops quad and glute force production for acceleration drive.', '{"squat","bilateral","primary","lower-body"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (2, 'Front Squat', 'Bilateral_Squat', '{"Quadriceps","Glutes","Core"}', '{"Upper Back","Erector Spinae"}', '{"barbell","rack"}', 'Clean or cross-arm grip. Elbows HIGH — parallel to floor. Upright torso is key. Knees track toes. Core braced throughout.', 'Elbows dropping. Forward lean. Weight too heavy for position.', FALSE, '{3,4}', 'Advanced', 'Develops upright torso strength and quad power — important for hurdles and acceleration mechanics.', '{"squat","bilateral","advanced","quad-dominant"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (3, 'Romanian Deadlift (RDL)', 'Hip_Hinge', '{"Hamstrings","Glutes"}', '{"Erector Spinae","Core"}', '{"barbell"}', 'Soft knee bend throughout. Push hips BACK not down. Bar stays close to legs. Feel hamstring stretch at bottom — stop there. Squeeze glutes at top.', 'Squatting down instead of hinging. Rounding lower back. Bar drifting away from legs. Going too deep past hamstring tension.', TRUE, '{1,2,3,4,5}', 'Beginner', 'CRITICAL for sprint injury prevention. Eccentric hamstring loading at high hip angles directly matches sprint ground contact mechanics. #1 hamstring protection exercise.', '{"hip-hinge","hamstring","posterior-chain","injury-prevention","primary"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (4, 'Conventional Deadlift', 'Hip_Hinge', '{"Glutes","Hamstrings","Erector Spinae"}', '{"Quads","Core","Traps"}', '{"barbell"}', 'Bar over mid-foot. Hip-width stance. Grip just outside legs. Push floor away — don''t think about pulling bar. Hips and shoulders rise together. Full lockout at top.', 'Bar drifting forward. Hips shooting up early. Rounding lower back. Jerking bar off floor.', TRUE, '{1,2,3,4,5}', 'Intermediate', 'Maximum posterior chain strength. Highest transfer to sprint propulsion force production.', '{"hip-hinge","posterior-chain","strength","primary"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (5, 'Good Morning', 'Hip_Hinge', '{"Hamstrings","Erector Spinae","Glutes"}', '{"Core"}', '{"barbell","rack"}', 'Bar on upper traps (not neck). Soft knee. Hinge until torso approaches parallel. Maintain neutral spine throughout. Drive hips forward to return.', 'Rounding lower back. Squatting pattern. Excessive load.', FALSE, '{1,2}', 'Intermediate', 'Posterior chain strength in hip extension — key movement pattern for sprint drive phase.', '{"hip-hinge","posterior-chain","accessory"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (6, 'Bulgarian Split Squat', 'Single_Leg', '{"Quads","Glutes"}', '{"Hamstrings","Core","Hip Flexors"}', '{"barbell","rack","bench"}', 'Rear foot elevated hip height. Torso upright. Front foot far enough forward — shin vertical at bottom. Lower rear knee toward floor. Drive through front heel.', 'Front foot too close. Excessive forward lean. Rear foot too high causing hip flexor strain.', TRUE, '{2,3,4,5}', 'Intermediate', 'Mirrors single-leg sprint stride. Develops unilateral strength and hip stability critical for running mechanics.', '{"single-leg","unilateral","squat","sprint-specific"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (7, 'Barbell Reverse Lunge', 'Single_Leg', '{"Quads","Glutes"}', '{"Hamstrings","Core"}', '{"barbell","rack"}', 'Step back — not sideways. Front shin vertical. Drop rear knee toward floor. Drive through front heel to return. Torso upright.', 'Stepping too short. Front knee caving. Torso collapsing forward.', FALSE, '{1,2}', 'Beginner', 'Safe single-leg loading for AA phase. Develops hip stability and single-leg strength.', '{"single-leg","lunge","accessory","aa-phase"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (8, 'Single Leg RDL', 'Single_Leg', '{"Hamstrings","Glutes"}', '{"Core","Hip Stabilisers"}', '{"barbell"}', 'Hinge from planted hip. Lift opposite leg as counterbalance. Maintain level hips throughout — don''t rotate. Feel hamstring stretch. Return by squeezing glute of standing leg.', 'Hip rotation/drop. Loss of balance. Bending planted knee excessively.', FALSE, '{2,3,4}', 'Intermediate', 'Single-leg hip hinge — closest gym exercise to sprint ground contact position. Essential for hamstring injury prevention.', '{"single-leg","hip-hinge","hamstring","injury-prevention"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (9, 'Barbell Hip Thrust', 'Single_Leg', '{"Glutes"}', '{"Hamstrings","Core"}', '{"barbell","bench"}', 'Upper back on bench edge. Barbell on hip crease (pad recommended). Drive hips to full extension. Squeeze glutes hard at top. Chin tucked — don''t hyperextend lower back.', 'Not reaching full hip extension. Hyperextending lumbar. Bar rolling during movement.', TRUE, '{2,3,4,5}', 'Beginner', 'Highest glute activation of any exercise. Directly develops hip extension force — the primary propulsive action in sprinting.', '{"glutes","hip-extension","posterior-chain","sprint-specific"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (10, 'Bench Press', 'Push', '{"Pectorals","Triceps"}', '{"Front Deltoid","Core"}', '{"barbell","rack","bench"}', 'Feet flat. Arch in lower back. Bar over lower chest. Elbows at 45-75 degrees. Touch chest, explosive press. Full lockout at top.', 'Bouncing bar off chest. Flared elbows. Feet off floor. Uneven bar path.', TRUE, '{1,2,3,4,5}', 'Beginner', 'Upper body pushing strength. Contributes to arm drive force and posture maintenance during sprint.', '{"push","upper-body","chest","primary"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (11, 'Overhead Press (OHP)', 'Push', '{"Deltoids","Triceps"}', '{"Core","Traps","Upper Back"}', '{"barbell","rack"}', 'Grip just outside shoulder width. Bar at collarbone. Full body brace. Press bar straight up — slight backward lean as bar passes face. Lockout overhead.', 'Excessive lower back arch. Bar path forward. Lack of lockout.', TRUE, '{2,3,4,5}', 'Intermediate', 'Shoulder and overhead pressing strength for arm drive power and shoulder stability during sprint.', '{"push","upper-body","shoulders","primary"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (12, 'Push Press', 'Push', '{"Deltoids","Triceps","Legs"}', '{"Core","Traps"}', '{"barbell","rack"}', 'Slight knee dip then explosive hip drive — use leg power to initiate press. Bar moves as fast as possible. Catch in lockout overhead. This is a POWER exercise.', 'Too much knee bend (becomes push jerk). Slow bar speed. Poor lockout.', FALSE, '{4,5}', 'Intermediate', 'Transfers lower body power to upper body — develops whole-body explosive coordination for sprint arm drive.', '{"push","power","upper-body","explosive"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (13, 'Bent Over Barbell Row', 'Pull', '{"Latissimus Dorsi","Rhomboids","Rear Deltoids"}', '{"Biceps","Erector Spinae","Core"}', '{"barbell"}', 'Hip hinge to 45-60 degrees. Brace core. Pull bar to lower chest/upper abdomen. Lead with elbows. Squeeze shoulder blades at top. Control the descent.', 'Using momentum. Rounding lower back. Pulling to wrong height. Torso too upright.', TRUE, '{1,2,3,4,5}', 'Intermediate', 'Upper back pulling strength. Critical for posture maintenance and arm drive efficiency during sprint.', '{"pull","upper-body","back","primary"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (14, 'Pendlay Row', 'Pull', '{"Latissimus Dorsi","Rhomboids","Traps"}', '{"Biceps","Core"}', '{"barbell"}', 'Bar starts from floor each rep. Torso parallel to floor. Explosive pull to lower chest. Bar returns to floor — full dead stop. Strict position maintained.', 'Torso not parallel. Using momentum from floor. Partial reps.', FALSE, '{3,4}', 'Advanced', 'Strict upper back strength at higher loads — strength phase variation for max force production.', '{"pull","upper-body","back","strength-phase"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (15, 'Hang Power Clean', 'Power', '{"Glutes","Hamstrings","Traps","Deltoids"}', '{"Quads","Core","Forearms"}', '{"barbell"}', 'Start from hang (just above knee). Aggressive hip drive. TRIPLE EXTENSION: ankle-knee-hip. High pull — elbows punch forward fast. Catch in quarter squat. This is about SPEED not load.', 'Arm pulling too early. Insufficient hip drive. Poor catch position. Too heavy — kills bar speed.', TRUE, '{4,5}', 'Advanced', 'Highest gym transfer to sprint mechanics. Triple extension power mirrors the sprint push-off action. Rate of force development (RFD) training.', '{"power","olympic","explosive","sprint-specific","high-transfer"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (16, 'Power Clean', 'Power', '{"Glutes","Hamstrings","Quads","Traps"}', '{"Core","Deltoids","Forearms"}', '{"barbell"}', 'Bar from floor. Maintain back angle from floor to knees. Accelerate through the pull. Triple extension. Fast elbows to catch position. Catch in quarter squat.', 'Early hip rise. Arm pull instead of leg drive. Slow transition. Poor catch.', TRUE, '{4,5}', 'Advanced', 'Full ground-to-overhead power expression. Develops the explosive hip extension power that drives sprint propulsion.', '{"power","olympic","explosive","sprint-specific","high-transfer"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (17, 'Jump Squat (Barbell)', 'Power', '{"Quads","Glutes","Calves"}', '{"Core","Hamstrings"}', '{"barbell","rack"}', 'Light load ONLY (20-40% 1RM squat). Squat to quarter depth. MAXIMUM intent to jump. Land softly — absorb through hip, knee, ankle. Safety squat bar preferred if available.', 'Too heavy — defeats the purpose. Hard landing. Full squat depth.', FALSE, '{4}', 'Intermediate', 'Develops the stretch-shortening cycle (SSC) and reactive strength — key for sprint acceleration.', '{"power","explosive","jump","reactive-strength"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (18, 'Good Morning (Light — Core focus)', 'Core', '{"Erector Spinae","Hamstrings"}', '{"Glutes","Core"}', '{"barbell","rack"}', 'Light load. Focus on maintaining neutral spine through full range. Breathing: inhale at top, exhale at bottom. Slow and controlled — this is a mobility and stability exercise here.', 'Too heavy. Rounding spine. Too fast.', FALSE, '{1}', 'Beginner', 'Establishes posterior chain mobility and spinal stability patterns — foundation for all loaded hip hinge exercises.', '{"core","stability","posterior-chain","aa-phase"}') ON CONFLICT DO NOTHING;
INSERT INTO sc_exercises (id, name, movement_pattern, primary_muscles, secondary_muscles, equipment, coaching_cues, common_errors, is_primary, suitable_phase_ids, difficulty_level, sprint_relevance, tags) VALUES (19, 'Barbell Rollout (Ab Wheel variation)', 'Core', '{"Rectus Abdominis","Obliques","Hip Flexors"}', '{"Lats","Shoulders"}', '{"barbell"}', 'Kneel behind loaded barbell. Roll forward, maintaining rigid body. Hips stay in line. Roll back using core — not momentum. Progress to standing rollout over weeks.', 'Hips sagging. Using hip flexors to return. Going too far forward too soon.', FALSE, '{1,2,3}', 'Intermediate', 'Anti-extension core strength. Crucial for force transfer from legs through torso during sprint.', '{"core","anti-extension","accessory"}') ON CONFLICT DO NOTHING;

-- ============================================================
-- SEED: S&C workout templates
-- ============================================================
INSERT INTO sc_workout_templates (id, name, sc_phase_id, session_label, session_focus, warmup_notes, cooldown_notes, coach_notes, week_placement, display_order) VALUES (1, 'AA Full Body A', 1, 'A', 'Full Body — Squat dominant', '10min: 5min jog + dynamic mobility (leg swings, hip circles, bodyweight squats x10, lunges x8 each). Activate glutes with bodyweight hip thrusts x15.', '10min static stretch: quads, hamstrings, hip flexors, calves, thoracic mobility.', 'AA Phase priority: TECHNIQUE over load. If form breaks, reduce weight. This is tissue preparation — not testing limits.', 'Monday (or Day 1 of training week)', 1) ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (1, 1, 1, 'Main', 3, 15, 20, 45, 'Very light. Focus on depth and control. Add weight only when form is solid across all sets.', 60, '2-1-2-0', 'Build depth gradually. By week 2 aim for parallel.', 'Add 2.5kg each week if form is solid') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (1, 3, 2, 'Main', 3, 15, 20, 40, 'Bar or very light plates. Feel the hamstring stretch — that''s the cue to stop descending.', 60, '3-1-2-0', 'Hinge not squat. Bar stays close to legs.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (1, 10, 3, 'Main', 2, 15, 20, 40, 'Just the bar or light plates.', 60, '2-1-2-0', 'Feel the movement pattern — not a strength test', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (1, 13, 4, 'Main', 2, 15, 20, 35, 'Light. Hip hinge position. Control the descent.', 60, '2-1-2-0', '45-60 degree torso angle. Brace before each rep.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (1, 7, 5, 'Accessory', 2, 12, 15, NULL, 'Bodyweight or empty bar on back', 60, '2-1-2-0', 'Front shin vertical. Torso upright.', 'Progress to loaded barbell in week 3') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (1, 18, 6, 'Core', 2, 15, 15, NULL, 'Empty bar or very light', 45, '3-0-3-0', 'This is a mobility exercise. Light and slow.', 'Increase range of motion before increasing load') ON CONFLICT DO NOTHING;
INSERT INTO sc_workout_templates (id, name, sc_phase_id, session_label, session_focus, warmup_notes, cooldown_notes, coach_notes, week_placement, display_order) VALUES (2, 'AA Full Body B', 1, 'B', 'Full Body — Hinge dominant', '10min: 5min bike/jog + mobility. Focus: 10x hip CARs each side, 10x thoracic rotations, 10x band pull-aparts (or plate pull-aparts).', '10min: Hip flexor stretch 60s each side, hamstring stretch, calf stretch, piriformis stretch.', 'Session B introduces single-leg work. Expect more difficulty here — this reveals bilateral deficits. No load until balance is solid.', 'Thursday (or Day 4 of training week)', 2) ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (2, 4, 1, 'Main', 3, 15, 20, 45, 'Light. Build the pulling pattern from floor.', 60, '2-1-2-0', 'Flat back. Bar over mid-foot. Push floor away.', 'Add 5kg/week — deadlift responds faster to loading than squat') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (2, 9, 2, 'Main', 3, 15, 20, NULL, 'Bodyweight week 1-2. Add 10-20kg bar from week 3.', 60, '2-1-2-0', 'Full hip extension at top. Feel glutes — not lower back.', 'Load up quickly. Athletes handle hip thrust volume well.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (2, 11, 3, 'Main', 2, 15, 20, 40, 'Empty bar to light weight.', 60, '2-1-2-0', 'Press straight up. Full lockout each rep.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (2, 6, 4, 'Accessory', 2, 10, 12, NULL, 'Bodyweight only first 2 weeks. No bar until balance established.', 60, '2-1-2-0', 'Rear foot elevated to hip height. Upright torso.', 'Add dumbbells held at sides, then barbell on back in Hypertrophy phase') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (2, 8, 5, 'Accessory', 2, 8, 10, NULL, 'Bodyweight. Absolute focus on balance and hip level.', 60, '3-0-2-0', 'Keep hips level. Don''t rush.', 'Add light dumbbells, then barbell in hand once balance established') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (2, 19, 6, 'Core', 2, 8, 10, NULL, 'Kneel only. Go 50% of range until comfortable.', 45, '3-0-3-0', 'Rigid body position. Core braced throughout.', 'Increase range each week. Progress to standing rollout over 4 weeks') ON CONFLICT DO NOTHING;
INSERT INTO sc_workout_templates (id, name, sc_phase_id, session_label, session_focus, warmup_notes, cooldown_notes, coach_notes, week_placement, display_order) VALUES (3, 'Hypertrophy A — Lower Dominant', 2, 'A', 'Lower dominant — Squat + Hip Thrust', '8min: 3min row/bike + glute activation (bodyweight hip thrusts x20, side-lying clams x15 each). Primer set: Back Squat x5 @40% 1RM.', 'Full posterior chain stretch: pigeon stretch, supine hamstring, pigeon rotation.', 'Hypertrophy: feel the muscle working. 3-second eccentric is non-negotiable — it''s where the growth stimulus comes from. Progressive overload: add 2.5kg to squat and RDL each week.', 'Monday', 3) ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (3, 1, 1, 'Main', 4, 8, 10, 70, 'Moderate load. Add 2.5kg/week if completing all reps with good form.', 90, '3-1-1-0', '3-second descent. Pause at bottom. Drive up.', 'Linear: +2.5kg/week. Deload at end of block.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (3, 3, 2, 'Main', 4, 10, 12, 65, 'Moderate. Feel the hamstring load on every rep. Never sacrifice position for load.', 90, '3-1-1-0', 'FEEL the hamstrings. This is injury prevention as much as strength.', 'Add 2.5kg/week. If hamstrings are sore next day — you''re hitting it right.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (3, 9, 3, 'Main', 4, 10, 12, 65, 'Load should feel challenging on reps 10-12. Glutes should be the primary feeling.', 90, '2-1-2-0', 'SQUEEZE at the top. Full hip extension — don''t shortchange the lockout.', 'Hip thrust responds well to load — can increase 5kg/week in early phase') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (3, 6, 4, 'Accessory', 3, 8, 10, 60, 'Load through rack then step back. Both sides equal.', 75, '3-1-1-0', 'Rear foot elevated. Upright torso. Drive through front heel.', 'Add 2.5kg/week. Compare left vs right — flag any asymmetries.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (3, 10, 5, 'Upper Finisher', 3, 10, 12, 65, 'Lighter than lower work — upper body is secondary in this phase.', 75, '3-1-1-0', 'Controlled descent. Chest touch. Explosive press.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_workout_templates (id, name, sc_phase_id, session_label, session_focus, warmup_notes, cooldown_notes, coach_notes, week_placement, display_order) VALUES (4, 'Hypertrophy B — Hinge Dominant', 2, 'B', 'Hinge dominant — Deadlift + Single Leg', '8min: Hip hinge rehearsal with bar (3x5). Single leg balance exercises (30s each side). Romanian deadlift with just bar x10.', 'Extended hamstring and glute stretch. Roll thoracic spine on bar.', 'Session B has the highest injury-prevention value. RDL and single-leg RDL develop the eccentric hamstring strength that protects athletes at top speed. This is the most important session in the block.', 'Thursday', 4) ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (4, 4, 1, 'Main', 4, 8, 10, 70, 'Heavy enough to feel, light enough to maintain bar speed and position.', 90, '3-1-1-0', 'Setup is everything. Bar over mid-foot, every rep.', 'Add 5kg/week — deadlift tolerates more load than squat.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (4, 8, 2, 'Main', 3, 8, 10, NULL, 'Light bar or dumbbells. Focus entirely on position and balance.', 75, '3-1-2-0', 'Hips stay LEVEL — use mirror or phone video to check. This is where asymmetries show.', 'Add small load each week. Video each set to check hip position.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (4, 9, 3, 'Main', 4, 12, 15, 65, 'Higher rep here vs Session A — cumulative glute volume.', 75, '2-1-2-0', 'Full range. Full squeeze. Consistent tempo.', 'Add 5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (4, 11, 4, 'Upper', 3, 10, 12, 65, 'Strict press. No leg drive in Hypertrophy phase.', 75, '2-1-2-0', 'Core braced throughout. Press straight up.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (4, 13, 5, 'Upper', 4, 10, 12, 65, 'Pull to lower chest/upper abdomen.', 75, '3-1-1-0', '45-60 degree torso. Lead with elbows.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (4, 19, 6, 'Core', 3, 10, 12, NULL, 'Progress range each week.', 45, '3-0-3-0', 'Rigid body. Hips don''t drop or pike.', 'Work toward standing rollout') ON CONFLICT DO NOTHING;
INSERT INTO sc_workout_templates (id, name, sc_phase_id, session_label, session_focus, warmup_notes, cooldown_notes, coach_notes, week_placement, display_order) VALUES (5, 'Max Strength A — Squat & Push', 3, 'A', 'Squat dominant + Upper Push', '15min: 5min bike. Then ramp up to working weight: Back Squat 5@50%, 3@65%, 2@75%, 1@82% before working sets. CNS activation is key at this intensity.', '5min light walk. Keep warm between sets — don''t sit. Light mobility work only — no aggressive stretching pre- or mid-session.', 'CNS DEMAND IS HIGH. Athletes may feel flat in the gym 24-48hrs after this session — that''s normal. Schedule 48hrs minimum before track. Spot all squats above 80%. Technical breakdown = immediate load reduction.', 'Monday', 5) ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (5, 1, 1, 'Main', 5, 3, 5, 82, 'Build to 85% by week 3. Week 4 deload to 70% x5x5.', 240, '2-1-X-0', 'EXPLOSIVE intent on concentric even at heavy loads. Nervous system must think ''fast''.', 'Week 1: 82%. Week 2: 84%. Week 3: 87%. Week 4: Deload 70%.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (5, 3, 2, 'Main', 4, 4, 6, 80, 'Hamstrings need to feel loaded but position never compromised.', 180, '3-1-X-0', 'Slow and controlled down. Explosive hip drive back to standing.', 'Add 2.5-5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (5, 10, 3, 'Upper', 4, 4, 5, 82, 'Heavy. Spot required above 85%.', 180, '2-1-X-0', 'Controlled descent. EXPLOSIVE press. Bar speed is the goal.', 'Add 2.5kg/week. Test 5RM in final week.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (5, 13, 4, 'Upper', 4, 5, 6, 78, 'Superset with bench if time-pressed. 90s between exercises.', 180, '2-1-X-0', 'Strict form. Don''t sacrifice position for load.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (5, 6, 5, 'Accessory', 3, 5, 6, 70, 'Loaded split squat. Accessory to main squat — not the focus today.', 120, '3-1-1-0', 'Quality over load. Single leg integrity check.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_workout_templates (id, name, sc_phase_id, session_label, session_focus, warmup_notes, cooldown_notes, coach_notes, week_placement, display_order) VALUES (6, 'Max Strength B — Hinge & Pull', 3, 'B', 'Deadlift dominant + Upper Pull', '15min: Ramp up deadlift: 5@50%, 3@65%, 2@75%, 1@82%. Strict position at every warm-up weight. Never rush the warm-up in strength phase.', 'Light walk. Lower back specific mobility: McKenzie extensions x10, hip flexor stretch 60s each side.', 'Deadlift CNS demand is highest of all exercises. Do not schedule within 48hrs of high-intensity track. Pendlay row is strict — if an athlete can''t maintain parallel torso, reduce load not range.', 'Thursday', 6) ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (6, 4, 1, 'Main', 5, 3, 3, 85, 'Week 3 peak at 90%. Week 4 deload 70% for 5x5.', 300, '2-1-X-0', 'Every rep like a max single. Bar speed as fast as possible even at 90%.', 'Week 1: 85%. Week 2: 87%. Week 3: 90%. Week 4: 70% deload.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (6, 11, 2, 'Upper', 4, 4, 5, 80, 'Strict press — no leg drive here.', 180, '2-1-X-0', 'Full body brace. Press through the ceiling.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (6, 14, 3, 'Upper', 4, 4, 5, 80, 'Strict Pendlay row — torso parallel each rep.', 180, '0-0-X-1', 'Dead stop on floor. Explosive pull. Control the return.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (6, 9, 4, 'Accessory', 3, 6, 8, 75, 'Load up hip thrust even in strength phase. Glute strength needs volume.', 120, '2-1-2-0', 'Full lockout. Glutes not lower back.', 'Add 5-10kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (6, 8, 5, 'Accessory', 3, 5, 6, NULL, 'Light load. Quality single-leg hinge.', 90, '3-0-2-0', 'Hips level. Hip to floor distance same each rep.', 'Add small load each week') ON CONFLICT DO NOTHING;
INSERT INTO sc_workout_templates (id, name, sc_phase_id, session_label, session_focus, warmup_notes, cooldown_notes, coach_notes, week_placement, display_order) VALUES (7, 'Power A — Clean & Squat', 4, 'A', 'Hang Power Clean + Back Squat', '20min: 5min row + jump rope 3min. Then Hang Power Clean ramp: 3@40%, 3@55%, 2@65%, 1@72% before working sets. Drop drills: high pull practice without catch. Triple extension drills.', 'Wrist and forearm mobility (important for clean catch). Hip flexor and shoulder mobility.', 'POWER PHASE RULE: bar speed is the load. If bar speed slows — the weight is too heavy. Reduce load before reducing reps. Athletes new to Olympic lifts: start at 50-60% of estimated 1RM hang clean regardless of strength levels. Technique always precedes load in Olympic lifts.', 'Monday', 7) ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (7, 15, 1, 'Main — Power', 4, 4, 4, 70, '60-70% of 1RM Hang Clean. SPEED not weight. Rest fully between sets — this is quality work.', 240, 'X-0-X-0', 'Hip drive FIRST, then high pull. Elbows lead the bar. Catch aggressively.', 'Week 1: 65%. Week 2: 68%. Week 3: 72%. Week 4: 75% for 3 reps.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (7, 1, 2, 'Main — Strength', 4, 4, 4, 82, 'Heavy squat to support the power work. Maintain strength gains from Phase 3.', 240, '2-0-X-0', 'EXPLOSIVE concentric intent — squat like you''re trying to jump.', 'Hold Phase 3 peak loads or slight reduction — volume drops here.') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (7, 12, 3, 'Power', 3, 3, 4, 75, 'Push press: use leg drive. This is a power exercise.', 180, 'X-0-X-0', 'Explosive hip dip-drive. Bar moves as fast as possible.', 'Add 2.5kg/week') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (7, 3, 4, 'Accessory', 3, 5, 6, 75, 'Maintain hamstring strength. Slightly less volume than previous phases.', 120, '3-1-X-0', 'Slow and controlled. Feel the hamstring load.', 'Maintain Phase 3 loads') ON CONFLICT DO NOTHING;
INSERT INTO sc_workout_templates (id, name, sc_phase_id, session_label, session_focus, warmup_notes, cooldown_notes, coach_notes, week_placement, display_order) VALUES (8, 'Power B — Clean & Hinge', 4, 'B', 'Power Clean + Deadlift Variants', '20min: Ramp Power Clean: 3@40%, 3@55%, 2@65%, 1@72%. Transition drill: Hang clean → Power clean. Full warm-up — this is technically demanding.', 'Forearm and wrist mobility. Hip flexor stretch. Light thoracic rolling.', 'Session B runs Power Clean from the floor — higher technical demand than hang. Watch for bar drifting forward on the way up. If technique degrades, revert to Hang Power Clean. Jump Squat is LOW LOAD — 30-40% of Back Squat max. Athletes will try to go heavier. Don''t allow it.'',', 'Thursday', 8) ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (8, 16, 1, 'Main — Power', 4, 3, 3, 75, '75% of Power Clean 1RM. Max 80% — quality over load.', 240, 'X-0-X-0', 'Maintain back angle from floor to knees. Accelerate through the pull. Explosive.', 'Add 2.5kg/week if bar speed maintained') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (8, 17, 2, 'Power — Reactive', 4, 4, 4, 35, '30-40% of Back Squat ONLY. MAX jump height intent. Light enough to leave the floor with bar.', 180, 'X-0-X-0', 'MAXIMUM jump height intent. Land softly. This is reactive strength training.', 'Focus on jump height quality, not load increase') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (8, 4, 3, 'Strength', 4, 3, 4, 85, 'Maintain deadlift strength from Phase 3.', 240, '2-0-X-0', 'Explosive pull. Bar speed as fast as possible.', 'Maintain Phase 3 peak loads') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (8, 10, 4, 'Upper', 3, 4, 5, 80, 'Maintain upper body strength.', 150, '2-1-X-0', 'Controlled down. EXPLOSIVE press.', 'Maintain Phase 3 loads') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (8, 13, 5, 'Upper', 3, 5, 6, 75, 'Row volume drops in Power phase.', 120, '2-1-X-0', 'Strict position. Bar speed matters here too.', 'Maintain loads') ON CONFLICT DO NOTHING;
INSERT INTO sc_workout_templates (id, name, sc_phase_id, session_label, session_focus, warmup_notes, cooldown_notes, coach_notes, week_placement, display_order) VALUES (9, 'Maintenance — Neural Activation', 5, 'A', 'Full Body Neural Drive — Low Volume High Intensity', '15min: Full ramp-up. Hang Power Clean: 3@50%, 2@62%, 1@70% before working sets. Back Squat: 5@50%, 3@65%, 1@75%. The warm-up IS the session volume.', 'Keep it short. No deep stretching post-heavy session. Light walk 5min. Foam roll as needed.', 'COMPETITION PHASE RULES: (1) Schedule gym 3-4+ days before race day minimum. (2) Volume is 40-50% of Power Phase. (3) Intensity maintained at 80-85% to keep neural adaptations alive. (4) If athlete has a major comp within 10 days, reduce to 1 session that week at 70%. (5) If in taper — gym drops to 1 session every 10-14 days.', 'Monday (or 4+ days before Saturday competition)', 9) ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (9, 15, 1, 'Power', 3, 3, 3, 72, 'Keep clean crisp and fast. This keeps the neural pathway primed.', 180, 'X-0-X-0', 'Quality over everything. Drop any set that looks slow.', 'Maintain — no load increases in competition phase') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (9, 1, 2, 'Strength', 3, 3, 3, 82, '3 heavy singles-to-triples. Enough to remind CNS what heavy feels like.', 240, '2-0-X-0', 'Explosive intent. Stay technical.', 'Maintain Phase 4 loads — never test maxes during competition') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (9, 4, 3, 'Strength', 2, 3, 3, 82, '2 sets only. Minimal deadlift volume in competition phase.', 240, '2-0-X-0', 'Perfect setup every rep.', 'Hold load') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (9, 3, 4, 'Injury Prevention', 2, 6, 8, 70, 'Hamstring maintenance. Cannot drop this even in competition phase.', 120, '3-1-2-0', 'Slow eccentric is the injury prevention. Don''t rush this.', 'Hold load') ON CONFLICT DO NOTHING;
INSERT INTO sc_template_exercises (template_id, exercise_id, order_index, block_label, sets, reps_min, reps_max, load_pct_1rm, load_notes, rest_seconds, tempo, coaching_cues, progression_note) VALUES (9, 9, 5, 'Glute Activation', 2, 8, 10, 70, 'Pre-activation before competition works. Light hip thrust 2 days out is fine.', 90, '2-1-2-0', 'Full extension. Feel the glutes fire.', 'Hold load') ON CONFLICT DO NOTHING;

-- ============================================================
-- SEED: 2025/26 macrocycle blocks
-- ============================================================
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 13, 'Block 13 — Transition', '2025-05-12', '2025-06-01', 'Transition', 'Introduce', 'Minimal', 'Low', 'High', 'AA') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 1, 'Block 1', '2025-06-02', '2025-06-29', 'General Prep', 'Volume', 'Introduce', 'Low', 'High', 'HYP') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 2, 'Block 2', '2025-06-30', '2025-07-27', 'General Prep', 'Intensity', 'Volume', 'Medium', 'Medium', 'MAX') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 3, 'Block 3', '2025-07-28', '2025-08-24', 'General Prep', 'Maintain', 'Intensity', 'High', 'Low', 'MAINT') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 4, 'Block 4', '2025-09-01', '2025-09-28', 'Specific Prep', 'Volume', 'Maintain', 'Low', 'High', 'HYP') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 5, 'Block 5', '2025-09-29', '2025-10-26', 'Specific Prep', 'Intensity', 'Volume', 'Low', 'High', 'MAX') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 6, 'Block 6', '2025-10-27', '2025-11-23', 'Competition Prep', 'Maintain', 'Intensity', 'Medium', 'Medium', 'MAINT') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 7, 'Block 7', '2025-11-24', '2025-12-21', 'Competition', 'Maintain', 'Intensity', 'Medium', 'Medium', 'MAINT') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 8, 'Block 8', '2025-12-22', '2026-01-18', 'Competition', 'Maintain', 'Volume', 'High', 'Low', 'MAINT') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 9, 'Block 9', '2026-01-19', '2026-02-15', 'Competition', 'Maintain', 'Maintain', 'Low', 'High', 'MAINT') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 10, 'Block 10', '2026-02-16', '2026-03-15', 'Comp Specific Prep 2', 'Reduce Loads', 'Maintain', 'High', 'Low', 'MAINT') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 11, 'Block 11', '2026-03-16', '2026-04-12', 'Competition Phase 2', 'Reduce Loads', 'Reduce Volumes', 'High', 'Low', 'MAINT') ON CONFLICT DO NOTHING;
INSERT INTO macrocycle_blocks (season, block_number, block_name, start_date, end_date, mesocycle_phase, strength_label, speed_label, intensity_level, volume_level, sc_phase_code) VALUES ('2025-26', 12, 'Block 12', '2026-04-13', '2026-05-10', 'Competition Phase 2', 'Reduce Loads', 'Reduce Volumes', 'High', 'Low', 'MAINT') ON CONFLICT DO NOTHING;

-- ============================================================
-- SEED: Sample athletes (update assessment_code to match speed-assessment.online)
-- ============================================================
INSERT INTO athletes (name, initials, event_group, squad, assessment_code) VALUES
  ('Archer McHugh', 'AM', '100m / 200m', 'Performance', 'ARCHER-001'),
  ('Luke Rollo',    'LR', '400m',        'Development', 'LUKE-001')
ON CONFLICT DO NOTHING;

-- ============================================================
-- SEED: Performance benchmarks (shared with speed-assessment.online)
-- ============================================================
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', '100m / 200m', '20m', 'U20', 'M', 'Good', 2.9, 'seconds') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', '100m / 200m', '20m', 'U20', 'M', 'State', 2.82, 'seconds') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', '100m / 200m', '20m', 'U20', 'M', 'National', 2.75, 'seconds') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', '100m / 200m', '60m', 'U20', 'M', 'Good', 7.1, 'seconds') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', '100m / 200m', '60m', 'U20', 'M', 'State', 6.95, 'seconds') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', '100m / 200m', '60m', 'U20', 'M', 'National', 6.75, 'seconds') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', '100m / 200m', '150m', 'U20', 'M', 'Good', 17.0, 'seconds') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', '100m / 200m', '150m', 'U20', 'M', 'State', 16.5, 'seconds') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', '100m / 200m', '150m', 'U20', 'M', 'National', 15.8, 'seconds') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', 'General', 'slj', 'U20', 'M', 'Good', 2.55, 'metres') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', 'General', 'slj', 'U20', 'M', 'State', 2.7, 'metres') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', 'General', 'slj', 'U20', 'M', 'National', 2.85, 'metres') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', 'General', 'vj', 'U20', 'M', 'Good', 45.0, 'centimetres') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', 'General', 'vj', 'U20', 'M', 'State', 52.0, 'centimetres') ON CONFLICT DO NOTHING;
INSERT INTO performance_benchmarks (sport, event_group, metric, age_group, gender, level, value, unit) VALUES ('Athletics', 'General', 'vj', 'U20', 'M', 'National', 58.0, 'centimetres') ON CONFLICT DO NOTHING;