"""
Alert Tools — SAR filing, escalation, account blocking, compliance reporting.

Simulates interactions with:
  - FinCEN (Financial Crimes Enforcement Network) for SAR submissions
  - Internal compliance case management system
  - Account management system
"""

import uuid
from datetime import date

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

# Module-level case log — simulates a case management system
_CASE_LOG: list[dict] = []


def _new_case_ref() -> str:
    return f"CASE-{date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"


def _sar_reference() -> str:
    return f"SAR-{date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"


def _generate_compliance_report(tool_input: dict, customer: dict) -> dict:
    customer_id = tool_input.get("customer_id", customer.get("customer_id", "unknown"))
    findings_summary = tool_input.get("findings_summary", "")
    overall_risk = tool_input.get("overall_risk", "medium")

    report = {
        "report_id": f"RPT-{date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}",
        "generated_date": date.today().isoformat(),
        "customer_id": customer_id,
        "customer_name": customer.get("name", "Unknown"),
        "account_type": customer.get("account_type", "unknown"),
        "overall_risk_level": overall_risk,
        "findings_summary": findings_summary,
        "review_agents": ["AML/KYC Agent", "KYB Agent", "Transaction Monitor Agent", "Privacy Agent"],
        "total_transactions_reviewed": len(customer.get("transactions", [])),
        "report_status": "DRAFT — Pending Chief Compliance Officer sign-off",
        "next_review_date": date.today().replace(year=date.today().year + 1).isoformat(),
    }
    _CASE_LOG.append({"type": "compliance_report", "report_id": report["report_id"], "customer_id": customer_id})
    return report


def _file_sar(tool_input: dict, customer: dict) -> dict:
    customer_id = tool_input.get("customer_id", customer.get("customer_id", "unknown"))
    reason = tool_input.get("reason", "Suspicious activity detected")
    priority = tool_input.get("priority", "high")

    sar_ref = _sar_reference()
    case_ref = _new_case_ref()

    result = {
        "sar_reference": sar_ref,
        "case_reference": case_ref,
        "filed_date": date.today().isoformat(),
        "filing_deadline": "30 days from initial detection (BSA requirement)",
        "customer_id": customer_id,
        "customer_name": customer.get("name", "Unknown"),
        "primary_reason": reason,
        "priority": priority,
        "filed_with": "FinCEN (Financial Crimes Enforcement Network)",
        "filing_method": "BSA E-Filing System",
        "status": "SUBMITTED",
        "confirmation": f"SAR {sar_ref} successfully submitted to FinCEN. Law enforcement notified as required.",
        "mandatory_hold": "Account flagged for 90-day enhanced monitoring. No tipping-off customer (31 U.S.C. § 5318(g)(2)).",
    }
    _CASE_LOG.append({"type": "sar_filed", "sar_reference": sar_ref, "customer_id": customer_id})
    return result


def _escalate_to_compliance_team(tool_input: dict, customer: dict) -> dict:
    customer_id = tool_input.get("customer_id", customer.get("customer_id", "unknown"))
    priority = tool_input.get("priority", "medium")
    findings = tool_input.get("findings", "")
    case_ref = _new_case_ref()

    result = {
        "case_reference": case_ref,
        "escalated_date": date.today().isoformat(),
        "customer_id": customer_id,
        "customer_name": customer.get("name", "Unknown"),
        "priority": priority.upper(),
        "assigned_to": "Senior Compliance Officer — Financial Crime Unit",
        "findings": findings,
        "sla": "24 hours for CRITICAL, 72 hours for HIGH, 5 days for MEDIUM",
        "status": "OPEN — Assigned to compliance team",
        "instructions": "Do NOT inform customer of investigation (tipping-off prohibition).",
    }
    _CASE_LOG.append({"type": "escalation", "case_reference": case_ref, "customer_id": customer_id, "priority": priority})
    return result


