"""
activity_source.py

Mock "agent-activity-source" for Riskbind (the underwriting-side agent
for the TrueFoundry x Polaris hackathon).

Stands in for a real payment/API gateway or cloud IAM system that would
report an AI agent's recent action history. This is intentionally a real,
running HTTP service (not a hardcoded blob in the prompt) so that
`get_agent_activity` in TrueForge makes an actual network call -- that's
the "real tool reached" requirement the judges will look for.

Run it with:
    pip install fastapi uvicorn --break-system-packages
    python3 activity_source.py
    # serves on http://127.0.0.1:8000

Endpoints:
    GET  /agents                -> list all known agent_ids (for demo/debug)
    GET  /agents/{agent_id}/activity
         -> {agent_id, n_actions, n_flagged_actions, max_single_exposure}
         (exactly the shape risk_model.score_agent expects)
    POST /agents/{agent_id}/log_action
         -> append a synthetic action to an agent's history (lets you
            demo "live" drift during the room, not just static fixtures)

Swap this out for a real Stripe test-mode account or a GitHub Actions
log later -- the contract (agent_id in, activity dict out) stays the same.
"""

import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="agent-activity-source (mock)")


@dataclass
class Action:
    ts: float
    action_type: str
    exposure: float
    flagged: bool


@dataclass
class AgentRecord:
    agent_id: str
    display_name: str
    actions: List[Action] = field(default_factory=list)

    def as_activity(self) -> dict:
        n_actions = len(self.actions)
        n_flagged = sum(1 for a in self.actions if a.flagged)
        max_exposure = max((a.exposure for a in self.actions), default=0.0)
        return {
            "agent_id": self.agent_id,
            "n_actions": n_actions,
            "n_flagged_actions": n_flagged,
            "max_single_exposure": max_exposure,
        }


def _seed_actions(n: int, flagged_count: int, base_exposure: float, spike: float = None) -> List[Action]:
    now = time.time()
    actions = []
    for i in range(n):
        is_flagged = i < flagged_count
        exposure = spike if (spike and i == 0) else base_exposure
        actions.append(Action(ts=now - (n - i) * 60, action_type="api_call",
                               exposure=exposure, flagged=is_flagged))
    return actions


# --- Canned demo agents ------------------------------------------------
# One clearly risky, one clearly safe, one borderline -- gives you a
# real spread to walk judges through instead of a single data point.
_AGENTS: Dict[str, AgentRecord] = {
    "agent-risky-01": AgentRecord(
        agent_id="agent-risky-01",
        display_name="New vendor-refund bot (thin history)",
        actions=_seed_actions(n=12, flagged_count=5, base_exposure=150, spike=9000),
    ),
    "agent-safe-01": AgentRecord(
        agent_id="agent-safe-01",
        display_name="Payroll reconciliation agent (2yr clean history)",
        actions=_seed_actions(n=240, flagged_count=2, base_exposure=80),
    ),
    "agent-borderline-01": AgentRecord(
        agent_id="agent-borderline-01",
        display_name="New support-refund agent (moderate exposure)",
        actions=_seed_actions(n=60, flagged_count=6, base_exposure=300, spike=1200),
    ),
}


class LogActionRequest(BaseModel):
    action_type: str = "api_call"
    exposure: float = 100.0
    flagged: bool = False


@app.get("/agents")
def list_agents():
    return [
        {"agent_id": rec.agent_id, "display_name": rec.display_name,
         "n_actions": len(rec.actions)}
        for rec in _AGENTS.values()
    ]


@app.get("/agents/{agent_id}/activity")
def get_activity(agent_id: str):
    rec = _AGENTS.get(agent_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"unknown agent_id: {agent_id}")
    return rec.as_activity()


@app.post("/agents/{agent_id}/log_action")
def log_action(agent_id: str, body: LogActionRequest):
    rec = _AGENTS.get(agent_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"unknown agent_id: {agent_id}")
    rec.actions.append(Action(ts=time.time(), action_type=body.action_type,
                               exposure=body.exposure, flagged=body.flagged))
    return rec.as_activity()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
