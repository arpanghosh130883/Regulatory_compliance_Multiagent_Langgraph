"""
Customer data loader — reads customer JSON files from the customers/ directory.
"""

import json
from pathlib import Path

CUSTOMERS_DIR = Path(__file__).parent.parent / "customers"


def load_customer(customer_id: str) -> dict:
    path = CUSTOMERS_DIR / f"{customer_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Customer file not found: {path}\n"
            f"Available customers: {', '.join(list_customers())}"
        )
    with open(path) as f:
        return json.load(f)


def list_customers() -> list[str]:
    return sorted(p.stem for p in CUSTOMERS_DIR.glob("*.json"))
