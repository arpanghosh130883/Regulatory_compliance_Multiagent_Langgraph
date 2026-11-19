"""
Transaction Monitor Tools — structuring, velocity, high-risk country exposure, pattern analysis.

CTR threshold: $10,000 (Bank Secrecy Act — deposits >= $10K must be reported)
Structuring: Breaking up large amounts into sub-$10K deposits to avoid CTR = federal crime
"""

from datetime import date, timedelta

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

CTR_THRESHOLD = 10_000
STRUCTURING_WINDOW_DAYS = 10
STRUCTURING_MIN_AMOUNT = 5_000

SANCTIONED_COUNTRIES = {"Iran", "North Korea", "Syria", "Cuba", "Myanmar"}

HIGH_RISK_COUNTRIES = SANCTIONED_COUNTRIES | {
    "Russia", "Belarus", "Venezuela", "Somalia", "Yemen",
    "Libya", "Sudan", "Iraq", "Afghanistan", "Pakistan",
    "UAE",
}

RAPID_MOVEMENT_HOURS = 24


def _parse_date(d: str) -> date:
    try:
        return date.fromisoformat(d)
    except Exception:
        return date.today()


def _get_recent_transactions(tool_input: dict, customer: dict) -> dict:
    days = tool_input.get("days", 30)
    transactions = customer.get("transactions", [])
    cutoff = date.today() - timedelta(days=days)

    recent = [t for t in transactions if _parse_date(t.get("date", "2000-01-01")) >= cutoff]

    total_in = sum(t["amount"] for t in recent if t["type"] in ("deposit", "wire_in"))
    total_out = sum(t["amount"] for t in recent if t["type"] in ("withdrawal", "wire_out", "payment"))
    countries = list({t.get("country", "US") for t in recent if t.get("country") and t.get("country") != "US"})

    return {
        "customer_id": customer.get("customer_id"),
        "period_days": days,
        "total_transactions": len(recent),
        "total_inflow": total_in,
        "total_outflow": total_out,
        "net_flow": total_in - total_out,
        "foreign_countries_involved": countries,
        "transactions": recent,
    }


def _detect_structuring(tool_input: dict, customer: dict) -> dict:
    transactions = customer.get("transactions", [])
    cash_deposits = [
        t for t in transactions
        if t.get("type") == "deposit"
        and t.get("counterparty", "").lower() in ("cash", "cash deposit")
        and STRUCTURING_MIN_AMOUNT <= t.get("amount", 0) < CTR_THRESHOLD
    ]

    structuring_clusters = []
    checked = set()

    for i, txn in enumerate(cash_deposits):
        if i in checked:
            continue
        cluster = [txn]
        d1 = _parse_date(txn.get("date", "2000-01-01"))
        for j, other in enumerate(cash_deposits):
            if j == i or j in checked:
                continue
            d2 = _parse_date(other.get("date", "2000-01-01"))
            if abs((d2 - d1).days) <= STRUCTURING_WINDOW_DAYS:
                cluster.append(other)
                checked.add(j)
        if len(cluster) >= 2:
            total = sum(c["amount"] for c in cluster)
            structuring_clusters.append({
                "transactions": cluster,
                "total_amount": total,
                "count": len(cluster),
                "window_days": STRUCTURING_WINDOW_DAYS,
                "note": f"{len(cluster)} cash deposits totalling ${total:,} within {STRUCTURING_WINDOW_DAYS} days — all below $10,000 CTR threshold",
            })
        checked.add(i)

    daily_groups: dict[str, list] = {}
    for t in transactions:
        d = t.get("date", "")
        daily_groups.setdefault(d, []).append(t)

    same_day_round_trips = []
    for d, txns in daily_groups.items():
        deposits = [t for t in txns if t.get("type") == "deposit"]
        withdrawals = [t for t in txns if t.get("type") in ("withdrawal", "wire_out")]
        if deposits and withdrawals:
            dep_total = sum(t["amount"] for t in deposits)
            with_total = sum(t["amount"] for t in withdrawals)
            if dep_total >= 10_000 and abs(dep_total - with_total) / dep_total < 0.1:
                same_day_round_trips.append({
                    "date": d,
                    "inflow": dep_total,
                    "outflow": with_total,
                    "note": "Same-day deposit and near-identical withdrawal (possible layering)",
                })

    return {
        "customer_id": customer.get("customer_id"),
        "structuring_detected": len(structuring_clusters) > 0,
        "structuring_clusters": structuring_clusters,
        "same_day_round_trips": same_day_round_trips,
        "severity": "HIGH" if structuring_clusters else "LOW",
        "ctr_threshold": CTR_THRESHOLD,
        "recommendation": "File SAR for structuring" if structuring_clusters else "No structuring detected",
    }


