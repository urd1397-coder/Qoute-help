# ============================================================
# الملف: app/main.py — الخادم الرئيسي (واجهات API وتقديم الصفحة)
# ما يفعله: يشغّل تطبيق FastAPI ويعرض الصفحة الرئيسية ويوفّر نقاط الاتصال: /api/health و /api/levers و /api/compare و /api/import-csv.
# متى تعدّله: لإضافة نقطة API جديدة أو لتغيير حدود رفع ملف CSV.
# ============================================================
import base64
import csv
import hmac
import io
import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator

from .engine import DISCLAIMER, compare
from .levers import LEVERS
from .models import CompareRequest, Quote



class BrowserSearchRequest(BaseModel):
    """Short-lived browser quote request; submitted values are never persisted."""
    provider_ids: list[str] = Field(..., min_length=1, max_length=5)
    form_data: dict[str, str] = Field(default_factory=dict)
    authorized_to_request_quote: bool = False

    @field_validator("form_data")
    @classmethod
    def _safe_form_data(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {
            "state", "zip_code", "annual_miles", "vehicles", "drivers",
            "vehicle_year", "vehicle_make", "vehicle_model",
            "bodily_injury_limit", "property_damage_limit",
            "comp_deductible", "collision_deductible", "driver_age_range",
        }
        blocked_terms = ("ssn", "social", "password", "license_number", "credit_card", "payment")
        cleaned = {}
        for key, raw in value.items():
            key = str(key).strip().lower()
            if key not in allowed or any(term in key for term in blocked_terms):
                raise ValueError(f"Unsupported browser form field: {key}")
            text = str(raw).strip()
            if len(text) > 160:
                raise ValueError(f"Browser form field is too long: {key}")
            cleaned[key] = text
        return cleaned


# ===== الإعدادات: مسار الملفات الثابتة وحدود ملف CSV =====
STATIC_DIR = Path(__file__).parent / "static"
MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 50

# ===== إنشاء التطبيق وربط مجلد الملفات الثابتة (CSS و JS) =====
app = FastAPI(title="BestQoute - Insurance Quote Optimizer", version="0.5.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ===== حماية الموقع بكلمة مرور: المالك فقط يفتح الموقع =====
# كلمة المرور تُضبط في Render كمتغير بيئة باسم BESTQOUTE_PASSWORD. إن لم تُضبط يبقى الموقع مقفلاً.
# مسار /api/health وحده يبقى مفتوحاً (يعيد {"status": "ok"} فقط) ليعمل فحص الصحة ومراقب التوقف.
OPEN_PATHS = {"/api/health"}


@app.middleware("http")
async def require_password(request: Request, call_next):
    if request.url.path in OPEN_PATHS:
        return await call_next(request)
    password = os.environ.get("BESTQOUTE_PASSWORD", "")
    if not password:
        return PlainTextResponse(
            "BestQoute is locked. Set the BESTQOUTE_PASSWORD environment variable in Render to open it.",
            status_code=503,
        )
    supplied = ""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
            supplied = decoded.partition(":")[2]  # the username is ignored; only the password counts
        except Exception:
            supplied = ""
    if not supplied or not hmac.compare_digest(supplied.encode("utf-8"), password.encode("utf-8")):
        return Response(
            "Password required.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="BestQoute", charset="UTF-8"'},
        )
    return await call_next(request)


# ===== الصفحة الرئيسية =====
@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index():
    """Home page. Accepts HEAD too, since uptime monitors may ping the root URL."""
    return FileResponse(STATIC_DIR / "index.html")


# ===== فحص الصحة (يستخدمه Render و UptimeRobot) =====
@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    """Cheap health check. Accepts HEAD too, because uptime monitors often ping with HEAD."""
    return {"status": "ok", "version": app.version}


# ===== البحث الآلي عبر واجهات شركات التأمين المصرّح بها =====
@app.get("/api/browser/providers")
def browser_providers():
    from .browser_jobs import provider_list
    return {
        "browser_automation": True,
        "engine": "Playwright Chromium",
        "providers": provider_list(),
        "message": (
            "No approved carrier browser adapters are configured yet. The browser engine is installed, "
            "but a carrier-specific adapter and authorized quote flow are required before live searches."
            if not provider_list() else "Approved browser quote providers are ready."
        ),
        "security": "No CAPTCHA or access-control bypass; human verification pauses the job; no purchase or binding actions.",
    }


@app.post("/api/browser/search", status_code=202)
async def start_browser_search(req: BrowserSearchRequest):
    if not req.authorized_to_request_quote:
        raise HTTPException(400, "Explicit authorization to request an insurance quote is required.")
    from .browser_jobs import create_job
    try:
        return await create_job(req.provider_ids, req.form_data)
    except ValueError as exc:
        raise HTTPException(503, str(exc))
    except RuntimeError as exc:
        raise HTTPException(429, str(exc))


@app.get("/api/browser/jobs/{job_id}")
def browser_job_status(job_id: str):
    from .browser_jobs import get_job
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Browser search job was not found or has expired after a server restart.")
    return job


# ===== قائمة الخصومات والخيارات المتاحة =====
@app.get("/api/search/status")
def search_status():
    """Report API and browser-search readiness without pretending quotes are live."""
    from .search_engine import provider_status
    from .browser_jobs import provider_list
    status = provider_status()
    status["browser_automation"] = {
        "engine": "Playwright Chromium",
        "enabled": bool(provider_list()),
        "providers": provider_list(),
    }
    return status


@app.get("/api/levers")
def levers():
    """Catalog of legitimate savings levers (illustrative ranges, not guarantees)."""
    return {
        "disclaimer": DISCLAIMER,
        "levers": [
            {"id": lv.id, "name": lv.name, "group": lv.group, "low": lv.low, "high": lv.high,
             "ask": lv.ask, "tip": lv.tip}
            for lv in LEVERS
        ],
    }


# ===== مقارنة عروض الأسعار وحساب التوفير =====
@app.post("/api/compare")
def compare_quotes(req: CompareRequest):
    return compare(req)


# ===== دالة مساعدة: تنظيف أسطر ملف CSV =====
def _clean(row: dict) -> dict:
    return {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}


# ===== استيراد عروض الأسعار من ملف CSV =====
@app.post("/api/import-csv")
async def import_csv(file: UploadFile = File(...)):
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV is too large (limit 1 MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 text.")

    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    missing = {"company", "state", "monthly_premium"} - headers
    if missing:
        raise HTTPException(400, f"Missing required column(s): {', '.join(sorted(missing))}")

    quotes, errors = [], []
    for i, row in enumerate(reader, start=2):
        if i - 2 >= MAX_CSV_ROWS:
            errors.append({"row": i, "error": f"Row limit of {MAX_CSV_ROWS} reached; remaining rows skipped."})
            break
        r = _clean(row)
        try:
            data = {
                "company": r.get("company", ""),
                "state": r.get("state", "")[:2].upper(),
                "monthly_premium": float(r.get("monthly_premium", "").replace("$", "").replace(",", "")),
                "fees_monthly": float((r.get("fees_monthly") or "0").replace("$", "").replace(",", "")),
                "bodily_injury_limit": r.get("bodily_injury_limit", ""),
                "property_damage_limit": r.get("property_damage_limit", ""),
                "comp_deductible": r.get("comp_deductible", ""),
                "collision_deductible": r.get("collision_deductible", ""),
                "quote_date": r.get("quote_date", ""),
                "source": r.get("source", ""),
                "notes": r.get("notes", ""),
                "applied_discounts": [d.strip() for d in r.get("applied_discounts", "").split(";") if d.strip()],
            }
            if r.get("vehicles"):
                data["vehicles"] = int(r["vehicles"])
            if r.get("drivers"):
                data["drivers"] = int(r["drivers"])
            quotes.append(Quote(**data).model_dump())
        except (ValueError, ValidationError) as exc:
            errors.append({"row": i, "error": str(exc).splitlines()[0][:160]})
    return {"quotes": quotes, "errors": errors}
