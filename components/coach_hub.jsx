import { useState, useMemo } from "react";

const SESSIONS = [{"id":1,"name":"100m & 200m start practice","description":"1 x30m, 1 x40m & 1x 50m Block starts\nRest = 3mins, 4 mins & 5mins\n2x50m bend - 5mins break\n1 x100m (50m bend + 50m straight) 6mins break\n1 x120m sprint","session_type":"Technical","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":2,"name":"100m Race preparation work","description":"100m work\n3 x 30m sprints - 3mins rest between\n2 x 60m sprints - 6 mins rest between\n2 x 100m - 10-12mins or Full recovery","session_type":"Speed","event_group":"100m","training_phase":"Competition","intensity_level":"Max"},{"id":3,"name":"100m Tempo / Speed Endurance","description":"5min jog, active warmup\n5min running drills\n4 x 60m run throughs\n2 Sets of 3-4x100m WB +1min to be fresh -\nHold form and run tall, no quicker than 80%\n6 mins break between sets","session_type":"Speed_Endurance","event_group":"100m","training_phase":"Base","intensity_level":"Moderate"},{"id":4,"name":"100m form runs","description":"Extended In & Out Warm Up\nStretches, Activation and SMR\n4 x 50m run throughs\n3 x 10 x Wickets at 5-6 shoe spacing - 5min break (20m fast run in)\n2 x 3 x 100m relaxed form runs - WB + 1 min\n8 mins betweens sets","session_type":"Technical","event_group":"100m","training_phase":"Base","intensity_level":"Moderate"},{"id":5,"name":"100m or 400m preparation work","description":"100m / 200m work\n3 x 30m sprints - 2mins rest between\n2 x 60m sprints - 5 mins rest between\n2 x 100m - 10 mins or Full recovery\n1 x 150m\n400m work - Split 400s\n2 x 60m bend (Race start setup)\n1 x 300m 400m start to top bend - 10-12mins recovery\n1 x 200m (200m start to 400 Finish mark) 8mins recovery\n1 x 100m to Finish line","session_type":"Speed","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":6,"name":"150-80s","description":"Active warmup and running drills\n4x60m run throughs\n*Short Hill Sprints*\n3 x10 sec hill - WB = 60-90secs recovery\n2 x13-15sec hill - WB = 2/2:30mins\n4 x 150m, WB 80m, run 80m\nWalk 250m recovery","session_type":"Speed_Endurance","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":7,"name":"150m speed endurance building session","description":"Dynamic warmup + running drills\n4 x 60m run throughs\n5 x 40m Sprints, 2mins recovery\n3 x 3 x 150m - Walk / Jog / Walk Recovery\n4mins between sets\nBodyweight circuit x 2","session_type":"Speed_Endurance","event_group":"Multi","training_phase":"Base","intensity_level":"High"},{"id":8,"name":"2 x 2km Tempo","description":"2 x 2km steady @4 to 4:30min pace - 5mins between reps","session_type":"Aerobic","event_group":"General","training_phase":"Base","intensity_level":"Moderate"},{"id":9,"name":"200m Endurance Session 1","description":"5 mins jog\n5 x Running drill circuit\n4 x 60m run throughs on track or grass\n3-4 x 30-40m bend starts\n2 x 3 x 200m @90% - walk 200m recovery (5-6mins between reps)\n8 mins between sets","session_type":"Speed_Endurance","event_group":"200m","training_phase":"Base","intensity_level":"High"},{"id":10,"name":"200m endurance Session 2","description":"5 mins jog\n5 x Running drill circuit\n4 x 60m run throughs on grass\n3-4 x 30-40m bend starts\n2 x 3 x 200m - walk 200m recovery\n8mins after 3\n*variation - 2 x 120, 150, 250m - 5mins rest\n8mins after each set","session_type":"Speed_Endurance","event_group":"200m","training_phase":"Base","intensity_level":"High"},{"id":11,"name":"200m prep work","description":"2 x 40m bend starts - 4mins\n2 x 70m bend starts - 6 mins\n2 x 150m - FAST\n10mins Break, then 12mins after 2\n1 x 250m in 30 secs or under\n4 x 60m ease down runs and stretching","session_type":"Speed","event_group":"200m","training_phase":"Competition","intensity_level":"High"},{"id":12,"name":"200m preparation - Split 200","description":"4 x 20m sprints\n3 x 30m sprints\n2 x 50m bend\n3 x 120m, 1min break, sprint back 80m\n6 mins Break","session_type":"Speed","event_group":"200m","training_phase":"Competition","intensity_level":"High"},{"id":13,"name":"200m preparation work","description":"3 x 30m sprints\n2 x 50m sprints\n2 x 40m bend, 2 x 60m bend\n2 x 100m - 50m bend, 50m straight\n2 x 150m, 1 x 200m, 1 x 250m 6-8mins between reps","session_type":"Speed","event_group":"200m","training_phase":"Competition","intensity_level":"High"},{"id":14,"name":"200m preparation work 2","description":"3 x 30m sprints\n2 x 50m sprints\n2 x 60m bend, 2 x 80m (40m & bend into straight)\n2 x 120m @90% 6mins between reps\nAthletes running at 95% = 8mins Recovery\n10mins Break\n2 x 200m @90%\n10mins between reps","session_type":"Speed","event_group":"200m","training_phase":"Competition","intensity_level":"High"},{"id":15,"name":"250 - 150 (400m session)","description":"4 x60m RT\n2 x 250 / 150m in 35-40sec 3-4mins between 250m\n10 min break between sets\n4 x 70m Strides\nAb Circuit","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Competition","intensity_level":"Max"},{"id":16,"name":"3-5 km at a steady pace","description":"Can also be done as 2 x 2km, with 5min rest and stretch in between","session_type":"Aerobic","event_group":"General","training_phase":"Transition","intensity_level":"Low"},{"id":17,"name":"3km run","description":"Easy run at a pace that you can have a chat","session_type":"Aerobic","event_group":"General","training_phase":"Transition","intensity_level":"Low"},{"id":18,"name":"400+ 150 tempo session","description":"After Warmup and Short Sprints\n400m 5mins rest\n4x150m 2mins rest\n400m 5mins rest\nEase down run throughs and stretching","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Competition","intensity_level":"High"},{"id":19,"name":"400m Endurance building session","description":"Dynamic warmup and running drills\n4 x 60m run throughs\n4 x 300m @80% - 6mins recovery\n8mins between sets\nOR - 4 x 500m with 6mins rest\n5 x 80m runs @ 80% - Recovery = WB in 1min\nCore workout circuit","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Base","intensity_level":"High"},{"id":20,"name":"400m Gut buster","description":"In and Out warmup\nActive stretching exercises and Core activation\n(leg swings, squats, plank, plank with leg left)\n3-4 x 80m RT's\n2 x 300-80-70m @90%\nRun 300, rest 1min, Run 80m to finish, WB to 70m, run to finish, then walk a slow lap in 6-8mins\nThen repeat\n4 x 50m Easy Stride Run throughs to help the legs recover","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Competition","intensity_level":"Max"},{"id":21,"name":"400m prep - 350 / 250","description":"Active Warmup and running drills\n4 x 60m run throughs\n3 x 40m sprints - Straight\n2 x 70m sprints - Bend\n1 x 350m, 1 x 250m - 15mins break","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Competition","intensity_level":"Max"},{"id":22,"name":"400m prep session - Speed Endurance","description":"4 x60m run throughs\n3 x 50m sprints - 5 mins rest between each\n2 x 2 x 200m @90% 8mins rest between reps\n15mins break after 1st set\n(Target time = 25 secs or under)","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Competition","intensity_level":"High"},{"id":23,"name":"400m race tempo 200s","description":"4 x60m run throughs\n3 x40m sprints - Straight - 3mins rest between each\n3 x 200m at 400m race pace\n10-12 mins break between each","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Competition","intensity_level":"High"},{"id":24,"name":"400m speed endurance","description":"3x30m block starts\n2x50m block starts\n300m @90%\nWalk 150m in 3mins recovery\n150m @90%\nWalkback 70m / 2mins rest\n70m hold form\nWalk 1 lap in 6mins\nRepeat","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Base","intensity_level":"High"},{"id":25,"name":"400m speed endurance work 1","description":"2 Lap jog\nSquats, leg swings, Skipping drills\nRunning drills x 2 each\n3-4 x 80m RT's\n4 x 20m fast starts\n3 x 50m sprints - 2mins rest between each\n2 x 250m @80% effort - walk 80m - sprint 70m to finish.\nRest is walk 1 lap in 5-6mins\n5-10 mins Stretching","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Base","intensity_level":"High"},{"id":26,"name":"800 - 1500m workout 1","description":"600m @ 1500m pace\n3mins Rest\n4x200m @800m pace 90 secs rest\nthen 3mins break\n600m @1500m pace","session_type":"Speed_Endurance","event_group":"800_1500m","training_phase":"Base","intensity_level":"High"},{"id":27,"name":"800m prep & Race sim","description":"Active / Skipping warmup\nRunning drills\n4 x 50m Run throughs\nSprint work x 3 reps\n300m @90% - 5mins rest\n200m @90% - From 300m start - 4mins rest\n200m from 200m start - 5mins rest\n120m or 150m\n1 lap easy jog or 4 x 60 ease down runs\nStretching","session_type":"Speed_Endurance","event_group":"800_1500m","training_phase":"Competition","intensity_level":"High"},{"id":28,"name":"Acceleration Development 1 (INTRO)","description":"3-4 SETS x Accel Ladder 20 / 30 / 40m = 300-400m\nRECOVERY = 2', 3 & 4 mins\n3 x Jumping and Bounding Drills over 30-40m = 200m\nTechnical Form Running = 4 x 100m @90% = 400m\nMedball Circuit x 3","session_type":"Speed","event_group":"General","training_phase":"Pre_season","intensity_level":"Moderate"},{"id":29,"name":"Acceleration and Speed Endurance","description":"3x20m sprints : 1min break\n2x30m Sprints : 2 mins break\n2x40m Sprints : 3mins break\n2 x 4 x 80m / 45 secs recovery\n4 mins between sets","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":30,"name":"Agility and Speed Endurance 1","description":"5min jog, active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n4 x 4 cone tennis ball drill (set cones up 4m apart in a square)\n1-2mins between reps\n4 x Agility / Zig Zag runs over 20-30m\nShort Sprints - 3 x 40m\n3 x 120m build up runs (40m 50%, 40m 75%, 40m 100% effort)\n4mins recovery\n1 x 250m Run","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":31,"name":"Agility and Speed Endurance 2","description":"5min jog, active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n3x30m, 2x50m, 2x80m WB +1min to be fresh\n3-4 150m build up runs - 50m@50%, 50m@75%, 50m@100% - 3mins recovery\nAb & Back exercises","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":32,"name":"Athletic Performance Testing","description":"Using Electronic Timing Gates and Jump Mat\n20m Sprint x 2\n60m sprint x 2\n150m Sprint\n300m (for 400m athletes)\nVertical Jump x 3\nStanding Long Jump","session_type":"Testing","event_group":"General","training_phase":"Base","intensity_level":"Max"},{"id":33,"name":"Block Starts + Max V","description":"Heavy Sled x 20m\nBlock Starts x 30m / 40m out to 50m\nFlying 30 x 2\nMed Ball Throws and Sandpit Jumps","session_type":"Speed","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":34,"name":"Block Starts and Max V Work","description":"Block Starts x 4 x 40m\n3 x 75m - In & Outs (15m Accel, 15m Maintain - 3 Accels)\n6 mins between reps\n3 x120m - hard bend relaxed straight\n5 mins recovery","session_type":"Speed","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":35,"name":"Footy Boys session 1","description":"Acceleration, Speed and Form running\nIn & Outs 20, on, 20m off, 20m on x 4\n60m, 80m, 120m x 2\n3-4 x 250m, walk 150m recovery\nLateral Hurdle jumps","session_type":"Speed","event_group":"Team_Sport","training_phase":"Base","intensity_level":"Moderate"},{"id":36,"name":"Hills + Track","description":"5 x 10sec hill, 1min WB recovery\n5mins break\n4x30m sprints, 1 min recovery\n4mins\n3 x 60m on/off 15m on, 10m off\n5x60m Jog/WB/Jog/WB/Jog","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":37,"name":"Hills + Track (150s)","description":"5 x 15sec hill, 1min WB recovery\n5mins break\n10m roll in into 4x30m sprints, 1 min recovery\n4mins\n2 x 2 x 150m - 2 mins rest between sets\n4 mins Break between sets","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":38,"name":"Hills and Track Workout","description":"5 min jog\nRunning Drills and Active Warmup\n4x60m Run throughs\n4 x 30m sprints - WB\n400/800m Runners = 4 x 90 sec gravel trail - 3mins rec\n100/200m runners = 5 x 20 sec efforts\nAll = 5 x 10 sec hill - WB + 30 secs\nTrack: 3 x 120 or 150m Reps - WB\nPowerband and Mini band strength exercises","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":39,"name":"Long Speed Endurance - Ladder Down","description":"2 lap easy jog\nRunning drills\n4 x 60m Run throughs\n500m, 400m, 300m, 200m, 100m\nRecoveries are 4min, 3min, 2min, 1min - judge your pace!\n1 lap easy jog or 4 x 60 ease down runs\nStretching","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Base","intensity_level":"High"},{"id":40,"name":"Long Speed Endurance - Ladders","description":"2 lap easy jog\nRunning drills\n4 x 60m Run throughs\n500, 300m, 100, 300m, 500m\nRecoveries are 5min, 3min, 1min, 3min - judge your pace!\n1 lap easy jog or 4 x 60 ease down runs\nStretching","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Base","intensity_level":"High"},{"id":41,"name":"Max V and Speed session","description":"3 x 30m Accels from 3 point start\n2 x 12 wickets with 20m run in and 5 stride gap\n6 mins recovery\n1 x 60-80-120\nRest = 6mins between reps","session_type":"Speed","event_group":"General","training_phase":"Competition","intensity_level":"High"},{"id":42,"name":"Plyo Intro + Speed Endurance","description":"Dynamic warmup + drills\n5 x standing long jumps\n4 x 20m bounding\n5 x 20m accelerations over low hurdles\n(1min rec between reps)\n5 x 100m @80%\n4mins recovery between reps\n4 x 20-30m resisted harness or sled pulls\nBodyweight circuit","session_type":"Plyo_Power","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":43,"name":"Short Fartlek","description":"5-6min jog warmup and Active stretches\n(squats, leg swings, inchworm & spidermans)\n3x60m run throughs\n4x30sec run, 30 sec jog - 3mins rest\n3x1min run, 1min jog\n2x2min run, 2mins rest","session_type":"Aerobic","event_group":"General","training_phase":"Transition","intensity_level":"Moderate"},{"id":44,"name":"Sled PUSH and Max V","description":"4 x 50m Run throughs\nHeavy Sled PUSHES x 20m x 3 reps - Superset with 3 x 30m Sprints\nFlying 30m over wickets x 3 - 6 mins break\nMed Ball Throws: Underhand throw 2x10, Ab Slams 2x10, Rotation Side throws 2x10 each side","session_type":"Speed","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":45,"name":"Sled Push and Max V","description":"4 x 50m Run throughs\nSled Push x 20m x 3 reps - Superset with 3 x 30m Sprints\nFlying 30m over wickets x 3 - 6 mins break\n2 x 70-80 run - 8 mins rest\nMed Ball Throws: Underhand throw 2x10, Ab Slams 2x10, Rotation Side throws 2x10 each side","session_type":"Speed","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":46,"name":"Sled Push, Max V and Wickets","description":"Heavy Sled x 20m\nBlock Starts x 30m / 40m out to 50m\nFlying 30 x 2 (Wicket runs?)\nMed Ball Throws and Sandpit Jumps","session_type":"Speed","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":47,"name":"Sled Towing and Max V","description":"4 x 50m Run throughs\n3 Point or Block Starts\nSled towing x 20m x 3 reps - Superset with 3 x 30m Sprints\nFlying 30m over wickets x 2 - 6 mins break\nMed Ball Throws: Underhand throw 2x10, Ab Slams 2x10, Rotation Side throws 2x10 each side","session_type":"Speed","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":48,"name":"Speed Endurance 2 - Ladder Up & Down","description":"2 lap easy jog\nRunning drills\n4 x 60m Run throughs\n5 x 30m sprints - Wb + 1 min recovery\n150-200-250-250-200-150m\nRecovery = 4, 5, 6, 8, 6, 4mins between reps\n4 x 70m ease down run throughs and stretching","session_type":"Speed_Endurance","event_group":"Multi","training_phase":"Base","intensity_level":"High"},{"id":49,"name":"Speed Endurance Building Session 1","description":"5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 80m run throughs\n2 sets of 4 x 100m @ 80% WB recovery\nBodyweight Exercises & Core","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"Moderate"},{"id":50,"name":"Speed Endurance Combo session 2","description":"Focussed Speed Drills\nMedball Push Pass starts - 4 x 20m\n2x5x80m @10-12secs, 60 sec break\n3mins between sets\n2 x 200m, walk 100m, run 100m - 4 mins break","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":51,"name":"Speed Endurance Ladder","description":"1 Lap jog, running drills and stretches\n4 x 50m Run throughs\n3 x 20m Sprint starts - FAST\n2 Sets of:\n50m @90% - WB + 1 min rest\n70m @90% - WB + 90 secs rest\n90m @90% - WB + 2mins rest\n120m @90% - 5 mins break\nRepeat in Reverse order\n5mins break then\n1 x 250m @80%\nAb & Back exercise circuit","session_type":"Speed_Endurance","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":52,"name":"Speed Endurance Session 1","description":"5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n1 x 60m, 80m, 100m @ 80% WB recovery +1min\n2 Sets of Speedmakers - 5xSprint 50m, Jog 50m, Walk 50m\n3 x 5 Double Leg Jumps for distance (measure it)\n3 x 6 Jumps onto a bench or stairs (for height)","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"Moderate"},{"id":53,"name":"Speed Endurance Session 2","description":"5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n2 x 4 x 80m @75%- rest 30 secs and run back\n2 Sets High bench stepup - 8-10 each leg\n2 Set of 5 hops for distance each leg","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":54,"name":"Speed Endurance Session 3","description":"5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n3 x 30m flying starts - 5m rolling start\n2 x 50m flying starts - 5m rolling start\n2 Set of 4 x 80m sprints @70% effort\nJog back, walk back, jog back, walk back Rec\n5min break, then do 2nd Set","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":55,"name":"Speed Endurance Session 4","description":"5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n4 x 30m block starts - WB + 1min\n4 x 120m sprints @70% effort\nJog back, walk back, jog back, walk back Rec\n5min break\n3 x 200m - WB, Jog back, WB recovery","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":56,"name":"Speed Endurance Session 5","description":"In & Out Warm up - Run 100m, jog/skip 50m, walk 50m (Until you have run 3 laps)\nActive Stretches\nRunning drills\n3 x 30m stand starts - WB\n2 x 60m sprints WB + 1-2mins\n6x200m@80%\nRec 3-4 mins rest\nLeg Circuit","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":57,"name":"Speed Session + hills","description":"5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n3 x 30m sprints\n2x 60m sprints\n4 x 15sec hill - WB in 1min\n4 x 100m @ 80% WB recovery +1min if needed","session_type":"Speed","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":58,"name":"Speed Session 1","description":"5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n3 x 30m Accelerations\n2 x 60m sprints\n1 x 100-120-150m 6-8mins between reps\nStretching","session_type":"Speed","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":59,"name":"Speed and Agility for Team Sport","description":"Dynamic warmup + drills\n3 x Compass Drill\n5 x standing long jumps + 20m sprint\n4 x 20m bounding\n5 x 20m accelerations over low hurdles\n(1min rec between reps)\n5 x 100m @80%\nWalk back recovery between reps","session_type":"Speed","event_group":"Team_Sport","training_phase":"Base","intensity_level":"Moderate"},{"id":60,"name":"Speed and Power Testing","description":"Standing Long jump - 2 attempts\n150m sprint - 1 attempt\n20mins break\n300m run - 1 attempt","session_type":"Testing","event_group":"General","training_phase":"Base","intensity_level":"Max"},{"id":61,"name":"Speed and Speed Endurance","description":"5min jog, active warmup\n5 min Balance and Activation\n5min running drills\n4 x 60m run throughs\n4x20m fast sprints, block or 3 point start\n3x60m blocks or standing start\n2 Sets of 4x100m WB +1min to be fresh\nHold form and run tall, no quicker than 80%\nAb & Back exercises","session_type":"Speed_Endurance","event_group":"General","training_phase":"Base","intensity_level":"High"},{"id":62,"name":"Speed session for 200m","description":"5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n4 x 50m run throughs\n3 x 30m Accelerations\n2 x 60m sprints\n3 x 100m fast 5mins between reps\n1 x 200m @90% 8mins\n1 x 250m @90%\nStretching","session_type":"Speed","event_group":"200m","training_phase":"Competition","intensity_level":"High"},{"id":63,"name":"Speed week - Race Sim for 400m","description":"1 lap jog and skipping warmup\n4 sets of each running drill\n4 x 60m run throughs\n3 x 20-30m block starts or 3 point start\n3 x 40m sprints from 400m start\n1 x 350m @ 400m Race pace - 10mins rest\n1 x 250m @ 400m Race pace - 10mins rest\n1 x100m @200m race pace\nWalk 5mins and stretch","session_type":"Speed_Endurance","event_group":"400m","training_phase":"Competition","intensity_level":"Max"},{"id":64,"name":"Speedweek Sprint Session","description":"In & Out Warmup + Dynamic Stretching\nSpeed Drills and Activation\n3x80m Run throughs\n2 x 40m Block Starts, 2 x 60m Bend starts\n3 x 150m @ 80%\n1 x 300m","session_type":"Speed","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":65,"name":"Sprint and Plyo Session","description":"In & Out Warmup + Dynamic Stretching\nSpeed Drills and Activation\n4x60m Run throughs\nBounding starts - 20m bound, 20 sprint - Grass\n3 x50m Block Starts, 4 x100m @ 90% 5mins recovery between reps\n3 x 150m - Walk Back recovery\nDouble leg jumps and Hops for Distance - 2 sets of 20m","session_type":"Plyo_Power","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":66,"name":"Start Practice and Speed Session 1","description":"5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 80m run throughs\nStart practice for 100m - 4 x 30m\nStart practice for 200m 3 x 50m bend\nForm Runs - 80, 100, 120, 150m\nBodyweight Exercises & Core","session_type":"Technical","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":67,"name":"Starts and 200m work","description":"4x60m RT\n4 x 30m starts\n3x50m\n1 x 150, 200, 250m 5', 8-10'","session_type":"Speed","event_group":"200m","training_phase":"Competition","intensity_level":"High"},{"id":68,"name":"Stawell Grass prep","description":"Setup blocks on Grass for start practice\nMark out 120m\n40m Blocks x 2 : 3-4mins break\n60m blocks x 2 : 5 mins break\n2 x 100m (diagonals) 6mins break","session_type":"Technical","event_group":"Multi","training_phase":"Competition","intensity_level":"Moderate"},{"id":69,"name":"Technical Session - Block set-ups and Start Execution","description":"Standing start with Back Block push-off 3 x 20m\nBlock start 3 x 30m - 3 mins rest\nBlock Starts 2 x 40m - 4 mins rest\n2 x Flying 30m - 20m run in (50m Total)\n6 mins between reps\nMedball Throws - 2 sets:\nChest pass x 8, Underhand FWD Throw x 8, Overhead FWD Throw x 8","session_type":"Technical","event_group":"Multi","training_phase":"Competition","intensity_level":"High"},{"id":70,"name":"Tempo Sandwich","description":"1km warmup run\nActive stretches and Running Drills\n5min tempo - 2 min rest\n4 x 30 sec hard/30sec easy - 3mins rest after the 4 hard efforts\n(30 secs easy is an active recovery)\n5min tempo","session_type":"Aerobic","event_group":"General","training_phase":"Transition","intensity_level":"Moderate"},{"id":71,"name":"Transition Week 1 - Session 1","description":"In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n3 x 10m Roll in 40m Accelerations\n5 x 80m relaxed runs - WB recovery\nSandpit bear crawls & inchworms\nAb - Flutter kicks and Planks","session_type":"Speed","event_group":"General","training_phase":"Transition","intensity_level":"Low"},{"id":72,"name":"Transition Week 1 - Session 2","description":"In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n2 x 20m Straight leg bound into 30m Accelerations\n2 x 20m Speed Bound into 30m Acceleration\n2 x 4 x 100m relaxed runs - WB recovery\n4mins between Sets\nCool down static stretches - 10mins","session_type":"Speed","event_group":"General","training_phase":"Transition","intensity_level":"Low"},{"id":73,"name":"Transition Week 2 - Session 1","description":"Continuous Warm-up\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n4 x 20m Accel - 20m Roll, 20m Accel, then coast down\n2 x 4 x 80m relaxed runs (Up and Backs) 30 secs recovery\n5mins between sets\nCore x 2 Sets x 10 reps: Double leg lifts, Plank with shoulder taps, V-Sit, Side plank\nCool down static stretches - 10mins","session_type":"Speed_Endurance","event_group":"General","training_phase":"Transition","intensity_level":"Moderate"},{"id":74,"name":"Transition Week 2 - Session 2","description":"In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n2 x 20m Straight leg bound into 30m Accelerations\n2 x 20m B Skip into 20m Acceleration\n3 x 120m relaxed runs - WB recovery\n4mins Break\n2 x Run 200m, walk 200m @70-80%\nCool down static stretches - 10mins","session_type":"Speed","event_group":"General","training_phase":"Transition","intensity_level":"Moderate"},{"id":75,"name":"Transition Week 3 - Session 1","description":"Continuous Warm-up\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n5 x 20m Accelerations - WB + 1min\n5 x 70m - WB recovery\n5mins Break\n2 x 250m - walk 200m recovery, run 150m - 4 mins rest & repeat\nCore x 2 Sets x 10 reps: Double leg lifts, Plank with shoulder taps, V-Sit, Side plank","session_type":"Speed_Endurance","event_group":"General","training_phase":"Transition","intensity_level":"Moderate"},{"id":76,"name":"Transition Week 3 - Session 2","description":"In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n2 x 3 x 150m relaxed runs - WB recovery\n4mins Break\nCool down static stretches - 10mins","session_type":"Speed_Endurance","event_group":"General","training_phase":"Transition","intensity_level":"Moderate"},{"id":77,"name":"Transition Week 4 - Session 1","description":"Continuous Warm-up\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n5 x 20m Accelerations - WB + 1min\n4 x 100m (or 13-15 sec) Grass or Track runs - 90secs-2min WB recovery\n5mins Break\n2 x 200m - walk 200m recovery in 4-5mins","session_type":"Speed_Endurance","event_group":"General","training_phase":"Transition","intensity_level":"Moderate"},{"id":78,"name":"Transition Week 4 - Session 2","description":"In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\nTraffic Light Drill for warmup\n4-5 x 10-15min 2 point stats with feedback\n2 x 4 x 80/40m @80% (run 80m, 30sec rest, run back 40m / 1min rest)\n5 mins Break\nCore Circuit x 2 - flutter kicks, Hollow rocks and Plank with alternating leg lifts\nCool down static stretches - 10mins","session_type":"Technical","event_group":"General","training_phase":"Transition","intensity_level":"Moderate"},{"id":79,"name":"Wickets and Max V Session 1","description":"Muscle activation and Active Warmup Drills\n4 x 50m Run throughs\n18w at 6 step spacing - 4 sets\nSpeed Bounding over 30m x 3-4\n3 x Flying 30m (20m run in)\n3 x 60-80m bend runs","session_type":"Speed","event_group":"General","training_phase":"Base","intensity_level":"High"}];

