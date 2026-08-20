# 🏆 FPL Team Builder (2026–2027 Edition)

A production-grade Python decision engine, mathematical optimizer (MILP), and transfer planning agent designed to maximize the probability of achieving a **Top 100 worldwide finish** in Fantasy Premier League for the **2026–2027 season**.

---

## 🚀 Quick Start Guide (How to Run in 60 Seconds)

### Step 1: Clone and Set Up Virtual Environment
```bash
git clone https://github.com/ankurdasmailbox-hue/FPLTeamBuilder.git
cd FPLTeamBuilder

# Create virtual environment (Python 3.11+)
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate      # Windows PowerShell / CMD
# source .venv/bin/activate # Linux / macOS

# Install dependencies and register CLI
pip install -e ".[test]"
```

### Step 2: Initialize Official FPL Data & Season Rules
Discovers live endpoints, ingests rules, and caches the player/fixture database:
```bash
fpl-team-builder init
# OR directly via Python:
python -m fpl_team_builder init
```

### Step 3: Run Your Desired Optimization Mode

#### A) Start of Season (Draft New £100m Squad)
```bash
fpl-team-builder recommend --gw 1 --budget 100.0 --horizon 4 --save
```

#### B) Mid-Season (Sync Your Live Team & Recommend Transfers)
```bash
fpl-team-builder recommend --team-link "https://fantasy.premierleague.com/entry/1234567" --gw 5 --save
```

#### C) Simulate Season-Long Strategies
```bash
fpl-team-builder simulate-strategies --runs 1000
```

#### D) Launch the Interactive REST API (FastAPI)
```bash
fpl-team-builder serve --host 127.0.0.1 --port 8000
```
Open your browser at **http://127.0.0.1:8000/docs** to use the interactive Swagger UI.

---

## 🌟 Key Capabilities

1. **Dynamic Runtime Rule Discovery**: Automatically discovers official FPL API endpoints, gameweek deadlines, scoring matrices, and chip structures at runtime. Never relies on hardcoded, stale season rules.
2. **Multi-Gameweek Expected Points ($xP$) Forecasting**:
   - Blends short-term form, season-long points per game, official $ep\_next$, and underlying per-90 metrics ($xG + xA$).
   - Adjusts for home/away advantage and fixture difficulty ratings (FDR).
   - Incorporates European competition rotation risk dampening for clubs in UCL/UEL/UECL.
   - Includes the calibrated **DEFCON bonus model** (+2 pts for DEF hitting 10 CBIT or MID/FWD hitting 12 CBIRT).
   - Computes multi-gameweek discounted plan values ($\gamma^k$ decay over configurable $N$-GW horizon).
3. **Mixed Integer Linear Programming (MILP) Squad Optimization**:
   - Solves the global optimum 15-player squad under £100.0m budget (or user bank).
   - Enforces exact formation requirements (1 GK, 3–5 DEF, 2–5 MID, 1–3 FWD = 11 starters) and max 3 players per club.
   - Selects optimal Captain & Vice-Captain with risk diversification.
   - Generates the **Top 3 Alternative Squads** (*Differential Upside*, *Premium Heavy*, *Balanced Template*).
4. **Intelligent Transfer & Hit Planner**:
   - Supports user team linking via official FPL URL or entry ID (`.../entry/1234567`).
   - Evaluates multi-gameweek transfer permutations.
   - Recommends transfer hits only when expected points gain over 2 GWs exceeds hit cost (4 pts) + uncertainty buffer.
   - Dynamically decides when to **HOLD/ROLL** banked free transfers (up to 5 FTs).
5. **Full-Season Chip Optimization**:
   - Scans 38 gameweeks for Blank (BGW) and Double (DGW) Gameweeks.
   - Optimizes Wildcard (WC1/WC2), Free Hit (FH1/FH2), Triple Captain (TC1/TC2), and Bench Boost (BB1/BB2) timing with ROI estimations and confidence ratings.
