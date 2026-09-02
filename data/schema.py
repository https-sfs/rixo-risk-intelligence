"""Canonical transaction schema for the synthetic dataset."""

from __future__ import annotations

TRANSACTION_COLUMNS: tuple[str, ...] = (
    "transaction_id",
    "timestamp",
    "account_id",
    "device_id",
    "ip_address",
    "ip_subnet",
    "pincode",
    "sku_id",
    "amount",
    "payment_method",
    "transaction_status",
    "fraud_label",
    "event_type",
    "account_tx_count_1h",
    "device_tx_count_1h",
    "ip_subnet_tx_count_1h",
)

PAYMENT_METHODS: tuple[str, ...] = ("UPI", "card", "netbanking", "wallet")
TRANSACTION_STATUSES: tuple[str, ...] = ("success", "failed", "declined")

EVENT_LEGITIMATE = "legitimate_purchase"
EVENT_FESTIVE = "festive_purchase"
EVENT_ABUSE = "coordinated_abuse"

DEFAULT_SEED = 42
TARGET_TRANSACTION_COUNT = 10_000
