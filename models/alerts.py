from dataclasses import dataclass, field


@dataclass
class ComplianceAlert:
    agent_name: str
    risk_level: str       # "clear" | "low" | "medium" | "high" | "critical"
    flags: list[str]
    recommended_action: str  # "clear" | "monitor" | "investigate" | "block" | "file_sar"
    data: dict = field(default_factory=dict)
    raw_text: str = ""


def parse_alert_text(agent_name: str, raw_text: str) -> ComplianceAlert:
    """Parse a free-text agent response into a typed ComplianceAlert."""
    risk_level = "medium"
    recommended_action = "investigate"

    for line in raw_text.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("RISK_LEVEL:"):
            level = stripped.split(":", 1)[1].strip().lower()
            if level in ("clear", "low", "medium", "high", "critical"):
                risk_level = level
        elif stripped.startswith("RECOMMENDED_ACTION:"):
            action = stripped.split(":", 1)[1].strip().lower()
            if action in ("clear", "monitor", "investigate", "block", "file_sar"):
                recommended_action = action

    flags = [
        line.strip().lstrip("-•* ")
        for line in raw_text.splitlines()
        if line.strip().startswith(("-", "•", "*")) and len(line.strip()) > 2
    ]
    if not flags:
        flags = [raw_text[:500]] if raw_text else ["No flags raised"]

    return ComplianceAlert(
        agent_name=agent_name,
        risk_level=risk_level,
        flags=flags,
        recommended_action=recommended_action,
        raw_text=raw_text,
    )
