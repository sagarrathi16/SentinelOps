"""
SentinelOps - Rapid Demo State Reset Script (< 5s)
Restores the target microservice to the buggy commit #8f9b2a and resets room memory.
"""

import sys
import os
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.switch_server import store
from target_service.payment_processor import PaymentProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reset_demo_state")


def reset_state():
    print("=" * 60)
    print("  [>] Resetting SentinelOps Demo Environment to Pre-Incident State...")
    print("=" * 60)

    # 1. Reset in-memory Switch Core stores
    room_id = "inc-checkout-482"
    store.events[room_id] = []
    store.roles[room_id] = {}
    store.documents[room_id] = {}
    store.global_seq = 0
    print("  [+] Switch Core store cleared (events, roles, documents reset).")

    # 2. Reset target service processor
    processor = PaymentProcessor(commit_sha="8f9b2a")
    print(f"  [+] Target microservice active commit set to: #{processor.active_commit} (injected regression bug).")

    print("\n  [OK] Environment successfully reset in < 1 second.")
    print("  Ready to run: python scripts/run_demo_simulation.py\n")


if __name__ == "__main__":
    reset_state()

