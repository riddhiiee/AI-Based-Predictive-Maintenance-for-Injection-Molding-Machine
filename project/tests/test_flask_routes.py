"""
Verifies every Flask route renders successfully (HTTP 200, no Jinja
exceptions) using Flask's in-process test client. This does NOT require
the FastAPI backend to be running, since page shells render before any
client-side JS fetch happens.

Run with:
    python3 tests/test_flask_routes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

ROUTES = ["/", "/dashboard", "/predictions", "/assistant", "/knowledge-base", "/history"]

PASS = 0
FAIL = 0


def main():
    global PASS, FAIL
    client = app.test_client()
    for route in ROUTES:
        resp = client.get(route)
        ok = resp.status_code == 200
        if ok:
            PASS += 1
            print(f"  OK   {route}  (200, {len(resp.data)} bytes)")
        else:
            FAIL += 1
            print(f"  FAIL {route}  (status {resp.status_code})")
            print(resp.data.decode("utf-8", errors="replace")[:2000])

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
