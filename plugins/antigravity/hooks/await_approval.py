#!/usr/bin/env python3
"""Hold the turn open while somebody answers an approval card.

Antigravity ends a turn once the model stops talking, which would leave the
card on screen with nobody listening for the answer. This runs on Stop, waits
for the person, and asks for one more turn when they approve.
"""

from __future__ import annotations

import json
import sys
import tempfile
import urllib.request
from pathlib import Path

ENDPOINT = Path(tempfile.gettempdir()) / "adk-harness-approval-endpoint.json"


def main() -> int:
    if not ENDPOINT.is_file():
        print("{}")
        return 0
    try:
        base = json.loads(ENDPOINT.read_text(encoding="utf-8"))["base"]
        with urllib.request.urlopen(f"{base}/waiting", timeout=150) as response:
            state = json.load(response)
    except Exception:
        # A harness that is not running must not keep the turn alive.
        print("{}")
        return 0

    if state.get("waiting") and state.get("answered") and state.get("approved"):
        print(
            json.dumps(
                {
                    "decision": "continue",
                    "reason": (
                        f"The person approved {state.get('operation')}. Call the same "
                        "tool again with exactly the same arguments to run it."
                    ),
                }
            )
        )
        return 0

    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
