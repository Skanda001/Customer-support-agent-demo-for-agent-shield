import argparse
import asyncio
import os
from pathlib import Path
import sys
from dotenv import load_dotenv
import httpx
from sqlalchemy import func, select, text

# Add ticket_demo root to python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

from db.session import engine, async_session_factory
from db.models import Ticket
from sender.sender_agent import run_sender
from receiver.receiver_agent import run_receiver
from shield.client import ShieldClient


async def verify_supabase_connectivity() -> bool:
    print("[orchestrator] Step 1: Verifying Supabase database connectivity...")
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            val = res.scalar()
            if val == 1:
                print("  [OK] Database connection successful (SELECT 1 passed).")
                return True
            print(f"  [ERROR] Database check returned unexpected value: {val}")
            return False
    except Exception as e:
        print(f"\n  [ERROR] Database connectivity failed: {e}")
        print("  Please ensure TICKET_DEMO_DATABASE_URL is correctly set in ticket_demo/.env")
        print("  and that Supabase migrations have been run with: alembic upgrade head\n")
        return False


def verify_agentshield_reachable(api_url: str) -> bool:
    print(f"[orchestrator] Step 2: Verifying AgentShield is reachable at {api_url}...")
    try:
        r = httpx.get(f"{api_url}/api/v1/health", timeout=5.0)
        if r.status_code == 200:
            print("  [OK] AgentShield is reachable and healthy.")
            return True
        print(f"  [ERROR] AgentShield returned HTTP {r.status_code}: {r.text}")
        return False
    except Exception as e:
        print(f"\n  [FATAL] AgentShield unreachable at {api_url}: {e}")
        print("  Ticket processing aborted. This proves the AgentShield gateway is load-bearing.\n")
        return False


def verify_agent_api_key(api_url: str, api_key: str) -> bool:
    print("[orchestrator] Step 3: Verifying AgentShield API key via test decide call...")
    try:
        client = ShieldClient(api_url=api_url, api_key=api_key)
        # Test decide call for order read
        decision = client.decide(
            tool="get_orders_ticket",
            arguments={"display_id": 100001},
            resource_type="order",
        )
        print(f"  [OK] API key verified. Test verdict={decision.verdict}, risk_score={decision.risk_score}")
        return True
    except Exception as e:
        print(f"\n  [ERROR] AgentShield API key verification failed: {e}")
        print("  Please run: python scripts/provision_agent.py to generate and set a valid key in .env.\n")
        return False


async def print_final_report(run_start=None):
    print("\n" + "=" * 65)
    print("DEMO SUMMARY & SECURITY GATEWAY REPORT")
    print("=" * 65)

    async with async_session_factory() as session:
        # Load only tickets created during this run (filter by run_start if available)
        stmt = select(Ticket).order_by(Ticket.created_at.asc())
        if run_start is not None:
            stmt = stmt.where(Ticket.created_at >= run_start)
        else:
            stmt = stmt.order_by(Ticket.created_at.desc()).limit(100)
        res = await session.execute(stmt)
        tickets = list(res.scalars().all())

    total = len(tickets)
    if total == 0:
        print("No tickets were processed.")
        return

    benign = [t for t in tickets if not t.is_malicious]
    malicious = [t for t in tickets if t.is_malicious]

    benign_replied = sum(1 for t in benign if t.status == "replied")
    benign_blocked = sum(1 for t in benign if t.status == "blocked")
    benign_escalated = sum(1 for t in benign if t.status == "escalated")
    benign_pending = sum(1 for t in benign if t.status == "pending")

    mal_replied = sum(1 for t in malicious if t.status == "replied")
    mal_blocked = sum(1 for t in malicious if t.status == "blocked")
    mal_escalated = sum(1 for t in malicious if t.status == "escalated")
    mal_pending = sum(1 for t in malicious if t.status == "pending")

    # Strength breakdown
    strong_tickets = [t for t in malicious if t.attack_strength == "strong"]
    weak_tickets = [t for t in malicious if t.attack_strength == "weak"]

    strong_blocked = sum(1 for t in strong_tickets if t.status == "blocked")
    strong_escalated = sum(1 for t in strong_tickets if t.status == "escalated")

    weak_blocked = sum(1 for t in weak_tickets if t.status == "blocked")
    weak_escalated = sum(1 for t in weak_tickets if t.status == "escalated")

    print(f"Processed {total} tickets (this run).")
    print(f"  benign:     {len(benign):<4}  replied={benign_replied:<4}  blocked={benign_blocked:<4}  escalated={benign_escalated:<4}  pending={benign_pending}")
    print(f"  malicious:  {len(malicious):<4}  replied={mal_replied:<4}  blocked={mal_blocked:<4}  escalated={mal_escalated:<4}  pending={mal_pending}")
    print()
    print("  Attack strength:")
    print(f"    strong:  {len(strong_tickets):<4} -> blocked {strong_blocked:<4} (escalated {strong_escalated})")
    print(f"    weak:    {len(weak_tickets):<4} -> blocked {weak_blocked:<4} (escalated {weak_escalated})")
    print()
    print(f"  False negatives (malicious replied): {mal_replied}")
    print(f"  False positives (benign blocked):    {benign_blocked}")
    print("=" * 65)


