"""
================================================================================
 FPL AGENT + CHIP SCHEDULER  -  Setup & Usage (2026/27)
================================================================================
This README is provided as a .py file for easy download. It contains no code to
run (though `python README_fpl.py` will simply print these instructions).

--------------------------------------------------------------------------------
FILES (keep all in the SAME folder)
--------------------------------------------------------------------------------
  fpl_agent.py        build / transfer / advise / sync  (main tool)
  chip_scheduler.py   season-long plan for all 8 chips
  defcon_seed.py      DEFCON per-90 seed (optional; also embedded in the agent)
  README_fpl.py       this file

Optional auto-created files: squad_state.json, chip_plan.json,
player_snapshot.json, defcon_per90.json.

NOTE: fpl_agent.py already EMBEDS the DEFCON seed, so it runs on its own. You
only need defcon_seed.py if you want to edit the seed separately or generate
defcon_per90.json (run:  python defcon_seed.py).

--------------------------------------------------------------------------------
1) INSTALL (once)
--------------------------------------------------------------------------------
  python -m pip install --upgrade requests pandas pulp certifi
  (Python 3.9+. pulp bundles the CBC solver - nothing else to install.)

--------------------------------------------------------------------------------
2) COMMANDS
--------------------------------------------------------------------------------
  Draft a squad (pre-GW1 / Wildcard):
      python fpl_agent.py build --budget 100 --horizon 6 --save

  Season-long chip plan (run monthly):
      python chip_scheduler.py --save

  Weekly transfer decision (shows a CHIP CALL when one is due):
      python fpl_agent.py transfer --save
      # Wildcard week:  python fpl_agent.py transfer --wildcard --save
      # Free Hit week:  python fpl_agent.py transfer --free-hit

  Chip advice + targets + DEFCON value picks:
      python fpl_agent.py advise --horizon 6

  Link your REAL team and pull live squad/bank:
      python fpl_agent.py sync --team-id 1234567

--------------------------------------------------------------------------------
3) HOW TO LINK YOUR REAL FPL TEAM (sync)
--------------------------------------------------------------------------------
  1. Log in at fantasy.premierleague.com and open the "Points" tab.
  2. Look at the URL:  .../entry/1234567/event/3
     The number after /entry/ (here 1234567) is your TEAM-ID.
  3. Run:
       python fpl_agent.py sync --team-id 1234567
       python fpl_agent.py transfer

  Caveats:
   - Works AFTER GW1 locks (picks don't exist preseason - use 'build' first).
   - The public API can't read banked free transfers, so sync sets it to 1.
     Override any week:  python fpl_agent.py transfer --free-transfers 2

--------------------------------------------------------------------------------
4) NEW-SIGNINGS / TRANSFERS WATCH
--------------------------------------------------------------------------------
  Every run compares the player pool to player_snapshot.json and prints players
  newly added to FPL since your last run (mid-season signings / new pricings).
  The first run just creates the baseline.

--------------------------------------------------------------------------------
5) DEFCON BOOST (2025/26)
--------------------------------------------------------------------------------
  +2 pts for DEF hitting 10 CBIT, or MID/FWD hitting 12 CBIRT (GK excluded).
  The agent models an expected bonus = 2 * P(hit), added per match
  (fixture-neutral, so it doubles in a Double Gameweek). Seed is tuned and
  includes promoted-club anchors (Esteve, Bijol, Reinildo, Sadiki, ...).
  'build' and 'advise' print a "Cheap DEFCON value picks (<= 5.0m)" table.

--------------------------------------------------------------------------------
6) SUGGESTED CADENCE
--------------------------------------------------------------------------------
  Pre-GW1 : build --save  -> enter the squad on the FPL site.
  After GW1 locks : sync --team-id <id>  to link your real team.
  Monthly : chip_scheduler.py --save
  Weekly  : sync (refresh) -> transfer (act/roll; CHIP CALL auto-shows)
            -> glance at the new-signings table.

--------------------------------------------------------------------------------
7) RULES BASIS (2025/26)
--------------------------------------------------------------------------------
  1 free transfer/GW, bank up to 5, -4 per extra. Two sets of 8 chips; Set 1
  expires at the GW19 deadline, Set 2 unlocks GW20. Everyone topped up to 5 FTs
  in GW16 (AFCON). Promoted clubs: Leeds, Burnley, Sunderland.
================================================================================