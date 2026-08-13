"""
================================================================================
 FPL AGENT  -  Fantasy Premier League optimization & maintenance agent
================================================================================
Author : Das, Ankur   (evolution of NewTeam.py)

MODES
-----
1. BUILD    : Build the best 15-man squad from scratch (season start / Wildcard).
2. TRANSFER : Multi-gameweek transfer planning for your OWNED squad, respecting
              1 free transfer, banking up to 5, and the -4 pts hit per extra.
              Prints a CHIP CALL when your season chip plan schedules a chip.
3. ADVISE   : Recommend WHEN to play chips (2 sets in 2025/26) + transfer targets
              + cheap DEFCON value picks.
4. SYNC     : Link your REAL FPL team by its team-id and pull your live squad,
              bank and value straight from the FPL API into squad_state.json.

Extra features
--------------
* DEFCON boost (seedable from defcon_per90.json) - values cheap CBs / DMs.
* New-signings watch - flags players newly added to the FPL pool since your last
  run (transfers/new signings as they come in), so you can jump on them early.
* Real-time team linking via --team-id (see SYNC and the README).

Companion tool: chip_scheduler.py (season-long plan for all 8 chips). Keep both
files in the SAME folder so the weekly chip-call fallback import works.

Requires: python 3.9+, and `pip install requests pandas pulp certifi`.
================================================================================
"""

import os
import json
import math
import unicodedata
import argparse
import requests
import pandas as pd
import pulp
import certifi

BASE_URL            = "https://fantasy.premierleague.com/api"
STATE_FILE          = "squad_state.json"
CHIP_PLAN_FILE      = "chip_plan.json"
DEFCON_SEED_FILE    = "defcon_per90.json"     # optional preseason DC-per-90 seed
PLAYER_SNAPSHOT_FILE = "player_snapshot.json" # for new-signings detection
DEFAULT_HORIZON     = 6
TRANSFER_HIT        = 4
MAX_FREE_TRANSFERS  = 5

POS_MAP      = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
SQUAD_LIMITS = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
MAX_PER_CLUB = 3
DEFCON_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12, "GK": 999}

CONFIG = {
    "w_form": 0.35, "w_ppg": 0.25, "w_epnext": 0.40,
    "fdr_strength": 0.10, "home_mult": 1.05, "away_mult": 0.97,
    "plan_decay": 0.84, "hit_buffer": 2.0, "roll_threshold": 1.5,
    "template_bias": 0.02,
    "defcon_weight": 1.0, "defcon_ramp": 0.55, "defcon_min_minutes": 180,
    "chip_set1_deadline_gw": 19, "afcon_topup_gw": 16, "cs_modifier": 0.15,
}

# Embedded DEFCON per-90 seed (name-keyed). Used automatically if
# defcon_per90.json is absent, so the agent works as a SINGLE FILE.
# Edit these numbers freely. DEF threshold=10 CBIT, MID/FWD=12 CBIRT.
DEFAULT_DEFCON_SEED = {
    # established defenders (actual 24/25 per-90)
    "Murillo": 10.6, "Tarkowski": 11.0, "Nathan Collins": 9.4, "Lacroix": 10.0,
    "Kilman": 8.8, "Milenkovic": 8.6, "Van Dijk": 8.1, "Branthwaite": 9.6,
    "Gvardiol": 7.8, "Guehi": 8.6, "Senesi": 9.8, "Andersen": 9.2, "Tosin": 8.7,
    "Saliba": 8.4, "Gabriel": 8.9,
    # established midfielders (tuned to real hit-rates)
    "Caicedo": 12.4, "Gueye": 13.7, "Joao Gomes": 13.1, "Elliot Anderson": 12.9,
    "Norgaard": 13.1, "Rice": 12.2, "Bruno Guimaraes": 12.5, "Gravenberch": 12.3,
    "Wharton": 12.4, "Bissouma": 12.7, "Sangare": 12.6, "Onana": 12.1,
    "Palhinha": 13.4,
    # promoted-club / new-signing anchors (Leeds / Burnley / Sunderland)
    "Esteve": 10.6, "Bijol": 10.5, "Reinildo": 10.1, "Ballard": 10.4,
    "Rodon": 9.9, "Struijk": 9.6, "Hartman": 8.6, "Bogle": 7.6,
    "Geertruida": 8.8, "Mukiele": 9.4, "Alderete": 10.0,
    "Tanaka": 12.3, "Sadiki": 12.4, "Habib Diarra": 12.0, "Longstaff": 11.6,
    "Stach": 12.1, "Ampadu": 12.5, "Xhaka": 12.6, "Cullen": 12.4,
}