def query_audit_and_verify(api_url: str):
    print("\n[orchestrator] Querying AgentShield Audit Chain...")
    try:
        r_events = httpx.get(f"{api_url}/api/v1/audit/events?limit=500", timeout=10.0)
        if r_events.status_code == 200:
            events = r_events.json()
            verdict_counts = {}
            for ev in events:
                p = ev.get("payload", {})
                if isinstance(p, dict):
                    inner = p.get("payload") if isinstance(p.get("payload"), dict) else p
                    v = inner.get("verdict") or "UNKNOWN"
                else:
                    v = ev.get("verdict", "UNKNOWN")
                verdict_counts[v] = verdict_counts.get(v, 0) + 1
            print(f"AgentShield /api/v1/audit/events GROUP BY decision:")
            for v, c in sorted(verdict_counts.items()):
                print(f"  {v}: {c}")
        else:
            print(f"Failed to fetch audit events: HTTP {r_events.status_code}")
    except Exception as e:
        print(f"Failed to query /api/v1/audit/events: {e}")

    try:
        r_verify = httpx.get(f"{api_url}/api/v1/audit/verify", timeout=10.0)
        if r_verify.status_code == 200:
            v_data = r_verify.json()
            print(f"AgentShield /api/v1/audit/verify: valid: {v_data.get('valid')} (total_events: {v_data.get('total_events')})")
        else:
            print(f"Failed to call /api/v1/audit/verify: HTTP {r_verify.status_code}")
    except Exception as e:
        print(f"Failed calling /api/v1/audit/verify: {e}")
    print("=" * 65)


async def abandon_orphan_pending_tickets() -> int:
    """Mark leftover 'pending' tickets from previous failed runs as 'abandoned'."""
    async with async_session_factory() as session:
        result = await session.execute(select(Ticket).where(Ticket.status == "pending"))
        orphans = list(result.scalars().all())
        for t in orphans:
            t.status = "abandoned"
        if orphans:
            await session.commit()
        return len(orphans)


async def orchestrate(burst_count: int = 100, rate: float = 0.45):
    from datetime import datetime, timezone
    api_url = (os.getenv("AGENTSHIELD_API_URL") or "http://localhost:8000").rstrip("/")
    api_key = os.getenv("AGENTSHIELD_API_KEY", "")

    # 1. DB Connectivity Check
    db_ok = await verify_supabase_connectivity()
    if not db_ok:
        sys.exit(1)

    # 2. AgentShield Reachability Check
    shield_ok = verify_agentshield_reachable(api_url)
    if not shield_ok:
        sys.exit(1)

    # 3. AgentShield API Key Check
    key_ok = verify_agent_api_key(api_url, api_key)
    if not key_ok:
        sys.exit(1)

    # 3b. Clean up orphan pending tickets from previous failed runs
    print("[orchestrator] Step 3b: Cleaning up orphan pending tickets...")
    abandoned = await abandon_orphan_pending_tickets()
    if abandoned:
        print(f"  [OK] Marked {abandoned} orphan ticket(s) as 'abandoned'.")
    else:
        print("  [OK] No orphan pending tickets found.")

    # Record run start so the report filters only this run's tickets
    run_start = datetime.now(tz=timezone.utc)

    # 4. Run Sender Agent (Burst Mode)
    print(f"\n[orchestrator] Step 4: Running sender agent burst of {burst_count} tickets (malicious_rate={rate})...")
    await run_sender(burst=burst_count, rate=rate)

    # 5. Run Receiver Agent
    print(f"\n[orchestrator] Step 5: Running receiver agent for {burst_count} cycles...")
    await run_receiver(cycles=burst_count)

    # 6. Report and Audit Verification
    await print_final_report(run_start=run_start)
    query_audit_and_verify(api_url)


def main():
    parser = argparse.ArgumentParser(description="Two-Agent Ticket Demo Orchestrator")
    parser.add_argument("--burst", type=int, default=100, help="Number of tickets to generate (default 100)")
    parser.add_argument("--rate", type=float, default=0.45, help="Malicious ticket rate (default 0.45)")
    args = parser.parse_args()

    asyncio.run(orchestrate(burst_count=args.burst, rate=args.rate))


if __name__ == "__main__":
    main()

