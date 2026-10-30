# ============================================================
# الملف: app/levers.py — قائمة الخصومات والخيارات (قابلة للتعديل)
# ما يفعله: يعرّف كل "رافعة توفير": خصومات بنفس التغطية، وتنازلات في التغطية، وبرامج الولايات. لكل واحدة نسبة توفير دنيا وعليا وشرط أهلية.
# متى تعدّله: لتعديل نسب التوفير أو إضافة خصم جديد (أضِف سطر Lever جديداً داخل LEVERS).
# ============================================================
"""Catalog of legitimate savings levers.

Every lever here is a lawful, truthful way to lower a premium. Percentages are rough,
illustrative industry ranges, NOT guarantees: each insurer sets its own discounts and
they vary by state. The official insurer quote is always the source of truth.
"""
from dataclasses import dataclass
from typing import Callable, List

from .models import Profile


# ===== شكل بيانات الرافعة الواحدة =====
@dataclass(frozen=True)
class Lever:
    id: str
    name: str
    group: str  # "discount" | "tradeoff" | "program"
    low: float  # conservative fractional savings
    high: float  # optimistic fractional savings
    ask: str  # how to ask for it, by name
    tip: str
    eligible: Callable[[Profile], bool]


# ===== دالة مساعدة: هل ولاية المتسوّق ضمن القائمة؟ =====
def _state(p: Profile, *states: str) -> bool:
    return p.state in states


