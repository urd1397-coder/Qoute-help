# ============================================================
# الملف: app/engine.py — محرك التوفير (قلب التطبيق)
# ما يفعله: يرتّب عروض الأسعار ويتحقق من تطابق التغطية ويقدّر التوفير من الخصومات ويكتب الحكم النهائي و"حزمة الشراء".
# متى تعدّله: لتغيير طريقة الحساب أو الحدود القصوى للخصومات (35% و 50%) أو نصوص الحكم.
# ============================================================
"""Lever engine: ranks user-entered quotes and estimates what legitimate levers could still save.

All estimates are rough and illustrative. The insurer's official quote is the source of truth.
"""
import re
from collections import Counter
from typing import Dict, List, Optional

from .levers import DISCOUNTS, LEVERS_BY_ID, PROGRAMS, TRADEOFFS, Lever
from .models import CompareRequest, Coverage, Profile, Quote

# ===== الإعدادات: الحد الأقصى لتراكم الخصومات =====
MAX_STACK_DISCOUNTS = 0.35  # discounts rarely stack beyond this
MAX_STACK_WITH_TRADEOFFS = 0.50

# ===== حقول التغطية التي تُقارَن بين العروض =====
COVERAGE_FIELDS = [
    ("bodily_injury_limit", "Bodily injury limit"),
    ("property_damage_limit", "Property damage limit"),
    ("comp_deductible", "Comprehensive deductible"),
    ("collision_deductible", "Collision deductible"),
]

# ===== نص إخلاء المسؤولية (يظهر أسفل الصفحة) =====
DISCLAIMER = (
    "Estimates are rough research leads based on typical industry ranges, not guaranteed prices. "
    "Only the insurer's official quote, run with your truthful information, is the real price. "
    "Never misstate or omit information on an application. This is not legal, financial, or insurance advice."
)


# ===== توحيد صيغ الحدود والمبالغ حتى تصحّ المقارنة =====
# ---------- normalization helpers ----------
# يحوّل صيغ حدود التغطية المختلفة إلى صيغة واحدة (مثل 100k/300k إلى 100/300)
def _norm_limit(value: str) -> str:
    """'100k/300k', '$100,000 / 300,000', '100/300' -> '100/300'."""
    if not value:
        return ""
    s = value.lower().replace("$", "").replace(",", "").replace(" ", "").replace("k", "")
    parts = []
    for part in s.split("/"):
        try:
            n = float(part)
            if n >= 1000:
                n /= 1000
            parts.append(str(int(n)) if n == int(n) else str(n))
        except ValueError:
            parts.append(part)
    return "/".join(parts)


# يحوّل المبالغ إلى صيغة موحّدة (بدون $ أو فواصل)
def _norm_money(value: str) -> str:
    if not value:
        return ""
    s = value.lower().replace("$", "").replace(",", "").strip()
    if s in {"none", "no", "n/a", "declined", "waived"}:
        return "none"
    try:
        n = float(s)
        return str(int(n)) if n == int(n) else str(n)
    except ValueError:
        return s


def _norm(field: str, value: str) -> str:
    return _norm_limit(value) if field in ("bodily_injury_limit", "property_damage_limit") else _norm_money(value)


# يحوّل المبلغ إلى رقم لاستخدامه في الحساب
def _money_to_float(value: str) -> Optional[float]:
    n = _norm_money(value)
    if n == "none":
        return 0.0
    try:
        return float(n)
    except ValueError:
        return None


# يحسب الأثر الإجمالي لعدة خصومات معاً مع الحد الأقصى
def _stack(fractions: List[float], cap: float) -> float:
    remaining = 1.0
    for f in fractions:
        remaining *= 1.0 - f
    return min(1.0 - remaining, cap)


# ===== التغطية المرجعية للمقارنة =====
# ---------- reference coverage ----------
def reference_coverage(quotes: List[Quote], desired: Coverage) -> Dict[str, str]:
    """Use what the shopper wants; otherwise the most common value among the quotes."""
    ref: Dict[str, str] = {}
    for field, _ in COVERAGE_FIELDS:
        wanted = getattr(desired, field, "")
        if wanted:
            ref[field] = wanted
            continue
        counts = Counter(_norm(field, getattr(q, field)) for q in quotes if getattr(q, field))
        if counts:
            top = counts.most_common(1)[0][0]
            original = next(getattr(q, field) for q in quotes if _norm(field, getattr(q, field)) == top)
            ref[field] = original
    return ref


def _lever_dict(lv: Lever) -> dict:
    return {"id": lv.id, "name": lv.name, "ask": lv.ask, "tip": lv.tip, "low": lv.low, "high": lv.high}


