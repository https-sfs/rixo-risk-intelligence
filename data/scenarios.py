"""Ground-truth scenario windows for synthetic generation and tests.

These constants describe how the dataset is constructed. The detection
layer must not read them; it classifies windows from operational features.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DATASET_START = datetime(2026, 1, 5, 0, 0, 0)
DATASET_END = datetime(2026, 1, 26, 0, 0, 0)

FESTIVE_START = datetime(2026, 1, 14, 0, 0, 0)
FESTIVE_END = datetime(2026, 1, 17, 0, 0, 0)
FESTIVE_NAME = "Winter Festival Sale"


@dataclass(frozen=True)
class AttackSpec:
    name: str
    start: datetime
    end: datetime
    n_accounts: int
    n_devices: int
    ip_prefixes: tuple[str, ...]
    pincodes: tuple[str, ...]
    sku_ids: tuple[str, ...]
    sku_weights: tuple[float, ...]
    hourly_extra_lambda: float
    amount_low: float
    amount_high: float
    small_amount_share: float
    success_rate: float
    failed_rate: float
    isolated_fraud_rate: float


ATTACK_DEVICE_FARM = AttackSpec(
    name="shared_device_promo_abuse",
    start=datetime(2026, 1, 8, 13, 0, 0),
    end=datetime(2026, 1, 8, 16, 0, 0),
    n_accounts=110,
    n_devices=5,
    ip_prefixes=("185.220.101", "185.220.102"),
    pincodes=("411001", "411014"),
    sku_ids=("sku_1048", "sku_1049"),
    sku_weights=(0.68, 0.32),
    hourly_extra_lambda=62.0,
    amount_low=2499.0,
    amount_high=8999.0,
    small_amount_share=0.05,
    success_rate=0.42,
    failed_rate=0.28,
    isolated_fraud_rate=0.86,
)

ATTACK_CARD_TESTING = AttackSpec(
    name="concentrated_card_testing",
    start=datetime(2026, 1, 18, 2, 0, 0),
    end=datetime(2026, 1, 18, 5, 0, 0),
    n_accounts=78,
    n_devices=8,
    ip_prefixes=("45.33.32",),
    pincodes=("110001", "110008"),
    sku_ids=("sku_1050",),
    sku_weights=(1.0,),
    hourly_extra_lambda=64.0,
    amount_low=29.0,
    amount_high=4999.0,
    small_amount_share=0.78,
    success_rate=0.18,
    failed_rate=0.14,
    isolated_fraud_rate=0.9,
)

ATTACKS: tuple[AttackSpec, ...] = (ATTACK_DEVICE_FARM, ATTACK_CARD_TESTING)

BASELINE_ISOLATED_FRAUD_RATE = 0.012
FESTIVE_VOLUME_MULTIPLIER = 2.75
WEEKEND_VOLUME_MULTIPLIER = 1.18
N_LEGIT_ACCOUNTS = 900
N_SKUS = 50