# --------------------------------------------------------------- data layer
def _get(url):
    r = requests.get(url, verify=certifi.where(), timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_bootstrap():
    return _get(f"{BASE_URL}/bootstrap-static/")

def fetch_fixtures():
    return _get(f"{BASE_URL}/fixtures/")

def get_next_gameweek(bootstrap):
    for e in bootstrap["events"]:
        if e.get("is_next"):
            return e["id"]
    for e in bootstrap["events"]:
        if e.get("is_current"):
            return e["id"]
    return 1

def get_current_gameweek(bootstrap):
    """Latest started GW (for pulling live picks). None preseason."""
    cur = None
    for e in bootstrap["events"]:
        if e.get("is_current"):
            return e["id"]
        if e.get("finished"):
            cur = e["id"]
    return cur


# ---------------------------------------------- REAL-TIME TEAM LINKING (SYNC)
def fetch_entry_squad(entry_id, boot, players):
    """
    Pull a manager's live squad from the public FPL API and return a
    squad_state dict. Uses:
      entry/{id}/                         -> name, bank, value, last_deadline info
      entry/{id}/event/{gw}/picks/        -> the 15 picks + entry_history (bank)
    Free transfers can't be read without login, so we estimate (see README) and
    let the user override with --free-transfers.
    """
    entry = _get(f"{BASE_URL}/entry/{entry_id}/")
    name  = f"{entry.get('player_first_name','')} {entry.get('player_last_name','')}".strip()
    team_name = entry.get("name", "")
    gw = get_current_gameweek(boot)
    cost = dict(zip(players["id"], players["now_cost"]))

    if gw is None:
        # Preseason: picks don't exist yet.
        print("[!] Season hasn't started - no live picks yet. "
              "Use 'build' to draft, then 'sync' once GW1 locks.")
        return None

    picks = _get(f"{BASE_URL}/entry/{entry_id}/event/{gw}/picks/")
    ids = [p["element"] for p in picks["picks"]]
    hist = picks.get("entry_history", {})
    bank = hist.get("bank", entry.get("last_deadline_bank", 0)) / 10.0

    # purchase cost isn't in public picks; use current cost as a safe proxy
    purchase = {int(i): int(cost.get(i, 0)) for i in ids}

    state = {
        "entry_id": int(entry_id),
        "manager": name,
        "team_name": team_name,
        "squad": [int(i) for i in ids],
        "bank": round(float(bank), 1),
        "free_transfers": 1,               # override with --free-transfers
        "chips_used": _chips_from_history(entry_id),
        "purchase_cost": purchase,
        "synced_gw": gw,
    }
    return state

def _chips_from_history(entry_id):
    """Best-effort list of chips already used this season (public history)."""
    try:
        h = _get(f"{BASE_URL}/entry/{entry_id}/history/")
        return [c.get("name") for c in h.get("chips", [])]
    except Exception:
        return []


# ---------------------------------------------------- feature engineering
def build_fixture_index(fixtures, team_ids, start_gw, horizon):
    gws = range(start_gw, start_gw + horizon)
    fx = {t: {gw: [] for gw in gws} for t in team_ids}
    for f in fixtures:
        gw = f.get("event")
        if gw is None or gw not in gws:
            continue
        fx[f["team_h"]][gw].append((f["team_h_difficulty"], True))
        fx[f["team_a"]][gw].append((f["team_a_difficulty"], False))
    return fx

def build_player_frame(bootstrap):
    players = pd.DataFrame(bootstrap["elements"])
    teams   = pd.DataFrame(bootstrap["teams"])
    players["team_name"] = players["team"].map(dict(zip(teams["id"], teams["short_name"])))
    players["position"]  = players["element_type"].map(POS_MAP)
    for col in ["form", "points_per_game", "ep_next", "selected_by_percent",
                "minutes", "defensive_contribution", "defensive_contribution_per_90"]:
        if col not in players.columns:
            players[col] = 0.0
        players[col] = pd.to_numeric(players[col], errors="coerce").fillna(0.0)
    players["chance"] = (pd.to_numeric(players["chance_of_playing_next_round"],
                         errors="coerce").fillna(100) / 100.0)
    return players[players["status"] != "u"].copy()


# ---------------------------------------- NEW-SIGNINGS / TRANSFERS WATCH
def detect_new_signings(players_full, boot, save=True):
    """
    Compare the current player pool against a saved snapshot and report players
    that are NEW since last run (mid-season signings / newly added elements).
    Returns a DataFrame of newcomers (id, name, team, pos, cost).
    """
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    current = {int(p["id"]): {"web_name": p["web_name"],
                              "team": teams.get(p["team"], "?"),
                              "pos": POS_MAP.get(p["element_type"], "?"),
                              "now_cost": p["now_cost"]}
               for p in boot["elements"]}

    prev = {}
    if os.path.exists(PLAYER_SNAPSHOT_FILE):
        try:
            with open(PLAYER_SNAPSHOT_FILE) as f:
                prev = {int(k): v for k, v in json.load(f).items()}
        except Exception:
            prev = {}

    new_ids = [i for i in current if i not in prev]
    rows = [{"id": i, "Name": current[i]["web_name"], "Team": current[i]["team"],
             "Pos": current[i]["pos"], "Cost": current[i]["now_cost"] / 10.0}
            for i in new_ids]
    newcomers = pd.DataFrame(rows).sort_values(["Pos", "Cost"], ascending=[True, False]) \
                if rows else pd.DataFrame(columns=["id", "Name", "Team", "Pos", "Cost"])

    if save:
        with open(PLAYER_SNAPSHOT_FILE, "w") as f:
            json.dump({str(k): v for k, v in current.items()}, f)
    return newcomers, bool(prev)   # also say whether we had a baseline


# ------------------------------------------------- DEFCON seed resolution
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().replace(".", " ").replace("-", " ").split())

