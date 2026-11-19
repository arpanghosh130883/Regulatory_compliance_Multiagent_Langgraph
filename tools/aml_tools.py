"""
AML/KYC Tools — identity verification, sanctions screening, PEP checks, risk scoring.
"""

from datetime import date

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

# Simulated OFAC / UN / EU sanctions database
_SANCTIONS_DB = [
    {"name": "Viktor Petrov",      "nationality": "Russia",   "list": "OFAC SDN",   "reason": "Financial crimes"},
    {"name": "Igor Volkov",        "nationality": "Russia",   "list": "EU",         "reason": "Sanctions evasion"},
    {"name": "Hassan Al-Zarqawi",  "nationality": "Iraq",     "list": "UN",         "reason": "Terror financing"},
    {"name": "Kim Jong-nam",       "nationality": "North Korea", "list": "OFAC",    "reason": "DPRK sanctions"},
    {"name": "Ali Khamenei",       "nationality": "Iran",     "list": "OFAC",       "reason": "Iran sanctions"},
]

_HIGH_RISK_NATIONALITIES = {
    "Iran", "North Korea", "Syria", "Cuba", "Myanmar", "Belarus",
    "Russia", "Venezuela", "Somalia", "Yemen", "Libya", "Sudan",
}

_HIGH_RISK_OCCUPATIONS = {
    "casino dealer", "money services", "cryptocurrency exchange",
    "arms dealer", "precious metals dealer",
}


def _verify_identity(tool_input: dict, customer: dict) -> dict:
    id_verified = customer.get("id_verified", False)
    id_expiry = customer.get("id_expiry", "")
    id_type = customer.get("id_type", "unknown")
    name = customer.get("name", "")

    expired = False
    if id_expiry:
        try:
            exp_date = date.fromisoformat(id_expiry)
            expired = exp_date < date.today()
        except ValueError:
            pass

    issues = []
    if not id_verified:
        issues.append("Identity documents not verified")
    if expired:
        issues.append(f"ID document expired: {id_expiry}")
    if id_type == "unknown":
        issues.append("No ID type on record")

    return {
        "customer_id": customer.get("customer_id"),
        "name": name,
        "id_type": id_type,
        "id_verified": id_verified,
        "id_expired": expired,
        "issues": issues,
        "status": "PASS" if id_verified and not expired and not issues else "FAIL",
    }


def _check_sanctions_list(tool_input: dict, customer: dict) -> dict:
    name = customer.get("name", "").lower()
    matches = []

    owners = customer.get("beneficial_owners", [])
    for entry in _SANCTIONS_DB:
        if entry["name"].lower() in name:
            matches.append({**entry, "matched_entity": "customer"})

    for owner in owners:
        owner_name = owner.get("name", "").lower()
        if not owner.get("sanctions_clear", True):
            matches.append({
                "name": owner.get("name"),
                "nationality": owner.get("nationality"),
                "list": "OFAC SDN",
                "reason": "Known sanctions match",
                "matched_entity": f"beneficial_owner ({owner.get('ownership_pct')}%)",
            })
        for entry in _SANCTIONS_DB:
            if entry["name"].lower() in owner_name and owner.get("sanctions_clear", True):
                matches.append({**entry, "matched_entity": f"beneficial_owner ({owner.get('ownership_pct')}%)"})

    return {
        "customer_id": customer.get("customer_id"),
        "sanctions_matches": matches,
        "is_sanctioned": len(matches) > 0,
        "severity": "CRITICAL" if matches else "CLEAR",
        "action_required": "IMMEDIATE BLOCK" if matches else "None",
    }


def _check_pep_database(tool_input: dict, customer: dict) -> dict:
    pep_status = customer.get("pep_status", False)
    owners = customer.get("beneficial_owners", [])

    pep_findings = []
    if pep_status:
        pep_findings.append({
            "entity": customer.get("name"),
            "type": "customer",
            "pep": True,
        })

    for owner in owners:
        if owner.get("pep", False):
            pep_findings.append({
                "entity": owner.get("name"),
                "type": "beneficial_owner",
                "ownership_pct": owner.get("ownership_pct"),
                "nationality": owner.get("nationality"),
            })

    return {
        "customer_id": customer.get("customer_id"),
        "pep_findings": pep_findings,
        "is_pep": len(pep_findings) > 0,
        "enhanced_due_diligence_required": len(pep_findings) > 0,
        "note": "PEPs require enhanced due diligence (EDD) under FATF Recommendation 12",
    }