const TYPE_META = {
  Speed:           { label: "Speed",           color: "#F26522", bg: "rgba(242,101,34,0.12)"  },
  Speed_Endurance: { label: "Speed End.",       color: "#00B4D8", bg: "rgba(0,180,216,0.12)"   },
  Technical:       { label: "Technical",        color: "#a78bfa", bg: "rgba(167,139,250,0.12)" },
  Aerobic:         { label: "Aerobic",          color: "#34d399", bg: "rgba(52,211,153,0.12)"  },
  Plyo_Power:      { label: "Plyo / Power",     color: "#f59e0b", bg: "rgba(245,158,11,0.12)"  },
  Testing:         { label: "Testing",          color: "#f87171", bg: "rgba(248,113,113,0.12)" },
};

const INTENSITY_COLOR = { Low:"#34d399", Moderate:"#00B4D8", High:"#f59e0b", Max:"#f87171" };

const DEFAULT_TAGS = {
  1:["starts","blocks","bend","technical"],2:["sprints","100m","race-prep"],3:["tempo","100m","form"],4:["wickets","form","100m"],
  5:["race-prep","100m","400m","splits"],6:["hills","150m","endurance"],7:["150m","endurance","bodyweight"],8:["tempo","aerobic"],
  9:["200m","bends","endurance"],10:["200m","bends","endurance"],11:["200m","prep","bends"],12:["200m","splits","prep"],
  13:["200m","bends","prep"],14:["200m","bends","prep"],15:["400m","250m","ladder"],16:["aerobic","easy","transition"],
  17:["aerobic","easy","transition"],18:["400m","tempo","150m"],19:["400m","endurance","base"],20:["400m","gut-buster","race-prep"],
  21:["400m","350m","race-prep"],22:["400m","200m","race-prep"],23:["400m","tempo","200m"],24:["400m","blocks","endurance"],
  25:["400m","250m","endurance"],26:["800m","1500m","endurance"],27:["800m","race-sim","prep"],28:["acceleration","intro","medball"],
  29:["acceleration","80m","endurance"],30:["agility","cones","250m"],31:["agility","150m","core"],32:["testing","gates","jumps"],
  33:["blocks","max-v","sled"],34:["blocks","max-v","120m"],35:["team-sport","footy","agility"],36:["hills","sprints","track"],
  37:["hills","150m","track"],38:["hills","track","multi-event"],39:["400m","ladder","endurance"],40:["400m","ladder","endurance"],
  41:["wickets","max-v","120m"],42:["plyometrics","sled","hurdles"],43:["fartlek","aerobic","intervals"],44:["sled","max-v","medball"],
  45:["sled","max-v","medball"],46:["sled","wickets","medball"],47:["sled","wickets","medball"],48:["ladder","150m","250m"],
  49:["100m","base","core"],50:["medball","80m","200m"],51:["ladder","hills","250m"],52:["speedmakers","jumps","base"],
  53:["80m","hops","base"],54:["flying-30","80m","base"],55:["blocks","120m","200m"],56:["200m","circuit","base"],
  57:["hills","100m","base"],58:["acceleration","sprints","base"],59:["agility","team-sport","hurdles"],60:["testing","jumps","150m"],
  61:["blocks","100m","core"],62:["200m","250m","race-prep"],63:["400m","race-sim","350m"],64:["sprints","150m","300m"],
  65:["plyometrics","blocks","150m"],66:["starts","form-runs","core"],67:["200m","starts","250m"],68:["blocks","grass","diagonals"],
  69:["blocks","medball","flying-30"],70:["tempo","fartlek","aerobic"],71:["drills","acceleration","form"],72:["bounds","acceleration","form"],
  73:["acceleration","core","form"],74:["bounds","120m","form"],75:["acceleration","250m","core"],76:["150m","drills","transition"],
  77:["acceleration","200m","transition"],78:["traffic-light","core","technical"],79:["wickets","max-v","bounds"],
};

