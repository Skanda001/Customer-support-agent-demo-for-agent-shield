import asyncio
import os
from pathlib import Path
import sys
from dotenv import load_dotenv
import httpx
from sqlalchemy import text

# Add ticket_demo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.session import engine

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

API_URL = (os.getenv("AGENTSHIELD_API_URL") or "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("AGENTSHIELD_API_KEY")


async def verify():
    print("=== TICKET DEMO VERIFICATION ===")
    
    # 1. Check DB
    print("[verify] Checking database connection (SELECT 1)...")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            val = result.scalar()
            print(f"[verify] Database OK: SELECT 1 returned {val}")
    except Exception as e:
        print(f"[verify] WARNING: Database connection failed: {e}")

    # 2. Check AgentShield Health
    print(f"[verify] Checking AgentShield health at {API_URL}...")
    try:
        r = httpx.get(f"{API_URL}/api/v1/health", timeout=5.0)
        if r.status_code == 200:
            print(f"[verify] AgentShield OK: {r.json()}")
        else:
            print(f"[verify] AgentShield returned HTTP {r.status_code}")
    except Exception as e:
        print(f"[verify] AgentShield unreachable: {e}")
        return

    # 3. Check Audit Chain Verification
    print(f"[verify] Verifying cryptographic audit chain...")
    try:
        r = httpx.get(f"{API_URL}/api/v1/audit/verify", timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            print(f"[verify] Audit Chain Valid: {data.get('valid')}")
            print(f"         Total Events:     {data.get('total_events')}")
        else:
            print(f"[verify] /audit/verify returned HTTP {r.status_code}")
    except Exception as e:
        print(f"[verify] Failed calling /audit/verify: {e}")

    # 4. Check Audit Events Summary
    print(f"[verify] Querying recent audit events...")
    try:
        r = httpx.get(f"{API_URL}/api/v1/audit/events?limit=100", timeout=10.0)
        if r.status_code == 200:
            events = r.json()
            verdicts = {}
            for ev in events:
                p = ev.get("payload", {})
                if isinstance(p, dict):
                    inner = p.get("payload") if isinstance(p.get("payload"), dict) else p
                    v = inner.get("verdict") or "UNKNOWN"
                else:
                    v = ev.get("verdict", "UNKNOWN")
                verdicts[v] = verdicts.get(v, 0) + 1
            print(f"[verify] Audit events by verdict (last {len(events)} events):")
            for k, count in sorted(verdicts.items()):
                print(f"         {k}: {count}")
    except Exception as e:
        print(f"[verify] Failed calling /audit/events: {e}")


if __name__ == "__main__":
    asyncio.run(verify())