6. **Persistence & Export**:
   - Automatically writes a machine-readable JSON snapshot keyed by gameweek (`snapshot_gw_<GW>.json`) with full player names, prices, $xP$, and "why this pick" rationale.
   - Persists all runs and user teams to SQLite (`fpl_builder.db`) via SQLAlchemy.
   - Supports CSV export (`snapshot_gw_<GW>.csv`).
7. **FastAPI REST API & Interactive CLI**:
   - Single-entry CLI (`fpl-team-builder`).
   - Full REST API with `/health`, `/init`, `/recommend`, `/snapshot/{gw}`, and `/simulate`.
8. **Monte Carlo Strategy Simulation**:
   - Simulates 38-GW seasons across competing managerial archetypes (*Optimal Alpha*, *Template Maximizer*, *Aggressive Differential*, *Set-and-Forget*), projecting Top 100 and Top 10k finish probabilities.

---

## 📁 Project Structure

```
FPLTeamPredictor/
├── config.yaml                    # Global hyperparameters & configuration
├── pyproject.toml                 # Packaging & CLI entry points
├── setup.py                       # Setuptools installation
├── README.md                      # Comprehensive documentation
├── fpl_team_builder/
│   ├── __init__.py                # Package version
│   ├── __main__.py                # Direct execution entry point
│   ├── config.py                  # Pydantic configuration loader
│   ├── service.py                 # Core pipeline orchestrator
│   ├── cli.py                     # CLI entry point (fpl-team-builder)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── player.py              # Player data model & rationale generator
│   │   ├── fixture.py             # Fixture & BGW/DGW models
│   │   ├── squad.py               # 15-player squad & starting XI models
│   │   ├── snapshot.py            # Gameweek snapshot schema (JSON contract)
│   │   └── user_team.py           # User manager state representation
│   ├── data/
│   │   ├── __init__.py
│   │   ├── client.py              # HTTP client with rate-limiting, backoff, & cache
│   │   ├── rules.py               # Runtime official rule discovery & validator
│   │   └── ingestion.py           # Data ingestion, team link parser, new signings
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── forecasting.py         # Multi-GW xP & DEFCON engine
│   │   ├── optimizer.py           # PuLP MILP solver & alternative squad generator
│   │   ├── transfers.py           # Multi-GW transfer & hit ROI planner
│   │   ├── chips.py               # Full-season chip scheduler & scenario analysis
│   │   ├── captaincy.py           # Captain & VC ceiling and confidence evaluator
│   │   ├── differentials.py       # Low-ownership (<10%) discovery engine
│   │   └── simulation.py          # Monte Carlo season simulation
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py                  # SQLAlchemy SQLite models & persistence
│   │   └── store.py               # JSON & CSV snapshot file exporter
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── notifier.py            # Weekly recommendation alert dispatcher
│   └── api/
│       ├── __init__.py
│       └── app.py                 # FastAPI REST application
└── tests/
    ├── conftest.py                # Mock fixtures & offline test environments
    ├── test_rules.py              # Unit tests for official rule engine
    ├── test_forecasting.py        # Unit tests for expected points & DEFCON
    ├── test_optimizer.py          # Unit tests for MILP solver
    ├── test_transfers.py          # Unit tests for transfer planning & hit logic
    ├── test_chips.py              # Unit tests for chip scheduling
    ├── test_differentials.py      # Unit tests for differential discovery
    ├── test_db.py                 # Unit tests for database CRUD
    ├── test_api.py                # Unit tests for FastAPI REST endpoints
    ├── test_cli.py                # Unit tests for CLI interface
    └── test_end_to_end_mocked.py  # End-to-End mocked pipeline verification
```

---

## 💻 Detailed CLI Reference

You can run commands using the `fpl-team-builder` executable or `python -m fpl_team_builder <command>`.

### 1. `init`
Fetches fresh metadata from official FPL API, parses dynamic scoring matrices, and initializes the local disk cache:
```bash
fpl-team-builder init
# Force refresh cache from network:
fpl-team-builder init --force
```

### 2. `recommend`
The primary decision engine command. Supports both start-of-season drafts and in-season transfer optimization.

