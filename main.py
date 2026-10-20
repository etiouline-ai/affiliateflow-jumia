from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional
import os
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DB_PATH") or (BASE_DIR / "affiliateflow.db"))
PORT = int(os.environ.get("PORT") or 8000)

app = FastAPI(title="AffiliateFlow MVP", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def get_db_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS brands (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            niche TEXT,
            website TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS affiliates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            company TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            brand_id TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            price REAL,
            commission_rate REAL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        );

        CREATE TABLE IF NOT EXISTS affiliate_links (
            id TEXT PRIMARY KEY,
            affiliate_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            target_url TEXT NOT NULL,
            clicks INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            revenue REAL DEFAULT 0,
            commission REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (affiliate_id) REFERENCES affiliates(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS stats (
            id TEXT PRIMARY KEY,
            link_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source TEXT,
            amount REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (link_id) REFERENCES affiliate_links(id)
        );
        """
    )
    conn.commit()
    conn.close()

    seed_demo_data()


def seed_demo_data() -> None:
    conn = get_db_connection()
    if conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0] > 0:
        conn.close()
        return

    now = datetime.utcnow().isoformat()
    brand_id = "jumia-partenaires"
    affiliate_id = "etienne-samba-diouf"
    conn.execute(
        "INSERT INTO brands (id, name, niche, website, created_at) VALUES (?, ?, ?, ?, ?)",
        (brand_id, "Jumia Partenaires", "E-commerce", "jumia.com.sn", now),
    )
    conn.execute(
        "INSERT INTO affiliates (id, name, email, company, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (affiliate_id, "Etienne Samba Diouf", "etiouline@gmail.com", "Jumia", "active", now),
    )

    catalog = [
        ("jumia-smartphone", "AF-bd17bc09-770", "Smartphone Android 64 Go", "High-tech", 45000.0, 0.05, "https://jumia.com.sn/smartphones/"),
        ("jumia-montre", "AF-a7daaa83-573", "Montre connectee", "High-tech", 18000.0, 0.05, "https://jumia.com.sn/montres/"),
        ("jumia-casque", "AF-51be0c7d-0f3", "Casque Bluetooth sans fil", "High-tech", 12500.0, 0.05, "https://jumia.com.sn/casques/"),
        ("jumia-powerbank", "AF-96aa26c2-db7", "Powerbank 20000 mAh", "Accessoires", 9500.0, 0.05, "https://jumia.com.sn/powerbanks/"),
        ("jumia-beaute", "AF-01974db1-d4d", "Produits beaute et soin", "Beaute", 8000.0, 0.05, "https://jumia.com.sn/beaute/"),
    ]
    for product_id, token, name, category, price, rate, url in catalog:
        conn.execute(
            "INSERT INTO products (id, brand_id, name, category, price, commission_rate, url, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (product_id, brand_id, name, category, price, rate, url, now),
        )
        conn.execute(
            "INSERT INTO affiliate_links (id, affiliate_id, product_id, token, target_url, clicks, conversions, revenue, commission, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"link-{product_id}", affiliate_id, product_id, token, url, 0, 0, 0.0, 0.0, now),
        )

    conn.commit()
    conn.close()


class BrandCreate(BaseModel):
    name: str = Field(..., min_length=2)
    niche: str = Field(default="General")
    website: str = Field(..., min_length=5)


class AffiliateCreate(BaseModel):
    name: str = Field(..., min_length=2)
    email: str = Field(..., min_length=5)
    company: str = Field(default="")


class ProductCreate(BaseModel):
    brand_id: str
    name: str = Field(..., min_length=2)
    category: str = Field(default="General")
    price: float = Field(ge=0)
    commission_rate: float = Field(ge=0, le=1)
    url: str = Field(..., min_length=5)


class LinkCreate(BaseModel):
    affiliate_id: str
    product_id: str
    target_url: str = Field(..., min_length=5)
    source: str = Field(default="social")


class ConversionCreate(BaseModel):
    link_id: str
    amount: float = Field(ge=0)
    source: str = Field(default="newsletter")


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def read_index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "database": str(DB_PATH)}


@app.get("/api/dashboard")
def get_dashboard() -> dict:
    conn = get_db_connection()
    brands = conn.execute("SELECT COUNT(*) as value FROM brands").fetchone()["value"]
    affiliates = conn.execute("SELECT COUNT(*) as value FROM affiliates").fetchone()["value"]
    products = conn.execute("SELECT COUNT(*) as value FROM products").fetchone()["value"]
    clicks = conn.execute("SELECT COALESCE(SUM(clicks), 0) as value FROM affiliate_links").fetchone()["value"]
    revenue = conn.execute("SELECT COALESCE(SUM(revenue), 0) as value FROM affiliate_links").fetchone()["value"]
    commissions = conn.execute("SELECT COALESCE(SUM(commission), 0) as value FROM affiliate_links").fetchone()["value"]
    recent_links = conn.execute(
        """
        SELECT l.id, l.token, p.name as product_name, a.name as affiliate_name, l.clicks, l.conversions, l.revenue, l.commission
        FROM affiliate_links l
        JOIN products p ON p.id = l.product_id
        JOIN affiliates a ON a.id = l.affiliate_id
        ORDER BY l.created_at DESC
        LIMIT 5
        """
    ).fetchall()
    conn.close()
    return {
        "summary": {
            "brands": brands,
            "affiliates": affiliates,
            "products": products,
            "clicks": clicks,
            "revenue": round(float(revenue), 2),
            "commissions": round(float(commissions), 2),
        },
        "recent_links": [dict(row) for row in recent_links],
    }


@app.get("/api/brands")
def get_brands() -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM brands ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/brands")
def create_brand(payload: BrandCreate) -> dict:
    conn = get_db_connection()
    brand_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO brands (id, name, niche, website, created_at) VALUES (?, ?, ?, ?, ?)",
        (brand_id, payload.name, payload.niche, payload.website, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"id": brand_id, "message": "Brand created"}


@app.get("/api/affiliates")
def get_affiliates() -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM affiliates ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/affiliates")
def create_affiliate(payload: AffiliateCreate) -> dict:
    conn = get_db_connection()
    affiliate_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO affiliates (id, name, email, company, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (affiliate_id, payload.name, payload.email, payload.company, "active", datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"id": affiliate_id, "message": "Affiliate created"}


@app.get("/api/products")
def get_products() -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT p.*, b.name as brand_name
        FROM products p
        LEFT JOIN brands b ON b.id = p.brand_id
        ORDER BY p.created_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/products")
def create_product(payload: ProductCreate) -> dict:
    conn = get_db_connection()
    product_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO products (id, brand_id, name, category, price, commission_rate, url, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (product_id, payload.brand_id, payload.name, payload.category, payload.price, payload.commission_rate, payload.url, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"id": product_id, "message": "Product created"}


@app.get("/api/links")
def get_links() -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT l.*, p.name as product_name, a.name as affiliate_name
        FROM affiliate_links l
        JOIN products p ON p.id = l.product_id
        JOIN affiliates a ON a.id = l.affiliate_id
        ORDER BY l.created_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/links")
def create_link(payload: LinkCreate, request: Request) -> dict:
    conn = get_db_connection()
    token = "AF-" + str(uuid.uuid4())[:12]
    route_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO affiliate_links (id, affiliate_id, product_id, token, target_url, clicks, conversions, revenue, commission, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (route_id, payload.affiliate_id, payload.product_id, token, payload.target_url, 0, 0, 0.0, 0.0, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    base = str(request.base_url).rstrip("/")
    return {"id": route_id, "token": token, "tracking_url": f"{base}/api/track/{token}"}


@app.get("/api/track/{token}")
def track_click(token: str) -> RedirectResponse:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM affiliate_links WHERE token = ?", (token,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Tracking link not found")

    clicks = int(row["clicks"]) + 1
    conn.execute("UPDATE affiliate_links SET clicks = ? WHERE id = ?", (clicks, row["id"]))
    conn.execute(
        "INSERT INTO stats (id, link_id, event_type, source, amount, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), row["id"], "click", "redirect", 0.0, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url=row["target_url"])


@app.post("/api/conversions")
def record_conversion(payload: ConversionCreate) -> dict:
    conn = get_db_connection()
    link = conn.execute("SELECT * FROM affiliate_links WHERE id = ?", (payload.link_id,)).fetchone()
    if link is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Link not found")

    product = conn.execute("SELECT * FROM products WHERE id = ?", (link["product_id"],)).fetchone()
    if product is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")

    new_conversions = int(link["conversions"]) + 1
    commission_value = float(payload.amount) * float(product["commission_rate"])
    new_revenue = float(link["revenue"]) + float(payload.amount)
    new_commission = float(link["commission"]) + commission_value

    conn.execute(
        "UPDATE affiliate_links SET conversions = ?, revenue = ?, commission = ? WHERE id = ?",
        (new_conversions, new_revenue, new_commission, link["id"]),
    )
    conn.execute(
        "INSERT INTO stats (id, link_id, event_type, source, amount, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), link["id"], "conversion", payload.source, payload.amount, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return {
        "message": "Conversion recorded",
        "amount": payload.amount,
        "commission": round(commission_value, 2),
    }


@app.get("/api/stats")
def get_stats() -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM stats ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/api/brands/{brand_id}")
def get_brand(brand_id: str) -> dict:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM brands WHERE id = ?", (brand_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Brand not found")
    return dict(row)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
