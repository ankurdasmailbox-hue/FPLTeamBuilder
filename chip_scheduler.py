"""
================================================================================
 FPL CHIP SCHEDULER  -  season-long plan for all 8 chips (2025/26)
================================================================================
Author : Das, Ankur

Scans the whole season's fixtures, detects Blank (BGW) and Double (DGW)
gameweeks, then assigns all EIGHT chips to their optimal gameweeks:

    Set 1 (use by the GW19 deadline):   WC1, FH1, TC1, BB1
    Set 2 (unlock at GW20):             WC2, FH2, TC2, BB2

Use `--save` to write chip_plan.json, which fpl_agent.py reads to print a CHIP
CALL in the weekly `transfer` mode. Re-run monthly - BGW/DGW only firm up once
cup draws happen mid-season.

Requires: python 3.9+, and `pip install requests certifi`.
================================================================================
"""

import os
import json
import argparse
import requests
import certifi

BASE_URL   = "https://fantasy.premierleague.com/api"
STATE_FILE = "squad_state.json"
TOTAL_GWS  = 38
SET1_DEADLINE_GW = 19
SET2_START_GW    = 20
AFCON_TOPUP_GW   = 16


def _get(url):
    r = requests.get(url, verify=certifi.where(), timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_bootstrap():
    return _get(f"{BASE_URL}/bootstrap-static/")

def fetch_fixtures():
    return _get(f"{BASE_URL}/fixtures/")


def detect_blanks_doubles(fixtures, team_ids):
    diff   = {gw: {} for gw in range(1, TOTAL_GWS + 1)}
    counts = {gw: {t: 0 for t in team_ids} for gw in range(1, TOTAL_GWS + 1)}
    for f in fixtures:
        gw = f.get("event")
        if gw is None or gw < 1 or gw > TOTAL_GWS:
            continue
        h, a = f["team_h"], f["team_a"]
        counts[gw][h] += 1; counts[gw][a] += 1
        diff[gw].setdefault(h, []).append(f.get("team_h_difficulty", 3))
        diff[gw].setdefault(a, []).append(f.get("team_a_difficulty", 3))
    gw_info = {}
    for gw in range(1, TOTAL_GWS + 1):
        c = counts[gw]
        num_games = sum(c.values()) // 2
        blanks  = [t for t, n in c.items() if n == 0]
        doubles = [t for t, n in c.items() if n >= 2]
        avg_fdr_dbl = {t: round(sum(diff[gw][t]) / len(diff[gw][t]), 2)
                       for t in doubles if t in diff[gw]}
        gtype = ("MIXED" if doubles and blanks else "DGW" if doubles
                 else "BGW" if blanks else "NORMAL")
        gw_info[gw] = {"num_games": num_games, "counts": c, "blanks": blanks,
                       "doubles": doubles, "avg_fdr_dbl": avg_fdr_dbl, "type": gtype}
    return gw_info


def _owned_teams(state, players_team_map):
    if not state:
        return {}
    owned = {}
    for pid in state.get("squad", []):
        t = players_team_map.get(pid)
        if t is not None:
            owned[t] = owned.get(t, 0) + 1
    return owned


def score_bench_boost(info, owned):
    n_double = len(info["doubles"])
    if n_double == 0:
        return 0.0
    mine = sum(cnt for t, cnt in owned.items() if t in info["doubles"]) if owned else 0
    ease = ((3 - (sum(info["avg_fdr_dbl"].values()) / len(info["avg_fdr_dbl"]))) * 0.5
            if info["avg_fdr_dbl"] else 0.0)
    return round(n_double * 1.0 + mine * 2.0 + ease, 2)

def score_triple_captain(info, owned):
    if info["doubles"]:
        easiest = min(info["avg_fdr_dbl"].values()) if info["avg_fdr_dbl"] else 3
        ease = (3 - easiest) * 1.5
        mine = 2.0 if (owned and any(t in info["doubles"] for t in owned)) else 0.0
        return round(3.0 + ease + mine, 2)
    easy_teams = [t for t, n in info["counts"].items() if n == 1]
    return round(0.8, 2) if easy_teams else 0.0

def score_free_hit(info, owned):
    n_blank = len(info["blanks"])
    if n_blank == 0 and len(info["doubles"]) < 4:
        return 0.0
    mine_blank = sum(cnt for t, cnt in owned.items() if t in info["blanks"]) if owned else 0
    dgw_bonus = len(info["doubles"]) * 0.4 if len(info["doubles"]) >= 6 else 0
    return round(n_blank * 1.0 + mine_blank * 2.0 + dgw_bonus, 2)

def score_wildcard(gw, gw_info, half):
    info = gw_info[gw]
    if half == 1:
        base = 3.0 if 7 <= gw <= 10 else (1.0 if 4 <= gw <= 12 else 0.0)
        base += 1.5 if info["type"] in ("BGW", "DGW", "MIXED") else 0
        return round(base, 2)
    nxt = gw_info.get(gw + 1)
    prep = (len(nxt["doubles"]) * 0.5) if nxt else 0
    base = 1.0 if SET2_START_GW <= gw <= 30 else 0.5
    return round(base + prep, 2)


def schedule_chips(gw_info, owned):
    plan = {}; used_gws = set()
    def best_gw(scorer, lo, hi, kind):
        best, best_s = None, -1
        for gw in range(lo, hi + 1):
            if gw in used_gws:
                continue
            s = scorer(gw, gw_info, 1 if hi <= SET1_DEADLINE_GW else 2) if kind == "wc" \
                else scorer(gw_info[gw], owned)
            if s > best_s:
                best, best_s = gw, s
        return best, best_s
    for chip, scorer, kind in [("BB1", score_bench_boost, "bb"),
                               ("TC1", score_triple_captain, "tc"),
                               ("FH1", score_free_hit, "fh"),
                               ("WC1", score_wildcard, "wc")]:
        gw, s = best_gw(scorer, 1, SET1_DEADLINE_GW, kind)
        if gw is not None and s > 0:
            used_gws.add(gw)
        plan[chip] = {"gw": gw if s > 0 else None, "score": s, "kind": kind}
    for chip, scorer, kind in [("BB2", score_bench_boost, "bb"),
                               ("TC2", score_triple_captain, "tc"),
                               ("FH2", score_free_hit, "fh"),
                               ("WC2", score_wildcard, "wc")]:
        gw, s = best_gw(scorer, SET2_START_GW, TOTAL_GWS, kind)
        if gw is not None and s > 0:
            used_gws.add(gw)
        plan[chip] = {"gw": gw if s > 0 else None, "score": s, "kind": kind}
    _annotate(plan, gw_info)
    return plan


def _annotate(plan, gw_info):
    labels = {"bb": "Bench Boost", "tc": "Triple Captain",
              "fh": "Free Hit", "wc": "Wildcard"}
    for chip, p in plan.items():
        gw, kind = p["gw"], p["kind"]
        if gw is None:
            p["why"] = (f"No strong {labels[kind]} window in this half yet - hold; "
                        f"re-run once cup draws confirm blanks/doubles.")
            continue
        info = gw_info[gw]
        if kind == "bb":
            p["why"] = (f"DGW with {len(info['doubles'])} teams playing twice - "
                        f"maximise all 15 players scoring.")
        elif kind == "tc":
            ease = min(info["avg_fdr_dbl"].values()) if info["avg_fdr_dbl"] else "-"
            p["why"] = ((f"DGW ({len(info['doubles'])} doublers, easiest FDR {ease}) - "
                         f"triple a premium who plays twice.") if info["doubles"]
                        else "Easiest available single-fixture week for your captain.")
        elif kind == "fh":
            p["why"] = ((f"BGW - only {info['num_games']} games; "
                         f"{len(info['blanks'])} teams blank. Field a full XI.")
                        if info["blanks"] else
                        (f"Big DGW ({len(info['doubles'])} doublers) you can "
                         f"attack without committing transfers."))
        else:
            nxt = gw_info.get(gw + 1)
            if nxt and len(nxt["doubles"]) >= 4:
                p["why"] = f"Set up BEFORE the GW{gw+1} double ({len(nxt['doubles'])} doublers)."
            elif gw <= SET1_DEADLINE_GW:
                p["why"] = "Reset once early fixtures/form settle (post-intl break)."
            else:
                p["why"] = "Rebuild for the second-half fixture swing."


def print_season_calendar(gw_info, plan, start_gw=1):
    chip_at = {}
    for chip, p in plan.items():
        if p["gw"] is not None:
            chip_at.setdefault(p["gw"], []).append(chip)
    print("\n=== SEASON FIXTURE MAP ===")
    print(f"{'GW':>3} {'Games':>5} {'Type':>6}  {'Blanks':>6} {'Dbls':>4}  Chip")
    for gw in range(start_gw, TOTAL_GWS + 1):
        i = gw_info[gw]
        tag = {"BGW": "BLANK", "DGW": "DBL", "MIXED": "MIX", "NORMAL": ""}[i["type"]]
        chips = ",".join(chip_at.get(gw, []))
        marker = (" <- Set-1 expiry" if gw == SET1_DEADLINE_GW
                  else " <- AFCON 5 FTs" if gw == AFCON_TOPUP_GW else "")
        print(f"{gw:>3} {i['num_games']:>5} {tag:>6}  "
              f"{len(i['blanks']):>6} {len(i['doubles']):>4}  {chips}{marker}")


def print_plan(plan):
    order = ["WC1", "FH1", "TC1", "BB1", "WC2", "FH2", "TC2", "BB2"]
    print("\n=== CHIP PLAN (8 chips, two sets) ===")
    print(f"{'Chip':>4}  {'GW':>4}  Reasoning")
    for chip in order:
        p = plan[chip]
        gw = f"GW{p['gw']}" if p["gw"] else "TBD"
        print(f"{chip:>4}  {gw:>4}  {p['why']}")
    print(f"\nSet-1 chips (WC1/FH1/TC1/BB1) MUST be used by the "
          f"GW{SET1_DEADLINE_GW} deadline or they expire.")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None


def main():
    ap = argparse.ArgumentParser(description="FPL season-long chip scheduler")
    ap.add_argument("--from-gw", type=int, default=1)
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    print("[i] Fetching FPL bootstrap + fixtures ...")
    boot = fetch_bootstrap(); fixtures = fetch_fixtures()
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    players_team = {p["id"]: p["team"] for p in boot["elements"]}

    state = load_state()
    owned = _owned_teams(state, players_team)
    if owned:
        print(f"[i] Tailoring Bench Boost / Triple Captain to your squad "
              f"({sum(owned.values())} players across {len(owned)} clubs).")
    else:
        print("[i] No squad_state.json - planning generically. "
              "Run 'fpl_agent.py build --save' or 'sync' first for a tailored plan.")

    gw_info = detect_blanks_doubles(fixtures, list(teams.keys()))
    plan = schedule_chips(gw_info, owned)
    print_season_calendar(gw_info, plan, start_gw=args.from_gw)
    print_plan(plan)

    n_dgw = sum(1 for g in gw_info.values() if g["doubles"])
    n_bgw = sum(1 for g in gw_info.values() if g["blanks"])
    print(f"\n[i] Detected {n_dgw} GWs with doubles and {n_bgw} with blanks "
          f"(provisional until cup draws finalise).")

    if args.save:
        out = {c: {"gw": p["gw"], "why": p["why"]} for c, p in plan.items()}
        with open("chip_plan.json", "w") as f:
            json.dump(out, f, indent=2)
        print("[i] Chip plan saved -> chip_plan.json "
              "(fpl_agent.py transfer will now show a CHIP CALL when due).")


if __name__ == "__main__":
    main()