| Argument | Type | Default | Description |
|---|---|---|---|
| `--team-link`, `--team-id` | `str` | `None` | Official FPL team URL or numeric entry ID |
| `--gw` | `int` | `Next GW` | Target Gameweek number to plan for |
| `--budget` | `float` | `100.0` | Total squad budget in £ millions |
| `--horizon` | `int` | `4` | Planning horizon lookahead in gameweeks |
| `--wildcard` | `flag` | `False` | Force simulate Wildcard activation |
| `--free-hit` | `flag` | `False` | Force simulate Free Hit activation |
| `--free-transfers` | `int` | `None` | Override available banked free transfers (1 to 5) |
| `--save` | `flag` | `True` | Persist snapshot to database and `snapshot_gw_<GW>.json` |
| `--dry-run` | `flag` | `False` | Simulate recommendations without writing to disk |
| `--export-csv` | `flag` | `False` | Also export recommended squad to CSV format |

#### Examples:
```bash
# Clean pre-season opening squad build:
fpl-team-builder recommend --gw 1 --budget 100.0 --horizon 6 --save

# Mid-season transfer recommendation linking live FPL entry ID:
fpl-team-builder recommend --team-link "https://fantasy.premierleague.com/entry/1234567" --gw 5 --save

# Simulate Wildcard activation for a linked team:
fpl-team-builder recommend --team-link 1234567 --gw 8 --wildcard --save

# Dry-run without modifying database or overwriting files:
fpl-team-builder recommend --team-link 1234567 --gw 5 --dry-run
```

### 3. `show-snapshot`
Displays the full human-readable table and analysis for any previously saved gameweek snapshot:
```bash
fpl-team-builder show-snapshot 1
fpl-team-builder show-snapshot 5
```

### 4. `simulate-strategies`
Executes Monte Carlo simulations comparing 4 manager archetypes (*Optimal Alpha*, *Template Maximizer*, *Aggressive Differential*, *Set-and-Forget*) across 38 gameweeks:
```bash
fpl-team-builder simulate-strategies --runs 1000
```

### 5. `agent` (Autonomous FPL Weekly Agent)
Controls the automated scheduler, change detector, and email notification dispatcher:

```bash
# Execute a single autonomous cycle (discovers GW deadline, optimizes team, detects changes, sends email):
fpl-team-builder agent run-once

# Force immediate email dispatch to ankur.das.mailbox@gmail.com:
fpl-team-builder agent run-once --force-email

# Test dry-run execution without modifying DB or sending emails:
fpl-team-builder agent run-once --dry-run

# Start autonomous background scheduler daemon (runs daily at 18:00 UTC, 6h before deadline, & 30m before lock):
fpl-team-builder agent start

# Run as foreground blocking process (for Docker / systemd service):
fpl-team-builder agent start --blocking

# Send a test email to verify SMTP configuration:
fpl-team-builder agent test-email

# Display agent status and upcoming scheduled jobs:
fpl-team-builder agent status
```

### 6. `serve`
Launches the high-performance FastAPI REST server:
```bash
fpl-team-builder serve --host 127.0.0.1 --port 8000
```

---

## 🤖 Autonomous Operation & 24/7 Deployment (Zero Human Intervention)

Once started, the **FPL Weekly Agent** operates 100% autonomously without any manual input:

1. **Automatic Deadline Discovery**: Fetches official FPL metadata at runtime to find the upcoming Gameweek deadline.
2. **Daily 18:00 UTC Monitoring**: Re-evaluates form, injuries, price changes, and lineups every evening.
3. **Pre-Deadline Dual Triggers**: Runs automatically **6 hours** and **30 minutes** prior to the Gameweek lock.
4. **Intelligent Change Detection**: Detects if Starting XI, Captain, Vice-Captain, Transfers, or Chips have changed.
5. **Persistence & Direct Delivery**: Persists `snapshot_gw_<GW>.json` + SQLite, and emails the formatted report to **`ankur.das.mailbox@gmail.com`**.

### Keeping the Agent Running 24/7

#### Option 1: Terminal / Foreground Daemon (Quickest)
Keep this running in a terminal or tmux session:
```bash
fpl-team-builder agent start --blocking
```

