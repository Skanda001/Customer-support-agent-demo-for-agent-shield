from pathlib import Path
import pytest
import yaml
from shield.client import ShieldClient


def test_policy_yaml_validity():
    policy_path = Path(__file__).resolve().parent.parent / "policies" / "ticket_demo.yaml"
    assert policy_path.exists(), f"Policy file {policy_path} not found"

    with open(policy_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["name"] == "ticket_demo_policy"
    assert data["version"] == 1
    assert "rules" in data
    assert isinstance(data["rules"], list)

    rule_names = {r["name"] for r in data["rules"]}
    expected_rules = {
        "allow_order_read",
        "allow_customer_read",
        "escalate_pii_read",
        "allow_reply_internal",
        "deny_external_email_with_pii",
        "allow_small_refund",
        "escalate_medium_refund",
        "deny_large_refund",
        "deny_customer_delete",
        "default_escalate",
    }
    for er in expected_rules:
        assert er in rule_names, f"Expected rule {er} not found in ticket_demo.yaml"


def test_policy_decisions_against_gateway():
    # If AgentShield is running on port 8000, test live policy verdicts
    import httpx
    import os

    api_url = os.getenv("AGENTSHIELD_API_URL", "http://localhost:8000").rstrip("/")
    api_key = os.getenv("AGENTSHIELD_API_KEY")
    if not api_key:
        pytest.skip("AGENTSHIELD_API_KEY not set; skipping live gateway decision test")

    try:
        r = httpx.get(f"{api_url}/api/v1/health", timeout=2.0)
        if r.status_code != 200:
            pytest.skip("AgentShield gateway not healthy; skipping live test")
    except Exception:
        pytest.skip("AgentShield gateway unreachable; skipping live test")

    client = ShieldClient(api_url=api_url, api_key=api_key)

    # 1. Test allow_order_read
    d_order = client.decide(
        tool="get_orders_ticket",
        arguments={"display_id": 100001},
        resource_type="order",
        data_classification="internal",
    )
    assert d_order.verdict == "ALLOW"

    # 2. Test deny_customer_delete
    d_del = client.decide(
        tool="delete_customer_ticket",
        arguments={"display_id": 1234},
        resource_type="customer",
        data_classification="restricted",
    )
    assert d_del.verdict == "BLOCK"
    assert "deny_customer_delete" in (d_del.policy_rule or "")
