"""CLI worker — what the GitHub Actions render farm (or cron on a VPS) runs.

    python -m app.worker tick [budget_s]     # publish due, plan, write, render, analytics, weekly compilation
    python -m app.worker process <id>        # write + render one episode
    python -m app.worker publish             # publish whatever is due
    python -m app.worker plan [category]     # queue one new episode
"""
from __future__ import annotations

import json
import sys

from . import config, pipeline


def main(argv: list[str]) -> int:
    probs = config.check_security(for_web=False)
    if probs and config.IS_PROD:
        print("Refusing to run:\n  - " + "\n  - ".join(probs))
        return 2
    cmd = argv[1] if len(argv) > 1 else "tick"
    if cmd == "tick":
        print(json.dumps(pipeline.tick(True, int(argv[2]) if len(argv) > 2 else 2700), indent=2, default=str))
    elif cmd == "process":
        ep = pipeline.process(argv[2])
        print(json.dumps({k: ep.get(k) for k in ("id", "status", "video_url", "error")}, indent=2))
    elif cmd == "publish":
        print(json.dumps(pipeline.publish_due()))
    elif cmd == "plan":
        print(json.dumps(pipeline.create(argv[2] if len(argv) > 2 else None), indent=2, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
