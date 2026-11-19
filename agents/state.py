"""
LangGraph state definitions for the compliance monitoring workflow.
"""

import operator
from typing import Annotated, Optional
from typing_extensions import TypedDict


class ComplianceWorkflowState(TypedDict):
    customer_id: str
    customer: dict
    # Annotated with operator.add so parallel specialist nodes each append their result
    specialist_results: Annotated[list[str], operator.add]
    final_decision: Optional[str]