#### Option 2: Windows Background Task (Auto-Starts on Boot)
Run in PowerShell as Administrator to keep the agent running persistently across restarts:
```powershell
$Action = New-ScheduledTaskAction -Execute "fpl-team-builder.exe" -Argument "agent start --blocking" -WorkingDirectory "C:\Users\ankur\PycharmProjects\FPLTeamPredictor"
$Trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "FPLWeeklyAgent" -Action $Action -Trigger $Trigger -Description "Autonomous FPL Weekly Agent"
```

#### Option 3: Linux / Server Deployment (systemd)
Create `/etc/systemd/system/fpl-agent.service`:
```ini
[Unit]
Description=FPL Weekly Autonomous Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/FPLTeamBuilder
ExecStart=/path/to/FPLTeamBuilder/.venv/bin/fpl-team-builder agent start --blocking
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fpl-agent
sudo systemctl start fpl-agent
```

#### Option 4: Docker Container
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install -e .
CMD ["fpl-team-builder", "agent", "start", "--blocking"]
```

---

## 🌐 REST API Usage

### Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | API health check & version info |
| `POST` | `/init` | Discovers and refreshes official FPL runtime data |
| `POST` | `/recommend` | Generates full squad optimization / transfer recommendation |
| `GET` | `/snapshot/{gw}` | Retrieves persisted snapshot by Gameweek number |
| `GET` | `/snapshots` | Lists all persisted snapshot summaries in SQLite |
| `POST` | `/simulate` | Runs Monte Carlo season strategy simulation |
| `POST` | `/agent/run-once` | Executes autonomous cycle with change detection & email |
| `GET` | `/agent/status` | Retrieves scheduler state, deadline info, and jobs |
| `POST` | `/agent/test-email` | Dispatches verification test email |

### Example cURL Requests

#### Health Check:
```bash
curl http://127.0.0.1:8000/health
```

#### Request Recommendations:
```bash
curl -X POST "http://127.0.0.1:8000/recommend" \
     -H "Content-Type: application/json" \
     -d '{
       "team_link": "https://fantasy.premierleague.com/entry/1234567",
       "gw": 5,
       "budget": 100.0,
       "horizon": 4,
       "save": true
     }'
```

#### Fetch Stored Snapshot:
```bash
curl http://127.0.0.1:8000/snapshot/5
```

---

## ⚙️ Configuration File (`config.yaml`)

You can tune all model hyperparameters directly in [`config.yaml`](file:///C:/Users/ankur/PycharmProjects/FPLTeamPredictor/config.yaml):

```yaml
# Forecasting Weights & Hyperparameters
weights:
  w_form: 0.35                  # Weight for recent form
  w_ppg: 0.25                   # Weight for points per game
  w_epnext: 0.40                # Weight for official ep_next
  w_xg_xa: 0.20                 # Weight for underlying xG90 + xA90
  fdr_strength: 0.10            # Impact of FDR difficulty
  home_mult: 1.05               # Home fixture boost
  away_mult: 0.97               # Away fixture discount
  plan_decay: 0.84              # Lookahead decay factor (0.84^k)
  rotation_penalty_europe: 0.08 # European match congestion penalty
  cs_modifier: 0.15             # Clean sheet modifier based on defensive FDR

# Defensive Contribution (DEFCON) Model
defcon:
  enabled: true
  defcon_weight: 1.0
  defcon_ramp: 0.55
  thresholds:
    DEF: 10.0                   # 10 CBIT for defenders
    MID: 12.0                   # 12 CBIRT for midfielders
    FWD: 12.0                   # 12 CBIRT for forwards

# Transfer Decision Rules
transfers:
  transfer_hit_cost: 4
  hit_buffer: 2.0
  uncertainty_buffer: 1.0
  roll_threshold: 1.5
  max_free_transfers: 5
  default_horizon: 4

# Optimization Constraints
optimization:
  default_budget: 100.0
  max_per_club: 3
  starters_required: 11
  min_def: 3
  min_mid: 2
  min_fwd: 1
