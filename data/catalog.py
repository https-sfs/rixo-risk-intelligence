"""Entity pools used to generate realistic behavioural relationships."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from data.scenarios import N_LEGIT_ACCOUNTS, N_SKUS

CITIES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "Mumbai",
        ("400001", "400050", "400070", "400092", "400102"),
        ("103.50.10", "103.50.11", "49.36.20"),
    ),
    (
        "Delhi",
        ("110001", "110016", "110024", "110048", "110085"),
        ("122.160.1", "122.160.2", "157.48.10"),
    ),
    (
        "Bengaluru",
        ("560001", "560034", "560066", "560076", "560102"),
        ("49.207.1", "49.207.2", "103.86.30"),
    ),
    (
        "Hyderabad",
        ("500001", "500032", "500081", "500084"),
        ("49.205.1", "103.210.20"),
    ),
    (
        "Chennai",
        ("600001", "600017", "600042", "600096"),
        ("117.192.1", "117.192.2"),
    ),
    (
        "Kolkata",
        ("700001", "700019", "700032", "700091"),
        ("203.197.1", "203.197.2"),
    ),
    (
        "Pune",
        ("411001", "411014", "411038", "411057"),
        ("103.88.1", "103.88.2"),
    ),
    (
        "Ahmedabad",
        ("380001", "380015", "380054"),
        ("103.240.1", "49.34.10"),
    ),
    ("Jaipur", ("302001", "302017", "302033"), ("103.12.1",)),
    ("Kochi", ("682001", "682016", "682030"), ("117.216.1",)),
    ("Lucknow", ("226001", "226010", "226021"), ("103.93.1",)),
    ("Chandigarh", ("160001", "160017", "160036"), ("14.139.1",)),
)

SKU_CATEGORIES: tuple[tuple[str, float, float], ...] = (
    ("grocery", 0.28, 420.0),
    ("apparel", 0.22, 1450.0),
    ("electronics", 0.16, 6200.0),
    ("beauty", 0.14, 890.0),
    ("home", 0.12, 2100.0),
    ("digital", 0.08, 499.0),
)


@dataclass(frozen=True)
class Sku:
    sku_id: str
    category: str
    typical_amount: float


@dataclass
class Catalog:
    accounts: list[str]
    account_weights: np.ndarray
    account_devices: dict[str, list[str]]
    account_pincode: dict[str, str]
    account_ip_prefixes: dict[str, tuple[str, ...]]
    skus: list[Sku]
    sku_weights: np.ndarray
    all_pincodes: list[str]
    all_ip_prefixes: list[str]


def _expand_categories(n_skus: int) -> list[tuple[str, float]]:
    categories: list[tuple[str, float]] = []
    remaining = n_skus
    for index, (category, share, typical) in enumerate(SKU_CATEGORIES):
        count = (
            remaining
            if index == len(SKU_CATEGORIES) - 1
            else max(1, round(n_skus * share))
        )
        count = min(count, remaining)
        categories.extend((category, typical) for _ in range(count))
        remaining -= count
    return categories


def build_catalog(rng: np.random.Generator, n_accounts: int = N_LEGIT_ACCOUNTS) -> Catalog:
    skus: list[Sku] = []
    sku_weights: list[float] = []
    for index, (category, typical) in enumerate(_expand_categories(N_SKUS), start=1):
        jitter = float(rng.uniform(0.7, 1.35))
        skus.append(
            Sku(
                sku_id=f"sku_{1000 + index}",
                category=category,
                typical_amount=round(typical * jitter, 2),
            )
        )
        sku_weights.append(1.0 / (index**0.7))

    city_sizes = np.array([len(city[1]) for city in CITIES], dtype=float)
    city_p = city_sizes / city_sizes.sum()

    accounts: list[str] = []
    account_devices: dict[str, list[str]] = {}
    account_pincode: dict[str, str] = {}
    account_ip_prefixes: dict[str, tuple[str, ...]] = {}
    device_seq = 1

    for account_index in range(1, n_accounts + 1):
        account_id = f"acc_{account_index:04d}"
        city = CITIES[int(rng.choice(len(CITIES), p=city_p))]
        _, pincodes, prefixes = city
        n_devices = 2 if rng.random() < 0.18 else 1
        devices = []
        for _ in range(n_devices):
            devices.append(f"dev_{device_seq:04d}")
            device_seq += 1
        accounts.append(account_id)
        account_devices[account_id] = devices
        account_pincode[account_id] = str(rng.choice(pincodes))
        account_ip_prefixes[account_id] = prefixes

    # Occasional household device sharing between two nearby accounts.
    for _ in range(max(8, n_accounts // 80)):
        left, right = rng.choice(np.array(accounts), size=2, replace=False)
        if account_pincode[left][:2] == account_pincode[right][:2]:
            shared = account_devices[left][0]
            if shared not in account_devices[right]:
                account_devices[right].append(shared)

    weights = rng.gamma(shape=1.15, scale=1.0, size=n_accounts)
    weights = weights / weights.sum()

    all_pincodes = [pin for _, pins, _ in CITIES for pin in pins]
    all_ip_prefixes = [prefix for _, _, prefixes in CITIES for prefix in prefixes]

    return Catalog(
        accounts=accounts,
        account_weights=weights,
        account_devices=account_devices,
        account_pincode=account_pincode,
        account_ip_prefixes=account_ip_prefixes,
        skus=skus,
        sku_weights=np.array(sku_weights) / np.sum(sku_weights),
        all_pincodes=all_pincodes,
        all_ip_prefixes=all_ip_prefixes,
    )


def subnet_from_prefix(prefix: str) -> str:
    return f"{prefix}.0/24"


def random_ip(rng: np.random.Generator, prefix: str) -> str:
    return f"{prefix}.{int(rng.integers(1, 255))}"
