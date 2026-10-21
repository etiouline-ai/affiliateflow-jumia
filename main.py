from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional
import html
import os
import re
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DB_PATH") or (BASE_DIR / "affiliateflow.db"))
PORT = int(os.environ.get("PORT") or 8000)
FB_PIXEL_ID = os.environ.get("FB_PIXEL_ID", "").strip() or "1390288544176312"
USD_TO_XOF = float(os.environ.get("USD_TO_XOF", "600"))

AD_PLATFORMS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "google": "Google Ads",
    "whatsapp": "WhatsApp Ads",
    "email": "Email",
    "organique": "Organique",
}

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

        CREATE TABLE IF NOT EXISTS ad_campaigns (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            link_id TEXT NOT NULL,
            audience TEXT DEFAULT '',
            budget REAL DEFAULT 0,
            daily_budget REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            clicks INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            revenue REAL DEFAULT 0,
            commission REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (link_id) REFERENCES affiliate_links(id)
        );

        CREATE TABLE IF NOT EXISTS ad_events (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            amount REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (campaign_id) REFERENCES ad_campaigns(id)
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
    brand_id = "systeme-io"
    affiliate_id = "etienne-samba-diouf"
    conn.execute(
        "INSERT INTO brands (id, name, niche, website, created_at) VALUES (?, ?, ?, ?, ?)",
        (brand_id, "Systeme.io", "Logiciel marketing", "systeme.io", now),
    )
    conn.execute(
        "INSERT INTO affiliates (id, name, email, company, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (affiliate_id, "Etienne Samba Diouf", "etiouline@gmail.com", "Systeme.io", "active", now),
    )

    catalog = [
        ("sys-startup", "AF-SYS-STARTUP", "Systeme.io Startup (27$/mois)", "Abonnement", 27.0, 0.60, "https://systeme.io/?sa=sa0023947314562614d0a980991bb60ef97b21813f"),
        ("sys-webinar", "AF-SYS-WEBINAR", "Systeme.io Webinar (47$/mois)", "Abonnement", 47.0, 0.60, "https://systeme.io/?sa=sa0023947314562614d0a980991bb60ef97b21813f"),
        ("sys-unlimited", "AF-SYS-UNLIMIT", "Systeme.io Unlimited (97$/mois)", "Abonnement", 97.0, 0.60, "https://systeme.io/?sa=sa0023947314562614d0a980991bb60ef97b21813f"),
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

    conn.execute(
        """
        INSERT INTO ad_campaigns (id, slug, name, platform, link_id, audience, budget, daily_budget, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """,
        (
            "campaign-meta-unlimited",
            "meta-senegal-systeme-io-unlimited",
            "Meta Senegal - Systeme.io Unlimited",
            "facebook",
            "link-sys-unlimited",
            "Entrepreneurs, e-commerce, marketing digital, freelancing",
            15000.0,
            1500.0,
            now,
        ),
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


class AdCampaignCreate(BaseModel):
    name: str = Field(..., min_length=2)
    platform: str = Field(default="facebook")
    link_id: str
    audience: str = Field(default="")
    budget: float = Field(ge=0)
    daily_budget: float = Field(ge=0)


class AdConversionCreate(BaseModel):
    amount: float = Field(ge=0)


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def read_index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "database": str(DB_PATH)}


@app.api_route("/api/ping", methods=["GET", "HEAD"])
def ping() -> dict:
    return {"pong": True}


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
def track_click(token: str, request: Request) -> RedirectResponse:
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

    campaign_slug = request.query_params.get("utm_campaign")
    source = request.query_params.get("utm_source") or "redirect"
    if campaign_slug:
        campaign = conn.execute("SELECT * FROM ad_campaigns WHERE slug = ?", (campaign_slug,)).fetchone()
        if campaign is not None:
            conn.execute("UPDATE ad_campaigns SET clicks = clicks + 1 WHERE id = ?", (campaign["id"],))
            conn.execute(
                "INSERT INTO ad_events (id, campaign_id, event_type, amount, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), campaign["id"], "click", 0.0, datetime.utcnow().isoformat()),
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


def _slugify(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:40]
    return base or "campagne"


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug = base
    suffix = 2
    while conn.execute("SELECT 1 FROM ad_campaigns WHERE slug = ?", (slug,)).fetchone() is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


@app.get("/api/campaigns")
def get_campaigns() -> list[dict]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT c.*, p.name as product_name, l.token, l.target_url, p.price, p.commission_rate
        FROM ad_campaigns c
        JOIN affiliate_links l ON l.id = c.link_id
        JOIN products p ON p.id = l.product_id
        ORDER BY c.created_at DESC
        """
    ).fetchall()
    conn.close()
    campaigns = []
    for row in rows:
        item = dict(row)
        item["platform_label"] = AD_PLATFORMS.get(item["platform"], item["platform"])
        item["ctr"] = round(float(item["clicks"]) / float(item["impressions"]) * 100, 2) if item["impressions"] else 0.0
        item["cpa"] = round(float(item["budget"]) / float(item["conversions"]), 2) if item["conversions"] else 0.0
        item["commission_xof"] = round(float(item["commission"]) * USD_TO_XOF, 0)
        item["roi"] = round(float(item["commission_xof"]) / float(item["budget"]) * 100, 1) if item["budget"] else 0.0
        campaigns.append(item)
    return campaigns


@app.post("/api/campaigns")
def create_campaign(payload: AdCampaignCreate, request: Request) -> dict:
    conn = get_db_connection()
    link = conn.execute("SELECT * FROM affiliate_links WHERE id = ?", (payload.link_id,)).fetchone()
    if link is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Link not found")

    slug = _unique_slug(conn, _slugify(payload.name))
    campaign_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO ad_campaigns (id, slug, name, platform, link_id, audience, budget, daily_budget, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """,
        (
            campaign_id,
            slug,
            payload.name,
            payload.platform,
            payload.link_id,
            payload.audience,
            payload.budget,
            payload.daily_budget,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    base = str(request.base_url).rstrip("/")
    utm = f"utm_source={payload.platform}&utm_medium=paid_social&utm_campaign={slug}"
    return {
        "id": campaign_id,
        "slug": slug,
        "ad_url": f"{base}/api/track/{link['token']}?{utm}",
        "landing_url": f"{base}/lp/{link['token']}?{utm}",
        "message": "Campaign created",
    }


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: str) -> dict:
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT c.*, p.name as product_name, l.token, p.price, p.commission_rate
        FROM ad_campaigns c
        JOIN affiliate_links l ON l.id = c.link_id
        JOIN products p ON p.id = l.product_id
        WHERE c.id = ?
        """,
        (campaign_id,),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Campaign not found")
    events = conn.execute(
        "SELECT * FROM ad_events WHERE campaign_id = ? ORDER BY created_at DESC LIMIT 50",
        (campaign_id,),
    ).fetchall()
    conn.close()
    campaign = dict(row)
    campaign["events"] = [dict(event) for event in events]
    return campaign


@app.post("/api/campaigns/{campaign_id}/conversions")
def create_campaign_conversion(campaign_id: str, payload: AdConversionCreate) -> dict:
    conn = get_db_connection()
    campaign = conn.execute("SELECT * FROM ad_campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if campaign is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Campaign not found")

    link = conn.execute("SELECT * FROM affiliate_links WHERE id = ?", (campaign["link_id"],)).fetchone()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (link["product_id"],)).fetchone()
    amount = float(payload.amount)
    commission_value = amount * float(product["commission_rate"])

    conn.execute(
        """
        UPDATE ad_campaigns
        SET conversions = conversions + 1, revenue = revenue + ?, commission = commission + ?
        WHERE id = ?
        """,
        (amount, commission_value, campaign_id),
    )
    conn.execute(
        "INSERT INTO ad_events (id, campaign_id, event_type, amount, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), campaign_id, "conversion", amount, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"message": "Conversion recorded", "commission": round(commission_value, 2)}


@app.post("/api/campaigns/{campaign_id}/status")
def update_campaign_status(campaign_id: str, status: str) -> dict:
    if status not in {"active", "paused", "archived"}:
        raise HTTPException(status_code=400, detail="Status must be active, paused or archived")
    conn = get_db_connection()
    conn.execute("UPDATE ad_campaigns SET status = ? WHERE id = ?", (status, campaign_id))
    conn.commit()
    conn.close()
    return {"message": "Status updated", "status": status}


@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str) -> dict:
    conn = get_db_connection()
    conn.execute("DELETE FROM ad_events WHERE campaign_id = ?", (campaign_id,))
    conn.execute("DELETE FROM ad_campaigns WHERE id = ?", (campaign_id,))
    conn.commit()
    conn.close()
    return {"message": "Campaign deleted", "id": campaign_id}


@app.get("/api/ads/config")
def get_ads_config() -> dict:
    return {
        "pixel_id": FB_PIXEL_ID,
        "pixel_active": bool(FB_PIXEL_ID),
        "platforms": [{"value": key, "label": value} for key, value in AD_PLATFORMS.items()],
        "playbook": [
            {
                "title": "Ciblage par interests",
                "detail": "Entrepreneurs, e-commerce, marketing digital, freelancing, gestion de business.",
            },
            {
                "title": "Audiences similaires (Lookalike)",
                "detail": "Cree un Lookalike 1% a partir des acheteurs Systeme.io : ils partagent le meme profil que tes clients payants.",
            },
            {
                "title": "Retargeting pixel",
                "detail": "Le pixel place sur la landing page (/lp/token) cree une audience de visiteurs a recibler sur Facebook et Instagram.",
            },
            {
                "title": "Budget test",
                "detail": "Demarre avec 1000-2000 FCFA par jour sur 7 jours. Coupe si aucun clic au bout de 500 impressions.",
            },
        ],
    }


LANDING_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         background:linear-gradient(160deg,#0f172a,#1e3a8a); color:#fff; min-height:100vh;
         display:flex; align-items:center; justify-content:center; padding:24px; }}
  .card {{ max-width:520px; width:100%; background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.16);
           border-radius:22px; padding:32px; text-align:center; }}
  .pill {{ display:inline-block; background:#22c55e; color:#052e16; font-weight:800; font-size:12px;
           padding:6px 12px; border-radius:999px; }}
  h1 {{ font-size:28px; line-height:1.2; margin:18px 0 10px; }}
  p {{ color:#cbd5e1; line-height:1.6; margin:0 0 22px; }}
  .cta {{ display:inline-block; background:#22c55e; color:#052e16; font-weight:800; text-decoration:none;
          padding:15px 30px; border-radius:12px; font-size:16px; }}
  .count {{ margin-top:18px; font-size:13px; color:#94a3b8; }}
  .bar {{ height:4px; background:rgba(255,255,255,.15); border-radius:99px; overflow:hidden; margin-top:20px; }}
  .bar span {{ display:block; height:100%; width:0; background:#22c55e; }}
</style>
{pixel}
</head>
<body>
  <div class="card">
    <span class="pill">{product_name}</span>
    <h1>{title}</h1>
    <p>{subtitle}</p>
    <a class="cta" id="cta" href="{target_url}" onclick="if(window.fbq)fbq('track','Lead');">Acceder a l'offre</a>
    <div class="count">Redirection automatique dans <span id="left">5</span> secondes</div>
    <div class="bar"><span id="bar"></span></div>
  </div>
  <script>
    var left = 5;
    var bar = document.getElementById('bar');
    setInterval(function () {{
      left -= 1;
      document.getElementById('left').textContent = left;
      bar.style.width = ((5 - left) * 20) + '%';
      if (left <= 0) window.location.href = "{target_url}";
    }}, 1000);
  </script>
</body>
</html>
"""


def _pixel_snippet() -> str:
    if not FB_PIXEL_ID:
        return ""
    pixel_id = html.escape(FB_PIXEL_ID, quote=True)
    return f"""<script>
!function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)}};if(!f._fbq)f._fbq=n;
n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}}(window,document,'script','https://connect.facebook.net/fr_FR/fbevents.js');
fbq('init', '{pixel_id}');
fbq('track', 'PageView');
fbq('track', 'ViewContent');
</script>
<noscript><img height="1" width="1" style="display:none" alt="" src="https://www.facebook.com/tr?id={pixel_id}&ev=PageView&noscript=1"/></noscript>"""


@app.get("/lp/{token}")
def landing_page(token: str, request: Request) -> HTMLResponse:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM affiliate_links WHERE token = ?", (token,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Tracking link not found")
    product = conn.execute("SELECT * FROM products WHERE id = ?", (row["product_id"],)).fetchone()

    campaign_slug = request.query_params.get("utm_campaign")
    if campaign_slug:
        campaign = conn.execute("SELECT * FROM ad_campaigns WHERE slug = ?", (campaign_slug,)).fetchone()
        if campaign is not None:
            conn.execute("UPDATE ad_campaigns SET impressions = impressions + 1 WHERE id = ?", (campaign["id"],))
            conn.execute(
                "INSERT INTO ad_events (id, campaign_id, event_type, amount, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), campaign["id"], "impression", 0.0, datetime.utcnow().isoformat()),
            )
    conn.commit()
    conn.close()

    product_name = html.escape(product["name"] if product else "Offre")
    title = html.escape(request.query_params.get("title") or f"{product_name} - Offre exclusive")
    subtitle = html.escape(
        request.query_params.get("subtitle")
        or "Acces immediat a l'offre. Paiement securise, annulation possible a tout moment."
    )
    target = html.escape(row["target_url"], quote=True)
    page = LANDING_TEMPLATE.format(
        title=title,
        product_name=product_name,
        subtitle=subtitle,
        target_url=target,
        pixel=_pixel_snippet(),
    )
    return HTMLResponse(content=page)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