# ===== القائمة الرئيسية للخصومات والخيارات =====
LEVERS: List[Lever] = [
    # --- أولاً: الخصومات (نفس التغطية بسعر أقل) ---
    # ---- Discounts (same coverage, lower price) ----
    Lever("bundle", "Bundle with home/renters", "discount", 0.05, 0.15,
          "Multi-policy (bundle) discount",
          "Ask for a bundled quote even if you only have renters insurance.",
          lambda p: p.homeowner or p.has_bundle_policy),
    Lever("multi_car", "Multi-car", "discount", 0.05, 0.20,
          "Multi-car discount",
          "Put every household vehicle on one policy and compare.",
          lambda p: p.vehicles >= 2),
    Lever("telematics", "Telematics / usage-based", "discount", 0.05, 0.25,
          "Usage-based / telematics program",
          "Many programs give a sign-up discount; some can raise rates for risky driving, so read the terms.",
          lambda p: p.willing_telematics),
    Lever("pay_in_full", "Pay in full", "discount", 0.04, 0.10,
          "Paid-in-full discount",
          "Compare the 6-month or 12-month upfront price against monthly installments and fees.",
          lambda p: p.willing_pay_in_full),
    Lever("autopay", "Autopay / EFT", "discount", 0.02, 0.05,
          "Automatic payment (EFT) discount",
          "Small but usually easy; also avoids installment fees at some companies.",
          lambda p: p.autopay_ok),
    Lever("paperless", "Paperless / e-sign", "discount", 0.01, 0.03,
          "Paperless / e-delivery discount",
          "Quick win at many insurers.",
          lambda p: p.paperless_ok),
    Lever("good_student", "Good student", "discount", 0.05, 0.15,
          "Good student discount",
          "Usually needs a B average or better; have a transcript ready.",
          lambda p: p.good_student),
    Lever("low_mileage", "Low mileage", "discount", 0.05, 0.15,
          "Low-mileage / pay-per-mile pricing",
          "Be accurate: some insurers verify mileage. Under ~7,500 miles a year often qualifies.",
          lambda p: p.annual_miles is not None and p.annual_miles < 7500),
    Lever("defensive_course", "Defensive driving course", "discount", 0.05, 0.10,
          "Defensive driving course discount",
          "Check that the course is approved for a discount in your state and with that insurer.",
          lambda p: p.willing_defensive_course),
    Lever("homeowner", "Homeowner", "discount", 0.03, 0.10,
          "Homeowner discount",
          "Some insurers give it even if the home is insured elsewhere.",
          lambda p: p.homeowner),
    Lever("group", "Employer / alumni / professional group", "discount", 0.03, 0.10,
          "Affiliation or employer group discount",
          "Give your employer, alumni association, union or professional group by name.",
          lambda p: p.employer_or_group),
    Lever("military", "Military / veteran", "discount", 0.05, 0.15,
          "Military or veteran discount",
          "Some insurers are built around military members; always request quotes from them.",
          lambda p: p.military),
    Lever("early_shopper", "Early shopper", "discount", 0.05, 0.10,
          "Advance purchase / early shopper discount",
          "Many insurers reward quoting about 1 to 4 weeks before the start date. Rules vary.",
          lambda p: p.days_before_renewal is not None and p.days_before_renewal >= 7),
    Lever("claim_free", "Claim-free / safe driver", "discount", 0.05, 0.15,
          "Claim-free / safe driver discount",
          "Applies when your record is clean; confirm the look-back period.",
          lambda p: p.clean_record_3yr),
    Lever("continuous", "Continuous coverage", "discount", 0.03, 0.10,
          "Prior insurance / continuous coverage discount",
          "Avoid any lapse in coverage; lapses can raise rates.",
          lambda p: p.continuous_coverage),
    Lever("vehicle_safety", "Vehicle safety / anti-theft", "discount", 0.02, 0.08,
          "Anti-theft, airbag and safety feature discounts",
          "List every safety feature on each vehicle.",
          lambda p: p.vehicle_safety_features),

    # --- ثانياً: تنازلات في التغطية (أرخص لكن مخاطرة أكبر) ---
    # ---- Coverage tradeoffs (cheaper, but you take on more risk) ----
    Lever("higher_deductible", "Higher deductible ($1,000)", "tradeoff", 0.10, 0.25,
          "Quote comp/collision at $1,000 deductible",
          "Only if you could pay that amount out of pocket after a claim.",
          lambda p: True),
    Lever("drop_collision", "Drop collision on an old, low-value car", "tradeoff", 0.15, 0.30,
          "Quote without collision on the older vehicle",
          "Often not worth it when a year of collision costs close to the car's value. Applies to that car only.",
          lambda p: p.oldest_vehicle_value is not None and p.oldest_vehicle_value <= 3000),
    Lever("pa_limited_tort", "Pennsylvania limited tort option", "tradeoff", 0.05, 0.15,
          "Limited tort option (PA)",
          "Lowers price but limits your right to sue for pain and suffering. Understand it first.",
          lambda p: _state(p, "PA")),
    Lever("nj_limited_suit", "New Jersey limited right to sue", "tradeoff", 0.05, 0.15,
          "Limited right to sue option (NJ)",
          "Lowers price but restricts lawsuits for non-economic damages. Understand it first.",
          lambda p: _state(p, "NJ")),
    Lever("mi_pip_level", "Michigan PIP medical coverage level", "tradeoff", 0.05, 0.20,
          "Lower PIP medical coverage level (MI)",
          "Depends on your health coverage; choosing a lower level has real risk if you are not covered elsewhere.",
          lambda p: _state(p, "MI")),

    # --- ثالثاً: برامج الولايات (للاطلاع على الأهلية فقط) ---
    # ---- State programs (check eligibility; not counted in estimates) ----
    Lever("ca_clca", "California Low Cost Auto program", "program", 0.0, 0.0,
          "California Low Cost Auto (CLCA) program",
          "Income and vehicle-value limits apply. Check eligibility with the California Department of Insurance.",
          lambda p: _state(p, "CA")),
    Lever("nj_sap", "New Jersey Special Automobile Insurance Policy", "program", 0.0, 0.0,
          "New Jersey Special Automobile Insurance Policy",
          "Very limited eligibility. Check with the New Jersey Department of Banking and Insurance.",
          lambda p: _state(p, "NJ")),
]

# ===== فهارس سريعة للبحث حسب المعرّف والمجموعة =====
LEVERS_BY_ID = {lv.id: lv for lv in LEVERS}
DISCOUNTS = [lv for lv in LEVERS if lv.group == "discount"]
TRADEOFFS = [lv for lv in LEVERS if lv.group == "tradeoff"]
PROGRAMS = [lv for lv in LEVERS if lv.group == "program"]