def resolve_defcon_seed(seed_raw, players):
    """Convert a name-keyed (or id-keyed) seed to {player_id: per90}, matching
    web_name -> 'first second' -> surname (accent-insensitive). Keys starting
    with '_' are ignored; ambiguous surname-only matches are skipped."""
    if not seed_raw:
        return {}, [], []
    by_web, by_full, by_surname = {}, {}, {}
    for _, p in players.iterrows():
        by_web.setdefault(_norm(p.get("web_name", "")), []).append(p["id"])
        by_full.setdefault(_norm(f"{p.get('first_name','')} {p.get('second_name','')}"), []).append(p["id"])
        by_surname.setdefault(_norm(p.get("second_name", "")), []).append(p["id"])
    resolved, matched, unmatched = {}, [], []
    for key, val in seed_raw.items():
        if str(key).startswith("_"):
            continue
        if str(key).isdigit():
            resolved[int(key)] = float(val); matched.append(str(key)); continue
        nk = _norm(key); hit = None
        for table in (by_web, by_full, by_surname):
            ids = table.get(nk)
            if ids and len(ids) == 1:
                hit = ids[0]; break
        if hit is None:
            unmatched.append(key)
        else:
            resolved[hit] = float(val); matched.append(key)
    return resolved, matched, unmatched

def defcon_per_match(pos, minutes, dc_total, dc_per90_api, seed_per90, cfg=CONFIG):
    if pos == "GK":
        return 0.0
    threshold = DEFCON_THRESHOLD.get(pos, 12)
    if seed_per90 and seed_per90 > 0:
        per90 = seed_per90
    elif dc_per90_api and dc_per90_api > 0:
        per90 = dc_per90_api
    elif minutes >= cfg["defcon_min_minutes"] and dc_total > 0:
        per90 = dc_total / (minutes / 90.0)
    else:
        return 0.0
    p = 1.0 / (1.0 + math.exp(-(per90 - threshold) * cfg["defcon_ramp"]))
    return round(2.0 * p * cfg["defcon_weight"], 3)

def compute_expected_points(players, fx, start_gw, horizon, cfg=CONFIG, defcon_seed=None):
    defcon_seed = defcon_seed or {}
    players["base_rate"] = (cfg["w_form"] * players["form"]
                            + cfg["w_ppg"] * players["points_per_game"]
                            + cfg["w_epnext"] * players["ep_next"])
    players["base_rate"] += cfg["template_bias"] * players["selected_by_percent"] / 100.0
    dc_bonus = {}
    # Get average fixture difficulty for the horizon
    for _, p in players.iterrows():
        seed = defcon_seed.get(str(p["id"]), defcon_seed.get(p["id"], 0))
        base_defcon = defcon_per_match(
            p["position"], p["minutes"], p["defensive_contribution"],
            p["defensive_contribution_per_90"], seed, cfg)

        # Apply fixture sensitivity: FDR 1-2 (easy) boosts, FDR 4-5 (hard) dampens
        # 3 is neutral.
        # We need to access fx[p['team']]
        team_id = p["team"]
        avg_fdr = 3.0  # Default neutral
        if team_id in fx:
            all_fdr = [fdr for gw in fx[team_id] for fdr, _ in fx[team_id][gw]]
            if all_fdr:
                avg_fdr = sum(all_fdr) / len(all_fdr)

        dc_bonus[p["id"]] = base_defcon * (1.0 + (3 - avg_fdr) * cfg.get("cs_modifier", 0.15))
    players["defcon_bonus"] = players["id"].map(dc_bonus)
    base   = dict(zip(players["id"], players["base_rate"]))
    chance = dict(zip(players["id"], players["chance"]))
    team   = dict(zip(players["id"], players["team"]))
    gw_cols, weights = [], []
    for k, gw in enumerate(range(start_gw, start_gw + horizon)):
        col = f"xP_gw{gw}"; w = cfg["plan_decay"] ** k; weights.append(w)
        vals = []
        for pid in players["id"]:
            g = 0.0
            for fdr, is_home in fx[team[pid]][gw]:
                g += base[pid] * (1.0 + (3 - fdr) * cfg["fdr_strength"]) * \
                     (cfg["home_mult"] if is_home else cfg["away_mult"])
                g += dc_bonus[pid]
            vals.append(round(g * chance[pid], 3))
        players[col] = vals; gw_cols.append(col)
    players["xP_next"]    = players[gw_cols[0]]
    players["xP_horizon"] = players[gw_cols].sum(axis=1)
    players["xP_plan"]    = sum(players[c] * w for c, w in zip(gw_cols, weights))
    return players, gw_cols