# ===== تحليل كل عرض سعر على حدة (التحذيرات، الخصومات، التقديرات) =====
# ---------- per-quote analysis ----------
def analyze_quote(q: Quote, profile: Profile, ref: Dict[str, str], target: float) -> dict:
    premium, fees = q.monthly_premium, q.fees_monthly
    effective = premium + fees
    applied_ids = set(q.applied_discounts)

    # Comparability checks
    warnings: List[str] = []
    comparable = True
    for field, label in COVERAGE_FIELDS:
        val = getattr(q, field)
        if not val:
            warnings.append(f"{label} not entered, so this quote can't be verified as comparable.")
        elif field in ref and _norm(field, val) != _norm(field, ref[field]):
            comparable = False
            warnings.append(f"{label} is {val}, but the comparison coverage is {ref[field]}. Not an apples-to-apples price.")
    if q.vehicles is not None and q.vehicles != profile.vehicles:
        comparable = False
        warnings.append(f"Quote covers {q.vehicles} vehicle(s) but your profile has {profile.vehicles}.")
    if q.drivers is not None and q.drivers != profile.drivers:
        comparable = False
        warnings.append(f"Quote covers {q.drivers} driver(s) but your profile has {profile.drivers}.")
    discount_ids = {lv.id for lv in DISCOUNTS}
    for did in sorted(applied_ids):
        if did not in discount_ids:
            warnings.append(f"Unknown discount id '{did}' was ignored.")

    # Discount levers: untapped = eligible per the profile and not already in the quote.
    # "Already applied" lists everything the quote says it includes, even if the profile
    # doesn't flag it, so the buy-ready packet still tells the shopper to confirm it.
    eligible = [lv for lv in DISCOUNTS if lv.eligible(profile)]
    untapped = [lv for lv in eligible if lv.id not in applied_ids]
    already = [lv for lv in DISCOUNTS if lv.id in applied_ids]

    cons = _stack([lv.low for lv in untapped], MAX_STACK_DISCOUNTS)
    expd = _stack([(lv.low + lv.high) / 2 for lv in untapped], MAX_STACK_DISCOUNTS)

    # Coverage tradeoffs (separate scenario, never mixed into the same-coverage numbers)
    ded_now = _money_to_float(q.collision_deductible)
    tradeoffs = []
    for lv in TRADEOFFS:
        if not lv.eligible(profile):
            continue
        if lv.id == "higher_deductible" and ded_now is not None and ded_now >= 1000:
            continue
        tradeoffs.append(lv)
    trade_exp = _stack(
        [(lv.low + lv.high) / 2 for lv in untapped] + [(lv.low + lv.high) / 2 for lv in tradeoffs],
        MAX_STACK_WITH_TRADEOFFS,
    )

    programs = [lv for lv in PROGRAMS if lv.eligible(profile)]

    def project(frac: float) -> float:
        return round(premium * (1 - frac) + fees, 2)

    projected = {
        "conservative": project(cons),
        "expected": project(expd),
        "with_tradeoffs": project(trade_exp),
    }

    return {
        "company": q.company,
        "source": q.source,
        "notes": q.notes,
        "monthly_premium": round(premium, 2),
        "fees_monthly": round(fees, 2),
        "effective_monthly": round(effective, 2),
        "annual_cost": round(effective * 12, 2),
        "comparable": comparable,
        "warnings": warnings,
        "coverage": {f: getattr(q, f) for f, _ in COVERAGE_FIELDS},
        "applied": [_lever_dict(lv) for lv in already],
        "untapped": [_lever_dict(lv) for lv in untapped],
        "tradeoffs": [_lever_dict(lv) for lv in tradeoffs],
        "programs": [_lever_dict(lv) for lv in programs],
        "projected": projected,
        "meets_target_now": effective <= target,
        "meets_target_conservative": projected["conservative"] <= target,
        "meets_target_expected": projected["expected"] <= target,
        "meets_target_with_tradeoffs": projected["with_tradeoffs"] <= target,
        "target_progress": round(min(target / effective, 1.0), 3),
    }


