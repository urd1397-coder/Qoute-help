# ============================================================
# الملف: app/main.py — الخادم الرئيسي (واجهات API وتقديم الصفحة)
# ما يفعله: يشغّل تطبيق FastAPI ويعرض الصفحة الرئيسية ويوفّر نقاط الاتصال: /api/health و /api/levers و /api/compare و /api/import-csv.
# متى تعدّله: لإضافة نقطة API جديدة أو لتغيير حدود رفع ملف CSV.
# ============================================================
import csv
import io
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .engine import DISCLAIMER, compare
from .levers import LEVERS
from .models import CompareRequest, Quote

# ===== الإعدادات: مسار الملفات الثابتة وحدود ملف CSV =====
STATIC_DIR = Path(__file__).parent / "static"
MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 50

# ===== إنشاء التطبيق وربط مجلد الملفات الثابتة (CSS و JS) =====
app = FastAPI(title="BestQoute", version="0.3.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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


# ===== قائمة الخصومات والخيارات المتاحة =====
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
        if len(quotes) >= MAX_CSV_ROWS:
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
