"""
Target Microservice - Payment Processor Logic
Simulates the production microservice with injected bug in commit #8f9b2a.
"""

from typing import Dict, Any, Optional
import uuid
import logging

logger = logging.getLogger("payment_processor")


class PaymentProcessor:
    def __init__(self, commit_sha: str = "8f9b2a"):
        self.active_commit = commit_sha
        logger.info(f"PaymentProcessor initialized with commit {self.active_commit}")

    def set_commit(self, commit_sha: str):
        self.active_commit = commit_sha

    def process_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes checkout payment transaction.
        In commit 8f9b2a ('Add expedited billing flag'), Alice introduced
        an unchecked dictionary access on customer_profile['billing_details']['expedited_flag'].
        When customer_profile['billing_details'] is None, it crashes with TypeError / NullPointer.
        """
        amount = payload.get("amount", 0.0)
        currency = payload.get("currency", "USD")
        customer = payload.get("customer", {})
        card_number = payload.get("card_number", "4111-XXXX-XXXX-1111")
        customer_email = customer.get("email", "john.doe@example.com")

        if amount <= 0:
            raise ValueError("Amount must be greater than zero")

        # Simulate Commit #8f9b2a (Injected Regression Bug by Alice)
        if self.active_commit == "8f9b2a":
            # BUG AT LINE 142: Incomplete null guard on expedited billing
            billing_details = customer.get("billing_details")
            # In Python, accessing billing_details["expedited_flag"] when None raises TypeError (NullPointer equivalent)
            expedited = billing_details["expedited_flag"]
            fee = 5.00 if expedited else 0.00
        else:
            # CLEAN / REVERTED COMMIT (#7c41e0)
            billing_details = customer.get("billing_details") or {}
            expedited = billing_details.get("expedited_flag", False)
            fee = 5.00 if expedited else 0.00

        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        return {
            "status": "success",
            "transaction_id": tx_id,
            "amount": amount + fee,
            "currency": currency,
            "expedited": expedited,
            "customer_masked": f"{customer_email[:3]}***@***",
            "commit_version": self.active_commit
        }