def _calculate_aml_risk_score(tool_input: dict, customer: dict) -> dict:
    score = 0
    risk_factors = []

    nationality = customer.get("nationality", "")
    if nationality in _HIGH_RISK_NATIONALITIES:
        score += 30
        risk_factors.append(f"High-risk nationality: {nationality} (+30)")

    if customer.get("pep_status", False):
        score += 25
        risk_factors.append("Customer is a PEP (+25)")

    for owner in customer.get("beneficial_owners", []):
        if owner.get("pep"):
            score += 20
            risk_factors.append(f"Beneficial owner PEP: {owner['name']} (+20)")
        if not owner.get("sanctions_clear", True):
            score += 40
            risk_factors.append(f"Beneficial owner on sanctions list: {owner['name']} (+40)")
        if owner.get("nationality") in _HIGH_RISK_NATIONALITIES:
            score += 15
            risk_factors.append(f"Beneficial owner high-risk nationality: {owner['nationality']} (+15)")

    transactions = customer.get("transactions", [])
    high_risk_countries_seen = set()
    for txn in transactions:
        country = txn.get("country", "US")
        if country in _HIGH_RISK_NATIONALITIES and country != "US":
            high_risk_countries_seen.add(country)
    if high_risk_countries_seen:
        score += 20
        risk_factors.append(f"Transactions to/from high-risk countries: {', '.join(high_risk_countries_seen)} (+20)")

    occupation = customer.get("occupation", "").lower()
    if any(occ in occupation for occ in _HIGH_RISK_OCCUPATIONS):
        score += 15
        risk_factors.append(f"High-risk occupation: {occupation} (+15)")

    if customer.get("previous_sars", 0) > 0:
        score += 20
        risk_factors.append(f"Previous SARs on file: {customer['previous_sars']} (+20)")

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
        "aml_risk_score": min(score, 100),
        "risk_band": risk_band,
        "risk_factors": risk_factors,
        "enhanced_due_diligence": score >= 40,
    }


def _get_customer_profile(tool_input: dict, customer: dict) -> dict:
    return {
        "customer_id": customer.get("customer_id"),
        "name": customer.get("name"),
        "account_type": customer.get("account_type"),
        "nationality": customer.get("nationality"),
        "occupation": customer.get("occupation"),
        "annual_income": customer.get("annual_income"),
        "account_opened": customer.get("account_opened"),
        "account_status": customer.get("account_status"),
        "previous_sars": customer.get("previous_sars", 0),
        "pep_status": customer.get("pep_status", False),
        "total_transactions": len(customer.get("transactions", [])),
    }


# ── LangGraph @tool wrappers ──────────────────────────────────────────────────
# Customer data is injected via RunnableConfig at graph invocation time.

@tool
def verify_identity(config: RunnableConfig) -> dict:
    """Verify customer identity documents and check ID validity and expiry."""
    customer = config["configurable"]["customer"]
    return _verify_identity({}, customer)


@tool
def check_sanctions_list(config: RunnableConfig) -> dict:
    """Check customer and beneficial owners against OFAC, UN, and EU sanctions lists."""
    customer = config["configurable"]["customer"]
    return _check_sanctions_list({}, customer)


@tool
def check_pep_database(config: RunnableConfig) -> dict:
    """Check if customer or beneficial owners are Politically Exposed Persons (PEPs)."""
    customer = config["configurable"]["customer"]
    return _check_pep_database({}, customer)


@tool
def calculate_aml_risk_score(config: RunnableConfig) -> dict:
    """Calculate overall AML risk score based on nationality, PEP status, and transaction history."""
    customer = config["configurable"]["customer"]
    return _calculate_aml_risk_score({}, customer)


@tool
def get_customer_profile(config: RunnableConfig) -> dict:
    """Retrieve full customer profile including identity, occupation, income, and account history."""
    customer = config["configurable"]["customer"]
    return _get_customer_profile({}, customer)


AML_TOOLS = [
    verify_identity,
    check_sanctions_list,
    check_pep_database,
    calculate_aml_risk_score,
    get_customer_profile,
]
