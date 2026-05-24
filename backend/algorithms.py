import numpy as np

class MCMC_Channel:
    def __init__(self):
        self.queue = []

    def send(self, tick, msg):
        latency = max(1, int(np.random.normal(2, 1)))
        self.queue.append((tick + latency, msg))

    def receive(self, tick):
        ready = [m for t, m in self.queue if t <= tick]
        self.queue = [x for x in self.queue if x[0] > tick]
        return ready