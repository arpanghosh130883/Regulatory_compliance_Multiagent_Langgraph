"""
LangGraph Compliance Workflow Graph
====================================
Orchestrates the 5-agent compliance monitoring system:

  Phase 1 (parallel via Send API):
    START → [AML/KYC, KYB, Transaction Monitor, Privacy] — all run concurrently

  Phase 2 (serial):
    All 4 results → Alert Agent → END

Customer data is passed through RunnableConfig so every tool can access it
without it being part of the LLM-visible tool schema.
"""

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.types import Send

from agents.aml_kyc_agent import AML_TOOLS, SYSTEM_PROMPT as AML_PROMPT
from agents.alert_agent import ALERT_TOOLS, SYSTEM_PROMPT as ALERT_PROMPT
from agents.kyb_agent import KYB_TOOLS, SYSTEM_PROMPT as KYB_PROMPT
from agents.privacy_agent import PRIVACY_TOOLS, SYSTEM_PROMPT as PRIVACY_PROMPT
from agents.state import ComplianceWorkflowState
from agents.transaction_monitor_agent import TRANSACTION_TOOLS, SYSTEM_PROMPT as TX_PROMPT

# Lazy singletons — created on first use so OPENAI_API_KEY is loaded from .env first
_llm = None
_aml_react_agent = None
_kyb_react_agent = None
_tx_react_agent = None
_privacy_react_agent = None
_alert_react_agent = None


def _get_agents():
    global _llm, _aml_react_agent, _kyb_react_agent, _tx_react_agent, _privacy_react_agent, _alert_react_agent
    if _llm is None:
        _llm = ChatOpenAI(model="gpt-4o", temperature=0)
        _aml_react_agent = create_react_agent(model=_llm, tools=AML_TOOLS, prompt=AML_PROMPT)
        _kyb_react_agent = create_react_agent(model=_llm, tools=KYB_TOOLS, prompt=KYB_PROMPT)
        _tx_react_agent = create_react_agent(model=_llm, tools=TRANSACTION_TOOLS, prompt=TX_PROMPT)
        _privacy_react_agent = create_react_agent(model=_llm, tools=PRIVACY_TOOLS, prompt=PRIVACY_PROMPT)
        _alert_react_agent = create_react_agent(model=_llm, tools=ALERT_TOOLS, prompt=ALERT_PROMPT)
    return _aml_react_agent, _kyb_react_agent, _tx_react_agent, _privacy_react_agent, _alert_react_agent


# ── Helper: invoke a specialist agent and capture its final text output ───────

async def _run_specialist(
    react_agent,
    agent_label: str,
    state: ComplianceWorkflowState,
) -> dict:
    customer = state["customer"]
    result = await react_agent.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        f"Perform your compliance check for customer ID: "
                        f"{customer.get('customer_id', 'unknown')}"
                    )
                )
            ]
        },
        config={"configurable": {"customer": customer}},
    )
    response_text = result["messages"][-1].content
    return {"specialist_results": [f"=== {agent_label} ===\n{response_text}"]}


# ── Graph node functions ──────────────────────────────────────────────────────

async def run_aml_agent(state: ComplianceWorkflowState) -> dict:
    aml, _, _, _, _ = _get_agents()
    return await _run_specialist(aml, "AML/KYC AGENT", state)


async def run_kyb_agent(state: ComplianceWorkflowState) -> dict:
    _, kyb, _, _, _ = _get_agents()
    return await _run_specialist(kyb, "KYB AGENT", state)


async def run_transaction_agent(state: ComplianceWorkflowState) -> dict:
    _, _, tx, _, _ = _get_agents()
    return await _run_specialist(tx, "TRANSACTION MONITOR AGENT", state)


async def run_privacy_agent(state: ComplianceWorkflowState) -> dict:
    _, _, _, privacy, _ = _get_agents()
    return await _run_specialist(privacy, "PRIVACY AGENT", state)


async def run_alert_agent(state: ComplianceWorkflowState) -> dict:
    _, _, _, _, alert = _get_agents()
    all_results = "\n\n".join(state.get("specialist_results", []))
    customer = state["customer"]

    user_message = (
        "You have received compliance alerts from all 4 specialist agents. "
        "Apply escalation rules, generate the compliance report, execute required actions, "
        "and produce the final compliance decision.\n\n"
        f"SPECIALIST ALERTS:\n{all_results}"
    )

    result = await alert.ainvoke(
        {"messages": [HumanMessage(content=user_message)]},
        config={"configurable": {"customer": customer}},
    )
    return {"final_decision": result["messages"][-1].content}


# ── Routing: fan-out from START to all 4 specialist nodes in parallel ─────────

def route_to_specialists(state: ComplianceWorkflowState) -> list[Send]:
    """Return Send objects so LangGraph executes all 4 nodes concurrently."""
    return [
        Send("aml_agent", state),
        Send("kyb_agent", state),
        Send("transaction_agent", state),
        Send("privacy_agent", state),
    ]


# ── Build and compile the graph ───────────────────────────────────────────────

def build_compliance_graph():
    workflow = StateGraph(ComplianceWorkflowState)

    # Register specialist nodes
    workflow.add_node("aml_agent", run_aml_agent)
    workflow.add_node("kyb_agent", run_kyb_agent)
    workflow.add_node("transaction_agent", run_transaction_agent)
    workflow.add_node("privacy_agent", run_privacy_agent)

    # Register alert (synthesiser) node
    workflow.add_node("alert_agent", run_alert_agent)

    # Phase 1: fan-out from START to all 4 specialists in parallel
    workflow.add_conditional_edges(
        START,
        route_to_specialists,
        ["aml_agent", "kyb_agent", "transaction_agent", "privacy_agent"],
    )

    # Phase 2: all 4 specialists feed into the alert agent
    workflow.add_edge("aml_agent", "alert_agent")
    workflow.add_edge("kyb_agent", "alert_agent")
    workflow.add_edge("transaction_agent", "alert_agent")
    workflow.add_edge("privacy_agent", "alert_agent")

    workflow.add_edge("alert_agent", END)

    return workflow.compile()


# Module-level compiled graph — imported by main.py
compliance_graph = build_compliance_graph()
