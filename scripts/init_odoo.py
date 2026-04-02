#!/usr/bin/env python3
"""
Odoo bootstrap script — run once after 'make ultra' or 'make up-all'.

What it does:
  1. Waits for Odoo HTTP to respond (polls every 5 s, up to 10 min)
  2. Authenticates via XML-RPC
  3. Installs foldiss_uav addon if not already installed
  4. Prints ready banner with login credentials

Usage:
  python3 scripts/init_odoo.py
  make init-odoo
"""

import os
import sys
import time
import urllib.request
import xmlrpc.client

# ── Config (reads from env, falls back to defaults) ───────────────────────────
ODOO_URL  = os.environ.get("ODOO_EXTERNAL_URL", "http://localhost:5433")
DB        = os.environ.get("ODOO_DB",           "odoo")
USER      = os.environ.get("ODOO_USER",         "admin")
PASSWORD  = os.environ.get("ODOO_PASSWORD",     "admin")
MAX_WAIT  = int(os.environ.get("ODOO_INIT_TIMEOUT", "600"))   # seconds
POLL_INTERVAL = 5


# ── Step 1: wait for Odoo HTTP ────────────────────────────────────────────────
def wait_for_odoo() -> bool:
    print(f"\nWaiting for Odoo at {ODOO_URL} ", end="", flush=True)
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        try:
            code = urllib.request.urlopen(
                f"{ODOO_URL}/web/login", timeout=3
            ).getcode()
            if code == 200:
                print(" ready!\n")
                return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(POLL_INTERVAL)
    print("\nERROR: Odoo did not become ready within %d seconds." % MAX_WAIT)
    return False


# ── Step 2: authenticate ──────────────────────────────────────────────────────
def authenticate(common) -> int:
    print(f"Authenticating as '{USER}' on db '{DB}' ...", end=" ", flush=True)
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            uid = common.authenticate(DB, USER, PASSWORD, {})
            if uid:
                print(f"uid={uid}")
                return uid
            print("failed (wrong credentials?)")
            return 0
        except Exception as exc:
            # Registry not yet loaded — keep retrying
            print(".", end="", flush=True)
            time.sleep(5)
    print("\nERROR: Could not authenticate within 2 minutes.")
    return 0


# ── Step 3: install foldiss_uav if needed ─────────────────────────────────────
def ensure_addon(models, uid) -> bool:
    rows = models.execute_kw(
        DB, uid, PASSWORD,
        "ir.module.module", "search_read",
        [[["name", "=", "foldiss_uav"]]],
        {"fields": ["name", "state"], "limit": 1},
    )

    if not rows:
        print("ERROR: foldiss_uav not found in addons path.")
        print("       Make sure odoo/src/addons/foldiss_uav/ exists and")
        print("       is mounted into the Odoo container.")
        return False

    state = rows[0]["state"]
    print(f"foldiss_uav state: {state}")

    if state == "installed":
        print("✓ foldiss_uav is already installed.")
        return True

    print("Installing foldiss_uav ...", end=" ", flush=True)
    module_id = rows[0]["id"]
    models.execute_kw(
        DB, uid, PASSWORD,
        "ir.module.module", "button_immediate_install",
        [[module_id]],
    )
    # Verify
    rows2 = models.execute_kw(
        DB, uid, PASSWORD,
        "ir.module.module", "read",
        [[module_id]], {"fields": ["state"]},
    )
    if rows2 and rows2[0]["state"] == "installed":
        print("done.")
        return True

    print("ERROR: installation may have failed — check Odoo logs.")
    return False


# ── Step 4: ensure admin password matches .env ────────────────────────────────
def ensure_admin_password(models, uid) -> None:
    """
    If ODOO_PASSWORD is set to something other than the Odoo default,
    update the admin user's password so it matches.
    This is idempotent — calling it again with the same password is safe.
    """
    if PASSWORD == "admin":
        return   # default, nothing to do
    try:
        models.execute_kw(
            DB, uid, PASSWORD,
            "res.users", "write",
            [[uid], {"password": PASSWORD}],
        )
        print(f"✓ Admin password synced from ODOO_PASSWORD env var.")
    except Exception:
        pass   # already set or insufficient permissions — not fatal


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 60)
    print("  Foldiss UAV — Odoo initialisation script")
    print("=" * 60)

    # 1. HTTP ready?
    if not wait_for_odoo():
        return 1

    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

    # 2. Auth
    uid = authenticate(common)
    if not uid:
        return 1

    # 3. Addon
    if not ensure_addon(models, uid):
        return 1

    # 4. Password sync
    ensure_admin_password(models, uid)

    # 5. Done
    print()
    print("=" * 60)
    print("  Odoo is ready — start working:")
    print()
    print(f"  URL      →  {ODOO_URL}/odoo/uav-missions")
    print(f"  Login    →  {USER}")
    print(f"  Password →  {PASSWORD}")
    print()
    print("  Frontend →  http://localhost:3000")
    print("  RabbitMQ →  http://localhost:15672  (guest / guest)")
    print("=" * 60)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
