"""Measure a dashboard's Event Log volume by event kind and level.

Runs the real dashboard, headless, over the Project of ``--checkout`` at the
``full`` level for ``--seconds``, writing its Event Log to a temporary
directory rather than the checkout's own. Every line names the level it
belongs to, so one ``full`` run also gives the ``standard`` volume.

Observation is read-only, but the dashboard sends its ordinary GitHub
requests with the caller's credentials. Run it with this checkout's locked
environment; pass ``--source-root`` to an exported ``src`` to measure
another revision.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DAY = 86_400
CHILD = """
import sys
from pathlib import Path
from dashpot.cli import main
from dashpot.core.event_log import EventLogDestination
sys.exit(main([], event_log=EventLogDestination(Path(sys.argv[1]))))
"""


def stamp(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def kind(event: dict[str, object]) -> str:
    name = str(event.get("event.name"))
    return f"span:{event.get('dashpot.span.name')}" if name == "span" else name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path.cwd())
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument(
        "--warmup",
        type=float,
        default=60,
        help="seconds after the first event left out of the daily rate",
    )
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()

    env = {
        **os.environ,
        "DASHPOT_EVENT_LEVEL": "full",
        "TEXTUAL_DRIVER": "textual.drivers.headless_driver:HeadlessDriver",
    }
    if args.source_root is not None:
        env["PYTHONPATH"] = str(args.source_root.resolve())

    with tempfile.TemporaryDirectory(prefix="dashpot-337-") as temporary:
        events = Path(temporary) / "events"
        with (Path(temporary) / "dashboard.log").open("w") as log:
            child = subprocess.Popen(
                [sys.executable, "-c", CHILD, str(events)],
                cwd=args.checkout,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                time.sleep(args.seconds)
            finally:
                child.send_signal(signal.SIGTERM)
                child.wait(timeout=30)

        lines = [
            line
            for path in sorted(events.glob("dashboard-*.jsonl"))
            for line in path.read_bytes().splitlines()
        ]

    parsed = [(json.loads(line), len(line) + 1) for line in lines]
    warmup = float(args.warmup)
    first = min(stamp(str(event["time"])) for event, _ in parsed)
    last = max(stamp(str(event["time"])) for event, _ in parsed)
    steady = [
        (event, size)
        for event, size in parsed
        if (stamp(str(event["time"])) - first).total_seconds() >= warmup
    ]
    steady_seconds = (last - first).total_seconds() - warmup

    kinds: dict[tuple[str, str], list[int]] = defaultdict(list)
    for event, size in parsed:
        kinds[kind(event), str(event["dashpot.level"])].append(size)

    def per_day(level: str | None) -> float:
        chosen = sum(
            size
            for event, size in steady
            if level is None or event["dashpot.level"] == level
        )
        return chosen / steady_seconds * DAY

    print(
        json.dumps(
            {
                "seconds": round((last - first).total_seconds(), 1),
                "steadySeconds": round(steady_seconds, 1),
                "lines": len(parsed),
                "bytes": sum(size for _, size in parsed),
                "kinds": {
                    f"{name} [{level}]": {
                        "count": len(sizes),
                        "averageBytes": round(sum(sizes) / len(sizes)),
                        "bytes": sum(sizes),
                    }
                    for (name, level), sizes in sorted(
                        kinds.items(), key=lambda item: -sum(item[1])
                    )
                },
                "bytesPerDay": {
                    "full": round(per_day(None)),
                    "standard": round(per_day("standard")),
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