# ------------------------------------------------------- shared MILP parts
def _make_vars(players):
    ids = list(players["id"])
    return ({i: pulp.LpVariable(f"sq_{i}", cat="Binary") for i in ids},
            {i: pulp.LpVariable(f"st_{i}", cat="Binary") for i in ids},
            {i: pulp.LpVariable(f"cp_{i}", cat="Binary") for i in ids},
            {i: pulp.LpVariable(f"vc_{i}", cat="Binary") for i in ids})

def _add_structure_constraints(prob, players, squad, start, cap, vc):
    ids  = list(players["id"])
    pos  = dict(zip(players["id"], players["position"]))
    team = dict(zip(players["id"], players["team_name"]))
    for i in ids:
        prob += start[i] <= squad[i]
        prob += cap[i]   <= start[i]
    for p, n in SQUAD_LIMITS.items():
        prob += pulp.lpSum(squad[i] for i in ids if pos[i] == p) == n
    prob += pulp.lpSum(start[i] for i in ids) == 11
    prob += pulp.lpSum(start[i] for i in ids if pos[i] == "GK")  == 1
    prob += pulp.lpSum(start[i] for i in ids if pos[i] == "DEF") >= 3
    prob += pulp.lpSum(start[i] for i in ids if pos[i] == "MID") >= 2
    prob += pulp.lpSum(start[i] for i in ids if pos[i] == "FWD") >= 1
    prob += pulp.lpSum(cap[i] for i in ids) == 1
    prob += pulp.lpSum(vc[i] for i in ids) == 1
    for i in ids:
        prob += vc[i] <= start[i]
        prob += vc[i] + cap[i] <= 1
    # Example: Diversify risk (VC must be different team than captain if possible)
    # This requires adding club-mapping to the function constraints
    for club in set(team.values()):
        prob += pulp.lpSum(squad[i] for i in ids if team[i] == club) <= MAX_PER_CLUB

