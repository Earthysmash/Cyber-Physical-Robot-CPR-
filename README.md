# Cyber-Physical-Robot-CPR-

A 20x20 grid-world simulation where two teams of 10 robots compete to find gold bars and carry them back to their team depot. Robots can only see a few tiles ahead, only talk to teammates, and must coordinate in pairs to lift any gold — no robot can lift a bar alone, and no group of 3+ can lift it either.

This is the term project for the **Cyber Physical Robotics** course (term project spec dated August 9, 2025). The project explores distributed design, mathematical formalisms for distributed systems, and simulation methodology.

---

## Live View

| Element | Meaning |
|--------|---------|
| **Blue squares (B1–B10)** | Team A robots |
| **Red squares (R1–R10)** | Team B robots |
| **Purple tile (BT)** | Blue Team depot — top-left `(0,0)` |
| **Orange tile (RT)** | Red Team depot — bottom-right `(19,19)` |
| **Gold ingots** | Gold bars, randomly placed at reset |
| **S / M / W / C badge** | Robot role: Scout / Moving / Waiting / Carrying |

A right-hand terminal panel streams every event (gold found, pickups, deposits, mission complete).

---

## Architecture

```
┌──────────────────────┐     HTTP/JSON     ┌──────────────────────┐
│   index.html (UI)    │ ◄───────────────► │  Flask API (main.py) │
│   Canvas + Controls  │   /state /step    │      Port 5001       │
└──────────────────────┘   /reset /jump    └──────────┬───────────┘
                                                      │
                                          ┌───────────▼───────────┐
                                          │   simulation.py       │
                                          │  (world, rules, loop) │
                                          └───┬───────────────┬───┘
                                              │               │
                                  ┌───────────▼───┐   ┌───────▼────────┐
                                  │   robot.py    │   │  algorithms.py │
                                  │ State machine │   │ MCMC channel + │
                                  │ + Paxos agent │   │ comms latency  │
                                  └───────────────┘   └────────────────┘
```

The frontend is a pure HTML/JS file — no build step. The backend is Python (Flask). They communicate over a small REST API.

---

## Frontend — `index.html`

A single-file dark-themed dashboard. No frameworks, just vanilla JS + a `<canvas>` element.

**What it does:**
- Polls the Flask backend on a configurable timer (1–50 ticks per second).
- Renders the 20×20 grid, both depots, every gold ingot, and every robot.
- Each robot is drawn as a colored square with its ID label (B1, R5, …) and a small role badge in the corner (S/M/W/C) so you can see at a glance what each unit is doing.
- HUD at the top shows Blue score, Red score, gold remaining, and the current simulation tick.
- Right-side terminal panel mirrors the backend log: which team found gold, which pair picked it up, when a team deposited, and when the mission is complete.

**Controls:**
| Button | Action |
|--------|--------|
| START SIMULATION | Runs continuously at the slider's TPS |
| STEP +1 | Advances exactly one simulation tick |
| PAUSE | Stops the autoplay loop |
| RESET WORLD | Re-randomizes gold + robot positions on the backend |
| Speed slider | 1–50 ticks/sec |

The game container border turns **teal when connected** to the backend and **red when disconnected** — useful when you forgot to start the Flask server.

---

## Backend — How a Robot Finds Gold

The backend is where the cyber-physical logic lives. Each robot is an independent agent: it only knows what it has seen, what it has been told by teammates, and where its own depot is. There is no global oracle.

### 1. Perception (vision)

Every tick, the simulator builds a small `vision` packet for each robot:

```python
# simulation.py
for g in self.gold_bars:
    if abs(g['x'] - r.x) + abs(g['y'] - r.y) <= 2:
        vision['gold_detected'] = True
        vision['gold_loc'] = (g['x'], g['y'])
        break
```

A robot detects a gold bar if it sits within **Manhattan distance ≤ 2** of the bar. Anything farther is invisible to that robot.

### 2. State machine

Each robot runs the same finite state machine (`robot.py`):

```
        ┌──────────────────────────────────────┐
        │                                      │
        ▼                                      │
     IDLE ──── sees gold ────► MOVING_TO_GOLD  │
       ▲                            │          │
       │                            ▼          │
       │                       arrived at      │
       │                       gold tile       │
       │                            │          │
       │                            ▼          │
       │      gold gone / timeout  WAITING_AT_GOLD
       └────────────────────────────│
                                    │
                       paired with teammate
                                    │
                                    ▼
                                CARRYING ──► depot ──► drop / score
```

- **IDLE** (`S` — Scout): random walk until it spots gold or hears a teammate's broadcast.
- **MOVING_TO_GOLD** (`M`): walks toward the target tile.
- **WAITING_AT_GOLD** (`W`): sits on the gold and re-broadcasts every 10 ticks; gives up after 60 ticks if no partner arrives.
- **CARRYING** (`C`): heads deterministically back to its team's depot.

### 3. Communication (the "Cyber" part)

Robots talk **only to teammates** (Group A ↔ A, Group B ↔ B). Cross-team messaging is impossible by construction — each team has its own message channel.

