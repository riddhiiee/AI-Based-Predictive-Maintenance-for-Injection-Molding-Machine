from __future__ import annotations

import csv
import io
import json
import os
import threading
from typing import Any


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

RUNTIME_DIR = os.path.join(
    BASE_DIR,
    "runtime",
)

HISTORY_FILE = os.path.join(
    RUNTIME_DIR,
    "live_history.json",
)

_lock = threading.Lock()


def _ensure_file() -> None:

    os.makedirs(
        RUNTIME_DIR,
        exist_ok=True,
    )

    if not os.path.exists(HISTORY_FILE):

        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                {"cycles": []},
                f,
                indent=2,
            )


def _read_unlocked() -> dict[str, Any]:

    _ensure_file()

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

    except (
        json.JSONDecodeError,
        OSError,
    ):

        data = {
            "cycles": []
        }

    if not isinstance(
        data.get("cycles"),
        list,
    ):
        data["cycles"] = []

    return data


def _write_unlocked(
    data: dict[str, Any],
) -> None:

    _ensure_file()

    temp_file = (
        HISTORY_FILE + ".tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(
        temp_file,
        HISTORY_FILE,
    )


def _health_score(
    predictions: list[dict[str, Any]],
) -> int:

    penalty = {
        "Healthy": 0,
        "Warning": 14,
        "Critical": 32,
    }

    total_penalty = 0

    for prediction in predictions:

        state = prediction.get(
            "predicted_state",
            "Healthy",
        )

        total_penalty += penalty.get(
            state,
            0,
        )

    return max(
        15,
        100 - total_penalty,
    )


def save_cycle(
    *,
    session_id: str,
    completed_cycle: int,
    generated_at: str,
    cycle_id: str,
    mold: str,
    material: str,
    predictions: list[dict[str, Any]],
) -> bool:
    """
    Save one completed simulation cycle.

    session_id + completed_cycle is used for duplicate
    protection. This is better than cycle_id alone because
    CSV cycle numbers may repeat after restarting a profile.
    """

    unique_key = (
        f"{session_id}::{completed_cycle}"
    )

    record = {

        "unique_key":
            unique_key,

        "session_id":
            session_id,

        "completed_cycle":
            int(completed_cycle),

        "generated_at":
            generated_at,

        "cycle_id":
            cycle_id,

        "mold":
            mold,

        "material":
            material,

        "overall_health":
            _health_score(
                predictions
            ),

        "predictions":
            predictions,
    }

    with _lock:

        data = _read_unlocked()

        existing = {
            item.get("unique_key")
            for item
            in data["cycles"]
        }

        if unique_key in existing:
            return False

        data["cycles"].append(
            record
        )

        # Keep latest 10,000 cycles.
        data["cycles"] = (
            data["cycles"][-10000:]
        )

        _write_unlocked(
            data
        )

    return True


def get_cycles(
    *,
    limit: int | None = None,
    subsystem: str | None = None,
) -> list[dict[str, Any]]:

    with _lock:
        data = _read_unlocked()

    cycles = list(
        data["cycles"]
    )

    if subsystem:

        filtered = []

        for cycle in cycles:

            predictions = (
                cycle.get(
                    "predictions",
                    []
                )
            )

            if any(
                p.get("subsystem")
                == subsystem
                for p in predictions
            ):
                filtered.append(
                    cycle
                )

        cycles = filtered

    cycles.reverse()

    if limit is not None:
        cycles = cycles[
            :max(1, int(limit))
        ]

    return cycles


def get_health_trend(
    limit: int = 50,
) -> dict[str, Any]:

    limit = max(
        1,
        min(
            int(limit),
            500,
        ),
    )

    with _lock:
        data = _read_unlocked()

    cycles = data[
        "cycles"
    ][-limit:]

    return {

        "labels": [
            cycle.get(
                "cycle_id",
                f"Cycle {i + 1}",
            )
            for i, cycle
            in enumerate(cycles)
        ],

        "series": [
            float(
                cycle.get(
                    "overall_health",
                    100,
                )
            )
            for cycle in cycles
        ],

        "unit": "%",
    }


def export_csv() -> str:

    with _lock:
        data = _read_unlocked()

    output = io.StringIO()

    writer = csv.writer(
        output
    )

    subsystem_names = [
        "hopper",
        "heater",
        "screw",
        "injection",
        "hydraulic",
        "clamp",
        "mold",
        "cooling",
        "ejector",
    ]

    header = [
        "Generated At",
        "Session ID",
        "Completed Cycle",
        "Cycle ID",
        "Mold",
        "Material",
        "Overall Health",
    ]

    for subsystem in subsystem_names:

        header.append(
            f"{subsystem.title()} State"
        )

        header.append(
            f"{subsystem.title()} Confidence"
        )

    writer.writerow(
        header
    )

    for cycle in data["cycles"]:

        predictions = {

            p.get("subsystem"):
                p

            for p in cycle.get(
                "predictions",
                []
            )
        }

        row = [

            cycle.get(
                "generated_at",
                "",
            ),

            cycle.get(
                "session_id",
                "",
            ),

            cycle.get(
                "completed_cycle",
                "",
            ),

            cycle.get(
                "cycle_id",
                "",
            ),

            cycle.get(
                "mold",
                "",
            ),

            cycle.get(
                "material",
                "",
            ),

            cycle.get(
                "overall_health",
                "",
            ),
        ]

        for subsystem in subsystem_names:

            prediction = (
                predictions.get(
                    subsystem,
                    {}
                )
            )

            row.extend([
                prediction.get(
                    "predicted_state",
                    "",
                ),

                prediction.get(
                    "confidence",
                    "",
                ),
            ])

        writer.writerow(
            row
        )

    return output.getvalue()