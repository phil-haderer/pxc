"""What is left of a GPU round, for the progress line of the live_*.py run loops (user 22.11.: "a counter for the runs
while they are running, so I can see how much is left"). Pictures skipped because they are already done do not count
towards the time per picture.

    left = Left(len(js))
    ... print(f"{i}/{len(js)} {fid}: {secs} s" + left(i))     ->  "7/24 q-r10-07: 26 s - 17 left, about 7 min"
"""
import time


class Left:
    def __init__(self, total: int, clock=time.time):
        self.total, self.clock, self.t0, self.done = total, clock, clock(), 0

    def __call__(self, i: int) -> str:
        """Call once per finished picture, with its 1-based place in the round."""
        self.done += 1
        left = self.total - i
        if left <= 0:
            return " - last one"
        mins = left * (self.clock() - self.t0) / self.done / 60
        return f" - {left} left, about {'<1' if mins < 1 else round(mins)} min"
