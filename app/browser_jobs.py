"""In-memory browser search job manager for a single Render web process."""
from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from .browser_agent import BrowserAgentError, ManualInterventionRequired, PlaywrightQuoteAgent

# No insurer is enabled by default. Add an adapter only after confirming authorized access.
PROVIDERS: dict[str, Any] = {}
JOBS: dict[str, dict[str, Any]] = {}
TASKS: set[asyncio.Task] = set()
MAX_ACTIVE_JOBS = 1
MAX_RETAINED_JOBS = 50
_SEMAPHORE = asyncio.Semaphore(1)  # one job at a time; providers within a job use two tabs


def register_provider(adapter: Any) -> None:
    """Register a provider-specific adapter from application startup code."""
    required = ("provider_id", "display_name", "start_url", "allowed_hosts", "submit_selector", "result_selectors", "prepare", "extract")
    missing = [name for name in required if not hasattr(adapter, name)]
    if missing:
        raise ValueError("Provider adapter is missing: " + ", ".join(missing))
    if adapter.provider_id in PROVIDERS:
        raise ValueError(f"Provider already registered: {adapter.provider_id}")
    PROVIDERS[adapter.provider_id] = adapter


def provider_list() -> list[dict[str, str]]:
    return [
        {"id": key, "name": adapter.display_name, "status": "enabled"}
        for key, adapter in PROVIDERS.items()
    ]


def _trim_jobs() -> None:
    if len(JOBS) <= MAX_RETAINED_JOBS:
        return
    finished = sorted(
        ((value.get("created_at", 0), key) for key, value in JOBS.items() if value.get("status") in {"completed", "failed", "needs_human"})
    )
    for _, key in finished[: max(0, len(JOBS) - MAX_RETAINED_JOBS)]:
        JOBS.pop(key, None)


async def create_job(provider_ids: list[str], form_data: dict[str, str]) -> dict[str, Any]:
    if not PROVIDERS:
        raise ValueError("No approved carrier browser adapters are configured yet.")
    unknown = [item for item in provider_ids if item not in PROVIDERS]
    if unknown:
        raise ValueError("Unknown or disabled provider: " + ", ".join(unknown))
    if len([j for j in JOBS.values() if j.get("status") in {"queued", "running"}]) >= MAX_ACTIVE_JOBS:
        raise RuntimeError("Browser search capacity is busy. Try again after an active search finishes.")

    job_id = secrets.token_urlsafe(12)
    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "created_at": time.time(),
        "providers": provider_ids,
        "results": [],
        "errors": [],
        "note": "Search uses approved provider pages only. No purchase or policy binding is performed.",
    }
    task = asyncio.create_task(_run_job(job_id, provider_ids, dict(form_data)))
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    _trim_jobs()
    return public_job(JOBS[job_id])


async def _run_job(job_id: str, provider_ids: list[str], form_data: dict[str, str]) -> None:
    job = JOBS.get(job_id)
    if not job:
        return
    job["status"] = "running"
    agent = PlaywrightQuoteAgent()
    try:
        adapters = [(PROVIDERS[provider_id], dict(form_data)) for provider_id in provider_ids]
        outcomes = await agent.run_many(adapters, concurrency=2)
        for provider_id, outcome in zip(provider_ids, outcomes):
            if isinstance(outcome, ManualInterventionRequired):
                job["errors"].append({"provider_id": provider_id, "status": "needs_human", "message": str(outcome)})
            elif isinstance(outcome, BrowserAgentError):
                job["errors"].append({"provider_id": provider_id, "status": "failed", "message": str(outcome)})
            elif isinstance(outcome, Exception):
                job["errors"].append({"provider_id": provider_id, "status": "failed", "message": "Unexpected browser error. No personal form values were logged."})
            else:
                job["results"].append(outcome.as_dict())
    except Exception:
        job["errors"].append({"provider_id": "browser-engine", "status": "failed", "message": "Browser engine failed to start or stopped unexpectedly."})

    if any(error["status"] == "needs_human" for error in job["errors"]):
        job["status"] = "needs_human"
    elif job["results"]:
        job["status"] = "completed"
    else:
        job["status"] = "failed"
    job["finished_at"] = time.time()


def get_job(job_id: str) -> dict[str, Any] | None:
    job = JOBS.get(job_id)
    return public_job(job) if job else None


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    # Never return or retain the submitted form data.
    return {
        "id": job["id"],
        "status": job["status"],
        "providers": job["providers"],
        "results": job["results"],
        "errors": job["errors"],
        "note": job["note"],
    }
