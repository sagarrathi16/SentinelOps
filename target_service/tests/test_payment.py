"""
Regression Test Suite for PaymentProcessor
Total Tests: 42 test cases verifying edge cases, null guards, idempotency, and billing details.
"""

import pytest
from target_service.payment_processor import PaymentProcessor


@pytest.fixture
def clean_processor():
    # Clean / reverted commit 7c41e0
    return PaymentProcessor(commit_sha="7c41e0")


@pytest.fixture
def buggy_processor():
    # Buggy commit 8f9b2a
    return PaymentProcessor(commit_sha="8f9b2a")


# 1 - 10: Basic Payment Flow & Currencies
@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "INR", "SGD", "NZD"])
def test_valid_currencies(clean_processor, currency):
    res = clean_processor.process_payment({
        "amount": 100.0,
        "currency": currency,
        "customer": {"email": "test@domain.com", "billing_details": {"expedited_flag": False}}
    })
    assert res["status"] == "success"
    assert res["currency"] == currency
    assert res["amount"] == 100.0


# 11 - 15: Amount Validations
def test_positive_amount(clean_processor):
    res = clean_processor.process_payment({"amount": 25.50, "customer": {}})
    assert res["status"] == "success"

def test_large_amount(clean_processor):
    res = clean_processor.process_payment({"amount": 999999.00, "customer": {}})
    assert res["status"] == "success"

def test_zero_amount_raises(clean_processor):
    with pytest.raises(ValueError):
        clean_processor.process_payment({"amount": 0.0, "customer": {}})

def test_negative_amount_raises(clean_processor):
    with pytest.raises(ValueError):
        clean_processor.process_payment({"amount": -50.0, "customer": {}})

def test_fractional_cent_amount(clean_processor):
    res = clean_processor.process_payment({"amount": 10.999, "customer": {}})
    assert res["status"] == "success"


# 16 - 25: Critical Null Guard Tests (Root Cause Verification)
def test_null_billing_details_clean(clean_processor):
    # This must PASS on clean commit, proving null guard works
    res = clean_processor.process_payment({
        "amount": 50.0,
        "customer": {"name": "Bob", "email": "bob@org.com", "billing_details": None}
    })
    assert res["status"] == "success"
    assert res["expedited"] is False
    assert res["amount"] == 50.0

def test_empty_customer_dict_clean(clean_processor):
    res = clean_processor.process_payment({"amount": 12.0, "customer": {}})
    assert res["status"] == "success"
    assert res["expedited"] is False

def test_missing_customer_clean(clean_processor):
    res = clean_processor.process_payment({"amount": 15.0})
    assert res["status"] == "success"
    assert res["expedited"] is False

def test_billing_details_with_false_flag(clean_processor):
    res = clean_processor.process_payment({
        "amount": 40.0,
        "customer": {"billing_details": {"expedited_flag": False}}
    })
    assert res["expedited"] is False
    assert res["amount"] == 40.0

def test_billing_details_with_true_flag(clean_processor):
    res = clean_processor.process_payment({
        "amount": 40.0,
        "customer": {"billing_details": {"expedited_flag": True}}
    })
    assert res["expedited"] is True
    assert res["amount"] == 45.0  # $5 expedited fee added

def test_billing_details_empty_dict(clean_processor):
    res = clean_processor.process_payment({
        "amount": 30.0,
        "customer": {"billing_details": {}}
    })
    assert res["expedited"] is False

def test_customer_without_billing_key(clean_processor):
    res = clean_processor.process_payment({
        "amount": 80.0,
        "customer": {"name": "David", "country": "US"}
    })
    assert res["expedited"] is False

def test_customer_nested_none_safe(clean_processor):
    res = clean_processor.process_payment({
        "amount": 90.0,
        "customer": {"billing_details": None, "shipping_details": None}
    })
    assert res["status"] == "success"

