import os
from pathlib import Path
import sys
from dotenv import load_dotenv
import httpx

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

API_URL = (os.getenv("AGENTSHIELD_API_URL") or "http://localhost:8000").rstrip("/")
ADMIN_KEY = os.getenv("AGENTSHIELD_ADMIN_API_KEY")

SCOPES = [
    "read:customer",
    "read:order",
    "read:payment",
    "write:payment",
    "write:email",
    "write:customer",
]


def provision():
    print(f"[provision] Connecting to AgentShield at {API_URL}...")
    headers = {"Content-Type": "application/json"}
    if ADMIN_KEY:
        headers["Authorization"] = f"Bearer {ADMIN_KEY}"

    # 1. Check health
    try:
        r = httpx.get(f"{API_URL}/api/v1/health", timeout=10.0)
        if r.status_code != 200:
            print(f"[provision] ERROR: AgentShield returned HTTP {r.status_code}: {r.text}")
            print_manual_setup_guide()
            sys.exit(1)
    except Exception as e:
        print(f"[provision] ERROR: Unable to reach AgentShield at {API_URL}: {e}")
        print_manual_setup_guide()
        sys.exit(1)

    # 2. Create or find tenant 'ticket-demo'
    print("[provision] Creating tenant 'ticket-demo'...")
    tenant_id = None
    try:
        r = httpx.post(
            f"{API_URL}/api/v1/tenants",
            json={"name": "Ticket Demo", "slug": "ticket-demo"},
            headers=headers,
            timeout=10.0,
        )
        if r.status_code == 201:
            tenant_data = r.json()
            tenant_id = tenant_data["id"]
            print(f"[provision] Tenant created: ID={tenant_id}")
        elif r.status_code == 400 and "already exists" in r.text:
            print("[provision] Tenant 'ticket-demo' already exists.")
            # Search decisions or logs to find tenant_id if possible
            r_dec = httpx.get(f"{API_URL}/api/v1/decisions?limit=50", headers=headers, timeout=10.0)
            if r_dec.status_code == 200 and r_dec.json():
                for d in r_dec.json():
                    if d.get("tenant_id"):
                        tenant_id = d["tenant_id"]
                        break
        elif r.status_code in (401, 403):
            print(f"[provision] ERROR: AgentShield API requires authentication ({r.status_code}).")
            print_manual_setup_guide()
            sys.exit(1)
        else:
            print(f"[provision] Unexpected response from /tenants: {r.status_code} {r.text}")
    except Exception as e:
        print(f"[provision] Failed creating tenant: {e}")
        print_manual_setup_guide()
        sys.exit(1)

    if not tenant_id:
        # Prompt user or generate with timestamped slug if needed
        import time
        unique_slug = f"ticket-demo-{int(time.time())}"
        r = httpx.post(
            f"{API_URL}/api/v1/tenants",
            json={"name": "Ticket Demo", "slug": unique_slug},
            headers=headers,
            timeout=10.0,
        )
        if r.status_code == 201:
            tenant_id = r.json()["id"]
            print(f"[provision] Created fallback tenant '{unique_slug}': ID={tenant_id}")
        else:
            print(f"[provision] Could not establish tenant: {r.status_code} {r.text}")
            print_manual_setup_guide()
            sys.exit(1)

    # 3. Create agent 'ticket-receiver'
    print("[provision] Creating agent 'ticket-receiver'...")
    try:
        r = httpx.post(
            f"{API_URL}/api/v1/agents",
            json={
                "tenant_id": tenant_id,
                "name": "ticket-receiver",
                "description": "Receiver agent for two-agent ticket demo",
                "role": "support_agent",
                "scopes": SCOPES,
            },
            headers=headers,
            timeout=10.0,
        )
        if r.status_code == 201:
            res = r.json()
            api_key = res["api_key"]
            agent_id = res["agent"]["id"]
            print("\n=======================================================")
            print(f"[provision] SUCCESS! Agent Provisioned.")
            print(f"  Agent ID:   {agent_id}")
            print(f"  Tenant ID:  {tenant_id}")
            print(f"  API Key:    {api_key}")
            print("=======================================================")
            print("\nACTION REQUIRED:")
            print(f"Please copy the API key above and paste it into ticket_demo/.env:")
            print(f"  AGENTSHIELD_API_KEY={api_key}\n")
            return api_key
        else:
            print(f"[provision] Failed creating agent: {r.status_code} {r.text}")
            print_manual_setup_guide()
            sys.exit(1)
    except Exception as e:
        print(f"[provision] Error creating agent: {e}")
        print_manual_setup_guide()
        sys.exit(1)


def print_manual_setup_guide():
    print("""
-------------------------------------------------------------------
MANUAL AGENT PROVISIONING GUIDE
-------------------------------------------------------------------
If automated provisioning cannot proceed due to custom authentication:
1. Open the AgentShield UI at http://localhost:3000 (or http://localhost:5173).
2. Create a Tenant named 'ticket-demo'.
3. Navigate to Agents -> Create New Agent:
   - Name: ticket-receiver
   - Role: support_agent
   - Scopes: read:customer, read:order, read:payment, write:payment, write:email, write:customer
4. Copy the generated API key.
5. Paste it into ticket_demo/.env as:
   AGENTSHIELD_API_KEY=ash_...
-------------------------------------------------------------------
""")


if __name__ == "__main__":
    provision()
