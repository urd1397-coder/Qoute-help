# ============================================================
# الملف: app/models.py — نماذج البيانات والتحقق من المدخلات
# ما يفعله: يحدد شكل البيانات المقبولة (ملف المتسوّق، التغطية، عرض السعر، الطلب) ويرفض القيم غير المنطقية مثل السعر السالب.
# متى تعدّله: لإضافة سؤال جديد في الملف الشخصي أو لتغيير حدود الأرقام المسموحة.
# ============================================================
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ===== بيانات المتسوّق (الحقائق الصحيحة عنه فقط) =====
class Profile(BaseModel):
    """Truthful facts about the shopper. Only what is needed to check legitimate savings levers."""

    state: str = ""
    vehicles: int = Field(1, ge=1, le=10)
    drivers: int = Field(1, ge=1, le=10)
    annual_miles: Optional[int] = Field(None, ge=0, le=200000)
    oldest_vehicle_value: Optional[float] = Field(None, ge=0, le=1_000_000)
    days_before_renewal: Optional[int] = Field(None, ge=0, le=3650)

    homeowner: bool = False
    has_bundle_policy: bool = False  # home/renters/other policy that could be bundled
    employer_or_group: bool = False  # employer, alumni, union, professional group
    military: bool = False
    good_student: bool = False
    clean_record_3yr: bool = False  # no at-fault accidents/tickets in 3 years
    continuous_coverage: bool = False  # no lapse in coverage
    vehicle_safety_features: bool = False

    willing_telematics: bool = False
    willing_pay_in_full: bool = False
    autopay_ok: bool = True
    paperless_ok: bool = True
    willing_defensive_course: bool = False

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        return (v or "").strip().upper()[:2]


# ===== التغطية المطلوبة للمقارنة =====
class Coverage(BaseModel):
    bodily_injury_limit: str = Field("", max_length=30)
    property_damage_limit: str = Field("", max_length=30)
    comp_deductible: str = Field("", max_length=30)
    collision_deductible: str = Field("", max_length=30)


# ===== عرض سعر واحد من شركة تأمين =====
class Quote(BaseModel):
    company: str = Field(..., min_length=1, max_length=80)
    monthly_premium: float = Field(..., gt=0, lt=5000)
    fees_monthly: float = Field(0, ge=0, lt=1000)
    state: str = Field("", max_length=2)
    bodily_injury_limit: str = Field("", max_length=30)
    property_damage_limit: str = Field("", max_length=30)
    comp_deductible: str = Field("", max_length=30)
    collision_deductible: str = Field("", max_length=30)
    vehicles: Optional[int] = Field(None, ge=1, le=10)
    drivers: Optional[int] = Field(None, ge=1, le=10)
    applied_discounts: List[str] = Field(default_factory=list, max_length=40)
    quote_date: str = Field("", max_length=20)
    source: str = Field("", max_length=120)
    notes: str = Field("", max_length=500)


# ===== الطلب الكامل المرسَل إلى /api/compare =====
class CompareRequest(BaseModel):
    profile: Profile = Field(default_factory=Profile)
    quotes: List[Quote] = Field(..., min_length=1, max_length=50)
    target_monthly: float = Field(200, gt=0, lt=5000)
    desired_coverage: Coverage = Field(default_factory=Coverage)
