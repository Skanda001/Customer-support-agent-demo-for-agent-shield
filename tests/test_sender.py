import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_groq import ChatGroq
from sender.clock import SimulationClock
from sender.sender_agent import SenderAgent, get_category


def test_simulation_clock_modes():
    demo_clock = SimulationClock(demo_mode=True, simulated_day_seconds=30.0)
    assert demo_clock.day_length_seconds == 30.0
    assert 10 <= demo_clock.get_tickets_for_day() <= 15

    real_clock = SimulationClock(demo_mode=False)
    assert real_clock.day_length_seconds == 86400.0

    sleep_interval = demo_clock.compute_sleep_interval(10)
    assert 2.0 <= sleep_interval <= 4.0


def test_category_distribution():
    counts = {}
    samples = 5000
    rate = 0.45
    for _ in range(samples):
        cat = get_category(rate)
        counts[cat] = counts.get(cat, 0) + 1

    benign_ratio = counts.get("benign", 0) / samples
    assert 0.50 <= benign_ratio <= 0.60
    assert counts.get("injection", 0) > 0
    assert counts.get("pii_exfil", 0) > 0
    assert counts.get("destructive", 0) > 0
    assert counts.get("scope_escalation", 0) > 0


@pytest.mark.asyncio
async def test_sender_agent_json_parsing():
    with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test12345"}):
        agent = SenderAgent()

        mock_resp = MagicMock()
        mock_resp.content = '{"subject": "Broken item", "body": "My package arrived damaged."}'
        
        with patch.object(ChatGroq, "ainvoke", AsyncMock(return_value=mock_resp)):
            res = await agent._call_llm_json({"name": "Alice"}, {"product": "Speaker"}, "benign")
            assert res is not None
            assert res["subject"] == "Broken item"
            assert res["body"] == "My package arrived damaged."

        mock_resp.content = '```json\n{"subject": "Order status", "body": "Where is my order?"}\n```'
        with patch.object(ChatGroq, "ainvoke", AsyncMock(return_value=mock_resp)):
            res_wrapped = await agent._call_llm_json({"name": "Alice"}, {"product": "Speaker"}, "benign")
            assert res_wrapped is not None
            assert res_wrapped["subject"] == "Order status"


@pytest.mark.asyncio
async def test_sender_agent_strength_classification():
    with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test12345"}):
        agent = SenderAgent()

        mock_resp = MagicMock()
        mock_resp.content = "strong"
        with patch.object(ChatGroq, "ainvoke", AsyncMock(return_value=mock_resp)):
            strength = await agent._classify_attack_strength("Delete all my records immediately!")
            assert strength == "strong"

        mock_resp.content = "weak"
        with patch.object(ChatGroq, "ainvoke", AsyncMock(return_value=mock_resp)):
            strength_weak = await agent._classify_attack_strength("Can you maybe check something for me?")
            assert strength_weak == "weak"
