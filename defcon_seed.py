"""
================================================================================
 DEFCON SEED  -  preseason defensive-contribution per-90 values (2025/26)
================================================================================
This is provided as a .py file for easy download. It contains DEFCON_SEED, a
name-keyed dict of estimated defensive-actions-per-90.

You do NOT strictly need this file: the same seed is embedded inside
fpl_agent.py (DEFAULT_DEFCON_SEED) and is used automatically. Use this file if
you'd rather keep the seed separate / editable, or to (re)generate the JSON.

USAGE
-----
  * Just run it to write defcon_per90.json next to fpl_agent.py:
        python defcon_seed.py
  * Or import it in your own scripts:
        from defcon_seed import DEFCON_SEED

Thresholds: DEF = 10 CBIT, MID/FWD = 12 CBIRT (GK cannot earn DEFCON).
Values are tuned so P(hit threshold) roughly matches each player's real
2024/25 DEFCON hit-rate. Defenders use actual per-90; midfield values are
tuned from hit-rate %; promoted-club anchors are estimates from Championship
24/25 defensive output. Edit freely - unknown names are simply skipped by the
agent's name resolver.
================================================================================
"""

import json

DEFCON_SEED = {
    # --- established defenders (actual 24/25 per-90) ------------------------
    "Murillo": 10.6, "Tarkowski": 11.0, "Nathan Collins": 9.4, "Lacroix": 10.0,
    "Kilman": 8.8, "Milenkovic": 8.6, "Van Dijk": 8.1, "Branthwaite": 9.6,
    "Gvardiol": 7.8, "Guehi": 8.6, "Senesi": 9.8, "Andersen": 9.2, "Tosin": 8.7,
    "Saliba": 8.4, "Gabriel": 8.9,

    # --- established midfielders (tuned to real hit-rates) ------------------
    "Caicedo": 12.4, "Gueye": 13.7, "Joao Gomes": 13.1, "Elliot Anderson": 12.9,
    "Norgaard": 13.1, "Rice": 12.2, "Bruno Guimaraes": 12.5, "Gravenberch": 12.3,
    "Wharton": 12.4, "Bissouma": 12.7, "Sangare": 12.6, "Onana": 12.1,
    "Palhinha": 13.4,

    # --- promoted-club / new-signing anchors (Leeds/Burnley/Sunderland) -----
    "Esteve": 10.6, "Bijol": 10.5, "Reinildo": 10.1, "Ballard": 10.4,
    "Rodon": 9.9, "Struijk": 9.6, "Hartman": 8.6, "Bogle": 7.6,
    "Geertruida": 8.8, "Mukiele": 9.4, "Alderete": 10.0,
    "Tanaka": 12.3, "Sadiki": 12.4, "Habib Diarra": 12.0, "Longstaff": 11.6,
    "Stach": 12.1, "Ampadu": 12.5, "Xhaka": 12.6, "Cullen": 12.4,
}


def write_json(path="defcon_per90.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFCON_SEED, f, indent=2, ensure_ascii=False)
    print(f"[i] Wrote {len(DEFCON_SEED)} DEFCON seeds -> {path}")


if __name__ == "__main__":
    write_json()