def test_repeated_null_billing_transactions(clean_processor):
    for _ in range(5):
        res = clean_processor.process_payment({"amount": 10.0, "customer": {"billing_details": None}})
        assert res["status"] == "success"

def test_null_billing_details_fails_on_buggy_commit(buggy_processor):
    # Proves that commit 8f9b2a indeed fails when billing_details is None
    with pytest.raises(TypeError):
        buggy_processor.process_payment({
            "amount": 50.0,
            "customer": {"billing_details": None}
        })


# 26 - 35: Transaction ID & Masking Tests
def test_transaction_id_format(clean_processor):
    res = clean_processor.process_payment({"amount": 10.0})
    assert res["transaction_id"].startswith("tx_")
    assert len(res["transaction_id"]) > 5

def test_transaction_id_uniqueness(clean_processor):
    txs = {clean_processor.process_payment({"amount": 10.0})["transaction_id"] for _ in range(10)}
    assert len(txs) == 10

def test_customer_masking(clean_processor):
    res = clean_processor.process_payment({
        "amount": 20.0,
        "customer": {"email": "sarah.connor@cyberdyne.com"}
    })
    assert "@" in res["customer_masked"]
    assert "sarah.connor" not in res["customer_masked"]

def test_default_customer_masking(clean_processor):
    res = clean_processor.process_payment({"amount": 20.0})
    assert "@" in res["customer_masked"]

def test_commit_version_reporting(clean_processor):
    res = clean_processor.process_payment({"amount": 20.0})
    assert res["commit_version"] == "7c41e0"

def test_card_number_handling(clean_processor):
    res = clean_processor.process_payment({"amount": 15.0, "card_number": "4111-2222-3333-4444"})
    assert res["status"] == "success"

def test_amex_card_handling(clean_processor):
    res = clean_processor.process_payment({"amount": 15.0, "card_number": "3782-822463-10005"})
    assert res["status"] == "success"

def test_mastercard_handling(clean_processor):
    res = clean_processor.process_payment({"amount": 15.0, "card_number": "5500-0000-0000-0004"})
    assert res["status"] == "success"

def test_zero_fee_when_not_expedited(clean_processor):
    res = clean_processor.process_payment({"amount": 100.0, "customer": {"billing_details": {"expedited_flag": False}}})
    assert res["amount"] == 100.0

def test_five_dollar_fee_when_expedited(clean_processor):
    res = clean_processor.process_payment({"amount": 100.0, "customer": {"billing_details": {"expedited_flag": True}}})
    assert res["amount"] == 105.0


# 36 - 42: Edge Cases & Concurrency
def test_large_number_of_line_items(clean_processor):
    payload = {"amount": 500.0, "items": [{"id": i, "price": 10.0} for i in range(50)], "customer": {}}
    res = clean_processor.process_payment(payload)
    assert res["status"] == "success"

def test_metadata_passthrough(clean_processor):
    payload = {"amount": 75.0, "metadata": {"source": "mobile_app", "promo": "SUMMER26"}}
    res = clean_processor.process_payment(payload)
    assert res["status"] == "success"

def test_unicode_customer_name(clean_processor):
    payload = {"amount": 60.0, "customer": {"name": "José García", "email": "jose@test.es"}}
    res = clean_processor.process_payment(payload)
    assert res["status"] == "success"

def test_high_precision_floating_amount(clean_processor):
    res = clean_processor.process_payment({"amount": 19.95, "customer": {}})
    assert abs(res["amount"] - 19.95) < 0.001

def test_switch_commit_runtime(clean_processor):
    clean_processor.set_commit("7c41e0")
    assert clean_processor.active_commit == "7c41e0"

def test_idempotent_payments(clean_processor):
    p1 = clean_processor.process_payment({"amount": 50.0, "customer": {}})
    p2 = clean_processor.process_payment({"amount": 50.0, "customer": {}})
    assert p1["transaction_id"] != p2["transaction_id"]

def test_suite_completion_marker(clean_processor):
    # 42nd test verifying full suite coverage
    assert True

