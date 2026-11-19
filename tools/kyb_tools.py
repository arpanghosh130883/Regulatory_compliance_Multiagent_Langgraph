"""
KYB Tools — Know Your Business verification, beneficial ownership, shell company detection.
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

_OFFSHORE_JURISDICTIONS = {
    "British Virgin Islands", "Cayman Islands", "Seychelles", "Panama",
    "Belize", "Marshall Islands", "Vanuatu", "Isle of Man", "Jersey",
    "Guernsey", "Liechtenstein", "Monaco",
}

_HIGH_RISK_INDUSTRIES = {
    "cannabis", "gambling", "adult entertainment", "cryptocurrency exchange",
    "arms", "weapons", "precious metals", "pawn", "money services",
    "payday loan", "hawala",
}

_VALID_BUSINESS_TYPES = {"LLC", "Corporation", "LLP", "Partnership", "Sole Proprietorship", "Co-operative"}


def _verify_business_registration(tool_input: dict, customer: dict) -> dict:
    if customer.get("account_type") != "business":
        return {"status": "N/A", "note": "KYB not applicable for personal accounts"}

    reg_number = customer.get("registration_number", "")
    reg_state = customer.get("registration_state", "")
    reg_date = customer.get("registration_date", "")
    business_type = customer.get("business_type", "")
    ein = customer.get("ein", "")

    issues = []
    if not reg_number:
        issues.append("Missing registration number")
    if not reg_state:
        issues.append("Missing registration state/jurisdiction")
    if business_type not in _VALID_BUSINESS_TYPES:
        issues.append(f"Unrecognised business type: {business_type}")
    if not ein:
        issues.append("Missing EIN (Tax ID)")
    if reg_state in _OFFSHORE_JURISDICTIONS:
        issues.append(f"Offshore registration jurisdiction: {reg_state} — elevated scrutiny required")

    return {
        "customer_id": customer.get("customer_id"),
        "business_name": customer.get("name"),
        "registration_number": reg_number,
        "registration_state": reg_state,
        "registration_date": reg_date,
        "business_type": business_type,
        "ein": ein,
        "is_offshore": reg_state in _OFFSHORE_JURISDICTIONS,
        "issues": issues,
        "status": "PASS" if not issues else "REVIEW_REQUIRED",
    }


def _check_beneficial_owners(tool_input: dict, customer: dict) -> dict:
    if customer.get("account_type") != "business":
        return {"status": "N/A", "note": "KYB not applicable for personal accounts"}

    owners = customer.get("beneficial_owners", [])
    high_risk_owners = []
    total_ownership = sum(o.get("ownership_pct", 0) for o in owners)

    for owner in owners:
        flags = []
        if owner.get("pep"):
            flags.append("POLITICALLY EXPOSED PERSON")
        if not owner.get("sanctions_clear", True):
            flags.append("SANCTIONS LIST MATCH")
        if owner.get("nationality") in {"Iran", "North Korea", "Syria", "Russia", "Cuba", "Myanmar"}:
            flags.append(f"High-risk nationality: {owner['nationality']}")
        if owner.get("name", "").endswith("Ltd") or owner.get("name", "").endswith("Holdings"):
            flags.append("Corporate beneficial owner — requires further UBO drill-down")
        if flags:
            high_risk_owners.append({**owner, "flags": flags})

    return {
        "customer_id": customer.get("customer_id"),
        "total_beneficial_owners": len(owners),
        "total_ownership_accounted": f"{total_ownership}%",
        "ownership_gap": f"{max(0, 100 - total_ownership)}% unaccounted",
        "high_risk_owners": high_risk_owners,
        "ubo_risk": "HIGH" if high_risk_owners else "LOW",
        "all_owners": owners,
    }


def _assess_shell_company_risk(tool_input: dict, customer: dict) -> dict:
    if customer.get("account_type") != "business":
        return {"status": "N/A", "note": "KYB not applicable for personal accounts"}

    indicators = []
    score = 0

    reg_state = customer.get("registration_state", "")
    if reg_state in _OFFSHORE_JURISDICTIONS:
        indicators.append(f"Offshore registration: {reg_state}")
        score += 30

    employees = customer.get("employees", 0)
    revenue = customer.get("annual_revenue", 0)
    if employees <= 5 and revenue > 1_000_000:
        indicators.append(f"Disproportionate revenue vs staff: ${revenue:,} revenue, {employees} employees")
        score += 25

    address = customer.get("address", "")
    if "po box" in address.lower() or "p.o. box" in address.lower():
        indicators.append("PO Box address — no physical presence verified")
        score += 20

    owners = customer.get("beneficial_owners", [])
    for owner in owners:
        if owner.get("nationality") in _OFFSHORE_JURISDICTIONS or \
           owner.get("name", "").endswith("Holdings") or \
           owner.get("name", "").endswith("Ltd"):
            indicators.append(f"Corporate UBO creating opacity: {owner['name']}")
            score += 15

    txn_total = sum(t.get("amount", 0) for t in customer.get("transactions", []))
    reg_date = customer.get("registration_date", "2000-01-01")
    if reg_date > "2021-01-01" and txn_total > 500_000:
        indicators.append(f"Recently formed company (${txn_total:,.0f} total transactions)")
        score += 10

    if score >= 60:
        risk = "CRITICAL"
    elif score >= 35:
        risk = "HIGH"
    elif score >= 15:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "customer_id": customer.get("customer_id"),
        "shell_company_risk": risk,
        "shell_company_score": score,
        "indicators": indicators,
        "recommendation": "BLOCK and investigate" if score >= 60 else "Enhanced due diligence" if score >= 35 else "Standard monitoring",
    }


def _check_industry_risk(tool_input: dict, customer: dict) -> dict:
    if customer.get("account_type") != "business":
        return {"status": "N/A", "note": "KYB not applicable for personal accounts"}

    industry = customer.get("industry", "").lower()
    naics = customer.get("naics_code", "")
    is_high_risk = any(hr in industry for hr in _HIGH_RISK_INDUSTRIES)

    return {
        "customer_id": customer.get("customer_id"),
        "industry": customer.get("industry"),
        "naics_code": naics,
        "is_high_risk_industry": is_high_risk,
        "risk_level": "HIGH" if is_high_risk else "STANDARD",
        "enhanced_monitoring_required": is_high_risk,
        "note": "High-risk industries require enhanced transaction monitoring and periodic reviews" if is_high_risk else "Standard industry risk profile",
    }


# ── LangGraph @tool wrappers ──────────────────────────────────────────────────

@tool
def verify_business_registration(config: RunnableConfig) -> dict:
    """Verify business registration number, jurisdiction, EIN, and legal structure."""
    customer = config["configurable"]["customer"]
    return _verify_business_registration({}, customer)


@tool
def check_beneficial_owners(config: RunnableConfig) -> dict:
    """Retrieve and assess all beneficial owners (UBOs) for PEP status, sanctions, and nationality risk."""
    customer = config["configurable"]["customer"]
    return _check_beneficial_owners({}, customer)


@tool
def assess_shell_company_risk(config: RunnableConfig) -> dict:
    """Assess shell company indicators: offshore registration, opaque ownership, PO Box, disproportionate revenue."""
    customer = config["configurable"]["customer"]
    return _assess_shell_company_risk({}, customer)


@tool
def check_industry_risk(config: RunnableConfig) -> dict:
    """Check if the business operates in a high-risk industry (gambling, arms, crypto exchanges, etc.)."""
    customer = config["configurable"]["customer"]
    return _check_industry_risk({}, customer)


KYB_TOOLS = [
    verify_business_registration,
    check_beneficial_owners,
    assess_shell_company_risk,
    check_industry_risk,
]