# ===== الحكم النهائي: هل نصل إلى الهدف الشهري؟ =====
# ---------- verdict ----------
def _verdict(best: dict, target: float) -> dict:
    gap_now = round(best["effective_monthly"] - target, 2)
    p = best["projected"]
    c = best["company"]
    if best["meets_target_now"]:
        return {"status": "under_target_now",
                "headline": f"{c} is already at ${best['effective_monthly']:.2f}/mo, under your ${target:.0f} target.",
                "detail": "Confirm the final price, fees and effective date with the insurer before buying.",
                "gap": gap_now}
    if best["meets_target_conservative"]:
        return {"status": "reachable",
                "headline": f"{c} looks reachable: about ${p['conservative']:.2f}/mo even with conservative discount estimates.",
                "detail": "Ask for every untapped discount by name when you get the official quote.",
                "gap": gap_now}
    if best["meets_target_expected"]:
        return {"status": "possible",
                "headline": f"{c} could reach about ${p['expected']:.2f}/mo if the typical discounts apply.",
                "detail": f"The conservative estimate is ${p['conservative']:.2f}/mo, so confirm each discount with the insurer.",
                "gap": gap_now}
    if best["meets_target_with_tradeoffs"]:
        return {"status": "possible_with_tradeoffs",
                "headline": f"Only reachable with coverage tradeoffs: about ${p['with_tradeoffs']:.2f}/mo.",
                "detail": f"Same-coverage estimate is ${p['expected']:.2f}/mo. Review the tradeoffs carefully before accepting them.",
                "gap": gap_now}
    gap_best = round(min(p["expected"], p["with_tradeoffs"]) - target, 2)
    return {"status": "gap",
            "headline": f"Lowest legal estimate is about ${p['expected']:.2f}/mo, ${p['expected'] - target:.2f} above your ${target:.0f} target.",
            "detail": "Add more quotes from other insurers, since the same profile can vary by hundreds between companies. "
                      "A $%.0f/mo full-coverage target may not be realistic for every profile or state." % target,
            "gap": gap_best}


# ===== حزمة الشراء الجاهزة لأخذها إلى شركة التأمين =====
# ---------- buy-ready packet ----------
def build_packet(best: dict, profile: Profile, ref: Dict[str, str], target: float, comparable_found: bool) -> dict:
    coverage_lines = []
    for field, label in COVERAGE_FIELDS:
        val = ref.get(field) or best["coverage"].get(field)
        if val:
            coverage_lines.append(f"{label}: {val}")

    ask_for = [lv["ask"] for lv in best["applied"]] + [lv["ask"] for lv in best["untapped"]]
    steps = [
        f"Go to {best['company']} directly (their website or an agent) and request an official quote.",
        "Enter your information exactly and truthfully: drivers, vehicles, garaging ZIP, mileage, and record.",
        "Request the same coverage limits and deductibles listed above so the price stays comparable.",
        "Ask for each discount listed above by name, and ask the agent which ones were applied.",
        "Compare the final price, including all fees, to the estimate before you pay.",
        "Confirm the effective date, and keep your current policy active until the new one starts so there's no lapse.",
    ]
    checks = [
        "Final monthly price (and total for the term) vs. your target.",
        "Fees: policy, installment, and any down payment.",
        "Which discounts were actually applied.",
        "Any telematics or program terms that could change your rate later.",
    ]
    if not comparable_found:
        checks.insert(0, "No fully comparable quote was found. Re-run with consistent coverage before buying.")

    lines = [f"BUY-READY PACKET: {best['company']}",
             f"Target: ${target:.0f}/mo | Current quote: ${best['effective_monthly']:.2f}/mo | "
             f"Estimated with levers: ${best['projected']['expected']:.2f}/mo",
             "", "COVERAGE TO REQUEST:"] + [f"- {c}" for c in coverage_lines] \
            + ["", "ASK FOR THESE DISCOUNTS BY NAME:"] + [f"- {a}" for a in ask_for] \
            + ["", "STEPS:"] + [f"{i}. {s}" for i, s in enumerate(steps, 1)] \
            + ["", "CHECK BEFORE PAYING:"] + [f"- {c}" for c in checks]
    return {
        "company": best["company"],
        "coverage_to_request": coverage_lines,
        "ask_for_discounts": ask_for,
        "steps": steps,
        "check_before_paying": checks,
        "text": "\n".join(lines),
    }


# ===== نقطة الدخول: دالة compare التي يستدعيها الخادم =====
# ---------- entry point ----------
def compare(req: CompareRequest) -> dict:
    ref = reference_coverage(req.quotes, req.desired_coverage)
    analyzed = [analyze_quote(q, req.profile, ref, req.target_monthly) for q in req.quotes]
    analyzed.sort(key=lambda r: (not r["comparable"], r["projected"]["expected"], r["effective_monthly"]))
    for i, r in enumerate(analyzed, 1):
        r["rank"] = i
    best = analyzed[0]
    comparable_found = best["comparable"]
    verdict = _verdict(best, req.target_monthly)
    if not comparable_found:
        verdict["detail"] += " Note: no quote matched the comparison coverage exactly."
    return {
        "target": req.target_monthly,
        "reference_coverage": ref,
        "verdict": verdict,
        "results": analyzed,
        "packet": build_packet(best, req.profile, ref, req.target_monthly, comparable_found),
        "disclaimer": DISCLAIMER,
    }
