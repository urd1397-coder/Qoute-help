"""Supervised Playwright browser automation for approved quote-provider adapters.

This module uses a normal Chromium session and provider-specific selectors. It does
not spoof fingerprints, solve CAPTCHAs, bypass logins, or evade rate limits. A provider
adapter must be explicitly implemented and approved before it can be used.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, async_playwright


class BrowserAgentError(RuntimeError):
    pass


class ManualInterventionRequired(BrowserAgentError):
    pass


class ProviderUnavailable(BrowserAgentError):
    pass


@dataclass(frozen=True)
class BrowserQuote:
    provider_id: str
    company: str
    monthly_premium: float
    fees_monthly: float
    coverage: dict[str, str]
    vehicles: int | None
    drivers: int | None
    source_url: str
    retrieved_at: str
    verification_status: str
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "company": self.company,
            "monthly_premium": self.monthly_premium,
            "fees_monthly": self.fees_monthly,
            "effective_monthly": round(self.monthly_premium + self.fees_monthly, 2),
            "coverage": self.coverage,
            "vehicles": self.vehicles,
            "drivers": self.drivers,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "verification_status": self.verification_status,
            "warnings": self.warnings,
            "is_simulated": False,
        }


class QuoteProviderAdapter(Protocol):
    provider_id: str
    display_name: str
    start_url: str
    allowed_hosts: tuple[str, ...]
    field_selectors: dict[str, str]
    submit_selector: str
    result_selectors: dict[str, str]

    async def prepare(self, page: Page, form_data: dict[str, str]) -> None: ...

    async def extract(self, page: Page) -> dict[str, Any]: ...


def _host_allowed(url: str, allowed_hosts: tuple[str, ...]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == item.lower() or host.endswith("." + item.lower()) for item in allowed_hosts)


def _money(value: Any, *, required: bool = True) -> float | None:
    if value is None:
        if required:
            raise BrowserAgentError("Provider result did not include a premium.")
        return 0.0
    match = re.search(r"\d[\d,]*(?:\.\d{1,2})?", str(value).replace("\u00a0", " "))
    if not match:
        if required:
            raise BrowserAgentError("Could not read a numeric premium from the provider result.")
        return 0.0
    number = float(match.group(0).replace(",", ""))
    if number < 0 or number != number or number == float("inf"):
        raise BrowserAgentError("Provider returned an invalid premium.")
    return number


class PlaywrightQuoteAgent:
    """Runs one approved provider adapter in an isolated, short-lived browser context."""

    CHALLENGE_SELECTORS = (
        'iframe[src*="captcha"]',
        '[class*="captcha" i]',
        '[id*="captcha" i]',
        'input[name*="captcha" i]',
    )
    CHALLENGE_TEXT = re.compile(
        r"verify you are human|unusual traffic|security challenge|access denied|too many requests|captcha",
        re.I,
    )

    def __init__(self, navigation_retries: int = 2, timeout_ms: int = 25_000):
        self.navigation_retries = max(1, min(navigation_retries, 3))
        self.timeout_ms = max(5_000, min(timeout_ms, 45_000))

    async def run(self, adapter: QuoteProviderAdapter, form_data: dict[str, str]) -> BrowserQuote:
        results = await self.run_many([(adapter, form_data)], concurrency=1)
        result = results[0]
        if isinstance(result, Exception):
            raise result
        return result

    async def run_many(
        self,
        requests: list[tuple[QuoteProviderAdapter, dict[str, str]]],
        concurrency: int = 2,
    ) -> list[BrowserQuote | Exception]:
        """Run multiple provider pages concurrently inside one Chromium process."""
        if not requests:
            return []
        for adapter, _ in requests:
            if not _host_allowed(adapter.start_url, adapter.allowed_hosts):
                raise ProviderUnavailable(f"Provider '{adapter.provider_id}' start URL is not HTTPS or is outside its approved host list.")

        async with async_playwright() as playwright:
            browser: Browser = await playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            semaphore = asyncio.Semaphore(max(1, min(concurrency, 3)))
            try:
                async def run_one(adapter: QuoteProviderAdapter, form_data: dict[str, str]):
                    async with semaphore:
                        context: BrowserContext = await browser.new_context(
                            locale="en-US",
                            timezone_id="America/New_York",
                            viewport={"width": 1365, "height": 900},
                            accept_downloads=False,
                        )
                        try:
                            page = await context.new_page()
                            page.set_default_timeout(self.timeout_ms)
                            await self._navigate(page, adapter.start_url)
                            await self._check_manual_gate(page)

                            # Provider-specific adapter owns exact form semantics. No
                            # generic blind clicking on unknown pages is performed.
                            await adapter.prepare(page, form_data)
                            await self._check_manual_gate(page)

                            # Quote submission is adapter-specific and quote-only.
                            try:
                                await page.locator(adapter.submit_selector).click()
                            except PlaywrightTimeoutError as exc:
                                raise BrowserAgentError("Quote form submit control was not available.") from exc

                            result_selector = adapter.result_selectors.get("monthly_premium", "")
                            if not result_selector:
                                raise ProviderUnavailable("Adapter is missing a premium result selector.")
                            try:
                                await page.locator(result_selector).first.wait_for(state="visible", timeout=self.timeout_ms)
                            except PlaywrightTimeoutError:
                                await self._check_manual_gate(page)
                                raise BrowserAgentError("No quote result appeared before the provider page timed out.")

                            await self._check_manual_gate(page)
                            extracted = await adapter.extract(page)
                            premium = _money(extracted.get("monthly_premium"))
                            fees = _money(extracted.get("fees_monthly", 0), required=False) or 0.0
                            coverage = extracted.get("coverage") or {}
                            warnings = list(extracted.get("warnings") or [])
                            required_coverage = {
                                "bodily_injury_limit", "property_damage_limit",
                                "comp_deductible", "collision_deductible",
                            }
                            if not required_coverage.issubset(coverage) or any(not str(coverage.get(k, "")).strip() for k in required_coverage):
                                warnings.append("One or more coverage fields were not extracted; exact match cannot be confirmed.")
                            if extracted.get("vehicles") is None or extracted.get("drivers") is None:
                                warnings.append("Vehicle or driver count was not extracted; policy scope is unverified.")
                            status = "UNVERIFIED" if warnings else "EXTRACTED_NEEDS_COVERAGE_CHECK"

                            return BrowserQuote(
                                provider_id=adapter.provider_id,
                                company=str(extracted.get("company") or adapter.display_name),
                                monthly_premium=float(premium),
                                fees_monthly=float(fees),
                                coverage={key: str(value) for key, value in coverage.items()},
                                vehicles=extracted.get("vehicles"),
                                drivers=extracted.get("drivers"),
                                source_url=page.url,
                                retrieved_at=datetime.now(timezone.utc).isoformat(),
                                verification_status=status,
                                warnings=warnings,
                            )
                        finally:
                            await context.close()

                return await asyncio.gather(
                    *(run_one(adapter, data) for adapter, data in requests),
                    return_exceptions=True,
                )
            finally:
                await browser.close()

    async def _navigate(self, page: Page, url: str) -> None:
        last_error: Exception | None = None
        for attempt in range(self.navigation_retries):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5_000)
                except PlaywrightTimeoutError:
                    # Some insurer pages keep analytics connections open; DOM readiness
                    # is enough to let the provider-specific adapter inspect the form.
                    pass
                return
            except PlaywrightTimeoutError as exc:
                last_error = exc
                # Retry only navigation/load. Never repeat a quote-form submission.
                if attempt + 1 < self.navigation_retries:
                    await asyncio.sleep(1.0 + attempt)
        raise BrowserAgentError("Provider page could not finish loading.") from last_error

    async def _check_manual_gate(self, page: Page) -> None:
        for selector in self.CHALLENGE_SELECTORS:
            try:
                if await page.locator(selector).first.is_visible(timeout=250):
                    raise ManualInterventionRequired(
                        "The provider requires a human security check. Complete it manually; BestQoute will not bypass it."
                    )
            except PlaywrightTimeoutError:
                continue
        try:
            body_text = (await page.locator("body").inner_text(timeout=1_500))[:20_000]
        except PlaywrightTimeoutError:
            body_text = ""
        if self.CHALLENGE_TEXT.search(body_text):
            raise ManualInterventionRequired(
                "The provider displayed a security or access challenge. Human action is required."
            )
