"""A text progress bar for ``match(progress=...)``.

    bar = verdy.ProgressBar()
    matches = verdy.match("my_input.csv", ["envo", "gold"], progress=bar)
    bar.close()

    Looking up ENA IDs         [##############################] 3/3
    Looking up hosts           [##############################] 1/1
    Reading GOLD               [###############...............] 312/604
"""

from __future__ import annotations

import sys


class ProgressBar:
    """``progress(stage, done, total)`` drawn on stderr: a bar per stage, each on its own line when done."""
    WIDTH = 30

    def __init__(self, out=None):
        self.out, self.stage = out or sys.stderr, None

    def __call__(self, stage: str, done, total) -> None:
        if stage != self.stage and self.stage is not None:
            self.out.write("\n")
        self.stage = stage
        if total:
            filled = round(self.WIDTH * done / total)
            line = f"{stage:<26} [{'#' * filled}{'.' * (self.WIDTH - filled)}] {done}/{total}"
        else:
            line = f"{stage:<26} ..."
        self.out.write("\r" + line)
        self.out.flush()

    def close(self) -> None:
        if self.stage is not None:
            self.out.write("\n")
            self.stage = None