def _check_high_risk_country_exposure(tool_input: dict, customer: dict) -> dict:
    transactions = customer.get("transactions", [])
    sanctions_violations = []
    high_risk_exposure = []

    for t in transactions:
        country = t.get("country", "US")
        if country in SANCTIONED_COUNTRIES:
            sanctions_violations.append({
                "txn_id": t.get("id"),
                "date": t.get("date"),
                "type": t.get("type"),
                "amount": t.get("amount"),
                "country": country,
                "counterparty": t.get("counterparty"),
                "severity": "CRITICAL — OFAC SANCTIONS VIOLATION",
            })
        elif country in HIGH_RISK_COUNTRIES and country != "US":
            high_risk_exposure.append({
                "txn_id": t.get("id"),
                "date": t.get("date"),
                "type": t.get("type"),
                "amount": t.get("amount"),
                "country": country,
                "counterparty": t.get("counterparty"),
                "severity": "HIGH — Enhanced monitoring required",
            })

    return {
        "customer_id": customer.get("customer_id"),
        "sanctions_violations": sanctions_violations,
        "high_risk_country_transactions": high_risk_exposure,
        "total_sanctions_exposure": sum(v["amount"] for v in sanctions_violations),
        "total_high_risk_exposure": sum(h["amount"] for h in high_risk_exposure),
        "severity": "CRITICAL" if sanctions_violations else "HIGH" if high_risk_exposure else "LOW",
        "action_required": "IMMEDIATE BLOCK + FILE SAR" if sanctions_violations else "Escalate for review" if high_risk_exposure else "None",
    }


def _analyze_transaction_velocity(tool_input: dict, customer: dict) -> dict:
    transactions = sorted(
        customer.get("transactions", []),
        key=lambda t: t.get("date", ""),
    )

    velocity_flags = []
    total_volume = sum(t.get("amount", 0) for t in transactions)

    for i, dep in enumerate(transactions):
        if dep.get("type") not in ("deposit", "wire_in"):
            continue
        dep_date = dep.get("date", "")
        dep_amount = dep.get("amount", 0)

        same_day_out = [
            t for t in transactions
            if t.get("type") in ("wire_out", "withdrawal", "payment")
            and t.get("date", "") <= dep_date
        ]

        next_day_out = [
            t for t in transactions[i + 1:]
            if t.get("type") in ("wire_out", "withdrawal")
            and abs((_parse_date(t.get("date", dep_date)) - _parse_date(dep_date)).days) <= 1
        ]

        combined_out = same_day_out + next_day_out
        out_total = sum(t.get("amount", 0) for t in combined_out)

        if combined_out and out_total >= dep_amount * 0.5 and dep_amount >= 50_000:
            velocity_flags.append({
                "pattern": "RAPID_DISPERSAL",
                "deposit": {"id": dep.get("id"), "amount": dep_amount, "date": dep_date},
                "outflows": [{"id": t.get("id"), "amount": t.get("amount"), "country": t.get("country")} for t in combined_out],
                "out_total": out_total,
                "note": f"${dep_amount:,} received then ${out_total:,} dispersed within 24-48 hours",
            })

    daily_groups: dict[str, list] = {}
    for t in transactions:
        daily_groups.setdefault(t.get("date", ""), []).append(t)

    for d, txns in daily_groups.items():
        outflows = [t for t in txns if t.get("type") in ("wire_out", "withdrawal")]
        if len(outflows) >= 3:
            destinations = {t.get("country", "US") for t in outflows}
            if len(destinations) >= 2:
                velocity_flags.append({
                    "pattern": "FAN_OUT",
                    "date": d,
                    "outflow_count": len(outflows),
                    "destination_countries": list(destinations),
                    "total_out": sum(t["amount"] for t in outflows),
                    "note": f"{len(outflows)} outgoing transfers to {len(destinations)} countries on a single day",
                })

    return {
        "customer_id": customer.get("customer_id"),
        "total_transaction_volume": total_volume,
        "velocity_flags": velocity_flags,
        "rapid_movement_detected": len(velocity_flags) > 0,
        "severity": "HIGH" if velocity_flags else "LOW",
    }


