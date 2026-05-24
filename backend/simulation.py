import random
from robot import Robot
from algorithms import MCMC_Channel

class Simulation:
    def __init__(self, grid_size, num_robots):
        self.grid_size = grid_size
        self.num_robots = num_robots
        self.logs = []
        self.game_over = False
        self.reset()

    def add_log(self, text, type="Sys"):
        self.logs.append({"tick": self.tick, "text": text, "type": type})
        if len(self.logs) > 20: self.logs.pop(0)

    def reset(self):
        print("--- RESET ---")
        self.tick = 0
        self.logs = []
        self.game_over = False
        self.add_log("Simulation Reset", "Sys")
        self.robots = []
        self.gold_bars = []
        self.score = {'A': 0, 'B': 0}
        self.depot_A = (0, 0)
        self.depot_B = (self.grid_size-1, self.grid_size-1)
        
        # TRACKING FOR SCOREBOARD
        self.total_gold = 10
        self.deposited_count = 0

        for _ in range(self.total_gold):
            self.gold_bars.append({'x': random.randint(0,19), 'y': random.randint(0,19)})

        for i in range(self.num_robots):
            group = 'A' if i < self.num_robots // 2 else 'B'
            while True:
                rx, ry = random.randint(0, 19), random.randint(0, 19)
                if (rx, ry) != self.depot_A and (rx, ry) != self.depot_B: break
            
            depot = self.depot_A if group == 'A' else self.depot_B
            self.robots.append(Robot(i, group, rx, ry, depot))

        self.channels = {'A': MCMC_Channel(), 'B': MCMC_Channel()}

    def step(self):
        if self.game_over: return

        self.tick += 1
        
        msgs = {'A': self.channels['A'].receive(self.tick), 'B': self.channels['B'].receive(self.tick)}

        moves = []
        for r in self.robots:
            vision = {'gold_detected': False, 'gold_loc': None}
            for g in self.gold_bars:
                if abs(g['x']-r.x) + abs(g['y']-r.y) <= 2:
                    vision['gold_detected'] = True; vision['gold_loc'] = (g['x'], g['y'])
                    break
            
            prev_target = r.target
            action = r.decide_action(vision, msgs[r.group])
            
            # Log if robot found gold newly
            if action != "STAY" and isinstance(action, dict) and action.get('action') == 'BROADCAST':
                if r.state == "MOVING_TO_GOLD" and prev_target != r.target:
                    self.add_log(f"R{r.id} ({r.group}) found gold at {r.target}!", r.group)

            if isinstance(action, dict):
                if action.get('action') == 'BROADCAST':
                    self.channels[r.group].send(self.tick, action['payload'])
                elif action.get('action') == 'MOVE':
                    moves.append((r, action['dx'], action['dy']))

        for r, dx, dy in moves:
            nx, ny = r.x + dx, r.y + dy
            if 0 <= nx < self.grid_size and 0 <= ny < self.grid_size:
                r.x, r.y = nx, ny

        # --- COOPERATIVE PICKUP LOGIC ---
        remaining_gold = []
        for g in self.gold_bars:
            on_tile = [r for r in self.robots if r.x == g['x'] and r.y == g['y'] and not r.carrying]
            cnt_A = [r for r in on_tile if r.group == 'A']
            cnt_B = [r for r in on_tile if r.group == 'B']
            
            picked = False
            
            # GROUP A LOGIC
            if len(cnt_A) == 2:
                for w in cnt_A: w.carrying = True; w.state = "CARRYING"
                picked = True
                self.add_log(f"Blue: R{cnt_A[0].id} & R{cnt_A[1].id} carrying gold!", "A")
            elif len(cnt_A) > 2:
                random.shuffle(cnt_A)
                keep = cnt_A[:2]; kick = cnt_A[2:]
                for w in keep: w.carrying = True; w.state = "CARRYING"
                for k in kick: k.state = "IDLE"; k.target = None; k.waiting_tick = 0
                picked = True
                self.add_log(f"Blue: R{keep[0].id} & R{keep[1].id} carrying (Crowd dispersed).", "A")

            # GROUP B LOGIC
            elif len(cnt_B) == 2:
                for w in cnt_B: w.carrying = True; w.state = "CARRYING"
                picked = True
                self.add_log(f"Red: R{cnt_B[0].id} & R{cnt_B[1].id} carrying gold!", "B")
            elif len(cnt_B) > 2:
                random.shuffle(cnt_B)
                keep = cnt_B[:2]; kick = cnt_B[2:]
                for w in keep: w.carrying = True; w.state = "CARRYING"
                for k in kick: k.state = "IDLE"; k.target = None; k.waiting_tick = 0
                picked = True
                self.add_log(f"Red: R{keep[0].id} & R{keep[1].id} carrying (Crowd dispersed).", "B")
            
            if not picked: remaining_gold.append(g)
        self.gold_bars = remaining_gold

        # Dropoff Logic
        for r in self.robots:
            if r.carrying and (r.x, r.y) == r.depot_loc:
                self.score[r.group] += 0.5
                self.deposited_count += 0.5 # Track total deposited
                
                if self.score[r.group] % 1 == 0:
                     self.add_log(f"Team {r.group} deposited gold! (+1 Score)", "Success")
                r.carrying = False
                r.state = "IDLE"

        # Check Game Over
        # If total deposited == total spawned, we are definitively done.
        # Or if map empty and nobody carrying (fallback)
        if int(self.deposited_count) >= self.total_gold or (len(self.gold_bars) == 0 and not any(r.carrying for r in self.robots)):
            if not self.game_over:
                self.game_over = True
                self.add_log("ALL GOLD DEPOSITED! MISSION COMPLETE.", "Success")
                print("--- GAME OVER ---")

    def get_state(self):
        # Calculate real gold left
        gold_left = int(self.total_gold - self.deposited_count)
        
        return {
            "tick": self.tick,
            "robots": [{"id":r.id, "x":r.x, "y":r.y, "group":r.group, "carrying":r.carrying, "role_char": r.get_role_char()} for r in self.robots],
            "gold": self.gold_bars,
            "score_a": int(self.score['A']),
            "score_b": int(self.score['B']),
            "gold_left": gold_left, # Send accurate count
            "logs": self.logs
        }