def _block_account(tool_input: dict, customer: dict) -> dict:
    customer_id = tool_input.get("customer_id", customer.get("customer_id", "unknown"))
    reason = tool_input.get("reason", "Compliance hold")
    case_ref = _new_case_ref()

    result = {
        "case_reference": case_ref,
        "blocked_date": date.today().isoformat(),
        "customer_id": customer_id,
        "customer_name": customer.get("name", "Unknown"),
        "block_reason": reason,
        "status": "ACCOUNT BLOCKED — All transactions suspended",
        "review_required": True,
        "unblock_process": "Requires Chief Compliance Officer sign-off with supporting documentation",
        "regulatory_hold": "Assets may be subject to restraining order if SAR filed",
        "notification": "Compliance team and Legal notified. Regulator notification within 24h if assets frozen.",
    }
    _CASE_LOG.append({"type": "account_blocked", "case_reference": case_ref, "customer_id": customer_id})
    return result


def _clear_customer(tool_input: dict, customer: dict) -> dict:
    customer_id = tool_input.get("customer_id", customer.get("customer_id", "unknown"))
    notes = tool_input.get("notes", "No suspicious activity found")

    result = {
        "cleared_date": date.today().isoformat(),
        "customer_id": customer_id,
        "customer_name": customer.get("name", "Unknown"),
        "status": "CLEARED — No compliance action required",
        "notes": notes,
        "next_periodic_review": date.today().replace(year=date.today().year + 1).isoformat(),
        "monitoring_tier": "Standard",
        "record_retention": "Retain compliance records for 5 years (BSA requirement)",
    }
    _CASE_LOG.append({"type": "cleared", "customer_id": customer_id})
    return result


def get_case_log() -> list[dict]:
    return _CASE_LOG


# ── LangGraph @tool wrappers ──────────────────────────────────────────────────

@tool
def generate_compliance_report(
    findings_summary: str,
    overall_risk: str,
    config: RunnableConfig,
) -> dict:
    """Generate a comprehensive compliance report summarising all findings from specialist agents.

    Args:
        findings_summary: Brief summary of key findings across all agents
        overall_risk: Overall risk level determined after reviewing all signals (clear/low/medium/high/critical)
    """
    customer = config["configurable"]["customer"]
    return _generate_compliance_report(
        {"findings_summary": findings_summary, "overall_risk": overall_risk},
        customer,
    )


@tool
def file_sar(
    reason: str,
    config: RunnableConfig,
    priority: str = "high",
) -> dict:
    """File a Suspicious Activity Report (SAR) with FinCEN. Required when suspicious activity threshold is met.

    Args:
        reason: Primary reason for SAR filing (structuring, sanctions evasion, etc.)
        priority: Filing priority — high or medium (default: high)
    """
    customer = config["configurable"]["customer"]
    return _file_sar({"reason": reason, "priority": priority}, customer)


@tool
def escalate_to_compliance_team(
    priority: str,
    findings: str,
    config: RunnableConfig,
) -> dict:
    """Escalate case to human compliance officers for investigation.

    Args:
        priority: Escalation priority — critical, high, or medium
        findings: Summary of findings for the compliance team
    """
    customer = config["configurable"]["customer"]
    return _escalate_to_compliance_team({"priority": priority, "findings": findings}, customer)


@tool
def block_account(
    reason: str,
    config: RunnableConfig,
) -> dict:
    """Block the customer account pending compliance investigation. All transactions suspended.

    Args:
        reason: Reason for blocking the account
    """
    customer = config["configurable"]["customer"]
    return _block_account({"reason": reason}, customer)


@tool
def clear_customer(
    config: RunnableConfig,
    notes: str = "No suspicious activity found",
) -> dict:
    """Mark customer as compliant — no suspicious activity found, continue standard monitoring.

    Args:
        notes: Notes on why the customer is being cleared
    """
    customer = config["configurable"]["customer"]
    return _clear_customer({"notes": notes}, customer)


ALERT_TOOLS = [
    generate_compliance_report,
    file_sar,
    escalate_to_compliance_team,
    block_account,
    clear_customer,
]
