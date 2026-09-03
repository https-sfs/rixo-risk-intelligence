"""Canonical field roles for user-provided CSVs. No values are invented."""

from __future__ import annotations

from typing import Any

from evaluation.custom_data import WORLD

CANONICAL_FIELDS = (
    "transaction_id",
    "amount",
    "timestamp",
    "fraud_label",
    "merchant",
    "account_id",
    "device_id",
    "ip_address",
    "product_sku",
    "payment_status",
)

REQUIRED_USEFUL = ("transaction_id", "amount", "timestamp")
IDENTIFICATION_FIELDS = (
    "transaction_id",
    "amount",
    "timestamp",
    "product_sku",
    "fraud_label",
)

FIELD_LABELS: dict[str, str] = {
    "transaction_id": "Transaction ID",
    "amount": "Amount",
    "timestamp": "Timestamp",
    "fraud_label": "Fraud label",
    "merchant": "Merchant",
    "account_id": "Account",
    "device_id": "Device",
    "ip_address": "IP address",
    "product_sku": "Product",
    "payment_status": "Payment status",
}

FIELD_QUESTIONS: dict[str, str] = {
    "transaction_id": "Which column uniquely identifies each transaction?",
    "amount": "Which column represents the transaction amount?",
    "timestamp": "Which column represents when the transaction occurred?",
    "fraud_label": "Which column is a genuine fraud label, if one exists?",
    "merchant": "Which column identifies the merchant or seller?",
    "account_id": "Which column identifies the customer or account?",
    "device_id": "Which column identifies the device?",
    "ip_address": "Which column contains the IP address?",
    "product_sku": "Which column identifies the product?",
    "payment_status": "Which column is the payment status?",
}

IEEE_EXACT_FIELDS: dict[str, tuple[str, ...]] = {
    "transaction_id": ("TransactionID",),
    "amount": ("TransactionAmt", "TransactionAMT"),
    "timestamp": ("TransactionDT",),
    "product_sku": ("ProductCD",),
    "fraud_label": ("isFraud",),
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "transaction_id": (
        "transaction_id",
        "transactionid",
        "txn_id",
        "txnid",
        "trans_id",
        "transaction_id_hash",
    ),
    "amount": (
        "amount",
        "amt",
        "transaction_amt",
        "transactionamt",
        "amount_usd",
        "transaction_amount",
        "value",
    ),
    "timestamp": (
        "timestamp",
        "time",
        "datetime",
        "event_time",
        "created_at",
        "event_timestamp",
        "txn_time",
        "transaction_time",
        "transactiondt",
        "transaction_dt",
    ),
    "fraud_label": (
        "is_fraud",
        "isfraud",
        "fraud_label",
        "fraud",
        "label",
        "is_fraudulent",
    ),
    "merchant": (
        "merchant",
        "merchant_id",
        "merchant_name",
        "merchantid",
    ),
    "account_id": (
        "account",
        "account_id",
        "customer_id",
        "customer",
        "user_id",
        "userid",
    ),
    "device_id": (
        "device",
        "device_id",
        "deviceid",
        "deviceinfo",
    ),
    "ip_address": (
        "ip",
        "ip_address",
        "ipaddr",
        "ipaddress",
    ),
    "product_sku": (
        "sku",
        "product",
        "product_id",
        "product_sku",
        "productcd",
    ),
    "payment_status": (
        "status",
        "payment_status",
        "txn_status",
        "transaction_status",
    ),
}

IEEE_EXACT_CORE = ("TransactionAmt", "TransactionDT", "ProductCD", "card1")

OPTIONAL_HELP = {
    "merchant": "Merchant or seller identifier, if genuinely present.",
    "account_id": "Account or customer identifier, if genuinely present.",
    "device_id": "Device identifier, if genuinely present.",
    "ip_address": "IP address as supplied; treated as a proxy, not verified identity.",
    "product_sku": "Product or SKU, if genuinely present.",
    "payment_status": "Payment status, if genuinely present.",
    "fraud_label": "Fraud label, if genuinely available. Used only as user-provided ground truth.",
}


class CustomDataError(ValueError):
    """User-provided dataset contract violation."""


class CustomSessionError(CustomDataError):
    """Unknown or expired custom-data session."""


def normalize_name(name: str) -> str:
    return "".join(ch for ch in name.strip().lower() if ch.isalnum() or ch == "_")


def field_catalog() -> dict[str, Any]:
    return {
        "world": WORLD,
        "minimum_useful_fields": list(REQUIRED_USEFUL),
        "optional_fields": {key: OPTIONAL_HELP[key] for key in OPTIONAL_HELP},
        "aliases": {key: list(values) for key, values in FIELD_ALIASES.items()},
        "ieee_core_names": list(IEEE_EXACT_CORE),
        "ieee_exact_fields": {key: list(values) for key, values in IEEE_EXACT_FIELDS.items()},
        "field_labels": dict(FIELD_LABELS),
        "note": (
            "Exact schema names outrank aliases. Low-confidence guesses are never assumed. "
            "Missing IEEE-CIS features are not fabricated."
        ),
    }
