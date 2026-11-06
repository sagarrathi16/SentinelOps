"""
Target Payment Microservice
FastAPI application simulating staging/production microservice monitored by SentinelOps.
"""

from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
import uvicorn
import logging
import time

from target_service.payment_processor import PaymentProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("target_service")

app = FastAPI(title="Payment Checkout Service", version="2.4.1")

processor = PaymentProcessor(commit_sha="8f9b2a")  # Starts in buggy state

class CustomerModel(BaseModel):
    id: str = "cust_992"
    name: str = "Alice Smith"
    email: str = "alice.smith@customer.net"
    billing_details: Optional[Dict[str, Any]] = None  # None triggers bug in 8f9b2a

class CheckoutRequest(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = "USD"
    card_number: str = "4111-2222-3333-4444"
    customer: CustomerModel = Field(default_factory=CustomerModel)

class DeployRequest(BaseModel):
    commit_sha: str

# In-memory metrics
metrics_store = {
    "requests_total": 0,
    "requests_failed": 0,
}
last_alert_time = 0.0

@app.get("/health")
def health():
    error_rate = 0.0
    if metrics_store["requests_total"] > 0:
        error_rate = (metrics_store["requests_failed"] / metrics_store["requests_total"]) * 100
    return {
        "status": "healthy" if error_rate < 5.0 else "degraded",
        "commit": processor.active_commit,
        "error_rate_pct": round(error_rate, 2),
        "requests_total": metrics_store["requests_total"],
        "requests_failed": metrics_store["requests_failed"]
    }

@app.get("/metrics")
def metrics():
    error_rate = 0.0
    if metrics_store["requests_total"] > 0:
        error_rate = (metrics_store["requests_failed"] / metrics_store["requests_total"]) * 100
    return {
        "checkout_error_rate_percentage": round(error_rate, 2),
        "active_commit": processor.active_commit
    }

@app.post("/checkout")
def checkout(req: CheckoutRequest):
    global last_alert_time
    metrics_store["requests_total"] += 1
    try:
        result = processor.process_payment(req.dict())
        return result
    except Exception as e:
        metrics_store["requests_failed"] += 1
        logger.error(
            f"Payment processing failed: {str(e)} | Stack: PaymentProcessor.ts:142 NullPointerException (customer email: {req.customer.email}, card: {req.card_number})"
        )

        # Notify Switch / SentinelOps if cooldown elapsed (simulating observability alert webhook)
        now = time.time()
        if now - last_alert_time > 8.0:
            last_alert_time = now
            try:
                import urllib.request
                import json
                alert_body = json.dumps({
                    "content": f"CRITICAL: HTTP 500 error rate spiked to 14.8% on /checkout (commit {processor.active_commit})"
                }).encode("utf-8")
                alert_urls = [
                    "http://host.docker.internal:8000/inject/alert",
                    "http://127.0.0.1:8000/inject/alert",
                    "http://switch:8000/inject/alert"
                ]
                dispatched = False
                for alert_url in alert_urls:
                    try:
                        req_obj = urllib.request.Request(
                            alert_url,
                            data=alert_body,
                            headers={"Content-Type": "application/json"},
                            method="POST"
                        )
                        urllib.request.urlopen(req_obj, timeout=1.5)
                        logger.info(f"Alert successfully dispatched to {alert_url}")
                        dispatched = True
                        break
                    except Exception:
                        continue
                if not dispatched:
                    logger.warning("Could not reach any alert webhook endpoint")
            except Exception as alert_err:
                logger.warning(f"Could not forward alert to Switch Core: {alert_err}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "PaymentProcessorException",
                "message": "NullPointerException at PaymentProcessor.ts:142 in billing_details null dereference",
                "commit": processor.active_commit,
                "raw_log": f"ERROR [PaymentService] Unhandled TypeError: NoneType object is not subscriptable at line 142 for card {req.card_number}"
            }
        )

@app.post("/admin/deploy")
def deploy(req: DeployRequest):
    """Admin endpoint to redeploy or roll back container commit"""
    processor.set_commit(req.commit_sha)
    # Reset error window on clean deploy
    if req.commit_sha != "8f9b2a":
        metrics_store["requests_failed"] = 0
        metrics_store["requests_total"] = 100  # baseline
    logger.info(f"Target Service deployed commit: {req.commit_sha}")
    return {"status": "deployed", "active_commit": req.commit_sha}

if __name__ == "__main__":
    uvicorn.run("target_service.app:app", host="0.0.0.0", port=8080, reload=True)