```

---

## 🧪 Testing Suite & Offline Mocking

The codebase includes a comprehensive test suite of 21 tests covering all decision layers.

### Run All Tests:
```bash
pytest -v
```

### Mocking the FPL API Offline
For offline testing, continuous integration, or unit tests without an internet connection, use `FPLClient.set_mock_data`:

```python
from fpl_team_builder.data.client import FPLClient
from fpl_team_builder.service import FPLTeamBuilderService

client = FPLClient()
# Register mocked payloads
client.set_mock_data("bootstrap-static", {"elements": [...], "teams": [...], "events": [...]})
client.set_mock_data("fixtures", [...])

service = FPLTeamBuilderService(client=client)
snapshot = service.recommend(gw=1, dry_run=True)
print(snapshot.starting_xi)
```

---

## 📄 Output Schema (`snapshot_gw_<GW>.json`)

On every run, a snapshot object is saved with full player names:

```json
{
  "gameweek": 1,
  "timestamp": "2026-08-20T17:19:58.665814+00:00",
  "season": "2026-2027",
  "budget_used": 100.0,
  "bank": 0.0,
  "confidence_score": 73.0,
  "recommended_squad": [
    {
      "id": 4,
      "name": "Gabriel dos Santos Magalhães",
      "web_name": "Gabriel",
      "team": "Arsenal",
      "position": "DEF",
      "price": 8.0,
      "expected_points": 4.5,
      "expected_points_plan": 12.5,
      "ownership_percent": 29.6,
      "starter": true,
      "captain": true,
      "vice_captain": false,
      "bench_order": 0,
      "defcon_bonus": 0.72,
      "why_this_pick": "Premier captaincy pick with 4.5 expected points next GW"
    }
  ],
  "starting_xi": ["David Raya Martín", "Gabriel dos Santos Magalhães", "..."],
  "bench": ["Reiss Nelson", "Shumaira Mheuka", "Dane Scarlett", "Walter Benítez"],
  "captain": {
    "name": "Gabriel dos Santos Magalhães",
    "team": "Arsenal",
    "expected_points": 9.0,
    "confidence": 70.8,
    "rationale": "Highest projected ceiling with 4.5 expected points (2x = 9.0 pts) and favorable fixture."
  },
  "vice_captain": {
    "name": "Bruno Borges Fernandes",
    "team": "Man Utd",
    "expected_points": 3.9,
    "confidence": 60.2,
    "rationale": "Strong backup option (3.9 xP) providing risk diversification."
  },
  "transfers": [],
  "chips": [
    {
      "chip": "BB1",
      "chip_name": "Bench Boost (Set 1)",
      "gameweek": 1,
      "rationale": "Optimal Set-1 timing at GW1 based on fixture schedule & pre-deadline expiry (GW19).",
      "expected_roi": 3.0,
      "confidence_pct": 65.0,
      "is_primary": true
    }
  ],
  "differentials": [
    {
      "name": "Daniel Ballard",
      "team": "Sunderland",
      "position": "DEF",
      "price": 5.0,
      "ownership_percent": 4.9,
      "expected_points": 3.4,
      "risk_level": "Medium",
      "rationale": "Explosive differential with only 4.9% ownership, £5.0m cost, and 3.4 projected xP."
    }
  ],
  "top_alternatives": [
    {
      "name": "Differential Upside",
      "description": "High-leverage squad maximizing sub-10% ownership players with favorable fixture runs.",
      "total_cost": 99.5,
      "starting_xi": ["..."],
      "captain": "Erling Haaland",
      "expected_points": 42.5,
      "confidence_score": 78.5
    }
  ],
  "rationale": [
    "Constructed optimal opening 15-man squad (£100.0m) maximizing expected points over 4-GW lookahead.",
    "Captain Gabriel dos Santos Magalhães (9.0 xP) projected as highest ceiling asset.",
    "Chip strategy: Prepare for Bench Boost (Set 1) around GW1 (+3.0 expected ROI)."
  ]
}
```

---

## 🔒 Security & Privacy

- Stores **only non-sensitive team IDs** and public FPL squad numbers in `fpl_builder.db`.
- Never requests, collects, or stores passwords or personal account tokens.
- Exponential backoff and rate-limiting protect against accidental API throttling.