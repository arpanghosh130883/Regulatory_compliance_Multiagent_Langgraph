"""
Privacy Tools — GDPR/CCPA compliance, consent management, data access auditing.
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

_GDPR_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "GB",  # UK GDPR post-Brexit
    "NO", "IS", "LI",  # EEA non-EU
}

_CCPA_STATES = {"CA"}

_CONSENT_CATEGORIES = {
    "marketing": "Direct marketing communications",
    "analytics": "Behavioural analytics and profiling",
    "third_party_sharing": "Sharing data with third parties",
    "credit_check": "Credit bureau access",
    "fraud_detection": "Fraud detection processing",
}

_LEGITIMATE_PURPOSES_NO_CONSENT = {
    "credit_check",
    "aml_screening",
    "fraud_detection",
}


def _check_data_consents(tool_input: dict, customer: dict) -> dict:
    consents = customer.get("data_consents", {})
    consent_date = consents.get("consent_date", "unknown")

    active_consents = []
    withheld_consents = []

    for category, description in _CONSENT_CATEGORIES.items():
        if category in consents:
            if consents[category]:
                active_consents.append({"category": category, "description": description})
            else:
                withheld_consents.append({"category": category, "description": description})

    return {
        "customer_id": customer.get("customer_id"),
        "consent_date": consent_date,
        "active_consents": active_consents,
        "withheld_consents": withheld_consents,
        "total_consents_given": len(active_consents),
        "total_consents_withheld": len(withheld_consents),
        "note": "Consents must be freely given, specific, informed, and unambiguous (GDPR Art. 7)",
    }


def _audit_data_access_log(tool_input: dict, customer: dict) -> dict:
    access_log = customer.get("data_access_log", [])
    consents = customer.get("data_consents", {})

    violations = []
    consented_access = []

    for entry in access_log:
        purpose = entry.get("purpose", "")
        consented_flag = entry.get("consented", False)

        if purpose in _LEGITIMATE_PURPOSES_NO_CONSENT:
            consented_access.append({**entry, "legal_basis": "Legitimate interest / legal obligation"})
            continue

        consent_on_file = consents.get(purpose, False)

        if not consented_flag or not consent_on_file:
            violations.append({
                **entry,
                "violation_type": "UNCONSENTED_DATA_ACCESS",
                "gdpr_article": "Art. 6 — Lawfulness of processing",
                "severity": "HIGH",
                "note": f"Data accessed for '{purpose}' without valid consent on file",
            })
        else:
            consented_access.append({**entry, "legal_basis": "Explicit consent"})

    return {
        "customer_id": customer.get("customer_id"),
        "total_access_events": len(access_log),
        "consented_accesses": len(consented_access),
        "violations": violations,
        "violation_count": len(violations),
        "severity": "HIGH" if violations else "CLEAR",
    }


def _check_gdpr_obligations(tool_input: dict, customer: dict) -> dict:
    nationality = customer.get("nationality", "US")
    address = customer.get("address", "")

    applicable_regs = []

    eu_indicators = any(country in address for country in ["Germany", "France", "UK", "Italy", "Spain", "Netherlands"])
    if eu_indicators or nationality in _GDPR_COUNTRIES:
        applicable_regs.append({
            "regulation": "GDPR",
            "jurisdiction": "EU/EEA",
            "key_rights": ["Right to access", "Right to erasure", "Right to portability", "Right to object"],
            "max_fine": "€20M or 4% of global annual turnover",
        })

    if "CA" in address or nationality == "CA":
        applicable_regs.append({
            "regulation": "CCPA",
            "jurisdiction": "California, USA",
            "key_rights": ["Right to know", "Right to delete", "Right to opt-out of sale"],
            "max_fine": "$7,500 per intentional violation",
        })

    applicable_regs.append({
        "regulation": "GLBA (Gramm-Leach-Bliley Act)",
        "jurisdiction": "USA",
        "key_rights": ["Privacy notice", "Opt-out of non-affiliated sharing"],
        "max_fine": "$100K per violation",
    })

    return {
        "customer_id": customer.get("customer_id"),
        "nationality": nationality,
        "applicable_regulations": applicable_regs,
        "data_retention_obligation": "Minimum 5 years for AML records (BSA requirement)",
        "breach_notification_window": "72 hours (GDPR) / without unreasonable delay (GLBA)",
    }


def _identify_privacy_violations(tool_input: dict, customer: dict) -> dict:
    access_log = customer.get("data_access_log", [])
    consents = customer.get("data_consents", {})

    violations = []

    for entry in access_log:
        purpose = entry.get("purpose", "")
        if purpose in _LEGITIMATE_PURPOSES_NO_CONSENT:
            continue

        consent_on_file = consents.get(purpose, False)
        consented_flag = entry.get("consented", False)

        if not consent_on_file or not consented_flag:
            violations.append({
                "event_date": entry.get("date"),
                "accessed_by": entry.get("accessed_by"),
                "purpose": purpose,
                "violation": "Processing without lawful basis",
                "gdpr_article": "Art. 6",
                "remediation": f"Obtain explicit consent for '{purpose}' OR document alternative legal basis",
                "severity": "HIGH",
            })

    if not consents.get("consent_date"):
        violations.append({
            "violation": "No consent timestamp recorded",
            "gdpr_article": "Art. 7(1) — Demonstrating consent",
            "remediation": "Record the date and method of consent collection",
            "severity": "MEDIUM",
        })

    return {
        "customer_id": customer.get("customer_id"),
        "total_violations": len(violations),
        "violations": violations,
        "regulatory_exposure": "HIGH" if any(v["severity"] == "HIGH" for v in violations) else "MEDIUM" if violations else "CLEAR",
        "action_required": "Remediate processing without consent and notify DPO" if violations else "None",
    }


# ── LangGraph @tool wrappers ──────────────────────────────────────────────────

@tool
def check_data_consents(config: RunnableConfig) -> dict:
    """Retrieve all data processing consents on file for the customer."""
    customer = config["configurable"]["customer"]
    return _check_data_consents({}, customer)


@tool
def audit_data_access_log(config: RunnableConfig) -> dict:
    """Audit all data access events and flag those without valid consent or legal basis."""
    customer = config["configurable"]["customer"]
    return _audit_data_access_log({}, customer)


@tool
def check_gdpr_obligations(config: RunnableConfig) -> dict:
    """Determine applicable privacy regulations (GDPR, CCPA, GLBA) based on customer nationality and location."""
    customer = config["configurable"]["customer"]
    return _check_gdpr_obligations({}, customer)


@tool
def identify_privacy_violations(config: RunnableConfig) -> dict:
    """Identify all privacy violations including unconsented data access and missing consent records."""
    customer = config["configurable"]["customer"]
    return _identify_privacy_violations({}, customer)


PRIVACY_TOOLS = [
    check_data_consents,
    audit_data_access_log,
    check_gdpr_obligations,
    identify_privacy_violations,
]
