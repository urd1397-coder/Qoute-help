"""Copy this template to implement one carrier adapter after authorized access is confirmed.

Do not add CAPTCHA solvers, stealth/fingerprint spoofing, credential stuffing, or logic
that repeats a quote submission after an ambiguous timeout. Use provider documentation
or a permitted quote flow, and stop for human security checks.
"""
from __future__ import annotations

from playwright.async_api import Page


class ExampleApprovedCarrier:
    provider_id = "replace_with_internal_id"
    display_name = "Replace with carrier name"
    start_url = "https://approved-carrier.example/auto/quote"
    allowed_hosts = ("approved-carrier.example",)

    # Map only fields that the carrier explicitly requests and the policyholder has
    # authorized. Never put SSNs, passwords, payment-card details, or license numbers
    # in logs. Sensitive fields should be entered through a secure, short-lived flow.
    field_selectors = {
        "state": "#state",
        "zip_code": "#zip",
        "vehicle_year": "#vehicle-year",
        "vehicle_make": "#vehicle-make",
        "vehicle_model": "#vehicle-model",
        "bodily_injury_limit": "#bi-limit",
        "property_damage_limit": "#pd-limit",
        "comp_deductible": "#comp-deductible",
        "collision_deductible": "#collision-deductible",
    }
    submit_selector = "button[type='submit']"  # quote-only button, never purchase/bind
    result_selectors = {
        "monthly_premium": "[data-testid='monthly-premium']",
    }

    async def prepare(self, page: Page, form_data: dict[str, str]) -> None:
        for key, selector in self.field_selectors.items():
            value = form_data.get(key)
            if value is None or value == "":
                continue
            locator = page.locator(selector)
            await locator.wait_for(state="visible")
            await locator.fill(str(value))

    async def extract(self, page: Page) -> dict:
        async def text(selector: str) -> str:
            return (await page.locator(selector).first.inner_text()).strip() if selector else ""

        return {
            "company": self.display_name,
            "monthly_premium": await text(self.result_selectors["monthly_premium"]),
            "fees_monthly": await text("[data-testid='monthly-fees']"),
            "coverage": {
                "bodily_injury_limit": await text("[data-testid='coverage-bi']"),
                "property_damage_limit": await text("[data-testid='coverage-pd']"),
                "comp_deductible": await text("[data-testid='coverage-comp']"),
                "collision_deductible": await text("[data-testid='coverage-collision']"),
            },
            "vehicles": None,
            "drivers": None,
        }
