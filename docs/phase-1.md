# Phase 1 — Synthetic data and deterministic detection

Phase 1 builds the foundation for DETECT. It does not investigate, decide, act, or verify.

## Synthetic data model

Each row in `data/transactions.csv` is a checkout-like event with:

- identity and infrastructure: `account_id`, `device_id`, `ip_address`, `ip_subnet`, `pincode`
- commerce: `sku_id`, `amount`, `payment_method`, `transaction_status`
- labels: `fraud_label`, `event_type`
- velocity: `account_tx_count_1h`, `device_tx_count_1h`, `ip_subnet_tx_count_1h`

`event_type` is synthetic scenario metadata. The detector does not read it.

`fraud_label` is delayed-style ground truth for evaluation. The detector reports window `fraud_rate` for transparency but does not treat a label as a block decision.

## Scenario design

The generator uses a fixed seed and produces about 10,000 rows over a multi-week horizon.

**Baseline.** Normal hourly seasonality, many cities, many SKUs, mostly 1:1 account-device relationships, low isolated fraud.

**Legitimate festive spike.** A named sale window with a large volume lift, broader shopping, and healthy success rates. Accounts, devices, IPs, pincodes, and SKUs remain diverse. This exists so the product can learn “busy” ≠ “attack.”

**Coordinated abuse.** Two injected clusters with different tactics (shared-device promo abuse and concentrated card-testing). Both reuse a small device/IP/pincode/SKU set across many accounts, with elevated failures and discoverable graph structure. Transactions inside a cluster still vary in amount, status, and reuse intensity.

## Detection methodology

1. Aggregate transactions into clock-hour windows.
2. Measure volume, failure rate, diversity, SKU concentration, and velocity.
3. Estimate a **same-hour-of-day** volume baseline so a multi-day sale is compared to typical evenings, not to the previous festive hour.
4. Estimate rolling baselines for failure and concentration features.
5. Compute z-scores and a transparent **coordination score** that ignores volume.
6. Classify:
   - `legitimate_festive_spike` — volume well above the hour-of-day baseline, diversity preserved, coordination low
   - `suspicious_coordinated_spike` — coordination/concentration/failure elevated
   - ordinary traffic is not emitted as a spike

This is a statistical rule layer. No precision, recall, or F1 is claimed until the evaluation layer runs held-out tests.

## Why festive spikes are treated differently

A sale increases count. Coordinated abuse increases **shared structure**: few devices and subnets serving many accounts, narrow SKU and pincode mass, abnormal velocity, and weaker authorization outcomes. Volume is a reason to look; coordination is the reason to treat a window as suspicious.

## Handoff to Phase 2

The Investigation Agent should receive:

- a `SpikeRecord` (`spike_id`, window, `spike_type`, severity, rates, diversity, `top_skus`, `anomaly_reasons`)
- access to the underlying transactions in that window through tools

Phase 2 should investigate *why* a suspicious window is coordinated (or confirm a festive window is benign). It should not re-assign an unrestricted block decision.