def _extract_squad(players, squad, start, cap, vc):
    rows = []
    for _, p in players.iterrows():
        i = p["id"]
        if squad[i].varValue == 1.0:
            rows.append({"id": i, "Name": p["web_name"], "Team": p["team_name"],
                         "Position": p["position"], "Cost": p["now_cost"] / 10.0,
                         "xP_next": round(p["xP_next"], 2),
                         "xP_plan": round(p["xP_plan"], 2),
                         "xP_horizon": round(p["xP_horizon"], 2),
                         "defcon": round(p.get("defcon_bonus", 0.0), 2),
                         "Starter": bool(start[i].varValue),
                         "Captain": bool(cap[i].varValue),
                         "VC": bool(vc[i].varValue)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------- MODE A: build
def build_squad(players, budget_m=100.0, cfg=CONFIG):
    budget = int(round(budget_m * 10))
    prob = pulp.LpProblem("FPL_Build", pulp.LpMaximize)
    squad, start, cap, vc = _make_vars(players)
    xn = dict(zip(players["id"], players["xP_next"]))
    xp = dict(zip(players["id"], players["xP_plan"]))
    co = dict(zip(players["id"], players["now_cost"]))
    ids = list(players["id"])
    prob += (pulp.lpSum(start[i] * xn[i] for i in ids)
             + pulp.lpSum(cap[i] * xn[i] for i in ids)
             + pulp.lpSum((squad[i] - start[i]) * xn[i] * 0.1 for i in ids)
             + pulp.lpSum(squad[i] * xp[i] * 0.25 for i in ids))
    prob += pulp.lpSum(squad[i] * co[i] for i in ids) <= budget
    _add_structure_constraints(prob, players, squad, start, cap, vc)
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[prob.status] != "Optimal":
        print("[!] No optimal build - relax the budget."); return None
    return _extract_squad(players, squad, start, cap, vc)


# ------------------------------------------------ MODE B: multi-GW transfer
def fpl_selling_price(buy, now):
    return now if now <= buy else buy + (now - buy) // 2

def _solve_transfer(players, state, plan_col, allow, wildcard, free_hit, cfg):
    cur = state["squad"]; cur_set = set(cur)
    free_t = min(state.get("free_transfers", 1), MAX_FREE_TRANSFERS)
    bank   = int(round(state.get("bank", 0.0) * 10))
    purch  = state.get("purchase_cost", {})
    prob = pulp.LpProblem("FPL_Transfer", pulp.LpMaximize)
    squad, start, cap, vc = _make_vars(players)
    ids = list(players["id"])
    xp  = dict(zip(players["id"], players[plan_col]))
    co  = dict(zip(players["id"], players["now_cost"]))
    t_in = pulp.lpSum(squad[i] for i in ids if i not in cur_set)
    if wildcard or free_hit:
        penalty = 0
    else:
        paid = pulp.LpVariable("paid", lowBound=0, cat="Integer")
        prob += paid >= t_in - free_t
        prob += t_in <= free_t + (allow or 0) + 3
        penalty = TRANSFER_HIT * paid
    if allow == 0 and not (wildcard or free_hit):
        prob += t_in == 0
    prob += (pulp.lpSum(start[i] * xp[i] for i in ids)
             + pulp.lpSum(cap[i] * xp[i] for i in ids)
             + pulp.lpSum((squad[i] - start[i]) * xp[i] * 0.1 for i in ids)
             - penalty)
    sell = []
    for i in cur:
        b = purch.get(str(i), purch.get(i, co.get(i, 0)))
        sell.append((1 - squad[i]) * fpl_selling_price(b, co.get(i, b)))
    prob += pulp.lpSum(squad[i] * co[i] for i in ids if i not in cur_set) <= bank + pulp.lpSum(sell)
    _add_structure_constraints(prob, players, squad, start, cap, vc)
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[prob.status] != "Optimal":
        return None, None, None
    ns = _extract_squad(players, squad, start, cap,vc)
    n  = int(round(sum(1 for i in ids if i not in cur_set and squad[i].varValue == 1.0)))
    return ns, n, pulp.value(prob.objective)

def plan_transfers(players, state, cfg=CONFIG, wildcard=False, free_hit=False):
    free_t = min(state.get("free_transfers", 1), MAX_FREE_TRANSFERS)
    _, _, base_val = _solve_transfer(players, state, "xP_plan", 0, wildcard, free_hit, cfg)
    ns, n, opt_val = _solve_transfer(players, state, "xP_plan", free_t, wildcard, free_hit, cfg)
    if ns is None:
        return None
    gain = (opt_val or 0) - (base_val or 0)
    paid = 0 if (wildcard or free_hit) else max(0, n - free_t)
    if wildcard or free_hit:
        act, decision = True, f"Play {'WILDCARD' if wildcard else 'FREE HIT'}: {n} changes."
    elif n == 0:
        act, decision = False, "HOLD - no beneficial transfer available."
    elif paid > 0:
        act = gain >= cfg["hit_buffer"]
        decision = (f"TAKE a -{paid*TRANSFER_HIT} hit ({n} transfers): +{gain:.1f} "
                    f"plan-pts (> {cfg['hit_buffer']} buffer)." if act else
                    f"ROLL - a -{paid*TRANSFER_HIT} hit only nets +{gain:.1f}; not worth it.")
    else:
        # Dynamic roll threshold:
        # If low FTs (1-2), be stingy (high threshold).
        # If high FTs (3+), be aggressive (low threshold).
        dynamic_roll_threshold = cfg["roll_threshold"] * (1.0 - (free_t - 1) * 0.2)

        if gain < dynamic_roll_threshold and free_t < MAX_FREE_TRANSFERS:
            act = False
            decision = (f"ROLL your free transfer - best move worth +{gain:.1f} "
                        f"(threshold {dynamic_roll_threshold:.1f}). Bank it ({free_t + 1}/5 next GW).")
        else:
            act = True
            decision = f"USE {n} free transfer(s): +{gain:.1f} plan-pts."
    return {"act": act, "decision": decision, "n_transfers": n, "paid_hits": paid,
            "gain": round(gain, 2), "new_squad": ns if act else None,
            "current_free_transfers": free_t}

def diff_squads(players, old_ids, new_df):
    old_set = set(old_ids); new_set = set(new_df["id"])
    look = players.set_index("id")
    outs = [look.loc[i, "web_name"] for i in old_set - new_set]
    ins  = [r["Name"] for _, r in new_df.iterrows() if r["id"] not in old_set]
    return ins, outs


# ----------------------------------------------------- MODE C: chip advise
def advise_chips(players, squad_df, fx, start_gw, horizon, chips_used, cfg=CONFIG):
    recs = []
    team_of = dict(zip(players["id"], players["team"]))
    chance  = dict(zip(players["id"], players["chance"]))
    hor     = dict(zip(players["id"], players["xP_horizon"]))
    ids = list(squad_df["id"]); set1 = start_gw <= cfg["chip_set1_deadline_gw"]
    if set1:
        left = cfg["chip_set1_deadline_gw"] - start_gw
        recs.append(f"NOTE: Set-1 chips expire at the GW{cfg['chip_set1_deadline_gw']} "
                    f"deadline (~{left} GWs away) - use it or lose it.")
        if start_gw <= cfg["afcon_topup_gw"]:
            recs.append(f"NOTE: 5 free transfers for everyone in GW{cfg['afcon_topup_gw']} (AFCON).")
    for gw in range(start_gw, start_gw + horizon):
        xp = dict(zip(players["id"], players[f"xP_gw{gw}"]))
        dbl = [i for i in ids if len(fx[team_of[i]][gw]) == 2]
        bl  = [i for i in ids if len(fx[team_of[i]][gw]) == 0]
        sx = sorted((xp[i] for i in ids), reverse=True)
        bench = sum(sx[11:15]) if len(sx) >= 15 else sum(sx[11:])
        best = max((xp[i] for i in ids), default=0)
        expiration_bonus = 1.2 if (17 <= gw <= 18 and set1) else 1.0
        afcon_penalty = 0.5 if (14 <= gw <= 16) else 1.0
        cd = any(len(fx[team_of[i]][gw]) == 2 and xp[i] == best for i in ids)
        if "bboost" not in chips_used and (len(dbl) >= 6 or bench >= 12):
            recs.append(f"GW{gw}: BENCH BOOST (Weighted: {expiration_bonus * afcon_penalty:.2f})")

        if "3xc" not in chips_used and (best >= 9 or (cd and best >= 7)):
            recs.append(f"GW{gw}: TRIPLE CAPTAIN (Weighted: {expiration_bonus * afcon_penalty:.2f})")

        if "freehit" not in chips_used and len(bl) >= 5:
            recs.append(f"GW{gw}: FREE HIT (Weighted: {expiration_bonus * afcon_penalty:.2f})")
    prob = [i for i in ids if chance.get(i, 1.0) < 0.75 or hor.get(i, 9) < 1.0]
    if "wildcard" not in chips_used and len(prob) >= 4:
        recs.append(f"NOW: WILDCARD - {len(prob)} players injured/flagged/low.")
    if len(recs) <= (2 if set1 else 0):
        recs.append("No chip strongly recommended - hold and reassess.")
    return recs

def flag_underperformers(players, squad_df, n=3):
    look = players.set_index("id")
    rows = [{"Name": look.loc[i, "web_name"], "Pos": look.loc[i, "position"],
             "xP_horizon": round(look.loc[i, "xP_horizon"], 2),
             "chance": look.loc[i, "chance"]} for i in squad_df["id"]]
    return pd.DataFrame(rows).sort_values(["chance", "xP_horizon"]).head(n)

def top_targets(players, owned, per_pos=3):
    avail = players[~players["id"].isin(owned)].copy(); out = {}
    for pos in ["GK", "DEF", "MID", "FWD"]:
        cols = ["web_name", "team_name", "now_cost", "xP_next", "xP_plan"]
        if pos != "GK":
            cols.append("defcon_bonus")
        out[pos] = avail[avail["position"] == pos].sort_values(
            "xP_plan", ascending=False).head(per_pos)[cols]
    return out

def defcon_value_picks(players, owned, max_cost=50, n=6):
    d = players[(~players["id"].isin(owned)) & (players["now_cost"] <= max_cost)
                & (players["defcon_bonus"] > 0)
                & (players["position"].isin(["DEF", "MID"]))].copy()
    d = d.sort_values("defcon_bonus", ascending=False).head(n)
    return d[["web_name", "team_name", "position", "now_cost", "defcon_bonus", "xP_plan"]]


# ------------------------------------------------------- chip-plan wiring
def owned_team_counts(squad_ids, players):
    m = dict(zip(players["id"], players["team"])); out = {}
    for i in squad_ids:
        t = m.get(i)
        if t is not None:
            out[t] = out.get(t, 0) + 1
    return out

CHIP_LABEL = {"BB": "Bench Boost", "TC": "Triple Captain",
              "FH": "Free Hit", "WC": "Wildcard"}

def get_planned_chip(start_gw, fixtures, boot, owned_teams):
    if os.path.exists(CHIP_PLAN_FILE):
        try:
            with open(CHIP_PLAN_FILE) as f:
                plan = json.load(f)
            for chip, info in plan.items():
                if info.get("gw") == start_gw:
                    return chip, info.get("why", "")
            return None, None
        except Exception:
            pass
    try:
        import chip_scheduler as cs
    except Exception:
        return None, None
    teams = [t["id"] for t in boot["teams"]]
    gw_info = cs.detect_blanks_doubles(fixtures, teams)
    plan = cs.schedule_chips(gw_info, owned_teams)
    for chip, p in plan.items():
        if p.get("gw") == start_gw:
            return chip, p.get("why", "")
    return None, None

def announce_chip(chip, why, wildcard_flag, freehit_flag):
    kind = chip[:2]; label = CHIP_LABEL.get(kind, chip)
    print("\n" + "=" * 60)
    print(f"  >>> CHIP CALL: your season plan says play {label} ({chip}) THIS GW")
    print(f"      Why: {why}")
    if kind == "WC" and not wildcard_flag:
        print("      -> Re-run:  python fpl_agent.py transfer --wildcard --save")
    elif kind == "FH" and not freehit_flag:
        print("      -> Re-run:  python fpl_agent.py transfer --free-hit")
    elif kind == "TC":
        print("      -> Keep your highest-xP starter as captain (shown below).")
    elif kind == "BB":
        print("      -> Bench matters this week - the plan already maximises bench xP.")
    print("=" * 60)


# ------------------------------------------------------ state persistence
def save_state(squad_df, bank, free_transfers, chips_used, players, extra=None):
    co = dict(zip(players["id"], players["now_cost"]))

    # Create a mapping for ID to Name
    id_to_name = dict(zip(players["id"], players["web_name"]))

    squad_ids = [int(i) for i in squad_df["id"]]

    state = {
        "squad": squad_ids,
        "squad_names": [id_to_name.get(i, "Unknown") for i in squad_ids],  # NEW: readable names
        "bank": round(float(bank), 1),
        "free_transfers": int(min(free_transfers, MAX_FREE_TRANSFERS)),
        "chips_used": chips_used,
        "purchase_cost": {int(i): int(co[i]) for i in squad_df["id"]}
    }
    if extra:
        state.update(extra)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    print(f"[i] Squad state saved (with names) -> {STATE_FILE}")

def load_state():
    if not os.path.exists(STATE_FILE):
        raise FileNotFoundError(f"{STATE_FILE} not found. Run 'build --save' or 'sync' first.")
    with open(STATE_FILE) as f:
        return json.load(f)


# --------------------------------------------------------------- printing
def print_squad(sq):
    # Sort starters by Position, then xP
    st = sq[sq["Starter"]].sort_values(["Position", "xP_next"], ascending=[True, False])

    # NEW: Sort bench by xP_next descending so the best sub is at the top
    bn = sq[~sq["Starter"]].sort_values("xP_next", ascending=False)

    cols = ["Name", "Team", "Position", "Cost", "xP_next", "xP_plan", "defcon", "Captain", "VC"]
    print("\n=== STARTING XI ===\n" + st[cols].to_string(index=False))
    print("\n=== BENCH (Sorted by xP for Auto-Sub) ===\n" + bn[cols[:-1]].to_string(index=False))

    print(f"\nSquad value: GBP {sq['Cost'].sum():.1f}m | XI xP(next): "
          f"{st['xP_next'].sum():.1f} | XI xP(plan): {st['xP_plan'].sum():.1f}")
# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="FPL optimization agent")
    ap.add_argument("mode", choices=["build", "transfer", "advise", "sync"])
    ap.add_argument("--budget", type=float, default=100.0)
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    ap.add_argument("--wildcard", action="store_true")
    ap.add_argument("--free-hit", action="store_true")
    ap.add_argument("--team-id", type=int, default=None,
                    help="your FPL team/entry id (see README) - links your real team")
    ap.add_argument("--free-transfers", type=int, default=None,
                    help="override free transfers when syncing (API can't read banked FTs)")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    print("[i] Fetching FPL data ...")
    boot = fetch_bootstrap(); fixtures = fetch_fixtures()
    start_gw = get_next_gameweek(boot)
    print(f"[i] Planning from GW{start_gw} (horizon {args.horizon}, decay {CONFIG['plan_decay']}).")
    players = build_player_frame(boot)

    # New-signings watch (runs on every mode; updates the snapshot).
    newcomers, had_baseline = detect_new_signings(players, boot, save=True)
    if had_baseline and not newcomers.empty:
        print(f"\n=== NEW IN THE FPL POOL SINCE LAST RUN ({len(newcomers)}) ===")
        print(newcomers.head(15).to_string(index=False))
        print("   (New signings/additions - watch for nailed starters & bargains.)")
    elif not had_baseline:
        print("[i] New-signings baseline created (player_snapshot.json). "
              "Future runs will flag additions.")

    # DEFCON seed (name-keyed -> resolved to this season's ids).
    # Priority: external defcon_per90.json (if present) else the embedded seed.
    defcon_seed = {}
    seed_raw, seed_src = DEFAULT_DEFCON_SEED, "embedded default"
    if os.path.exists(DEFCON_SEED_FILE):
        try:
            with open(DEFCON_SEED_FILE, encoding="utf-8") as f:
                seed_raw = json.load(f); seed_src = DEFCON_SEED_FILE
        except Exception as e:
            print(f"[!] Could not read {DEFCON_SEED_FILE} ({e}) - using embedded seed.")
    try:
        defcon_seed, matched, unmatched = resolve_defcon_seed(seed_raw, players)
        print(f"[i] DEFCON seed ({seed_src}): matched {len(matched)} players"
              + (f"; unmatched {len(unmatched)}" if unmatched else "."))
    except Exception as e:
        print(f"[!] Could not resolve DEFCON seed ({e}) - continuing without it.")

    # --------------------------------------------------------------- SYNC
    if args.mode == "sync":
        if not args.team_id:
            print("[!] Provide your team id:  python fpl_agent.py sync --team-id 1234567")
            return
        state = fetch_entry_squad(args.team_id, boot, players)
        if state is None:
            return
        if args.free_transfers is not None:
            state["free_transfers"] = int(args.free_transfers)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"[i] Linked '{state['team_name']}' ({state['manager']}), "
              f"GW{state['synced_gw']} squad -> {STATE_FILE}")
        print(f"    Bank GBP {state['bank']}m | Free transfers set to "
              f"{state['free_transfers']} (override with --free-transfers).")
        print("    Now run:  python fpl_agent.py transfer   (or advise)")
        return

    fx = build_fixture_index(fixtures, players["team"].unique(), start_gw, args.horizon)
    players, _ = compute_expected_points(players, fx, start_gw, args.horizon,
                                         defcon_seed=defcon_seed)

    if args.mode == "build":
        sq = build_squad(players, args.budget)
        if sq is None:
            return
        print_squad(sq)
        print("\n=== CHIP OUTLOOK ===")
        for r in advise_chips(players, sq, fx, start_gw, args.horizon, []):
            print(" -", r)
        print("\n=== CHEAP DEFCON VALUE PICKS (<= GBP 5.0m) ===")
        print(defcon_value_picks(players, list(sq["id"])).to_string(index=False))
        if args.save:
            save_state(sq, args.budget - sq["Cost"].sum(), 1, [], players)

    elif args.mode == "transfer":
        state = load_state()
        if args.free_transfers is not None:
            state["free_transfers"] = int(args.free_transfers)
        owned_teams = owned_team_counts(state["squad"], players)
        chip, why = get_planned_chip(start_gw, fixtures, boot, owned_teams)
        if chip:
            announce_chip(chip, why, args.wildcard, args.free_hit)
        plan = plan_transfers(players, state, wildcard=args.wildcard, free_hit=args.free_hit)
        if plan is None:
            return
        print(f"\n=== TRANSFER DECISION (GW{start_gw}) ===\n >> {plan['decision']}")
        if plan["new_squad"] is not None:
            ins, outs = diff_squads(players, state["squad"], plan["new_squad"])
            print("OUT:", ", ".join(outs) or "none")
            print("IN :", ", ".join(ins) or "none")
            print_squad(plan["new_squad"])
        print("\n=== UNDERPERFORMERS TO WATCH ===")
        print(flag_underperformers(players, pd.DataFrame({"id": state["squad"]})).to_string(index=False))
        if args.save and plan["act"] and not args.free_hit:
            new_ft = 1 if plan["n_transfers"] > 0 else min(MAX_FREE_TRANSFERS,
                     state.get("free_transfers", 1) + 1)
            save_state(plan["new_squad"], state.get("bank", 0.0), new_ft,
                       state.get("chips_used", []), players,
                       extra={k: state[k] for k in ("entry_id", "team_name", "manager")
                              if k in state})
        elif args.save and not plan["act"]:
            state["free_transfers"] = min(MAX_FREE_TRANSFERS, state.get("free_transfers", 1) + 1)
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
            print(f"[i] Rolled -> {state['free_transfers']}/5 free transfers.")

    elif args.mode == "advise":
        state = load_state(); owned = state["squad"]
        sq = players[players["id"].isin(owned)][
            ["id", "web_name", "team_name", "position", "now_cost",
             "xP_next", "xP_plan", "xP_horizon"]].rename(
            columns={"web_name": "Name", "team_name": "Team", "position": "Position"})
        sq["Cost"] = sq["now_cost"] / 10.0
        print("\n=== CHIP RECOMMENDATIONS ===")
        for r in advise_chips(players, sq, fx, start_gw, args.horizon,
                              state.get("chips_used", [])):
            print(" -", r)
        print("\n=== TOP TRANSFER TARGETS (by position, plan xP) ===")
        for pos, tbl in top_targets(players, owned).items():
            print(f"\n[{pos}]\n" + tbl.to_string(index=False))
        print("\n=== CHEAP DEFCON VALUE PICKS (<= GBP 5.0m) ===")
        print(defcon_value_picks(players, owned).to_string(index=False))


if __name__ == "__main__":
    main()
