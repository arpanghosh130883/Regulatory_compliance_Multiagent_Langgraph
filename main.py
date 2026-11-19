"""
Regulatory Compliance Monitoring — Multi-Agent System (LangGraph)
=================================================================
Runs AML/KYC, KYB, Transaction Monitor, and Privacy agents in parallel
using LangGraph's Send API, then synthesises all alerts through the Alert
Agent to produce a final compliance decision.

Architecture:
  START → (Send) → 4 parallel specialist ReAct agents → alert agent → END

Usage:
  python main.py                             # defaults to john_smith
  python main.py --customer business_alpha
  python main.py --customer customer_gamma
  python main.py --list                      # show available customers

Prerequisites:
  export OPENAI_API_KEY=sk-...
  uv sync  (or: pip install langgraph langchain-openai langchain-core python-dotenv)
"""

import argparse
import asyncio
import sys
import textwrap
import time

from dotenv import load_dotenv
load_dotenv()

from agents.compliance_graph import compliance_graph
from data.loader import list_customers, load_customer
from models.alerts import parse_alert_text

DIVIDER = "─" * 72

_RISK_ICONS = {
    "critical": "[CRITICAL]",
    "high":     "[HIGH]    ",
    "medium":   "[MEDIUM]  ",
    "low":      "[LOW]     ",
    "clear":    "[CLEAR]   ",
}

_ACTION_LABELS = {
    "block":        "ACCOUNT BLOCKED",
    "file_sar":     "SAR FILED WITH FinCEN",
    "investigate":  "ESCALATED FOR INVESTIGATION",
    "monitor":      "ENHANCED MONITORING",
    "clear":        "CLEARED — NO ACTION",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regulatory Compliance Monitoring — Multi-Agent System (LangGraph)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py                              # run john_smith (default)\n"
            "  python main.py --customer business_alpha    # run clean business\n"
            "  python main.py --customer customer_gamma    # run high-risk business\n"
            "  python main.py --list                       # show all available customers\n\n"
            "To add a new customer, drop a JSON file into the customers/ folder."
        ),
    )
    parser.add_argument(
        "--customer", default="john_smith",
        help="Customer ID (filename without .json). Default: john_smith",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all available customer IDs and exit",
    )
    return parser.parse_args()


def _print_specialist_result(result: str) -> None:
    print(f"\n{DIVIDER}")
    lines = result.strip().split("\n")
    for line in lines[:25]:
        print(f"  {line}")
    if len(lines) > 25:
        print(f"  ... ({len(lines) - 25} more lines)")
    print(DIVIDER)


async def run_compliance_check(customer_id: str) -> None:
    customer = load_customer(customer_id)

    print("\n" + "=" * 72)
    print("   REGULATORY COMPLIANCE MONITORING SYSTEM")
    print("   Powered by LangGraph + GPT-4o  |  AML · KYB · Transaction Monitor · Privacy")
    print("=" * 72)

    total_txn_volume = sum(t.get("amount", 0) for t in customer.get("transactions", []))
    print(f"\n  Customer:       {customer['name']}")
    print(f"  ID:             {customer_id}")
    print(f"  Account Type:   {customer.get('account_type', 'unknown').upper()}")
    print(f"  Status:         {customer.get('account_status', 'unknown').upper()}")
    print(f"  Transactions:   {len(customer.get('transactions', []))}  |  Total volume: ${total_txn_volume:,.0f}")

    if customer.get("account_type") == "business":
        print(f"  Business:       {customer.get('industry', 'N/A')}  |  {customer.get('employees', '?')} employees  |  Revenue: ${customer.get('annual_revenue', 0):,.0f}/yr")
        print(f"  Registered:     {customer.get('registration_state', 'N/A')}  ({customer.get('business_type', 'N/A')})")
    else:
        print(f"  Nationality:    {customer.get('nationality', 'N/A')}  |  Occupation: {customer.get('occupation', 'N/A')}")
        print(f"  Annual Income:  ${customer.get('annual_income', 0):,.0f}  |  PEP: {customer.get('pep_status', False)}")

    print(f"\n{DIVIDER}")
    print("  PHASE 1: 4 specialist agents dispatched in parallel (LangGraph Send API)")
    print("           AML/KYC  ·  KYB  ·  Transaction Monitor  ·  Privacy")
    print(f"{DIVIDER}\n")

    t0 = time.monotonic()

    initial_state = {
        "customer_id": customer_id,
        "customer": customer,
        "specialist_results": [],
        "final_decision": None,
    }

    final_state = await compliance_graph.ainvoke(initial_state)

    elapsed = time.monotonic() - t0

    # ── Print specialist results (Phase 1 output) ─────────────────────────────
    specialist_results = final_state.get("specialist_results", [])
    print(f"  Phase 1 complete — {len(specialist_results)} specialist agents returned results\n")

    for result in specialist_results:
        _print_specialist_result(result)

    # ── Print final decision (Phase 2 output) ─────────────────────────────────
    print(f"\n{DIVIDER}")
    print("  PHASE 2: Alert Agent — synthesised final compliance decision")
    print(f"{DIVIDER}")

    final_text = final_state.get("final_decision", "No decision returned")
    alert = parse_alert_text("Alert Agent", final_text)

    icon = _RISK_ICONS.get(alert.risk_level, "[UNKNOWN]  ")
    action = _ACTION_LABELS.get(alert.recommended_action, alert.recommended_action.upper())

    print(f"\n  {icon}  -->  {action}\n")

    for flag in alert.flags[:10]:
        wrapped = textwrap.fill(
            flag, width=68, initial_indent="    * ", subsequent_indent="      "
        )
        print(wrapped)
    if len(alert.flags) > 10:
        print(f"    ... and {len(alert.flags) - 10} more findings")

    print(f"\n{DIVIDER}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print(f"  COMPLIANCE CHECK COMPLETE — {customer['name']}")
    print(f"{'=' * 72}")
    print(f"  Customer ID:    {customer_id}")
    print(f"  Account Type:   {customer.get('account_type', 'N/A')}")
    print(f"  Final Risk:     {icon.strip()}  {alert.risk_level.upper()}")
    print(f"  Final Action:   {action}")
    print(f"  Total runtime:  {elapsed:.1f}s")
    print(f"  Framework:      LangGraph  |  Agents: 4 parallel + 1 serial alert agent")
    print(f"{'=' * 72}\n")


def run() -> None:
    args = parse_args()

    if args.list:
        customers = list_customers()
        print("\nAvailable customers:")
        for c in customers:
            print(f"  * {c}")
        print(f"\nUsage: python main.py --customer <customer_id>")
        sys.exit(0)

    asyncio.run(run_compliance_check(args.customer))


if __name__ == "__main__":
    run()
