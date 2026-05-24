import random

class PaxosAgent:
    def __init__(self, id):
        self.id = id
        self.pid = 0
    def propose(self, val):
        self.pid += 1
        return {"type": "PREPARE", "pid": self.pid, "val": val}

class Robot:
    def __init__(self, id, group, x, y, depot):
        self.id = id; self.group = group; self.x = x; self.y = y; self.depot_loc = depot
        self.state = "IDLE"
        self.carrying = False
        self.target = None
        self.paxos = PaxosAgent(id)
        self.waiting_tick = 0
        self.MAX_WAIT = 60 

    def get_role_char(self):
        if self.state == "IDLE": return "S" 
        if self.state == "MOVING_TO_GOLD": return "M" 
        if self.state == "WAITING_AT_GOLD": return "W" 
        if self.state == "CARRYING": return "C" 
        return "?"

    def decide_action(self, vision, inbox):
        # 1. Process Inbox 
        for msg in inbox:
            if msg['type'] == "PREPARE" and self.state == "IDLE":
                self.target = msg['val']
                self.state = "MOVING_TO_GOLD"
                self.waiting_tick = 0

        # 2. State Machine Logic
        if self.state == "IDLE":
            if vision['gold_detected']:
                self.target = vision['gold_loc']
                self.state = "MOVING_TO_GOLD"
                return {"action": "BROADCAST", "payload": self.paxos.propose(self.target)}
            else: 
                return self.random_move()

        elif self.state == "MOVING_TO_GOLD":
            if (self.x, self.y) == self.target:
                # ARRIVED: Check if gold is actually here!
                # If gold is gone (false alarm or taken), go back to IDLE
                if not vision['gold_detected']:
                    self.state = "IDLE"
                    self.target = None
                    return self.random_move()
                
                self.state = "WAITING_AT_GOLD"
                self.waiting_tick = 0
                return "STAY"
            return self.move_towards(self.target)

        elif self.state == "WAITING_AT_GOLD":
            if self.carrying: 
                self.state = "CARRYING"
                self.waiting_tick = 0
                return "STAY"

            # REALITY CHECK: Is gold still here?
            # If gold disappears while waiting (e.g. other team took it), leave.
            if not vision['gold_detected']:
                self.state = "IDLE"
                self.target = None
                self.waiting_tick = 0
                return self.random_move()

            self.waiting_tick += 1
            if self.waiting_tick % 10 == 0:
                return {"action": "BROADCAST", "payload": self.paxos.propose(self.target)}

            if self.waiting_tick > self.MAX_WAIT:
                self.state = "IDLE"
                self.waiting_tick = 0
                self.target = None
                return self.random_move()

            return "STAY"

        elif self.state == "CARRYING":
            return self.move_towards(self.depot_loc, deterministic=True)

        return "STAY"

    def random_move(self):
        if random.random() < 0.2: return "STAY"
        dx, dy = random.choice([(0,1), (0,-1), (1,0), (-1,0)])
        return {"action": "MOVE", "dx": dx, "dy": dy}

    def move_towards(self, t, deterministic=False):
        dx, dy = 0, 0
        if self.x < t[0]: dx = 1
        elif self.x > t[0]: dx = -1
        if self.y < t[1]: dy = 1
        elif self.y > t[1]: dy = -1
        
        if deterministic:
            if dx != 0: dy = 0
        else:
            if dx!=0 and dy!=0:
                if random.choice([True, False]): dx=0
                else: dy=0
        
        if dx==0 and dy==0: return "STAY"
        return {"action": "MOVE", "dx": dx, "dy": dy}