def _calculate_transaction_risk_score(tool_input: dict, customer: dict) -> dict:
    score = 0
    factors = []
    transactions = customer.get("transactions", [])

    sanctions_txns = [t for t in transactions if t.get("country") in SANCTIONED_COUNTRIES]
    if sanctions_txns:
        score += 50
        factors.append(f"Transactions with sanctioned countries: {len(sanctions_txns)} (+50)")

    hr_txns = [t for t in transactions if t.get("country") in HIGH_RISK_COUNTRIES and t.get("country") != "US"]
    if hr_txns:
        score += 20
        factors.append(f"High-risk country transactions: {len(hr_txns)} (+20)")

    large_cash = [t for t in transactions if t.get("type") == "deposit" and t.get("counterparty", "").lower() == "cash" and t.get("amount", 0) >= 10_000]
    if large_cash:
        score += 15
        factors.append(f"Large cash deposits >= $10,000: {len(large_cash)} (+15)")

    sub_threshold_cash = [t for t in transactions if t.get("type") == "deposit" and t.get("counterparty", "").lower() == "cash" and 5_000 <= t.get("amount", 0) < 10_000]
    if len(sub_threshold_cash) >= 2:
        score += 25
        factors.append(f"Multiple sub-CTR-threshold cash deposits: {len(sub_threshold_cash)} (+25)")

    daily_out: dict[str, int] = {}
    for t in transactions:
        if t.get("type") in ("wire_out", "withdrawal"):
            daily_out[t.get("date", "")] = daily_out.get(t.get("date", ""), 0) + 1
    if any(v >= 3 for v in daily_out.values()):
        score += 20
        factors.append("Multiple same-day outgoing transfers (fan-out pattern) (+20)")

    total_volume = sum(t.get("amount", 0) for t in transactions)
    annual_income = customer.get("annual_income", 0)
    if annual_income and total_volume > annual_income * 2:
        score += 15
        factors.append(f"Transaction volume (${total_volume:,}) exceeds 2× annual income (${annual_income:,}) (+15)")

    if score >= 60:
        risk_band = "CRITICAL"
    elif score >= 40:
        risk_band = "HIGH"
    elif score >= 20:
        risk_band = "MEDIUM"
    else:
        risk_band = "LOW"

    return {
        "customer_id": customer.get("customer_id"),
        "transaction_risk_score": min(score, 100),
        "risk_band": risk_band,
        "risk_factors": factors,
        "total_transaction_volume": total_volume,
    }


# ── LangGraph @tool wrappers ──────────────────────────────────────────────────

@tool
def get_recent_transactions(config: RunnableConfig, days: int = 60) -> dict:
    """Retrieve recent transactions with summary statistics (inflow, outflow, countries involved).

    Args:
        days: Number of days of transaction history to retrieve (default: 60)
    """
    customer = config["configurable"]["customer"]
    return _get_recent_transactions({"days": days}, customer)


@tool
def detect_structuring(config: RunnableConfig) -> dict:
    """Detect structuring — multiple sub-$10,000 cash deposits within a short window to avoid Currency Transaction Reports."""
    customer = config["configurable"]["customer"]
    return _detect_structuring({}, customer)


@tool
def check_high_risk_country_exposure(config: RunnableConfig) -> dict:
    """Identify transactions to or from sanctioned countries (OFAC) or high-risk jurisdictions."""
    customer = config["configurable"]["customer"]
    return _check_high_risk_country_exposure({}, customer)


@tool
def analyze_transaction_velocity(config: RunnableConfig) -> dict:
    """Detect rapid fund movement: large inflow immediately followed by dispersal to multiple accounts or countries."""
    customer = config["configurable"]["customer"]
    return _analyze_transaction_velocity({}, customer)


@tool
def calculate_transaction_risk_score(config: RunnableConfig) -> dict:
    """Calculate composite transaction risk score from all detected patterns."""
    customer = config["configurable"]["customer"]
    return _calculate_transaction_risk_score({}, customer)


TRANSACTION_TOOLS = [
    get_recent_transactions,
    detect_structuring,
    check_high_risk_country_exposure,
    analyze_transaction_velocity,
    calculate_transaction_risk_score,
]