Each robot owns a tiny **Paxos-style proposer** (`PaxosAgent` in `robot.py`). When a robot discovers gold or is still waiting on a partner, it broadcasts a `PREPARE` message with an incrementing proposal ID and the target location:

```python
class PaxosAgent:
    def propose(self, val):
        self.pid += 1
        return {"type": "PREPARE", "pid": self.pid, "val": val}
```

Any IDLE teammate who receives this message adopts the target and transitions to `MOVING_TO_GOLD`. This is how the swarm converges on a gold tile without central coordination.

Messages do **not** arrive instantly. They flow through an `MCMC_Channel` (`algorithms.py`) that injects realistic network latency:

```python
latency = max(1, int(np.random.normal(2, 1)))  # ~2 ticks ± 1
self.queue.append((tick + latency, msg))
```

The "MCMC" naming reflects that latency is sampled from a probability distribution every send — a stand-in for noisy real-world wireless transport. Faraway messages can arrive late, in batches, or get stacked with newer ones, which forces robots to tolerate stale information.

### 4. Path calculation

Path-finding here is intentionally **greedy** rather than A* — the project spec emphasizes distributed reasoning, not optimal navigation. Each robot's `move_towards(target)`:

```python
def move_towards(self, t, deterministic=False):
    dx = sign(t[0] - self.x)
    dy = sign(t[1] - self.y)
    # IDLE/MOVING: pick one axis at random to keep paths diverse
    # CARRYING: deterministic (dx first), so a pair stays in sync
```

The deterministic mode for **CARRYING** is critical: per spec, *"a pair of robots holding a gold bar can move it only if they both move in the same direction each tick — otherwise the bar is dropped."* Forcing a fixed axis-priority makes the two carriers naturally pick identical moves and keeps them locked together on the return trip.

---

## The 2-Robot Pickup Rule

This is the central coordination puzzle of the project:

> A gold bar can be picked up **if and only if exactly two robots of the same group** are on its tile and both perform a pickup. Fewer fails. More fails. Mixed-team conflicts can split gold between teams.

Implemented in `simulation.py`:

```python
on_tile = [r for r in self.robots if r.x == g['x'] and r.y == g['y'] and not r.carrying]
cnt_A = [r for r in on_tile if r.group == 'A']
cnt_B = [r for r in on_tile if r.group == 'B']

if len(cnt_A) == 2:
    for w in cnt_A: w.carrying = True; w.state = "CARRYING"
elif len(cnt_A) > 2:
    # Crowd dispersal: keep 2 at random, the rest go back to IDLE
    random.shuffle(cnt_A); keep, kick = cnt_A[:2], cnt_A[2:]
    ...
```

If three or more teammates pile onto the same gold tile, the simulator randomly picks **two** to carry and sends the rest back to scouting. This prevents permanent deadlock around a single bar.

Once the carrying pair reaches their depot tile, each robot contributes `+0.5` to the team score (one full point per delivered bar), the bar is removed from the world, and both robots go back to IDLE to scout for the next find.

---

## REST API

The backend exposes four endpoints on `http://127.0.0.1:5001`:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET`  | `/state` | Current snapshot (robots, gold, scores, logs) |
| `POST` | `/step`  | Advance the simulation by exactly one tick |
| `POST` | `/jump`  | Body: `{"steps": N}` — fast-forward N ticks |
| `POST` | `/reset` | Re-randomize the world |

Every response is the full game state JSON the frontend renders.

---

## Running It

### 1. Backend

```bash
cd backend
pip install -r requirement.txt        # flask, flask-cors, numpy
python main.py
```

The server prints `Server starting on Port 5001...` and listens on all interfaces.

### 2. Frontend

Just open `index.html` in any modern browser. The page hits `http://127.0.0.1:5001` directly — no build, no bundler. The container border turns teal once it sees the backend.

Click **START SIMULATION**, watch the swarm scout, pair up at gold tiles, and ferry ingots back to their depots until the terminal logs `ALL GOLD DEPOSITED! MISSION COMPLETE.`

---

## Project Structure

```
Cyber-Physical-Robot-CPR-/
├── index.html               # Frontend: canvas viz + controls + log panel
└── backend/
    ├── main.py              # Flask API (5001) — /state, /step, /jump, /reset
    ├── simulation.py        # World, tick loop, pickup/deposit rules
    ├── robot.py             # Per-robot state machine + Paxos proposer
    ├── algorithms.py        # MCMC_Channel — per-team message queue with latency
    └── requirement.txt      # flask, flask-cors, numpy
```

---

## Spec Compliance

| Requirement | Status |
|-------------|--------|
| 20×20 grid | ✅ |
| 2 groups × 10 robots, intra-group comms only | ✅ |
| Per-robot independent control logic | ✅ |
| Local vision only (no global oracle) | ✅ |
| One depot per team, fixed and known to its team | ✅ |
| Gold randomly initialized | ✅ |
| Exactly-2 same-group rule for pickup | ✅ |
| Pair must move together to carry | ✅ (deterministic axis priority) |
| Deposit → score | ✅ |