const initSessions = SESSIONS.map(s => ({
  ...s,
  tags: [...(DEFAULT_TAGS[s.id] || [])],
  videos: [],
}));

export default function CoachHub() {
  const [sessions, setSessions] = useState(initSessions);
  const [selectedId, setSelectedId] = useState(null);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({ type:"", event:"", phase:"", intensity:"", tag:"" });
  const [activeTab, setActiveTab] = useState("desc");
  const [newTag, setNewTag] = useState("");
  const [showVidForm, setShowVidForm] = useState(false);
  const [vidType, setVidType] = useState("reference");
  const [vidForm, setVidForm] = useState({ url:"", title:"", notes:"", athlete:"", date:"" });

  const allTags = useMemo(() => {
    const t = new Set();
    sessions.forEach(s => s.tags.forEach(tag => t.add(tag)));
    return [...t].sort();
  }, [sessions]);

  const filtered = useMemo(() => {
    return sessions.filter(s => {
      if (filters.type && s.session_type !== filters.type) return false;
      if (filters.event && s.event_group !== filters.event) return false;
      if (filters.phase && s.training_phase !== filters.phase) return false;
      if (filters.intensity && s.intensity_level !== filters.intensity) return false;
      if (filters.tag && !s.tags.includes(filters.tag)) return false;
      if (search) {
        const q = search.toLowerCase();
        return s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q) || s.tags.some(t => t.includes(q));
      }
      return true;
    });
  }, [sessions, filters, search]);

  const selected = sessions.find(s => s.id === selectedId);

  const updateSession = (id, fn) => setSessions(prev => prev.map(s => s.id === id ? fn(s) : s));

  const addTag = () => {
    const t = newTag.trim().toLowerCase().replace(/\s+/g,'-');
    if (!t || selected.tags.includes(t)) { setNewTag(""); return; }
    updateSession(selectedId, s => ({...s, tags:[...s.tags, t]}));
    setNewTag("");
  };

  const removeTag = (tag) => updateSession(selectedId, s => ({...s, tags: s.tags.filter(t => t !== tag)}));

  const addVideo = () => {
    if (!vidForm.url) return;
    const vid = { id: Date.now(), type: vidType, ...vidForm, added: new Date().toLocaleDateString('en-AU') };
    updateSession(selectedId, s => ({...s, videos:[...s.videos, vid]}));
    setVidForm({ url:"", title:"", notes:"", athlete:"", date:"" });
    setShowVidForm(false);
  };

  const removeVideo = (vid_id) => updateSession(selectedId, s => ({...s, videos: s.videos.filter(v => v.id !== vid_id)}));

  const getVideoId = (url) => {
    try {
      const yt = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)/);
      if (yt) return { type:'youtube', id: yt[1] };
      const vm = url.match(/vimeo\.com\/(\d+)/);
      if (vm) return { type:'vimeo', id: vm[1] };
    } catch(e) {}
    return null;
  };

  const filterBtnStyle = (active) => ({
    padding: "4px 10px", borderRadius: 6, fontSize: 12, cursor:"pointer", border: "none",
    background: active ? "#F26522" : "var(--color-background-secondary)",
    color: active ? "#fff" : "var(--color-text-secondary)",
    fontWeight: active ? 600 : 400,
  });

  const sel = (key, val) => setFilters(f => ({...f, [key]: f[key]===val ? "" : val}));

  return (
    <div style={{fontFamily:"var(--font-sans)", minHeight:680, display:"flex", flexDirection:"column", gap:0}}>
      {/* Header */}
      <div style={{display:"flex", alignItems:"center", justifyContent:"space-between", padding:"14px 20px 12px", borderBottom:"0.5px solid var(--color-border-tertiary)"}}>
        <div style={{display:"flex", alignItems:"baseline", gap:10}}>
          <span style={{fontSize:18, fontWeight:500, color:"var(--color-text-primary)"}}>Coach Hub</span>
          <span style={{fontSize:13, color:"var(--color-text-secondary)"}}>Session Library</span>
          <span style={{fontSize:12, background:"rgba(242,101,34,0.15)", color:"#F26522", padding:"2px 8px", borderRadius:20, fontWeight:500}}>{filtered.length} sessions</span>
        </div>
        <input
          placeholder="Search sessions, tags..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{width:220, fontSize:13, padding:"6px 12px", borderRadius:8, border:"0.5px solid var(--color-border-secondary)", background:"var(--color-background-secondary)", color:"var(--color-text-primary)", outline:"none"}}
        />
      </div>

      {/* Body */}
      <div style={{display:"flex", flex:1, overflow:"hidden"}}>
        {/* Filter Sidebar */}
        <div style={{width:180, flexShrink:0, padding:"16px 14px", borderRight:"0.5px solid var(--color-border-tertiary)", overflowY:"auto", maxHeight:620}}>
          <div style={{marginBottom:18}}>
            <div style={{fontSize:11, fontWeight:500, color:"var(--color-text-secondary)", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8}}>Type</div>
            <div style={{display:"flex", flexWrap:"wrap", gap:4}}>
              {Object.entries(TYPE_META).map(([k,v]) => (
                <button key={k} style={{...filterBtnStyle(filters.type===k), background: filters.type===k ? v.color : "var(--color-background-secondary)", color: filters.type===k ? "#fff" : "var(--color-text-secondary)"}} onClick={()=>sel("type",k)}>{v.label}</button>
              ))}
            </div>
          </div>
          <div style={{marginBottom:18}}>
            <div style={{fontSize:11, fontWeight:500, color:"var(--color-text-secondary)", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8}}>Event</div>
            <div style={{display:"flex", flexWrap:"wrap", gap:4}}>
              {["General","Multi","100m","200m","400m","800_1500m","Team_Sport"].map(e => (
                <button key={e} style={filterBtnStyle(filters.event===e)} onClick={()=>sel("event",e)}>{e.replace("_","/ ")}</button>
              ))}
            </div>
          </div>
          <div style={{marginBottom:18}}>
            <div style={{fontSize:11, fontWeight:500, color:"var(--color-text-secondary)", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8}}>Phase</div>
            <div style={{display:"flex", flexWrap:"wrap", gap:4}}>
              {["Pre_season","Transition","Base","Competition","Taper"].map(p => (
                <button key={p} style={filterBtnStyle(filters.phase===p)} onClick={()=>sel("phase",p)}>{p.replace("_"," ")}</button>
              ))}
            </div>
          </div>
          <div style={{marginBottom:18}}>
            <div style={{fontSize:11, fontWeight:500, color:"var(--color-text-secondary)", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8}}>Intensity</div>
            <div style={{display:"flex", flexWrap:"wrap", gap:4}}>
              {["Low","Moderate","High","Max"].map(i => (
                <button key={i} style={{...filterBtnStyle(filters.intensity===i), background: filters.intensity===i ? INTENSITY_COLOR[i] : "var(--color-background-secondary)", color: filters.intensity===i ? "#fff" : "var(--color-text-secondary)"}} onClick={()=>sel("intensity",i)}>{i}</button>
              ))}
            </div>
          </div>
          <div>
            <div style={{fontSize:11, fontWeight:500, color:"var(--color-text-secondary)", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8}}>Tags</div>
            <select value={filters.tag} onChange={e=>setFilters(f=>({...f,tag:e.target.value}))}
              style={{width:"100%", fontSize:12, padding:"5px 8px", borderRadius:6, border:"0.5px solid var(--color-border-secondary)", background:"var(--color-background-secondary)", color:"var(--color-text-primary)"}}>
              <option value="">All tags</option>
              {allTags.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          {(filters.type||filters.event||filters.phase||filters.intensity||filters.tag||search) &&
            <button onClick={()=>{setFilters({type:"",event:"",phase:"",intensity:"",tag:""});setSearch("");}}
              style={{marginTop:14, width:"100%", padding:"5px 0", borderRadius:6, fontSize:12, cursor:"pointer", border:"0.5px solid var(--color-border-secondary)", background:"transparent", color:"var(--color-text-secondary)"}}>
              Clear filters
            </button>
          }
        </div>

        {/* Session Cards */}
        <div style={{flex:1, overflowY:"auto", maxHeight:620, padding:"14px 16px", display:"grid", gridTemplateColumns: selected ? "1fr" : "repeat(auto-fill, minmax(220px, 1fr))", gap:10, alignContent:"start"}}>
          {filtered.length === 0 && (
            <div style={{padding:40, textAlign:"center", color:"var(--color-text-secondary)", fontSize:13}}>No sessions match your filters.</div>
          )}
          {filtered.map(s => {
            const tm = TYPE_META[s.session_type] || TYPE_META.Speed;
            const isActive = s.id === selectedId;
            return (
              <div key={s.id} onClick={()=>{ setSelectedId(isActive ? null : s.id); setActiveTab("desc"); setShowVidForm(false); }}
                style={{
                  background: isActive ? "var(--color-background-secondary)" : "var(--color-background-primary)",
                  border: isActive ? `1.5px solid ${tm.color}` : "0.5px solid var(--color-border-tertiary)",
                  borderRadius: 10, padding:"12px 14px", cursor:"pointer",
                  borderLeft: `3px solid ${tm.color}`,
                  transition:"border 0.15s",
                }}>
                <div style={{display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:6}}>
                  <span style={{fontSize:13, fontWeight:500, color:"var(--color-text-primary)", lineHeight:1.3}}>{s.name}</span>
                  <span style={{fontSize:10, fontWeight:500, padding:"2px 6px", borderRadius:10, background:tm.bg, color:tm.color, whiteSpace:"nowrap", marginLeft:6, flexShrink:0}}>{tm.label}</span>
                </div>
                <div style={{display:"flex", gap:6, flexWrap:"wrap", marginBottom:6}}>
                  <span style={{fontSize:10, color:"var(--color-text-secondary)"}}>{s.event_group.replace("_","/")} · {s.training_phase.replace("_"," ")}</span>
                  <span style={{fontSize:10, fontWeight:500, color: INTENSITY_COLOR[s.intensity_level]}}>{s.intensity_level}</span>
                </div>
                <div style={{display:"flex", gap:4, flexWrap:"wrap"}}>
                  {s.tags.slice(0,3).map(t => (
                    <span key={t} style={{fontSize:10, padding:"1px 6px", borderRadius:10, background:"var(--color-background-secondary)", color:"var(--color-text-secondary)", border:"0.5px solid var(--color-border-tertiary)"}}>{t}</span>
                  ))}
                  {s.tags.length > 3 && <span style={{fontSize:10, color:"var(--color-text-secondary)"}}>+{s.tags.length-3}</span>}
                  {s.videos.length > 0 && <span style={{fontSize:10, padding:"1px 6px", borderRadius:10, background:"rgba(0,180,216,0.1)", color:"#00B4D8"}}>▶ {s.videos.length}</span>}
                </div>
              </div>
            );
          })}
        </div>

        {/* Detail Panel */}
        {selected && (() => {
          const tm = TYPE_META[selected.session_type] || TYPE_META.Speed;
          const refVids = selected.videos.filter(v => v.type==="reference");
          const fbVids = selected.videos.filter(v => v.type==="feedback");
          return (
            <div style={{width:340, flexShrink:0, borderLeft:"0.5px solid var(--color-border-tertiary)", overflowY:"auto", maxHeight:620, display:"flex", flexDirection:"column"}}>
              {/* Detail Header */}
              <div style={{padding:"14px 16px 10px", borderBottom:"0.5px solid var(--color-border-tertiary)", background:"var(--color-background-primary)"}}>
                <div style={{display:"flex", justifyContent:"space-between", alignItems:"flex-start"}}>
                  <div style={{flex:1}}>
                    <div style={{fontSize:14, fontWeight:500, color:"var(--color-text-primary)", lineHeight:1.3, marginBottom:6}}>{selected.name}</div>
                    <div style={{display:"flex", gap:8, alignItems:"center", flexWrap:"wrap"}}>
                      <span style={{fontSize:11, padding:"2px 8px", borderRadius:10, background:tm.bg, color:tm.color, fontWeight:500}}>{tm.label}</span>
                      <span style={{fontSize:11, color:INTENSITY_COLOR[selected.intensity_level], fontWeight:500}}>{selected.intensity_level}</span>
                      <span style={{fontSize:11, color:"var(--color-text-secondary)"}}>{selected.event_group.replace("_","/")} · {selected.training_phase.replace("_"," ")}</span>
                    </div>
                  </div>
                  <button onClick={()=>setSelectedId(null)} style={{background:"none", border:"none", cursor:"pointer", color:"var(--color-text-secondary)", fontSize:16, padding:"0 0 0 8px", lineHeight:1}}>×</button>
                </div>
                {/* Tabs */}
                <div style={{display:"flex", gap:0, marginTop:12, borderBottom:"0.5px solid var(--color-border-tertiary)"}}>
                  {[["desc","Description"],["tags","Tags"],["ref","Reference"],["feedback","Feedback"]].map(([key,label]) => {
                    const count = key==="ref" ? refVids.length : key==="feedback" ? fbVids.length : null;
                    return (
                      <button key={key} onClick={()=>setActiveTab(key)} style={{
                        padding:"6px 12px", fontSize:12, cursor:"pointer", border:"none", background:"none",
                        color: activeTab===key ? "#F26522" : "var(--color-text-secondary)",
                        borderBottom: activeTab===key ? "2px solid #F26522" : "2px solid transparent",
                        fontWeight: activeTab===key ? 500 : 400,
                      }}>
                        {label}{count !== null && count > 0 && <span style={{marginLeft:4, fontSize:10, background: activeTab===key ? "#F26522" : "var(--color-background-secondary)", color: activeTab===key ? "#fff" : "var(--color-text-secondary)", borderRadius:10, padding:"1px 5px"}}>{count}</span>}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Tab Content */}
              <div style={{padding:"14px 16px", flex:1, overflowY:"auto"}}>
                {activeTab==="desc" && (
                  <pre style={{fontFamily:"var(--font-sans)", fontSize:13, color:"var(--color-text-primary)", lineHeight:1.7, margin:0, whiteSpace:"pre-wrap", wordBreak:"break-word"}}>{selected.description}</pre>
                )}

                {activeTab==="tags" && (
                  <div>
                    <div style={{display:"flex", flexWrap:"wrap", gap:6, marginBottom:14}}>
                      {selected.tags.map(t => (
                        <span key={t} style={{display:"flex", alignItems:"center", gap:4, fontSize:12, padding:"3px 10px", borderRadius:20, background:"var(--color-background-secondary)", color:"var(--color-text-primary)", border:"0.5px solid var(--color-border-secondary)"}}>
                          {t}
                          <button onClick={()=>removeTag(t)} style={{background:"none", border:"none", cursor:"pointer", color:"var(--color-text-secondary)", fontSize:13, padding:0, lineHeight:1, marginTop:1}}>×</button>
                        </span>
                      ))}
                    </div>
                    <div style={{display:"flex", gap:8}}>
                      <input
                        placeholder="Add tag..."
                        value={newTag}
                        onChange={e=>setNewTag(e.target.value)}
                        onKeyDown={e=>e.key==="Enter" && addTag()}
                        style={{flex:1, fontSize:12, padding:"6px 10px", borderRadius:6, border:"0.5px solid var(--color-border-secondary)", background:"var(--color-background-secondary)", color:"var(--color-text-primary)", outline:"none"}}
                      />
                      <button onClick={addTag} style={{padding:"6px 14px", borderRadius:6, fontSize:12, cursor:"pointer", background:"#F26522", color:"#fff", border:"none", fontWeight:500}}>Add</button>
                    </div>
                    <div style={{marginTop:12, fontSize:11, color:"var(--color-text-secondary)"}}>Press Enter or click Add. Spaces become hyphens.</div>
                  </div>
                )}

                {(activeTab==="ref" || activeTab==="feedback") && (() => {
                  const vids = activeTab==="ref" ? refVids : fbVids;
                  const vtype = activeTab==="ref" ? "reference" : "feedback";
                  return (
                    <div>
                      {vids.map(v => {
                        const vid = getVideoId(v.url);
                        return (
                          <div key={v.id} style={{marginBottom:14, padding:"12px", borderRadius:8, border:"0.5px solid var(--color-border-tertiary)", background:"var(--color-background-secondary)"}}>
                            <div style={{display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:6}}>
                              <div style={{flex:1}}>
                                <div style={{fontSize:13, fontWeight:500, color:"var(--color-text-primary)"}}>{v.title || "Untitled video"}</div>
                                {v.athlete && <div style={{fontSize:11, color:"var(--color-text-secondary)", marginTop:2}}>Athlete: {v.athlete}</div>}
                                {v.date && <div style={{fontSize:11, color:"var(--color-text-secondary)"}}>Date: {v.date}</div>}
                              </div>
                              <button onClick={()=>removeVideo(v.id)} style={{background:"none", border:"none", cursor:"pointer", color:"var(--color-text-secondary)", fontSize:13}}>×</button>
                            </div>
                            {v.notes && <div style={{fontSize:12, color:"var(--color-text-secondary)", marginBottom:8, lineHeight:1.5}}>{v.notes}</div>}
                            <a href={v.url} target="_blank" rel="noopener noreferrer"
                              style={{display:"inline-flex", alignItems:"center", gap:5, fontSize:12, color: vid?.type==="youtube" ? "#e53935" : "#00B4D8", textDecoration:"none", padding:"4px 10px", borderRadius:6, background: vid?.type==="youtube" ? "rgba(229,57,53,0.1)" : "rgba(0,180,216,0.1)"}}>
                              ▶ {vid?.type==="youtube" ? "YouTube" : vid?.type==="vimeo" ? "Vimeo" : "Watch video"}
                            </a>
                          </div>
                        );
                      })}
                      {!showVidForm && (
                        <button onClick={()=>{ setShowVidForm(true); setVidType(vtype); }}
                          style={{width:"100%", padding:"8px", borderRadius:8, fontSize:12, cursor:"pointer", border:"0.5px dashed var(--color-border-secondary)", background:"transparent", color:"#F26522", fontWeight:500, marginTop: vids.length>0 ? 4 : 0}}>
                          + Add {vtype} video
                        </button>
                      )}
                      {showVidForm && vidType===vtype && (
                        <div style={{padding:14, borderRadius:8, border:"0.5px solid var(--color-border-secondary)", background:"var(--color-background-secondary)", marginTop:8}}>
                          <div style={{fontSize:12, fontWeight:500, color:"var(--color-text-primary)", marginBottom:10}}>Add {vtype} video</div>
                          {[["url","URL (YouTube / Vimeo) *"],["title","Title"],["notes","Coaching notes"]].map(([field,label]) => (
                            <div key={field} style={{marginBottom:8}}>
                              <div style={{fontSize:11, color:"var(--color-text-secondary)", marginBottom:3}}>{label}</div>
                              {field==="notes"
                                ? <textarea value={vidForm[field]} onChange={e=>setVidForm(f=>({...f,[field]:e.target.value}))}
                                    rows={2} style={{width:"100%", fontSize:12, padding:"6px 8px", borderRadius:6, border:"0.5px solid var(--color-border-secondary)", background:"var(--color-background-primary)", color:"var(--color-text-primary)", resize:"vertical", boxSizing:"border-box", outline:"none"}} />
                                : <input value={vidForm[field]} onChange={e=>setVidForm(f=>({...f,[field]:e.target.value}))}
                                    style={{width:"100%", fontSize:12, padding:"6px 8px", borderRadius:6, border:"0.5px solid var(--color-border-secondary)", background:"var(--color-background-primary)", color:"var(--color-text-primary)", boxSizing:"border-box", outline:"none"}} />
                              }
                            </div>
                          ))}
                          {vtype==="feedback" && [["athlete","Athlete name"],["date","Session date"]].map(([field,label]) => (
                            <div key={field} style={{marginBottom:8}}>
                              <div style={{fontSize:11, color:"var(--color-text-secondary)", marginBottom:3}}>{label}</div>
                              <input value={vidForm[field]} onChange={e=>setVidForm(f=>({...f,[field]:e.target.value}))}
                                style={{width:"100%", fontSize:12, padding:"6px 8px", borderRadius:6, border:"0.5px solid var(--color-border-secondary)", background:"var(--color-background-primary)", color:"var(--color-text-primary)", boxSizing:"border-box", outline:"none"}} />
                            </div>
                          ))}
                          <div style={{display:"flex", gap:8, marginTop:4}}>
                            <button onClick={addVideo} style={{flex:1, padding:"7px", borderRadius:6, fontSize:12, cursor:"pointer", background:"#F26522", color:"#fff", border:"none", fontWeight:500}}>Save</button>
                            <button onClick={()=>setShowVidForm(false)} style={{flex:1, padding:"7px", borderRadius:6, fontSize:12, cursor:"pointer", background:"transparent", color:"var(--color-text-secondary)", border:"0.5px solid var(--color-border-secondary)"}}>Cancel</button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            </div>
          );
        })()}
      </div>

      {/* Footer stats */}
      <div style={{padding:"8px 20px", borderTop:"0.5px solid var(--color-border-tertiary)", display:"flex", gap:20}}>
        {Object.entries(TYPE_META).map(([k,v]) => (
          <span key={k} style={{fontSize:11, color:"var(--color-text-secondary)"}}>
            <span style={{fontWeight:500, color:v.color}}>{sessions.filter(s=>s.session_type===k).length}</span> {v.label}
          </span>
        ))}
      </div>
    </div>
  );
}
