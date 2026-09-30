"""
Runs the Copilot spec's exact test scenarios against the live backend.
Scenario 6 (unknown engine) costs zero LLM calls by design; the others
do call the configured provider, so this is deliberately NOT part of
the automated E2E suite (it would burn real quota on every CI run) —
run manually.
"""
import httpx

from _common import BASE_URL, ENGINE_ID, auth_headers, login

SCENARIOS = [
    ("1. Static (RUL)", "What is RUL?"),
    ("2. Static (Health Fusion)", "What is Health Fusion?"),
    ("3. Live (RUL)", "What is the current RUL of SIM-ENGINE-01?"),
    ("4. Live (RPM)", "What is the current RPM of SIM-ENGINE-01?"),
    ("5. Combined (why low)", "Why is the current health score of SIM-ENGINE-01 low?"),
    ("6. Unknown engine", "What is the current RUL of UNKNOWN-ENGINE?"),
]


def main():
    with httpx.Client(timeout=60.0) as client:
        token = login(client)
        headers = auth_headers(token)
        for label, message in SCENARIOS:
            print(f"\n=== {label} ===")
            print(f"Q: {message}")
            try:
                resp = client.post(f"{BASE_URL}/copilot/query", json={"message": message, "engine_id": ENGINE_ID},
                                    headers=headers)
                print(f"Status: {resp.status_code}")
                print(f"A: {resp.text[:500]}".encode("ascii", "replace").decode("ascii"))
            except httpx.ReadTimeout:
                print("TIMEOUT (client-side) — check backend log for the provider's own outcome")


if __name__ == "__main__":
    main()
