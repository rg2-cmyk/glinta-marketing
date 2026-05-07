import sys
from datetime import date, timedelta, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from shared.styles import COLORS, inject_css, plot_theme, top_nav, campaign_context_card
from shared.data import load_data, fmt_revenue

# ── Google Drive integration (graceful degradation if creds unavailable) ─────
try:
    from shared import drive as _gdrive
    _DRIVE_AVAILABLE = True
except Exception:
    _gdrive = None
    _DRIVE_AVAILABLE = False

# ── Current user (used for save/review attribution) ──────────────────────────
CURRENT_USER = "Riddhima Goel"

inject_css()
top_nav("Content Generation")

# Seed plan_added from sheet if Planning hasn't synced yet this session
if st.session_state.get("_last_sheet_sync") is None:
    try:
        from shared.sheets import load_all_campaigns as _load_all
        _p, _d = _load_all()
        st.session_state["plan_added"]  = _p
        st.session_state["plan_drafts"] = _d
        st.session_state["_last_sheet_sync"] = date.today()
    except Exception:
        st.session_state.setdefault("plan_added", [])
        st.session_state.setdefault("plan_drafts", [])

st.markdown("<h1>Generation</h1>", unsafe_allow_html=True)

# ── Data connections banner ───────────────────────────────────────────────────
st.markdown(
    '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
    'font-weight:800;letter-spacing:0.12em;text-transform:uppercase;'
    'color:#888;margin:4px 0 8px;">Data connections</div>',
    unsafe_allow_html=True,
)

_GEN_STATUS_STYLE = {
    "mock data":     ("background:#f5f000;color:#000;",  "Mock data"),
    "connected":     ("background:#caf30b;color:#000;",  "Connected"),
    "not connected": ("background:#f2f2f2;color:#888;",  "Not connected"),
    "tbd":           ("background:#e8c5ff;color:#000;",  "Connection Unknown"),
}

_GEN_CONNECTIONS = [
    {
        "abbr":   "GD",
        "color":  "#1a73e8",
        "name":   "Drive",
        "status": "not connected",
        "what":   "All finalized copy and briefs saved to Drive for commenting and editing",
        "why":    "Team can approve via Copilot or Drive — edits sync back automatically",
    },
    {
        "abbr":   "Air",
        "color":  "#1C1C1E",
        "name":   "Air / Dropbox",
        "status": "not connected",
        "what":   "Reference and pull campaign assets; share direct links with the design team",
        "why":    "Design brief includes asset links from your creative library — no extra steps",
    },
    {
        "abbr":   "AS",
        "color":  "#F06A6A",
        "name":   "Asana",
        "status": "not connected",
        "what":   "Push design brief tasks to Asana; assign owners and set due dates",
        "why":    "Brief flows directly into project management — no copy-paste handoff",
    },
    {
        "abbr":   "BL",
        "color":  "#5B4FCF",
        "name":   "Brand & Legal",
        "status": "not connected",
        "what":   "Brand voice, tone guidelines, and legal copy rules used to ground all AI generation",
        "why":    "Copy stays on-brand and legally compliant without manual review every draft",
    },
]

_gen_conn_html = (
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;'
    'margin-bottom:14px;">'
)
for _gc in _GEN_CONNECTIONS:
    _gst_css, _gst_lbl = _GEN_STATUS_STYLE.get(
        _gc["status"], ("background:#eee;color:#666;", _gc["status"])
    )
    _gen_conn_html += (
        f'<div style="border:1.5px solid #e4e4e4;border-radius:8px;padding:12px 14px;'
        f'background:#fff;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        f'<span style="background:{_gc["color"]};color:#fff;border-radius:5px;'
        f'width:26px;height:26px;display:inline-flex;align-items:center;justify-content:center;'
        f'font-family:\'Barlow Condensed\',sans-serif;font-size:10px;font-weight:900;'
        f'letter-spacing:0.04em;flex-shrink:0;">{_gc["abbr"]}</span>'
        f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:13px;'
        f'font-weight:800;letter-spacing:0.04em;color:#000;">{_gc["name"]}</span>'
        f'<span style="margin-left:auto;{_gst_css}border-radius:4px;padding:1px 7px;'
        f'font-size:9px;font-weight:700;white-space:nowrap;font-family:Barlow,sans-serif;'
        f'letter-spacing:0.04em;text-transform:uppercase;">{_gst_lbl}</span>'
        f'</div>'
        f'<div style="font-family:Barlow,sans-serif;font-size:11px;font-weight:600;'
        f'color:#000;margin-bottom:3px;line-height:1.4;">{_gc["what"]}</div>'
        f'<div style="font-family:Barlow,sans-serif;font-size:10px;color:#888;line-height:1.4;">'
        f'{_gc["why"]}</div>'
        f'</div>'
    )
_gen_conn_html += '</div>'
st.markdown(_gen_conn_html, unsafe_allow_html=True)

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ── Load historical performance data (used for subject-line grounding) ───────
campaigns_df, *_ = load_data()
_cdf = campaigns_df.dropna(subset=["Send Date"]).copy()
_cdf["_date"] = _cdf["Send Date"].dt.date


# ── Build the list of campaigns the user can edit ────────────────────────────
# Source 1: campaigns scheduled in the historical data with send_date >= today
# Source 2: campaigns the user added in Planning → Plan a Campaign (plan_added)
# Mirrors the Planning → Upcoming Campaigns tab. No mock fixtures.
def _normalize_data_row(row, idx):
    auds = []
    if pd.notna(row.get("Audiences")):
        auds = [a.strip() for a in str(row["Audiences"]).split(",") if a.strip()]
    recipients = row.get("Recipients", 0)
    revenue    = row.get("Revenue", 0)
    return {
        "id":          str(row.get("Campaign ID", f"D{idx:04d}")),
        "name":        str(row.get("Campaign Name", "(unnamed)")),
        "category":    str(row.get("Category", "")) or "Editorial",
        "channel":     str(row.get("Channel", "email")).lower() or "email",
        "send_date":   row["_date"],
        "phase":       "planning",
        "tags":        [],
        "segment":     ", ".join(auds) if auds else "—",
        "audience_est": int(recipients) if pd.notna(recipients) else 0,
        "subject_line_draft": str(row.get("Subject Line", "") or ""),
        "revenue_est": float(revenue) if pd.notna(revenue) else 0.0,
        "assigned_to": "—",
        "brief_status": "Not Started",
        "design_status": "Not Started",
        "qa_status":    "Not Started",
        "priority":     "Medium",
        "category_tag": str(row.get("Category", "")).lower().replace(" ", "_"),
        # extra fields used by Generation
        "audiences":    auds,
        "product":      str(row.get("Primary Product", "") or ""),
        "studio":       str(row.get("Primary Studio", "") or ""),
        "goal":         "",
        "_source":      "scheduled",
    }


def _normalize_planned(p):
    auds = p.get("audiences", []) or []
    return {
        "id":          p["id"],
        "name":        p["name"],
        "category":    p.get("category", "Editorial"),
        "channel":     p.get("channel", "email"),
        "send_date":   p["send_date"],
        "phase":       "planning",
        "tags":        [p.get("goal", "")],
        "segment":     ", ".join(auds) if auds else "—",
        "audience_est": 0,
        "subject_line_draft": p.get("subject", ""),
        "revenue_est": 0.0,
        "assigned_to": "Unassigned",
        "brief_status": "Not Started",
        "design_status": "Not Started",
        "qa_status":   "Not Started",
        "priority":    "Medium",
        "category_tag": p.get("category", "ed").lower().replace(" ", "_"),
        "audiences":   auds,
        "product":     p.get("product", ""),
        "studio":      p.get("studio", ""),
        "goal":        p.get("goal", ""),
        "_source":     "planned",
    }


_today = date.today()
_data_upcoming = _cdf[_cdf["_date"] >= _today].sort_values("Send Date")
all_campaigns = (
    [_normalize_data_row(r, i) for i, (_, r) in enumerate(_data_upcoming.iterrows())]
    + [_normalize_planned(p) for p in st.session_state.get("plan_added", [])]
)
all_campaigns.sort(key=lambda c: c["send_date"])


# ── Empty state if no upcoming campaigns ─────────────────────────────────────
if not all_campaigns:
    st.markdown(
        f'<div style="border:2px dashed {COLORS["border"]};border-radius:10px;'
        f'padding:32px 24px;text-align:center;background:{COLORS["offwhite"]};'
        f'margin:20px 0;">'
        f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.1rem;'
        f'font-weight:700;letter-spacing:0.04em;text-transform:uppercase;'
        f'margin-bottom:8px;">No upcoming campaigns</div>'
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.9rem;'
        f'color:{COLORS["muted"]};line-height:1.5;">'
        f'Generation pulls from Planning → Upcoming Campaigns. '
        f'Add a campaign there first, then come back here to draft copy.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_Planning.py", label="→ Go to Planning")
    st.stop()


def _camp_label(c):
    tag = " · planned" if c.get("_source") == "planned" else " · scheduled"
    return f"{c['name']}{tag}"

camp_labels = [_camp_label(c) for c in all_campaigns]

active_id = st.session_state.get("active_campaign_id", all_campaigns[0]["id"])
active_idx = next((i for i, c in enumerate(all_campaigns) if c["id"] == active_id), 0)

# ── Per-campaign color constants (used in tab_brief expanders) ───────────────
_AIR_COLOR   = "#1C1C1E"   # Air brand near-black
_DBX_COLOR   = "#0061FF"   # Dropbox blue
_ASANA_COLOR = "#F06A6A"   # Asana coral


def _mock_assets_for_campaign(camp):
    """Generate context-aware mock asset entries for the campaign."""
    name = camp.get("name", "")
    prod = camp.get("product", "")
    cat  = camp.get("category", "")

    assets = []
    if "Mother" in name or "Mom" in name:
        assets = [
            {"name": "Mothers_Day_Hero_Stack.jpg",       "type": "Hero",         "fmt": "JPEG"},
            {"name": "Gold_Studs_Product_Tile_01.jpg",   "type": "Product tile", "fmt": "JPEG"},
            {"name": "Pearl_Huggie_Product_Tile_02.jpg", "type": "Product tile", "fmt": "JPEG"},
            {"name": "Lifestyle_BTS_Hand_01.jpg",        "type": "Lifestyle",    "fmt": "JPEG"},
        ]
    elif "Opal" in name or "Opal" in prod:
        assets = [
            {"name": "Opal_Collection_Hero.jpg",         "type": "Hero",         "fmt": "JPEG"},
            {"name": "Opal_Cluster_Stud_Detail.jpg",     "type": "Product tile", "fmt": "JPEG"},
            {"name": "Opal_Stack_Lifestyle.jpg",         "type": "Lifestyle",    "fmt": "JPEG"},
            {"name": "Opal_Campaign_Lockup.png",         "type": "Graphic",      "fmt": "PNG"},
        ]
    elif "VIP" in name or "VIP" in cat:
        assets = [
            {"name": "VIP_Early_Access_Hero.jpg",        "type": "Hero",         "fmt": "JPEG"},
            {"name": "Summer_Drop_Product_Flat.jpg",     "type": "Product tile", "fmt": "JPEG"},
            {"name": "VIP_Email_Header_Banner.png",      "type": "Banner",       "fmt": "PNG"},
            {"name": "Studio_Interior_BTS.jpg",          "type": "Lifestyle",    "fmt": "JPEG"},
        ]
    elif "Studio" in name or "Studio" in cat:
        assets = [
            {"name": "Studio_Opening_Hero.jpg",          "type": "Hero",         "fmt": "JPEG"},
            {"name": "Studio_Interior_Wide.jpg",         "type": "Lifestyle",    "fmt": "JPEG"},
            {"name": "Williamsburg_Exterior.jpg",        "type": "Lifestyle",    "fmt": "JPEG"},
            {"name": "Studio_Product_Display.jpg",       "type": "Product tile", "fmt": "JPEG"},
        ]
    elif "Diamond" in name or "Diamond" in prod or "Flatback" in name:
        assets = [
            {"name": "Diamond_Flatback_Hero.jpg",        "type": "Hero",         "fmt": "JPEG"},
            {"name": "Diamond_Cluster_Detail.jpg",       "type": "Product tile", "fmt": "JPEG"},
            {"name": "Flatback_Stack_Ear_Flat.jpg",      "type": "Lifestyle",    "fmt": "JPEG"},
        ]
    elif "Flash" in name or "Sale" in cat or "Promo" in cat:
        assets = [
            {"name": "Flash_Sale_Hero_Banner.jpg",       "type": "Hero",         "fmt": "JPEG"},
            {"name": "Hoops_Product_Tile_01.jpg",        "type": "Product tile", "fmt": "JPEG"},
            {"name": "Flash_Sale_Countdown_Badge.png",   "type": "Graphic",      "fmt": "PNG"},
        ]
    elif "Grad" in name or "Gift" in name:
        assets = [
            {"name": "Gift_Guide_Hero.jpg",              "type": "Hero",         "fmt": "JPEG"},
            {"name": "Gift_Stack_Flat.jpg",              "type": "Product tile", "fmt": "JPEG"},
            {"name": "Grad_Lifestyle_Hands.jpg",         "type": "Lifestyle",    "fmt": "JPEG"},
            {"name": "Gift_Box_Packaging.jpg",           "type": "Packaging",    "fmt": "JPEG"},
        ]
    else:
        assets = [
            {"name": f"{name.replace(' ','_')[:24]}_Hero.jpg",    "type": "Hero",         "fmt": "JPEG"},
            {"name": "Product_Tile_Primary.jpg",                   "type": "Product tile", "fmt": "JPEG"},
            {"name": "Lifestyle_Stack_Shot.jpg",                   "type": "Lifestyle",    "fmt": "JPEG"},
        ]

    air_base = "https://app.air.inc/a/glinta-creative/2026/may"
    dbx_base = "https://www.dropbox.com/sh/glinta-assets/may2026"
    for a in assets:
        slug = a["name"].replace(".jpg", "").replace(".png", "").lower()
        a["air_url"] = f"{air_base}/{slug}"
        a["dbx_url"] = f"{dbx_base}/{slug}"
    return assets


tab_review, tab_copy, tab_brief = st.tabs(["Campaign Review", "Copy Generation", "Design Brief"])


# ── Subject-line suggestions grounded in historical performance ──────────────
def _classify_subject_style(subj: str) -> str:
    s = (subj or "").lower()
    has_emoji  = any(ord(c) > 127 for c in subj)
    if "?" in subj:
        return "Question hook"
    if "$" in subj or "%" in subj or "off" in s:
        return "Discount + price anchor"
    if any(w in s for w in ["last", "ending", "tonight", "today", "hours",
                            "expires", "final", "left"]):
        return "Urgency"
    if any(w in s for w in ["new", "drop", "introducing", "launch", "just landed"]):
        return "Launch + news"
    if any(w in s for w in ["back", "restock", "again"]):
        return "Restock"
    if any(w in s for w in ["vip", "early access", "first", "exclusive"]):
        return "Exclusivity"
    if any(w in s for w in ["love", "your", "you'll", "for you"]):
        return "Personal + direct"
    if has_emoji:
        return "Emoji-led"
    return "Editorial"


def historical_subject_options(camp, df, n=3, recency_window_days=540):
    """Top historical subject lines for this campaign's (category, channel),
    ranked by a composite of open + click + conversion rate.

    Returns a list of (subject, style_label, strength, rationale_text) tuples.
    Falls back to broader pools if the (category, channel) bucket is too small.
    """
    pool = df.copy()
    pool = pool[pool["Subject Line"].notna()]
    pool["Subject Line"] = pool["Subject Line"].astype(str).str.strip()
    pool = pool[pool["Subject Line"].str.len() > 3]
    if pool.empty:
        return []

    # Prefer recency
    if "_date" in pool.columns:
        cutoff = _today - timedelta(days=recency_window_days)
        recent = pool[pool["_date"] >= cutoff]
        if len(recent) >= n * 2:
            pool = recent

    cat = camp.get("category") or ""
    ch  = (camp.get("channel") or "").lower()

    cat_pool = pool[pool["Category"] == cat] if cat else pool
    if len(cat_pool) < n:
        cat_pool = pool  # fall back to all categories
    same_ch = cat_pool[cat_pool["Channel"].astype(str).str.lower() == ch] if ch else cat_pool
    if len(same_ch) >= n:
        cat_pool = same_ch

    cat_pool = cat_pool.copy()
    cat_pool["_open"]  = pd.to_numeric(cat_pool.get("Open Rate"),       errors="coerce").fillna(0)
    cat_pool["_click"] = pd.to_numeric(cat_pool.get("Click Rate"),      errors="coerce").fillna(0)
    cat_pool["_conv"]  = pd.to_numeric(cat_pool.get("Conversion Rate"), errors="coerce").fillna(0)
    cat_pool["_score"] = cat_pool["_open"] + 4 * cat_pool["_click"] + 12 * cat_pool["_conv"]

    cat_pool = cat_pool.sort_values("_score", ascending=False)
    cat_pool = cat_pool.drop_duplicates(subset=["Subject Line"]).head(n)

    # Category benchmark for "vs avg" framing
    cat_bench = df[df["Category"] == cat] if cat else df
    cat_avg_open  = pd.to_numeric(cat_bench.get("Open Rate"),  errors="coerce").mean()
    cat_avg_click = pd.to_numeric(cat_bench.get("Click Rate"), errors="coerce").mean()

    options = []
    for _, r in cat_pool.iterrows():
        subj = str(r["Subject Line"])
        when = r["Send Date"].strftime("%b %Y") if pd.notna(r.get("Send Date")) else "—"
        oo, cc = r["_open"], r["_click"]
        # Strength: relative to the category open-rate average
        if pd.notna(cat_avg_open) and cat_avg_open > 0 and oo / cat_avg_open >= 1.10:
            strength = "High"
        elif pd.notna(cat_avg_open) and cat_avg_open > 0 and oo / cat_avg_open >= 0.90:
            strength = "Medium"
        else:
            strength = "Low"
        # Rationale grounded in numbers
        rat_bits = [
            f"Sent {when}",
            f"open {oo:.1%}" if oo else None,
            f"click {cc:.2%}" if cc else None,
        ]
        rationale = " · ".join([b for b in rat_bits if b])
        if pd.notna(cat_avg_open) and cat_avg_open > 0 and oo:
            delta = (oo - cat_avg_open) / cat_avg_open
            sign  = "+" if delta >= 0 else ""
            rationale += f" ({sign}{delta:.0%} vs {cat or 'category'} avg open)"
        style = _classify_subject_style(subj)
        options.append((subj, style, strength, rationale))
    return options


def historical_preview_text(camp, df):
    """Preview / preheader suggestion grounded in the campaign's product/category."""
    prod = (camp.get("product") or "").strip()
    cat  = camp.get("category") or ""
    if prod:
        return f"Featuring {prod} · shop the edit →"
    if cat:
        return f"This week's {cat.lower()} edit →"
    return "Shop the new edit →"


# ── Copy composition helpers (mock LLM behavior) ─────────────────────────────
def _tone_opener(tone_text: str, subject: str) -> str:
    t = (tone_text or "").lower()
    if any(w in t for w in ["urgent", "limit", "fast", "today", "hurry", "expire"]):
        return f"It's almost over.\n\n{subject}"
    if any(w in t for w in ["celebr", "warm", "love", "joy", "thank"]):
        return f"{subject}\n\nWe're so glad you're here for this one."
    if any(w in t for w in ["minimal", "spare", "clean", "quiet"]):
        return f"{subject}"
    if any(w in t for w in ["playful", "fun", "cheek", "wink"]):
        return f"{subject}\n\nLet's get into it."
    if any(w in t for w in ["confiden", "bold", "direct", "matter-of-fact"]):
        return f"{subject}\n\nHere's the truth:"
    if any(w in t for w in ["editorial", "lifestyle", "story"]):
        return f"{subject}\n\nA short story to set the scene."
    if any(w in t for w in ["exclus", "vip", "insider"]):
        return f"{subject}\n\nYou're seeing this before anyone else."
    return subject


def _highlights_line(highlights: str) -> str:
    h = (highlights or "").strip()
    if not h:
        return ""
    items = [x.strip() for x in h.replace(";", ",").replace("\n", ",").split(",") if x.strip()]
    if len(items) >= 2:
        return "Featured in this send: " + ", ".join(items[:-1]) + f", and {items[-1]}."
    return f"Featured in this send: {items[0]}."


def _tone_middle(tone_text: str) -> str:
    """Body paragraph that visibly tracks the requested tone."""
    t = (tone_text or "").lower()
    if any(w in t for w in ["urgent", "limit", "fast", "today", "hurry", "expire"]):
        return ("Stock is moving fast and we don't want you to miss it. "
                "These are the pieces our team is wearing this week — "
                "order in the next few hours for same-day shipping.")
    if any(w in t for w in ["celebr", "warm", "love", "joy", "thank"]):
        return ("Made for moments worth marking. Every piece is hypoallergenic, "
                "water-safe, and designed in our NYC studio — built to be worn "
                "through the small celebrations and the big ones.")
    if any(w in t for w in ["minimal", "spare", "clean", "quiet"]):
        return "Versatile. Layerable. Built to last. That's the whole pitch."
    if any(w in t for w in ["playful", "fun", "cheek", "wink"]):
        return ("We made these because the existing options were boring. "
                "Our piercers wear them. So do their friends. So does our intern. "
                "(You'll get it when you see it.)")
    if any(w in t for w in ["confiden", "bold", "direct", "matter-of-fact"]):
        return ("Hypoallergenic. Water-safe. Made for daily wear. "
                "No filler — just the styles our customers come back for.")
    if any(w in t for w in ["editorial", "lifestyle", "story"]):
        return ("Crafted in our NYC studio in small batches — designed for the way "
                "our customers actually live. Layerable, versatile, and built around "
                "the pieces you'll reach for again and again.")
    if any(w in t for w in ["exclus", "vip", "insider"]):
        return ("You're seeing this before our broader list. Same studio, same "
                "craftsmanship — first pick goes to the people who've been with "
                "us longest.")
    return ("Crafted for the way you actually wear them — versatile, layerable, "
            "and built to last. Every piece is hypoallergenic, water-safe, and "
            "designed in our NYC studio.")


def compose_email(camp, tone, cta, offer, highlights, subject_text):
    cta_clean = (cta or "").strip() or "Shop now"
    opener = _tone_opener(tone, subject_text or "Something new from Glinta.")
    hl_line = _highlights_line(highlights)
    offer_line = f"Use code **{offer.strip()}** at checkout." if offer.strip() else ""
    body_middle = _tone_middle(tone)

    # Audience reference grounds the body in the campaign's actual targeting.
    auds = camp.get("audiences") or []
    aud_line = ""
    if auds:
        aud_line = (f"_Sent to: {auds[0]}._" if len(auds) == 1
                    else f"_Sent to: {', '.join(auds)}._")

    parts = [opener]
    if hl_line:
        parts.append(hl_line)
    parts.append(body_middle)
    if offer_line:
        parts.append(offer_line)
    parts.append(f"→ {cta_clean}")
    parts.append("— The Glinta Team")
    if aud_line:
        parts.append(aud_line)
    if tone.strip():
        parts.append(f"_Tone: {tone.strip()}_")
    return "\n\n".join(parts)


def compose_sms(camp, tone, cta, offer, highlights, subject_text):
    cta_clean = (cta or "").strip() or "Shop now"
    lead = (subject_text or "New from Glinta").strip()
    if len(lead) > 70:
        lead = lead[:67].rstrip() + "…"
    h = (highlights or "").strip()
    hl_short = ""
    if h:
        first = h.replace(";", ",").replace("\n", ",").split(",")[0].strip()
        if first:
            hl_short = first[:50]
    offer_part = f"Code: {offer.strip()}." if offer.strip() else ""
    parts = [f"Glinta: {lead}"]
    if hl_short:
        parts.append(hl_short + ".")
    if offer_part:
        parts.append(offer_part)
    parts.append("studs.com")
    parts.append("Reply STOP to opt out.")
    return " ".join(parts)


# ── Segment personalization heuristics ───────────────────────────────────────
def segment_personalization(segment_name: str) -> dict:
    s = (segment_name or "").lower()
    if "vip" in s or "loyal" in s or "high-ltv" in s or "high ltv" in s or "3+" in s:
        return {
            "tone": "Exclusive and grateful — emphasize early access and insider feel.",
            "hook": "You're first.",
            "cta": "Shop your early access",
            "lift": "+24% open vs broadcast",
        }
    if ("new" in s and ("subscriber" in s or "30d" in s)) or "welcome" in s:
        return {
            "tone": "Warm welcome — orient to brand and bestsellers.",
            "hook": "Welcome — let us show you around.",
            "cta": "Shop the starter edit",
            "lift": "+12% click vs broadcast",
        }
    if "laps" in s or "winback" in s or "no purchase" in s or "dormant" in s:
        return {
            "tone": "Inviting — lead with a comeback offer.",
            "hook": "It's been a while — here's something to make it worth it.",
            "cta": "Claim your offer",
            "lift": "+8% reactivation vs control",
        }
    if "wishlist" in s or "saved" in s:
        return {
            "tone": "Specific and helpful — call out what they saved.",
            "hook": "The pieces you saved are ready.",
            "cta": "Shop your wishlist",
            "lift": "+31% click vs broadcast",
        }
    if "nyc" in s or "metro" in s or "local" in s or "geo" in s:
        return {
            "tone": "Local and inviting — mention nearby studio.",
            "hook": "We're in your neighborhood.",
            "cta": "Book your studio visit",
            "lift": "+18% conv for geo-targeted",
        }
    if "engaged" in s:
        return {
            "tone": "Confident and warm — build on existing trust.",
            "hook": "You know us. Here's what's new.",
            "cta": "Shop the new edit",
            "lift": "+9% click vs cold",
        }
    if "sms" in s:
        return {
            "tone": "Punchy and short — built for mobile.",
            "hook": "Quick heads up.",
            "cta": "Tap to shop",
            "lift": "Standard SMS engaged baseline",
        }
    return {
        "tone": "Brand-default — clean and confident.",
        "hook": "Here's what's new.",
        "cta": "Shop the edit",
        "lift": "Baseline broadcast",
    }


def _seg_compose(camp, base_tone, base_cta, offer, highlights, subject_text, seg_name):
    sp = segment_personalization(seg_name)
    seg_tone = (base_tone + " · " + sp["tone"]).strip(" ·")
    seg_cta = sp["cta"] or base_cta
    seg_subject = f"[{seg_name}] {sp['hook']} — {subject_text}" if subject_text else f"[{seg_name}] {sp['hook']}"
    return (
        compose_email(camp, seg_tone, seg_cta, offer, highlights, seg_subject),
        compose_sms(camp, seg_tone, seg_cta, offer, highlights, sp['hook']),
        sp,
    )


# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN REVIEW TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_review:
    st.markdown("<h2>Campaign Review</h2>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;color:#666;'
        'margin:-0.4rem 0 1.2rem;">All campaigns at a glance — click any row to see '
        'finalized copy and brief. Use the Copy Generation tab to make edits.</p>',
        unsafe_allow_html=True,
    )

    n_with_copy      = sum(1 for c in all_campaigns
                           if st.session_state.get(f"saved_copy_{c['id']}"))
    n_approved       = sum(1 for c in all_campaigns
                           if (st.session_state.get(f"saved_copy_{c['id']}", {})
                               .get("status") == "Approved"))
    n_brief_review   = sum(1 for c in all_campaigns
                           if st.session_state.get(f"brief_review_{c['id']}", {})
                           .get("status") == "In Review")
    n_brief_approved = sum(1 for c in all_campaigns
                           if st.session_state.get(f"brief_review_{c['id']}", {})
                           .get("status") == "Approved")

    rv1, rv2, rv3, rv4 = st.columns(4)
    for col, label, val, accent in [
        (rv1, "Total Campaigns",  len(all_campaigns), COLORS["border"]),
        (rv2, "Copy Generated",   n_with_copy,        COLORS["border"]),
        (rv3, "Copy Approved",    n_approved,
             COLORS["lime"] if n_approved else COLORS["border"]),
        (rv4, "Briefs In Review", n_brief_review,
             COLORS["yellow"] if n_brief_review else COLORS["border"]),
    ]:
        with col:
            st.markdown(
                f'<div style="border:1.5px solid {accent};border-radius:8px;'
                f'padding:10px 14px;text-align:center;">'
                f'<div style="font-size:1.4rem;font-weight:700;">{val}</div>'
                f'<div style="font-size:0.65rem;color:{COLORS["muted"]};'
                f'text-transform:uppercase;letter-spacing:0.08em;">{label}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Reviewer identity ─────────────────────────────────────────────────────
    _rname_col, _ = st.columns([2, 4])
    with _rname_col:
        st.text_input(
            "Reviewing as",
            placeholder="Your name",
            key="reviewer_name",
            help="Used when you click 'Approve copy' on any campaign.",
        )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Recent activity log ───────────────────────────────────────────────────
    _log = st.session_state.get("copy_review_log", [])
    if _log:
        st.markdown(
            '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.72rem;'
            'letter-spacing:0.1em;text-transform:uppercase;font-weight:700;'
            'border-bottom:1.5px solid #e0e0e0;padding-bottom:5px;'
            'margin-bottom:10px;">Recent activity</div>',
            unsafe_allow_html=True,
        )
        for entry in reversed(_log[-8:]):
            _sc  = COLORS["warn"] if entry["status"] == "Draft" else COLORS["lime"]
            _sb  = "#777" if entry["status"] == "Draft" else COLORS["black"]
            _log_rev = entry.get("reviewer", "")
            _rev_frag = (f' · <strong>→ {_log_rev}</strong>' if _log_rev else "")
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;'
                f'padding:5px 0;border-bottom:1px solid {COLORS["border"]};">'
                f'<span style="background:{_sc};border:1px solid {_sb};border-radius:4px;'
                f'padding:1px 7px;font-family:\'Barlow Condensed\',sans-serif;font-weight:700;'
                f'font-size:0.62rem;letter-spacing:0.07em;text-transform:uppercase;'
                f'white-space:nowrap;">{entry["status"]}</span>'
                f'<span style="font-size:0.78rem;font-weight:600;flex:1;">'
                f'{entry["campaign_name"]}</span>'
                f'<span style="font-size:0.65rem;color:{COLORS["muted"]};">'
                f'{entry["action"]} · {entry["saved_by"]} · {entry["saved_at"]}'
                f'{_rev_frag}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    for c in all_campaigns:
        saved = st.session_state.get(f"saved_copy_{c['id']}", {})
        has_copy = bool(saved.get("email"))

        brief_subj    = st.session_state.get(f"brief_subject_{c['id']}",
                            c.get("subject_line_draft", "")).strip()
        brief_tone_raw = (st.session_state.get(f"brief_tone_{c['id']}", "")
                          or saved.get("tone", "")).strip()
        brief_tone_display = brief_tone_raw.split("\n\nVisual")[0].strip() if brief_tone_raw else ""
        brief_prev    = (st.session_state.get(f"brief_preview_{c['id']}", "")
                         or saved.get("preview", "")).strip()
        brief_assets  = st.session_state.get(f"brief_assets_{c['id']}", "").strip()

        brief_subj_display = brief_subj or saved.get("subject", "")
        brief_cta      = saved.get("cta", "")
        brief_offer    = saved.get("offer", "")
        brief_hl       = saved.get("highlights", "")
        brief_exists   = any([brief_subj_display, brief_prev,
                               brief_tone_display, brief_cta, brief_offer,
                               brief_hl, brief_assets])

        _brief_review = st.session_state.get(f"brief_review_{c['id']}", {})
        _brief_rv_status = _brief_review.get("status", "")

        copy_tick  = "✓" if has_copy else "○"
        brief_tick = (
            "✓" if _brief_rv_status == "Approved"
            else "⏳" if _brief_rv_status == "In Review"
            else ("✓" if brief_exists else "○")
        )
        _copy_status  = saved.get("status", "")
        _status_suffix = f"  ·  {_copy_status}" if _copy_status else ""
        _brief_suffix  = f"  ·  Brief {_brief_rv_status}" if _brief_rv_status else ""

        expander_label = (
            f"{c['name']}  ·  {c['send_date'].strftime('%b %d')}  ·  "
            f"{c['channel'].upper()}  ·  "
            f"Copy {copy_tick}  Brief {brief_tick}{_status_suffix}{_brief_suffix}"
        )

        with st.expander(expander_label, expanded=False):
            # Status badge + attribution row
            if _copy_status:
                _sc = COLORS["warn"] if _copy_status == "Draft" else COLORS["lime"]
                _sb = "#777" if _copy_status == "Draft" else COLORS["black"]
                _attr_by  = saved.get("saved_by", "")
                _attr_at  = saved.get("saved_at", "")
                _attr_rev = saved.get("reviewer", "")
                _rev_part = (
                    f'<span style="margin-left:10px;font-size:0.65rem;color:#555;">'
                    f'Reviewer: <strong>{_attr_rev}</strong></span>'
                ) if _attr_rev else ""
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:0;'
                    f'flex-wrap:wrap;margin-bottom:12px;">'
                    f'<span style="display:inline-flex;align-items:center;gap:8px;'
                    f'background:{_sc};border:1.5px solid {_sb};border-radius:6px;'
                    f'padding:4px 10px;">'
                    f'<span style="font-family:\'Barlow Condensed\',sans-serif;'
                    f'font-weight:700;font-size:0.72rem;letter-spacing:0.08em;'
                    f'text-transform:uppercase;">{_copy_status}</span>'
                    f'<span style="font-size:0.65rem;color:#555;">'
                    f' · {_attr_by} · {_attr_at}</span>'
                    f'</span>'
                    f'{_rev_part}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            mc1, mc2, mc3, mc4 = st.columns(4)
            for mcol, lbl, val in [
                (mc1, "Send Date",    c["send_date"].strftime("%b %d, %Y")),
                (mc2, "Segment",      c["segment"] or "—"),
                (mc3, "Category",     c["category"] or "—"),
                (mc4, "Brief Status", c.get("brief_status", "—")),
            ]:
                with mcol:
                    st.markdown(
                        f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                        f'text-transform:uppercase;letter-spacing:0.08em;">{lbl}</div>'
                        f'<div style="font-size:0.82rem;font-weight:600;">{val}</div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

            # ── Brief ──────────────────────────────────────────────────────
            def _render_brief_fields():
                """Inline helper — renders brief field rows inside any container."""
                if brief_subj_display:
                    st.markdown(
                        f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">'
                        f'Subject line</div>'
                        f'<div style="font-size:0.88rem;font-weight:600;margin-bottom:10px;">'
                        f'{brief_subj_display}</div>',
                        unsafe_allow_html=True,
                    )
                if brief_prev:
                    st.markdown(
                        f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">'
                        f'Preview / preheader</div>'
                        f'<div style="font-size:0.82rem;margin-bottom:10px;">'
                        f'{brief_prev}</div>',
                        unsafe_allow_html=True,
                    )
                bfl, bfr = st.columns(2)
                with bfl:
                    if brief_tone_display:
                        st.markdown(
                            f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">'
                            f'Tone</div>'
                            f'<div style="font-size:0.82rem;margin-bottom:10px;">'
                            f'{brief_tone_display}</div>',
                            unsafe_allow_html=True,
                        )
                    if brief_cta:
                        st.markdown(
                            f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">'
                            f'CTA</div>'
                            f'<div style="font-size:0.82rem;margin-bottom:10px;">'
                            f'{brief_cta}</div>',
                            unsafe_allow_html=True,
                        )
                with bfr:
                    if brief_offer:
                        st.markdown(
                            f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">'
                            f'Offer / promo</div>'
                            f'<div style="font-size:0.82rem;margin-bottom:10px;">'
                            f'{brief_offer}</div>',
                            unsafe_allow_html=True,
                        )
                    if brief_hl:
                        st.markdown(
                            f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                            f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">'
                            f'Key highlights</div>'
                            f'<div style="font-size:0.82rem;margin-bottom:10px;">'
                            f'{brief_hl}</div>',
                            unsafe_allow_html=True,
                        )
                if brief_assets:
                    st.markdown(
                        f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">'
                        f'Required assets</div>'
                        f'<div style="font-size:0.78rem;white-space:pre-line;'
                        f'margin-bottom:10px;">{brief_assets}</div>',
                        unsafe_allow_html=True,
                    )

            if _brief_rv_status in ("In Review", "Approved"):
                _brief_exp_bg = COLORS["lime"] if _brief_rv_status == "Approved" else COLORS["yellow"]
                _brief_exp_icon = "✓" if _brief_rv_status == "Approved" else "⏳"
                _brief_reviewer_label = _brief_review.get("reviewer", "")
                _brief_exp_label = (
                    f"{_brief_exp_icon} Brief · **{_brief_rv_status}**"
                    + (f" → {_brief_reviewer_label}" if _brief_reviewer_label else "")
                )
                with st.expander(_brief_exp_label, expanded=False):
                    _render_brief_fields()

                    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

                    if _brief_rv_status == "Approved":
                        _approved_by = _brief_review.get("approved_by", "—")
                        _approved_at = _brief_review.get("approved_at", "")
                        st.markdown(
                            f'<div style="background:{COLORS["lime"]};border:1.5px solid '
                            f'{COLORS["black"]};border-radius:6px;padding:6px 12px;'
                            f'font-size:0.75rem;font-weight:600;margin-bottom:8px;">'
                            f'✓ Approved by <strong>{_approved_by}</strong>'
                            f'{(" · " + _approved_at) if _approved_at else ""}</div>',
                            unsafe_allow_html=True,
                        )
                        if st.button("Revoke brief approval",
                                     key=f"rv_revoke_brief_{c['id']}", type="secondary"):
                            _br = st.session_state.get(f"brief_review_{c['id']}", {})
                            _br["status"] = "In Review"
                            _br.pop("approved_by", None)
                            _br.pop("approved_at", None)
                            st.session_state[f"brief_review_{c['id']}"] = _br
                            st.rerun()

                    else:  # In Review — show approve button
                        _rname = (st.session_state.get("reviewer_name") or "").strip()
                        _bappr_col, _bnote_col = st.columns([2, 3])
                        with _bappr_col:
                            if st.button("Approve brief",
                                         key=f"rv_approve_brief_{c['id']}",
                                         type="primary",
                                         use_container_width=True):
                                if not _rname:
                                    st.error('Enter your name in "Reviewing as" above first.')
                                else:
                                    _br = st.session_state.get(f"brief_review_{c['id']}", {})
                                    _br["status"]      = "Approved"
                                    _br["approved_by"] = _rname
                                    _br["approved_at"] = _today.strftime("%b %d")
                                    st.session_state[f"brief_review_{c['id']}"] = _br
                                    _log = st.session_state.get("copy_review_log", [])
                                    _log.append({
                                        "campaign_name": c["name"],
                                        "status":        "Approved",
                                        "action":        "Brief approved",
                                        "saved_by":      _rname,
                                        "saved_at":      _today.strftime("%b %d"),
                                        "reviewer":      _rname,
                                    })
                                    st.session_state["copy_review_log"] = _log
                                    st.rerun()
                        with _bnote_col:
                            if _brief_review.get("note"):
                                st.markdown(
                                    f'<div style="font-size:0.72rem;color:{COLORS["muted"]};'
                                    f'padding:8px 0;font-style:italic;">'
                                    f'Reviewer note: {_brief_review["note"]}</div>',
                                    unsafe_allow_html=True,
                                )

            elif brief_exists:
                st.markdown(
                    '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.72rem;'
                    'letter-spacing:0.1em;text-transform:uppercase;font-weight:700;'
                    'border-bottom:1.5px solid #e0e0e0;padding-bottom:5px;'
                    'margin-bottom:12px;">Brief</div>',
                    unsafe_allow_html=True,
                )
                _render_brief_fields()
            else:
                st.markdown(
                    f'<div style="font-size:0.78rem;color:{COLORS["muted"]};'
                    f'font-style:italic;margin-bottom:10px;">Brief not yet filled in — '
                    f'open the <strong>Design Brief</strong> tab for this campaign.</div>',
                    unsafe_allow_html=True,
                )

            # ── Copy ───────────────────────────────────────────────────────
            st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

            _is_approved = saved.get("status") == "Approved"
            _copy_hdr_col, _approve_col = st.columns([4, 2])
            with _copy_hdr_col:
                st.markdown(
                    '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.72rem;'
                    'letter-spacing:0.1em;text-transform:uppercase;font-weight:700;'
                    'border-bottom:1.5px solid #e0e0e0;padding-bottom:5px;'
                    'margin-bottom:12px;">Copy</div>',
                    unsafe_allow_html=True,
                )
            with _approve_col:
                if has_copy:
                    if _is_approved:
                        st.markdown(
                            f'<div style="text-align:right;padding-top:2px;">'
                            f'<span style="background:{COLORS["lime"]};border:1.5px solid {COLORS["black"]};'
                            f'border-radius:6px;padding:3px 10px;font-family:\'Barlow Condensed\',sans-serif;'
                            f'font-weight:700;font-size:0.7rem;letter-spacing:0.08em;'
                            f'text-transform:uppercase;">✓ Approved</span></div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        _rname = (st.session_state.get("reviewer_name") or "").strip()
                        if st.button("Approve copy", key=f"approve_{c['id']}",
                                     type="primary", use_container_width=True):
                            if not _rname:
                                st.error('Enter your name in "Reviewing as" above before approving.')
                            else:
                                _s = st.session_state.get(f"saved_copy_{c['id']}", {})
                                _s["status"]   = "Approved"
                                _s["saved_by"] = _rname
                                _s["saved_at"] = _today.strftime("%b %d")
                                st.session_state[f"saved_copy_{c['id']}"] = _s
                                _log = st.session_state.get("copy_review_log", [])
                                _log.append({
                                    "campaign_name": c["name"],
                                    "status":        "Approved",
                                    "action":        "Approved copy",
                                    "saved_by":      _rname,
                                    "saved_at":      _today.strftime("%b %d"),
                                })
                                st.session_state["copy_review_log"] = _log
                                st.rerun()

            if has_copy:
                cp1, cp2 = st.columns(2)
                with cp1:
                    st.markdown(
                        '<div style="font-size:0.62rem;color:#666;text-transform:uppercase;'
                        'letter-spacing:0.08em;margin-bottom:4px;">Email body</div>',
                        unsafe_allow_html=True,
                    )
                    st.text_area(
                        "email_body",
                        value=saved.get("email", ""),
                        height=220,
                        disabled=True,
                        label_visibility="collapsed",
                        key=f"review_email_{c['id']}",
                    )
                with cp2:
                    st.markdown(
                        '<div style="font-size:0.62rem;color:#666;text-transform:uppercase;'
                        'letter-spacing:0.08em;margin-bottom:4px;">SMS copy</div>',
                        unsafe_allow_html=True,
                    )
                    st.text_area(
                        "sms_copy",
                        value=saved.get("sms", ""),
                        height=130,
                        disabled=True,
                        label_visibility="collapsed",
                        key=f"review_sms_{c['id']}",
                    )
                if _is_approved:
                    _attr = saved.get("saved_by", "Reviewer")
                    _when = saved.get("saved_at", "")
                    st.markdown(
                        f'<div style="font-size:0.65rem;color:#555;margin-top:4px;">'
                        f'Approved by <strong>{_attr}</strong>'
                        f'{(" · " + _when) if _when else ""}  — '
                        f'<span style="cursor:pointer;text-decoration:underline;" '
                        f'title="Click Revoke to undo">revoke below</span></div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Revoke approval", key=f"revoke_{c['id']}", type="secondary"):
                        _rname_rev = (st.session_state.get("reviewer_name") or "").strip() or "Reviewer"
                        _s = st.session_state.get(f"saved_copy_{c['id']}", {})
                        _s["status"] = "Draft"
                        st.session_state[f"saved_copy_{c['id']}"] = _s
                        _log = st.session_state.get("copy_review_log", [])
                        _log.append({
                            "campaign_name": c["name"],
                            "status":        "Draft",
                            "action":        "Revoked approval",
                            "saved_by":      _rname_rev,
                            "saved_at":      _today.strftime("%b %d"),
                        })
                        st.session_state["copy_review_log"] = _log
                        st.rerun()
            else:
                st.markdown(
                    f'<div style="font-size:0.78rem;color:{COLORS["muted"]};'
                    f'font-style:italic;padding:4px 0 8px;">No copy generated yet — '
                    f'select this campaign in <strong>Copy Generation</strong> and '
                    f'click "Generate copy".</div>',
                    unsafe_allow_html=True,
                )

            # ── Per-segment personalizations ───────────────────────────────
            _audiences = c.get("audiences") or (
                [c["segment"]] if c.get("segment") and c["segment"] not in ("—", "") else []
            )
            _seg_variants = []
            for _si, _seg_name in enumerate(_audiences):
                _se = st.session_state.get(f"seg_email_{c['id']}_{_si}")
                _ss = st.session_state.get(f"seg_sms_{c['id']}_{_si}")
                _sinp = st.session_state.get(f"seg_input_{c['id']}_{_si}", "")
                if _se or _ss:
                    _seg_variants.append((_si, _seg_name, _se, _ss, _sinp))

            if _audiences:
                st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
                _seg_hdr = (
                    f"Per-segment personalizations "
                    f"({len(_seg_variants)} of {len(_audiences)} generated)"
                )
                st.markdown(
                    f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.72rem;'
                    f'letter-spacing:0.1em;text-transform:uppercase;font-weight:700;'
                    f'border-bottom:1.5px solid #e0e0e0;padding-bottom:5px;'
                    f'margin-bottom:10px;">{_seg_hdr}</div>',
                    unsafe_allow_html=True,
                )

                if not _seg_variants:
                    st.markdown(
                        f'<div style="font-size:0.78rem;color:{COLORS["muted"]};'
                        f'font-style:italic;padding:4px 0 8px;">'
                        f'No segment variants generated yet — open '
                        f'<strong>Copy Generation</strong>, expand '
                        f'"Per-segment personalization", and click '
                        f'"Generate for this segment".</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    for _si, _seg_name, _se, _ss, _sinp in _seg_variants:
                        with st.expander(f"**{_seg_name}**", expanded=False):
                            if _sinp:
                                st.markdown(
                                    f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                                    f'text-transform:uppercase;letter-spacing:0.08em;'
                                    f'margin-bottom:2px;">Personalization input</div>'
                                    f'<div style="font-size:0.78rem;font-style:italic;'
                                    f'margin-bottom:10px;">{_sinp}</div>',
                                    unsafe_allow_html=True,
                                )
                            _scp1, _scp2 = st.columns(2)
                            with _scp1:
                                st.markdown(
                                    '<div style="font-size:0.62rem;color:#666;'
                                    'text-transform:uppercase;letter-spacing:0.08em;'
                                    'margin-bottom:4px;">Email — personalized</div>',
                                    unsafe_allow_html=True,
                                )
                                st.text_area(
                                    "seg_email",
                                    value=_se or "",
                                    height=200,
                                    disabled=True,
                                    label_visibility="collapsed",
                                    key=f"review_seg_email_{c['id']}_{_si}",
                                )
                            with _scp2:
                                st.markdown(
                                    '<div style="font-size:0.62rem;color:#666;'
                                    'text-transform:uppercase;letter-spacing:0.08em;'
                                    'margin-bottom:4px;">SMS — personalized</div>',
                                    unsafe_allow_html=True,
                                )
                                st.text_area(
                                    "seg_sms",
                                    value=_ss or "",
                                    height=110,
                                    disabled=True,
                                    label_visibility="collapsed",
                                    key=f"review_seg_sms_{c['id']}_{_si}",
                                )

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if st.button("Open in Copy Generation →",
                         key=f"review_jump_{c['id']}", type="secondary"):
                st.session_state["active_campaign_id"] = c["id"]
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# COPY GENERATION TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_copy:
    # ── Campaign selector ─────────────────────────────────────────────────────
    _copy_active_id  = st.session_state.get("active_campaign_id", all_campaigns[0]["id"])
    _copy_active_idx = next((i for i, c in enumerate(all_campaigns)
                             if c["id"] == _copy_active_id), 0)
    _copy_sel_col, _ = st.columns([3, 3])
    with _copy_sel_col:
        _copy_chosen = st.selectbox(
            "Editing campaign",
            camp_labels,
            index=_copy_active_idx,
            key="gen_camp_copy",
            help="Pulls from Planning → Upcoming Campaigns: scheduled sends from your "
                 "campaign data plus anything you added in Plan a Campaign.",
        )
    camp = all_campaigns[camp_labels.index(_copy_chosen)]
    st.session_state["active_campaign_id"] = camp["id"]
    campaign_context_card(camp)

    st.markdown("<h2>Copy Generation</h2>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;color:#666;'
        'margin:-0.4rem 0 1rem;">Generate email and SMS copy using the Glinta brand voice — '
        'powered by Claude (mock output)</p>',
        unsafe_allow_html=True,
    )

    subject_options = historical_subject_options(camp, _cdf, n=3)
    preview_default  = historical_preview_text(camp, _cdf)

    # If the campaign already has a draft subject (from Plan a Campaign or
    # the source row), surface it as option 0 with a note so it isn't lost.
    draft_subj = (camp.get("subject_line_draft") or "").strip()
    if draft_subj and draft_subj not in {s for s, *_ in subject_options}:
        subject_options.insert(0, (
            draft_subj, "From your brief", "—",
            "This is the subject line currently saved for this campaign.",
        ))
        subject_options = subject_options[:3]

    # Reset generated copy + form fields if campaign changed
    if st.session_state.get("gen_for_camp_id") != camp["id"]:
        st.session_state["gen_for_camp_id"] = camp["id"]
        st.session_state["selected_subject"] = 0
        st.session_state["gen_version"] = st.session_state.get("gen_version", 0) + 1
        # Clear widget state so all form / output widgets re-init from the
        # new campaign's defaults instead of the previous campaign's values.
        for wkey in ("gen_tone", "gen_cta", "gen_offer", "gen_highlights",
                     "gen_preview", "gen_email_text", "gen_sms_text"):
            if wkey in st.session_state:
                del st.session_state[wkey]
        for k in list(st.session_state.keys()):
            if k.startswith("seg_email_") or k.startswith("seg_sms_") \
               or k.startswith("seg_input_") or k.startswith("seg_email_view_") \
               or k.startswith("seg_sms_view_") \
               or k.startswith("gen_body_v") or k.startswith("gen_sms_v") \
               or k.startswith("gen_offer_v"):
                del st.session_state[k]

    # Default highlights — broader: combine product, studio, segment context
    def _default_highlights():
        bits = []
        if camp.get("product"):
            bits.append(camp["product"])
        if camp.get("studio"):
            bits.append(f"{camp['studio']} studio")
        if not bits:
            if "Opal" in camp["name"] or "Mother" in camp["name"]:
                bits.extend(["Gold flatbacks", "Opal cluster stud", "Pearl huggie hoops"])
            else:
                bits.append(camp["name"])
        return ", ".join(bits)

    # ── Top: Brief inputs (left, larger) + Subject options (right, smaller) ──
    cg1, cg2 = st.columns([3, 2], gap="large")

    with cg1:
        st.markdown("<h3>Brief inputs</h3>", unsafe_allow_html=True)
        tone = st.text_area(
            "Tone",
            value=st.session_state.get("gen_tone", "Warm and confident, with a celebratory hint."),
            placeholder="Describe the tone in your own words — e.g. \"urgent but warm, "
                        "lean into FOMO without sounding pushy\"",
            height=70,
            key="gen_tone",
        )
        cta = st.text_input(
            "Primary CTA",
            value=st.session_state.get("gen_cta", "Shop the edit"),
            key="gen_cta",
        )

        # ── Offer / promo code with inline generator ──────────────────────
        def _generate_offer_code(camp):
            """Derive a promo code from campaign context."""
            name = (camp.get("name") or "").upper()
            cat  = (camp.get("category") or "").upper()
            prod = (camp.get("product") or "").upper()
            ch   = (camp.get("channel") or "").lower()

            # Discount level by category
            if any(w in cat for w in ["PROMO", "SALE", "FLASH"]):
                pct = "20"
            elif any(w in cat for w in ["VIP", "LOYALTY"]):
                pct = "15"
            elif any(w in cat for w in ["STUDIO", "RETAIL", "EVENT"]):
                pct = "10"
            elif any(w in cat for w in ["HOLIDAY", "SEASONAL"]):
                pct = "20"
            else:
                pct = "15"

            # Keyword from campaign name / product / category
            _kw_map = [
                ("MOTHER", "MDAY"), ("MOM", "MDAY"), ("GRAD", "GRAD"),
                ("VALENTINE", "VDAY"), ("HOLIDAY", "HLDY"), ("CHRISTMAS", "XMAS"),
                ("OPAL", "OPAL"), ("DIAMOND", "DIAM"), ("PEARL", "PEARL"),
                ("GOLD", "GOLD"), ("HOOP", "HOOPS"), ("STUD", "STUDS"),
                ("FLATBACK", "FLAT"), ("HUGGIE", "HUG"), ("RING", "RING"),
                ("VIP", "VIP"), ("LOYALTY", "VIP"), ("FLASH", "FLASH"),
                ("RESTOCK", "BACK"), ("BACK IN STOCK", "BACK"),
                ("SUMMER", "SUMMER"), ("SPRING", "SPRING"),
                ("FALL", "FALL"), ("WINTER", "WINTER"),
                ("STUDIO", "STUDIO"), ("WILLIAMSBURG", "WBG"),
                ("LAUNCH", "LAUNCH"), ("DROP", "DROP"),
                ("GIFT", "GIFT"), ("EDITORIAL", "EDIT"),
            ]
            keyword = "GLINTA"
            for trigger, kw in _kw_map:
                if trigger in name or trigger in prod or trigger in cat:
                    keyword = kw
                    break

            # SMS codes are shorter
            if ch == "sms" and len(keyword) > 4:
                keyword = keyword[:4]

            return f"{keyword}{pct}"

        _offer_ver = st.session_state.get("gen_offer_ver", 0)
        _offer_default = st.session_state.get(
            "gen_offer",
            "HOOPS20" if camp["category"] in ("Promotional", "Sale", "Promo") else "",
        )
        _off_col, _gen_col = st.columns([4, 1])
        with _off_col:
            offer = st.text_input(
                "Offer / promo code (optional)",
                value=_offer_default,
                key=f"gen_offer_v{_offer_ver}",
            )
        with _gen_col:
            st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
            if st.button("Generate", key="gen_offer_code_btn",
                         use_container_width=True,
                         help="Auto-generate a code from campaign context"):
                _code = _generate_offer_code(camp)
                st.session_state["gen_offer"] = _code
                st.session_state["gen_offer_ver"] = _offer_ver + 1
                st.rerun()

        # Keep the backing store in sync with whatever the user has typed
        # so that save payloads always read the latest value via "gen_offer".
        st.session_state["gen_offer"] = offer
        highlights = st.text_area(
            "Key highlights (product, studio, other context)",
            value=st.session_state.get("gen_highlights", _default_highlights()),
            placeholder="Any combination of products, studio openings, customer milestones, "
                        "press mentions, or other context to lead with.",
            height=90,
            key="gen_highlights",
            help="Broader than just products — include studio context, occasion, "
                 "press, or any other framing the copy should reflect.",
        )

        gen_clicked = st.button(
            "Generate copy",
            type="primary",
            key="gen_btn",
            use_container_width=True,
        )

        st.markdown(
            f'<p style="font-size:0.65rem;color:{COLORS["muted"]};margin-top:6px;">'
            f'Connected to Claude API · Glinta brand skill active. '
            f'Click Generate to update the email & SMS based on your inputs and selected subject.</p>',
            unsafe_allow_html=True,
        )

    with cg2:
        st.markdown("<h3>Subject lines</h3>", unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.7rem;'
            f'color:{COLORS["muted"]};margin:-0.4rem 0 0.6rem;line-height:1.35;">'
            f'Top historical subject lines for <strong>{camp.get("category","—")}</strong> · '
            f'{(camp.get("channel","").upper() or "—")}, ranked by open + click + conversion. '
            f'Each shows the date, performance, and lift vs the category average.</p>',
            unsafe_allow_html=True,
        )
        selected_subject = st.session_state.get("selected_subject", 0)

        if not subject_options:
            st.info("No historical subject lines found for this category and channel.")

        for i, (subj, style, strength, rationale) in enumerate(subject_options):
            is_sel = (selected_subject == i)
            border_color = COLORS["black"] if is_sel else COLORS["border"]
            bg = COLORS["yellow"] if is_sel else COLORS["white"]
            strength_col = (
                "#2ECC71" if strength == "High"
                else COLORS["warn"] if strength == "Medium"
                else COLORS["muted"]
            )

            st.markdown(f"""
            <div style="background:{bg};border:2px solid {border_color};
                        border-radius:8px;padding:9px 11px;margin-bottom:6px;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;">
                <div style="font-family:'Barlow',sans-serif;font-size:0.78rem;
                            font-weight:600;flex:1;line-height:1.25;">{subj}</div>
                <span style="background:{strength_col};color:#fff;padding:1px 6px;
                             border-radius:50px;font-size:0.55rem;font-weight:700;
                             white-space:nowrap;font-family:'Barlow Condensed',sans-serif;">
                  {strength.upper()}</span>
              </div>
              <div style="margin-top:3px;font-size:0.65rem;color:{COLORS['muted']};
                          line-height:1.3;">
                <strong>{style}</strong> · {rationale}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Use option {i+1}", key=f"sel_subj_{i}",
                         type="primary" if is_sel else "secondary",
                         use_container_width=True):
                st.session_state["selected_subject"] = i
                st.rerun()

        st.markdown(
            '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.65rem;'
            'letter-spacing:0.08em;text-transform:uppercase;color:#666;margin-top:8px;">'
            'Preview text</div>',
            unsafe_allow_html=True,
        )
        preview_val = st.text_input(
            "Preview / preheader",
            value=preview_default,
            key="gen_preview",
            label_visibility="collapsed",
        )

    # Recompute body & SMS when Generate is clicked (always reflects latest inputs)
    selected_subject = min(st.session_state.get("selected_subject", 0),
                           max(len(subject_options) - 1, 0))
    selected_subject_text = (subject_options[selected_subject][0]
                             if subject_options else (camp.get("subject_line_draft") or ""))
    if gen_clicked:
        new_email = compose_email(camp, tone, cta, offer, highlights, selected_subject_text)
        new_sms   = compose_sms(camp,   tone, cta, offer, highlights, selected_subject_text)
        # Bump a version counter so the body/SMS textareas use fresh widget
        # keys on the next run — Streamlit ignores `value=` for widgets whose
        # keys already exist in session_state, so deleting/clearing the keys
        # alone isn't reliable. Versioning the key forces a fresh widget that
        # actually reads the new text.
        st.session_state["gen_email_text"] = new_email
        st.session_state["gen_sms_text"]   = new_sms
        st.session_state["gen_version"] = st.session_state.get("gen_version", 0) + 1
        # Auto-save per-campaign copy for the Campaign Review tab
        st.session_state[f"saved_copy_{camp['id']}"] = {
            "email":      new_email,
            "sms":        new_sms,
            "subject":    selected_subject_text,
            "tone":       tone,
            "cta":        cta,
            "offer":      offer,
            "highlights": highlights,
            "preview":    st.session_state.get("gen_preview", ""),
        }
        # invalidate any per-segment cached copy so they regenerate too
        for k in list(st.session_state.keys()):
            if k.startswith("seg_email_") or k.startswith("seg_sms_") \
               or k.startswith("seg_email_view_") or k.startswith("seg_sms_view_"):
                del st.session_state[k]
        st.rerun()

    st.divider()

    body_col, sms_col = st.columns(2)

    # On first render for this campaign, seed the body/SMS using compose_*
    # so the textareas show something grounded in the user's inputs and the
    # selected campaign — not a hand-written mock.
    if "gen_email_text" not in st.session_state:
        st.session_state["gen_email_text"] = compose_email(
            camp, tone, cta, offer, highlights, selected_subject_text)
    if "gen_sms_text" not in st.session_state:
        st.session_state["gen_sms_text"] = compose_sms(
            camp, tone, cta, offer, highlights, selected_subject_text)

    # Seed per-campaign saved copy on first visit (populates Campaign Review)
    if f"saved_copy_{camp['id']}" not in st.session_state:
        st.session_state[f"saved_copy_{camp['id']}"] = {
            "email":      st.session_state["gen_email_text"],
            "sms":        st.session_state["gen_sms_text"],
            "subject":    selected_subject_text,
            "tone":       st.session_state.get("gen_tone", ""),
            "cta":        st.session_state.get("gen_cta", ""),
            "offer":      st.session_state.get("gen_offer", ""),
            "highlights": st.session_state.get("gen_highlights", ""),
            "preview":    st.session_state.get("gen_preview", ""),
        }

    gen_version = st.session_state.get("gen_version", 0)

    with body_col:
        st.markdown("<h3>Email body</h3>", unsafe_allow_html=True)
        email_body = st.text_area(
            "Email copy",
            value=st.session_state["gen_email_text"],
            height=380,
            key=f"gen_body_v{gen_version}",
            label_visibility="collapsed",
        )
        wc = len(email_body.split())
        st.markdown(
            f'<p style="font-size:0.65rem;color:{COLORS["muted"]};">'
            f'{wc} words · Recommended: 80–150 words</p>',
            unsafe_allow_html=True,
        )

    with sms_col:
        st.markdown("<h3>SMS copy</h3>", unsafe_allow_html=True)
        sms_body = st.text_area(
            "SMS copy",
            value=st.session_state["gen_sms_text"],
            height=220,
            key=f"gen_sms_v{gen_version}",
            label_visibility="collapsed",
        )
        chars = len(sms_body)
        segs  = (chars // 160) + 1
        char_color = COLORS["danger"] if chars > 320 else COLORS["warn"] if chars > 160 else "#2ECC71"
        st.markdown(
            f'<p style="font-size:0.65rem;color:{char_color};">'
            f'{chars} characters · {segs} SMS segment(s) · 160 chars = 1 segment</p>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<p style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.7rem;'
            'letter-spacing:0.08em;text-transform:uppercase;color:#666;margin-top:12px;">'
            'SMS compliance checklist</p>',
            unsafe_allow_html=True,
        )
        has_brand  = "Glinta:" in sms_body or "studs" in sms_body.lower()
        has_stop   = "STOP" in sms_body
        has_link   = "studs.com" in sms_body or "http" in sms_body
        under_320  = chars <= 320
        for label, ok in [
            ("Brand name included", has_brand),
            ("Opt-out language (STOP)", has_stop),
            ("Link included", has_link),
            ("Under 320 characters", under_320),
        ]:
            icon  = "✓" if ok else "✗"
            color = "#2ECC71" if ok else COLORS["danger"]
            st.markdown(
                f'<div style="font-size:0.75rem;color:{color};font-weight:600;">'
                f'{icon} {label}</div>',
                unsafe_allow_html=True,
            )

    # ── Per-segment personalization (only if campaign defines audiences) ─────
    audiences_list = camp.get("audiences") or (
        [camp.get("segment", "")] if camp.get("segment") else []
    )
    audiences_list = [a for a in audiences_list if a]

    if audiences_list:
        st.divider()
        st.markdown("<h3>Per-segment personalization</h3>", unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
            f'color:{COLORS["muted"]};margin:-0.4rem 0 1rem;">Each defined audience gets '
            f'its own variant. Click a segment to expand and see personalized email + SMS '
            f'for that segment. Edit the personalization input to refine.</p>',
            unsafe_allow_html=True,
        )

        seg_cols = st.columns(min(len(audiences_list), 3))
        for i, seg_name in enumerate(audiences_list):
            sp = segment_personalization(seg_name)
            with seg_cols[i % len(seg_cols)]:
                with st.expander(f"**{seg_name}**", expanded=False):
                    st.markdown(
                        f'<div style="font-size:0.7rem;color:{COLORS["muted"]};'
                        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">'
                        f'Suggested tone</div>'
                        f'<div style="font-size:0.8rem;font-weight:600;margin-bottom:8px;">'
                        f'{sp["tone"]}</div>'
                        f'<div style="font-size:0.7rem;color:{COLORS["muted"]};'
                        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">'
                        f'Suggested hook</div>'
                        f'<div style="font-size:0.85rem;font-style:italic;margin-bottom:8px;">'
                        f'"{sp["hook"]}"</div>'
                        f'<div style="display:flex;gap:14px;font-size:0.72rem;'
                        f'color:{COLORS["muted"]};margin-bottom:10px;">'
                        f'<span><strong>CTA:</strong> {sp["cta"]}</span>'
                        f'<span><strong>Lift:</strong> {sp["lift"]}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    seg_input_key = f"seg_input_{camp['id']}_{i}"
                    seg_input = st.text_area(
                        "Personalization input for this segment",
                        value=st.session_state.get(seg_input_key,
                            f"Lead with: {sp['hook']} · Tone: {sp['tone']}"),
                        height=70,
                        key=seg_input_key,
                    )

                    seg_email_key = f"seg_email_{camp['id']}_{i}"
                    seg_sms_key   = f"seg_sms_{camp['id']}_{i}"

                    if st.button("Generate for this segment",
                                 key=f"seg_btn_{camp['id']}_{i}",
                                 use_container_width=True):
                        seg_tone_combined = (tone or "") + " · " + seg_input
                        seg_email, seg_sms, _ = _seg_compose(
                            camp, seg_tone_combined, cta, offer, highlights,
                            selected_subject_text, seg_name,
                        )
                        st.session_state[seg_email_key] = seg_email
                        st.session_state[seg_sms_key]   = seg_sms

                    seg_saved_key = f"seg_saved_{camp['id']}_{i}"

                    if seg_email_key in st.session_state:
                        st.markdown(
                            '<div style="font-family:\'Barlow Condensed\',sans-serif;'
                            'font-size:0.7rem;letter-spacing:0.08em;text-transform:uppercase;'
                            'color:#666;margin-top:10px;">Email — personalized</div>',
                            unsafe_allow_html=True,
                        )
                        _seg_email_view = st.text_area(
                            "Email", value=st.session_state[seg_email_key],
                            height=200, key=f"seg_email_view_{camp['id']}_{i}",
                            label_visibility="collapsed",
                        )
                        st.markdown(
                            '<div style="font-family:\'Barlow Condensed\',sans-serif;'
                            'font-size:0.7rem;letter-spacing:0.08em;text-transform:uppercase;'
                            'color:#666;margin-top:6px;">SMS — personalized</div>',
                            unsafe_allow_html=True,
                        )
                        _seg_sms_view = st.text_area(
                            "SMS", value=st.session_state[seg_sms_key],
                            height=110, key=f"seg_sms_view_{camp['id']}_{i}",
                            label_visibility="collapsed",
                        )

                        # ── Save segment copy ─────────────────────────────
                        _seg_meta = st.session_state.get(seg_saved_key, {})
                        if _seg_meta:
                            st.markdown(
                                f'<div style="display:inline-flex;align-items:center;'
                                f'gap:6px;background:{COLORS["lime"]};border:1px solid '
                                f'{COLORS["black"]};border-radius:5px;padding:3px 8px;'
                                f'margin-top:6px;margin-bottom:4px;">'
                                f'<span style="font-size:0.62rem;font-weight:700;">✓ Saved</span>'
                                f'<span style="font-size:0.60rem;color:#555;">'
                                f'· {_seg_meta["saved_by"]} · {_seg_meta["saved_at"]}'
                                f'</span></div>',
                                unsafe_allow_html=True,
                            )
                        if st.button("Save segment copy", key=f"seg_save_{camp['id']}_{i}",
                                     use_container_width=True):
                            _now = datetime.now().strftime("%b %d, %Y %H:%M")
                            st.session_state[seg_saved_key] = {
                                "email":    _seg_email_view,
                                "sms":      _seg_sms_view,
                                "segment":  seg_name,
                                "saved_by": CURRENT_USER,
                                "saved_at": _now,
                            }
                            log = st.session_state.setdefault("copy_review_log", [])
                            log.append({
                                "campaign_id":   camp["id"],
                                "campaign_name": camp["name"],
                                "channel":       camp["channel"].upper(),
                                "action":        f"Segment copy saved — {seg_name}",
                                "saved_by":      CURRENT_USER,
                                "saved_at":      _now,
                                "status":        "Draft",
                                "reviewer":      "",
                            })
                            st.rerun()
                    else:
                        st.markdown(
                            f'<div style="font-size:0.72rem;color:{COLORS["muted"]};'
                            f'font-style:italic;margin-top:6px;">Click "Generate for this '
                            f'segment" to see the personalized email and SMS.</div>',
                            unsafe_allow_html=True,
                        )

    # ── Save / Send for Review ───────────────────────────────────────────────
    st.divider()
    st.markdown(
        '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.72rem;'
        'letter-spacing:0.1em;text-transform:uppercase;font-weight:700;'
        'margin-bottom:12px;">Save copy</div>',
        unsafe_allow_html=True,
    )

    # Read current textarea values (user may have edited them after Generate)
    _current_email = st.session_state.get(
        f"gen_body_v{gen_version}", st.session_state.get("gen_email_text", ""))
    _current_sms   = st.session_state.get(
        f"gen_sms_v{gen_version}",   st.session_state.get("gen_sms_text", ""))

    _saved_meta     = st.session_state.get(f"saved_copy_{camp['id']}", {})
    _saved_status   = _saved_meta.get("status", "")
    _saved_by       = _saved_meta.get("saved_by", "")
    _saved_at       = _saved_meta.get("saved_at", "")
    _saved_reviewer = _saved_meta.get("reviewer", "")

    if _saved_status:
        _sc = COLORS["warn"] if _saved_status == "Draft" else COLORS["lime"]
        _sb = "#777" if _saved_status == "Draft" else COLORS["black"]
        _rev_part = f" · Reviewer: {_saved_reviewer}" if _saved_reviewer else ""
        st.markdown(
            f'<div style="display:inline-flex;align-items:center;gap:8px;'
            f'background:{_sc};border:1.5px solid {_sb};border-radius:6px;'
            f'padding:5px 10px;margin-bottom:10px;">'
            f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-weight:700;'
            f'font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;">'
            f'{_saved_status}</span>'
            f'<span style="font-size:0.68rem;color:#555;">'
            f' · {_saved_by} · {_saved_at}{_rev_part}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Layout: Save btn | Reviewer picker | Send btn | hint text
    _act1, _act2, _act3, _act4 = st.columns([1, 1.4, 1, 2])

    REVIEWERS = [
        "Anna", "Marketing Director", "Marketing Strategy",
        "Brand & Social", "Growth Marketing", "Retail Marketing",
        "Merchandising & Planning", "Design", "Operations", "Data",
    ]
    _REVIEWER_OPTIONS = ["— select reviewer —"] + REVIEWERS

    with _act2:
        st.markdown(
            '<div style="font-size:0.65rem;color:#555;margin-bottom:3px;">'
            'Reviewer <span style="color:#c00;font-weight:700;">*</span>'
            ' <span style="font-style:italic;color:#999;">'
            '(required to send for review)</span></div>',
            unsafe_allow_html=True,
        )
        _reviewer_sel = st.selectbox(
            "Reviewer",
            _REVIEWER_OPTIONS,
            index=0,
            key=f"copy_reviewer_{camp['id']}",
            label_visibility="collapsed",
        )
    _reviewer_chosen = _reviewer_sel if _reviewer_sel != "— select reviewer —" else ""

    def _build_copy_payload(status, reviewer=""):
        _now = datetime.now().strftime("%b %d, %Y %H:%M")
        st.session_state[f"saved_copy_{camp['id']}"] = {
            "email":      _current_email,
            "sms":        _current_sms,
            "subject":    selected_subject_text,
            "tone":       st.session_state.get("gen_tone", ""),
            "cta":        st.session_state.get("gen_cta", ""),
            "offer":      st.session_state.get("gen_offer", ""),
            "highlights": st.session_state.get("gen_highlights", ""),
            "preview":    st.session_state.get("gen_preview", ""),
            "status":     status,
            "saved_by":   CURRENT_USER,
            "saved_at":   _now,
            "reviewer":   reviewer,
        }
        log = st.session_state.setdefault("copy_review_log", [])
        log.append({
            "campaign_id":   camp["id"],
            "campaign_name": camp["name"],
            "channel":       camp["channel"].upper(),
            "action":        "Saved as draft" if status == "Draft" else "Sent for review",
            "saved_by":      CURRENT_USER,
            "saved_at":      _now,
            "status":        status,
            "reviewer":      reviewer,
        })

    with _act1:
        st.markdown('<div style="height:22px"></div>', unsafe_allow_html=True)
        if st.button("Save as draft", key="copy_save_draft", use_container_width=True):
            _build_copy_payload("Draft")
            st.rerun()

    with _act3:
        st.markdown('<div style="height:22px"></div>', unsafe_allow_html=True)
        _can_review = bool(_reviewer_chosen)
        if st.button("Send for review", key="copy_send_review", type="primary",
                     use_container_width=True, disabled=not _can_review):
            _build_copy_payload("In Review", reviewer=_reviewer_chosen)
            st.rerun()
        if not _can_review:
            st.markdown(
                f'<div style="font-size:0.62rem;color:{COLORS["danger"]};margin-top:3px;">'
                f'Select a reviewer first</div>',
                unsafe_allow_html=True,
            )

    with _act4:
        st.markdown('<div style="height:22px"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-size:0.65rem;color:{COLORS["muted"]};padding:4px 0;">'
            f'By <strong>{CURRENT_USER}</strong>. '
            f'<em>Save as draft</em> preserves without routing. '
            f'<em>Send for review</em> notifies the reviewer and flags '
            f'the copy in Campaign Review.</p>',
            unsafe_allow_html=True,
        )

    # ── Save to Google Drive ─────────────────────────────────────────────────
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    _gdoc_id_key  = f"gdoc_id_{camp['id']}"
    _gdoc_url_key = f"gdoc_url_{camp['id']}"
    _gdoc_id  = st.session_state.get(_gdoc_id_key, "")
    _gdoc_url = st.session_state.get(_gdoc_url_key, "")

    _drive_col1, _drive_col2, _drive_col3 = st.columns([1, 1, 3])

    with _drive_col1:
        _save_drive_label = "📄 Update in Drive" if _gdoc_id else "📄 Save to Drive"
        if st.button(_save_drive_label, key="copy_save_drive", use_container_width=True,
                     disabled=not _DRIVE_AVAILABLE):
            _copy_payload = st.session_state.get(f"saved_copy_{camp['id']}", {})
            if not _copy_payload:
                # build one on the fly from current textarea values
                _copy_payload = {
                    "email":      _current_email,
                    "sms":        _current_sms,
                    "subject":    selected_subject_text,
                    "tone":       st.session_state.get("gen_tone", ""),
                    "cta":        st.session_state.get("gen_cta", ""),
                    "offer":      st.session_state.get("gen_offer", ""),
                    "highlights": st.session_state.get("gen_highlights", ""),
                    "preview":    st.session_state.get("gen_preview", ""),
                    "saved_by":   CURRENT_USER,
                }
            with st.spinner("Saving to Google Drive…"):
                try:
                    if _gdoc_id:
                        _gdrive.update_copy_doc(_gdoc_id, camp, _copy_payload)
                    else:
                        _new_id, _new_url = _gdrive.create_copy_doc(camp, _copy_payload)
                        st.session_state[_gdoc_id_key]  = _new_id
                        st.session_state[_gdoc_url_key] = _new_url
                    st.session_state[f"gdoc_saved_at_{camp['id']}"] = \
                        datetime.now().strftime("%b %d, %Y %H:%M")
                    st.rerun()
                except Exception as _e:
                    st.error(f"Drive error: {_e}")

    with _drive_col2:
        if st.button("↻ Sync from Drive", key="copy_sync_drive",
                     use_container_width=True,
                     disabled=(not _DRIVE_AVAILABLE or not _gdoc_id)):
            with st.spinner("Reading from Google Drive…"):
                try:
                    _synced = _gdrive.read_copy_doc(_gdoc_id)
                    # Push synced fields into session state so the next render
                    # picks them up via the seeded gen_email_text / gen_sms_text.
                    if _synced.get("email"):
                        st.session_state["gen_email_text"] = _synced["email"]
                    if _synced.get("sms"):
                        st.session_state["gen_sms_text"]   = _synced["sms"]
                    # Update the saved_copy payload with the Drive version
                    _existing = st.session_state.get(f"saved_copy_{camp['id']}", {})
                    _existing.update({k: v for k, v in _synced.items() if v})
                    st.session_state[f"saved_copy_{camp['id']}"] = _existing
                    # Bump gen_version so email/SMS textareas refresh
                    st.session_state["gen_version"] = \
                        st.session_state.get("gen_version", 0) + 1
                    st.rerun()
                except Exception as _e:
                    st.error(f"Sync error: {_e}")

    with _drive_col3:
        if _gdoc_url:
            _saved_at_drive = st.session_state.get(f"gdoc_saved_at_{camp['id']}", "")
            _ts = f" · {_saved_at_drive}" if _saved_at_drive else ""
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;padding:8px 0;">'
                f'<span style="font-size:0.65rem;color:{COLORS["muted"]};">'
                f'Saved to Drive{_ts}</span>'
                f'<a href="{_gdoc_url}" target="_blank" '
                f'style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.72rem;'
                f'font-weight:700;letter-spacing:0.05em;text-transform:uppercase;'
                f'color:{COLORS["black"]};background:{COLORS["lime"]};'
                f'border:1.5px solid {COLORS["black"]};border-radius:5px;'
                f'padding:3px 10px;text-decoration:none;">Open in Drive →</a>'
                f'</div>',
                unsafe_allow_html=True,
            )
        elif not _DRIVE_AVAILABLE:
            st.markdown(
                f'<p style="font-size:0.65rem;color:{COLORS["muted"]};padding:8px 0;">'
                f'Drive unavailable — run <code>gcloud auth application-default login</code> '
                f'and restart the dashboard.</p>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<p style="font-size:0.65rem;color:{COLORS["muted"]};padding:8px 0;">'
                f'Saves to '
                f'<a href="https://drive.google.com/drive/folders/{_gdrive.FOLDER_ID}" '
                f'target="_blank" style="color:{COLORS["black"]};">Glinta Copy folder</a>. '
                f'One Google Doc per campaign — edits made there sync back here.</p>',
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# DESIGN BRIEF TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_brief:

    # ── Campaign selector ─────────────────────────────────────────────────────
    _brief_active_id  = st.session_state.get("active_campaign_id", all_campaigns[0]["id"])
    _brief_active_idx = next((i for i, c in enumerate(all_campaigns)
                              if c["id"] == _brief_active_id), 0)
    _brief_sel_col, _ = st.columns([3, 3])
    with _brief_sel_col:
        _brief_chosen = st.selectbox(
            "Editing campaign",
            camp_labels,
            index=_brief_active_idx,
            key="gen_camp_brief",
            help="Pulls from Planning → Upcoming Campaigns: scheduled sends from your "
                 "campaign data plus anything you added in Plan a Campaign.",
        )
    camp = all_campaigns[camp_labels.index(_brief_chosen)]
    st.session_state["active_campaign_id"] = camp["id"]
    campaign_context_card(camp)

    # ── Air / Dropbox ─────────────────────────────────────────────────────────
    _assets = _mock_assets_for_campaign(camp)
    _air_folder_key = f"air_folder_{camp['id']}"
    _dbx_folder_key = f"dbx_folder_{camp['id']}"

    with st.expander("**Air / Dropbox** — reference assets & links for this campaign",
                     expanded=False):
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">'
            f'<div style="display:flex;align-items:center;gap:6px;">'
            f'<div style="width:22px;height:22px;border-radius:5px;background:{_AIR_COLOR};'
            f'display:flex;align-items:center;justify-content:center;">'
            f'<span style="color:#fff;font-size:0.55rem;font-weight:900;'
            f'font-family:\'Barlow Condensed\',sans-serif;letter-spacing:0.05em;">AIR</span>'
            f'</div>'
            f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.9rem;'
            f'font-weight:800;letter-spacing:0.04em;text-transform:uppercase;">Air</span>'
            f'</div>'
            f'<span style="color:{COLORS["muted"]};font-size:0.8rem;">+</span>'
            f'<div style="display:flex;align-items:center;gap:6px;">'
            f'<div style="width:22px;height:22px;border-radius:50%;background:{_DBX_COLOR};'
            f'display:flex;align-items:center;justify-content:center;">'
            f'<span style="color:#fff;font-size:0.5rem;font-weight:900;">◆</span>'
            f'</div>'
            f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.9rem;'
            f'font-weight:800;letter-spacing:0.04em;text-transform:uppercase;">Dropbox</span>'
            f'</div>'
            f'<span style="font-size:0.65rem;color:{COLORS["muted"]};margin-left:4px;">'
            f'Campaign asset references — include links in the brief for the design team</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        _fl1, _fl2 = st.columns(2)
        with _fl1:
            _air_folder = st.text_input(
                "Air folder URL",
                value=st.session_state.get(_air_folder_key,
                    "https://app.air.inc/a/glinta-creative/2026/may"),
                key=_air_folder_key,
                placeholder="https://app.air.inc/…",
            )
        with _fl2:
            _dbx_folder = st.text_input(
                "Dropbox folder URL",
                value=st.session_state.get(_dbx_folder_key,
                    "https://www.dropbox.com/sh/glinta-assets/may2026"),
                key=_dbx_folder_key,
                placeholder="https://www.dropbox.com/sh/…",
            )
        st.markdown(
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.65rem;'
            f'letter-spacing:0.1em;text-transform:uppercase;color:#888;'
            f'margin:10px 0 8px;">Assets for this campaign</div>',
            unsafe_allow_html=True,
        )
        _type_colors = {
            "Hero": "#1C1C1E", "Product tile": "#444", "Lifestyle": "#5B4FCF",
            "Graphic": "#0061FF", "Banner": "#C47F00", "Packaging": "#2E7D32",
        }
        _asset_pairs = [_assets[i:i+2] for i in range(0, len(_assets), 2)]
        for pair in _asset_pairs:
            _pair_cols = st.columns(2)
            for _col, asset in zip(_pair_cols, pair):
                _incl_key = f"asset_incl_{camp['id']}_{asset['name']}"
                _included = st.session_state.get(_incl_key, True)
                _tc = _type_colors.get(asset["type"], "#555")
                _bg = COLORS["offwhite"] if _included else COLORS["white"]
                _border = COLORS["black"] if _included else COLORS["border"]
                with _col:
                    st.markdown(
                        f'<div style="background:{_bg};border:1.5px solid {_border};'
                        f'border-radius:8px;padding:9px 11px;margin-bottom:8px;">'
                        f'<div style="display:flex;justify-content:space-between;'
                        f'align-items:flex-start;gap:6px;margin-bottom:6px;">'
                        f'<div style="font-size:0.76rem;font-weight:600;flex:1;'
                        f'line-height:1.2;word-break:break-all;">{asset["name"]}</div>'
                        f'<span style="background:{_tc};color:#fff;padding:1px 6px;'
                        f'border-radius:50px;font-size:0.55rem;font-weight:700;'
                        f'white-space:nowrap;font-family:\'Barlow Condensed\',sans-serif;">'
                        f'{asset["type"].upper()}</span>'
                        f'</div>'
                        f'<div style="display:flex;gap:8px;flex-wrap:wrap;">'
                        f'<a href="{asset["air_url"]}" target="_blank" '
                        f'style="font-size:0.62rem;font-weight:700;color:{_AIR_COLOR};'
                        f'background:#f0f0f0;border-radius:4px;padding:2px 7px;'
                        f'text-decoration:none;font-family:\'Barlow Condensed\',sans-serif;'
                        f'letter-spacing:0.04em;text-transform:uppercase;">Air →</a>'
                        f'<a href="{asset["dbx_url"]}" target="_blank" '
                        f'style="font-size:0.62rem;font-weight:700;color:{_DBX_COLOR};'
                        f'background:#e8f0ff;border-radius:4px;padding:2px 7px;'
                        f'text-decoration:none;font-family:\'Barlow Condensed\',sans-serif;'
                        f'letter-spacing:0.04em;text-transform:uppercase;">Dropbox →</a>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    _new_incl = st.checkbox(
                        "Include in brief",
                        value=_included,
                        key=f"asset_cb_{camp['id']}_{asset['name']}",
                    )
                    if _new_incl != _included:
                        st.session_state[_incl_key] = _new_incl
                        st.rerun()
        _included_assets = [
            a for a in _assets
            if st.session_state.get(f"asset_incl_{camp['id']}_{a['name']}", True)
        ]
        if _included_assets:
            st.markdown(
                f'<div style="background:{COLORS["offwhite"]};border-left:3px solid '
                f'{COLORS["black"]};border-radius:0 6px 6px 0;padding:9px 12px;'
                f'margin-top:6px;">'
                f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.62rem;'
                f'letter-spacing:0.09em;text-transform:uppercase;color:#888;margin-bottom:5px;">'
                f'Included in brief ({len(_included_assets)} asset{"s" if len(_included_assets)!=1 else ""})'
                f'</div>'
                + "".join(
                    f'<div style="font-size:0.72rem;padding:2px 0;">'
                    f'<span style="font-weight:600;">{a["name"]}</span>'
                    f' &nbsp;<span style="color:{COLORS["muted"]};">{a["type"]}</span>'
                    f' &nbsp;<a href="{a["air_url"]}" target="_blank" '
                    f'style="color:{_AIR_COLOR};font-size:0.65rem;text-decoration:none;'
                    f'font-weight:700;">Air</a>'
                    f' · <a href="{a["dbx_url"]}" target="_blank" '
                    f'style="color:{_DBX_COLOR};font-size:0.65rem;text-decoration:none;'
                    f'font-weight:700;">Dropbox</a>'
                    f'</div>'
                    for a in _included_assets
                )
                + f'</div>',
                unsafe_allow_html=True,
            )

    # ── Asana ─────────────────────────────────────────────────────────────────
    with st.expander("**Asana** — push brief & assign task owners", expanded=False):
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">'
            f'<div style="width:28px;height:28px;border-radius:50%;'
            f'background:{_ASANA_COLOR};display:flex;align-items:center;'
            f'justify-content:center;">'
            f'<div style="width:10px;height:10px;border-radius:50%;background:#fff;"></div>'
            f'</div>'
            f'<div>'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.9rem;'
            f'font-weight:800;letter-spacing:0.04em;text-transform:uppercase;">Asana</div>'
            f'<div style="font-size:0.65rem;color:#888;">Push design brief tasks to Asana '
            f'and assign owners — pulls copy and campaign details automatically</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        _asana_col1, _asana_col2, _asana_col3 = st.columns([2, 2, 2])
        with _asana_col1:
            asana_project = st.selectbox(
                "Asana project",
                ["Campaign Operations — 2026", "Creative Briefs", "Email & SMS Launches",
                 "Studio Operations"],
                key=f"asana_project_{camp['id']}",
            )
            asana_section = st.selectbox(
                "Section / board column",
                ["📋 Backlog", "🔵 In Brief", "🟡 Design In Progress",
                 "🟠 In Review", "✅ Approved"],
                index=1,
                key=f"asana_section_{camp['id']}",
            )
        with _asana_col2:
            asana_task_name = st.text_input(
                "Task name",
                value=f"[{camp['channel'].upper()}] {camp['name']} — Design Brief",
                key=f"asana_task_{camp['id']}",
            )
            _brief_due = camp["send_date"] - __import__("datetime").timedelta(days=5)
            asana_due = st.date_input(
                "Due date",
                value=_brief_due,
                key=f"asana_due_{camp['id']}",
                help="Defaults to 5 days before send date — adjust as needed.",
            )
        with _asana_col3:
            _ASANA_OWNERS = [
                "Anna", "Marketing Director", "Marketing Strategy",
                "Brand & Social", "Growth Marketing", "Retail Marketing",
                "Merchandising & Planning", "Design", "Operations", "Data",
            ]
            asana_owner = st.selectbox(
                "Assigned to",
                _ASANA_OWNERS,
                index=_ASANA_OWNERS.index("Design"),
                key=f"asana_owner_{camp['id']}",
            )
            asana_collaborators = st.multiselect(
                "Collaborators",
                _ASANA_OWNERS,
                default=["Design"],
                key=f"asana_collab_{camp['id']}",
            )
        st.markdown(
            f'<div style="background:{COLORS["offwhite"]};border-radius:8px;'
            f'padding:10px 14px;margin:10px 0 12px;font-size:0.72rem;line-height:1.6;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.62rem;'
            f'letter-spacing:0.09em;text-transform:uppercase;color:#888;margin-bottom:4px;">'
            f'Fields that will populate the Asana task description</div>'
            f'<span style="color:#888;">Campaign:</span> {camp["name"]} &nbsp;·&nbsp; '
            f'<span style="color:#888;">Channel:</span> {camp["channel"].upper()} &nbsp;·&nbsp; '
            f'<span style="color:#888;">Send date:</span> {camp["send_date"].strftime("%b %d, %Y")}'
            f'<br>'
            f'<span style="color:#888;">Segment:</span> {camp["segment"]} &nbsp;·&nbsp; '
            f'<span style="color:#888;">Objective:</span> '
            f'{camp["category"]} · {camp["channel"].upper()} revenue target'
            f'<br>'
            f'<span style="color:#888;">Subject:</span> '
            + (
                f'<em>(select a subject on Copy Generation tab)</em>'
                if not st.session_state.get("gen_email_text")
                else f'pulled from Copy Generation'
            ) +
            f'<br>'
            f'<span style="color:#888;">Assets required:</span> Hero image · Product tiles · '
            f'CTA button'
            f'</div>',
            unsafe_allow_html=True,
        )
        _push_col, _status_col = st.columns([2, 3])
        with _push_col:
            if st.button(
                "Push to Asana",
                type="primary",
                key=f"asana_push_{camp['id']}",
                use_container_width=True,
            ):
                st.session_state[f"asana_pushed_{camp['id']}"] = {
                    "project": asana_project,
                    "section": asana_section,
                    "task":    asana_task_name,
                    "owner":   asana_owner,
                    "due":     asana_due.strftime("%b %d, %Y"),
                }
                st.rerun()
        with _status_col:
            _pushed = st.session_state.get(f"asana_pushed_{camp['id']}")
            if _pushed:
                st.markdown(
                    f'<div style="background:{COLORS["lime"]};border:1.5px solid '
                    f'{COLORS["black"]};border-radius:6px;padding:7px 12px;'
                    f'font-size:0.72rem;font-weight:600;line-height:1.5;">'
                    f'✓ Task created in <strong>{_pushed["project"]}</strong> · '
                    f'{_pushed["section"]}<br>'
                    f'Assigned to <strong>{_pushed["owner"]}</strong> · '
                    f'Due <strong>{_pushed["due"]}</strong> · <em>(mock)</em>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="font-size:0.7rem;color:{COLORS["muted"]};'
                    f'padding:8px 0;">No task pushed yet.</div>',
                    unsafe_allow_html=True,
                )

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # DESIGN BRIEF
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("<h2>Design Brief</h2>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;color:#666;'
        'margin:-0.4rem 0 1rem;">Auto-filled from campaign details and the Copy Generation tab — '
        'complete and drop in the briefs folder for design review</p>',
        unsafe_allow_html=True,
    )

    # ── Pull approved values from the Copy Generation tab ────────────────────
    cg_tone       = (st.session_state.get("gen_tone")       or "").strip()
    cg_cta        = (st.session_state.get("gen_cta")        or "").strip()
    cg_offer      = (st.session_state.get("gen_offer")      or "").strip()
    cg_highlights = (st.session_state.get("gen_highlights") or "").strip()
    cg_preview    = (st.session_state.get("gen_preview")    or "").strip()
    cg_email      = (st.session_state.get("gen_email_text") or "").strip()
    cg_sms        = (st.session_state.get("gen_sms_text")   or "").strip()

    # Selected subject line from Copy Generation (mirrors that tab's logic)
    _brief_options = historical_subject_options(camp, _cdf, n=3)
    _draft_subj = (camp.get("subject_line_draft") or "").strip()
    if _draft_subj and _draft_subj not in {s for s, *_ in _brief_options}:
        _brief_options.insert(0, (_draft_subj, "From your brief", "—", ""))
        _brief_options = _brief_options[:3]
    _sel_idx = min(st.session_state.get("selected_subject", 0),
                   max(len(_brief_options) - 1, 0))
    cg_subject = (_brief_options[_sel_idx][0] if _brief_options else _draft_subj)

    has_copy_gen = bool(cg_email or cg_sms)
    if has_copy_gen:
        st.markdown(
            f'<div style="background:{COLORS["lime"]};border:1.5px solid {COLORS["black"]};'
            f'border-radius:8px;padding:9px 12px;margin-bottom:14px;'
            f'font-family:\'Barlow\',sans-serif;font-size:0.78rem;font-weight:600;">'
            f'✓ Pulled from Copy Generation: subject, tone, CTA, offer, highlights, '
            f'preview text, and approved email + SMS copy.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="background:{COLORS["offwhite"]};border-left:3px solid {COLORS["warn"]};'
            f'padding:9px 12px;margin-bottom:14px;font-family:\'Barlow\',sans-serif;'
            f'font-size:0.78rem;">No Copy Generation output yet — open the '
            f'<strong>Copy Generation</strong> tab first so this brief can be informed by '
            f'the approved subject, tone, and copy.</div>',
            unsafe_allow_html=True,
        )

    b1, b2 = st.columns(2)

    with b1:
        st.markdown("<h3>Campaign details</h3>", unsafe_allow_html=True)
        brief_name     = st.text_input("Campaign name",    value=camp["name"])
        brief_channel  = st.text_input("Channel",          value=camp["channel"].upper())
        brief_send     = st.text_input("Send date",        value=camp["send_date"].strftime("%B %d, %Y"))
        brief_segment  = st.text_input("Segment",          value=camp["segment"])
        brief_audience = st.text_input("Audience size",    value=f"{camp['audience_est']:,}")
        brief_owner    = st.text_input("Campaign owner",   value=camp["assigned_to"])

    with b2:
        st.markdown("<h3>Creative direction</h3>", unsafe_allow_html=True)

        # Campaign objective — augmented with CTA + offer from Copy Generation
        _obj_lines = [
            f"Drive revenue for {camp['category']} send. "
            f"Target {fmt_revenue(camp['revenue_est'])} revenue. "
            f"Segment: {camp['segment']}."
        ]
        if cg_cta:
            _obj_lines.append(f"Primary CTA: {cg_cta}.")
        if cg_offer:
            _obj_lines.append(f"Offer: code {cg_offer}.")
        brief_objective = st.text_area(
            "Campaign objective",
            value=" ".join(_obj_lines),
            height=90,
            key=f"brief_objective_{camp['id']}",
        )

        brief_subject = st.text_area(
            "Subject line (approved)",
            value=cg_subject,
            height=60,
            key=f"brief_subject_{camp['id']}",
            help="Pulled from the subject line you selected on the Copy Generation tab.",
        )
        brief_preview = st.text_input(
            "Preview / preheader text",
            value=cg_preview,
            key=f"brief_preview_{camp['id']}",
            help="Pulled from the preview text on the Copy Generation tab.",
        )

        # Tone direction — lead with what was set in Copy Generation
        _tone_default = (
            f"{cg_tone}\n\n"
            "Visual direction: clean white background, minimal makeup, "
            "no text on hero image."
        ) if cg_tone else (
            "Warm and celebratory. Feature a curated stack with gold studs + opal hoops. "
            "Clean white background. Models with minimal makeup. No text on hero image."
        )
        brief_tone_dir = st.text_area(
            "Tone & style direction",
            value=_tone_default,
            height=110,
            key=f"brief_tone_{camp['id']}",
            help="First line is the tone description from Copy Generation.",
        )

        # Required assets — reference the highlights from Copy Generation
        if cg_highlights:
            _asset_default = (
                f"Hero image (600×400px): feature {cg_highlights}\n"
                f"Product tiles (300×300px): 3–4 individual products from the highlights above\n"
                f"CTA button: black, Barlow Condensed 700, '{cg_cta or 'Shop the edit'}'"
            )
        else:
            _asset_default = (
                "Hero image (600×400px): stack shot with gold flatbacks + opal cluster\n"
                "Product tiles (300×300px): 3–4 individual products\n"
                "CTA button: black, Barlow Condensed 700, 'Shop the edit'"
            )
        brief_assets = st.text_area(
            "Required assets",
            value=_asset_default,
            height=110,
            key=f"brief_assets_{camp['id']}",
        )

    # ── CTA callout box ──────────────────────────────────────────────────────
    st.divider()
    _display_cta = cg_cta or "Shop the edit"
    _display_offer = cg_offer or ""
    st.markdown(
        f'<div style="background:{COLORS["offwhite"]};border:2px solid {COLORS["black"]};'
        f'border-radius:10px;padding:16px 20px;margin:4px 0 16px;">'
        f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.65rem;'
        f'letter-spacing:0.1em;text-transform:uppercase;color:{COLORS["muted"]};'
        f'margin-bottom:6px;">Primary CTA</div>'
        f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.35rem;'
        f'font-weight:800;letter-spacing:0.04em;text-transform:uppercase;'
        f'margin-bottom:{"10px" if _display_offer else "0"};">{_display_cta}</div>'
        + (
            f'<div style="display:inline-block;background:{COLORS["yellow"]};'
            f'border:1.5px solid {COLORS["black"]};border-radius:4px;'
            f'padding:3px 10px;font-family:\'Barlow Condensed\',sans-serif;'
            f'font-size:0.75rem;font-weight:700;letter-spacing:0.06em;">'
            f'CODE: {_display_offer}</div>'
            if _display_offer else ""
        ) +
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Approved copy from Copy Generation (read-only reference for design) ──
    if has_copy_gen:
        st.markdown("<h3>Approved copy (from Copy Generation)</h3>",
                    unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
            f'color:{COLORS["muted"]};margin:-0.4rem 0 0.8rem;">Reference for the '
            f'designer — edit on the Copy Generation tab to change.</p>',
            unsafe_allow_html=True,
        )
        ac1, ac2 = st.columns(2)
        with ac1:
            st.markdown(
                '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.7rem;'
                'letter-spacing:0.08em;text-transform:uppercase;color:#666;margin-bottom:4px;">'
                'Email body</div>',
                unsafe_allow_html=True,
            )
            st.text_area(
                "Approved email", value=cg_email or "(no email copy generated yet)",
                height=240, key=f"brief_email_ref_{camp['id']}",
                label_visibility="collapsed", disabled=True,
            )
        with ac2:
            st.markdown(
                '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.7rem;'
                'letter-spacing:0.08em;text-transform:uppercase;color:#666;margin-bottom:4px;">'
                'SMS copy</div>',
                unsafe_allow_html=True,
            )
            st.text_area(
                "Approved SMS", value=cg_sms or "(no SMS copy generated yet)",
                height=140, key=f"brief_sms_ref_{camp['id']}",
                label_visibility="collapsed", disabled=True,
            )

    # ── Insights from previous campaigns ─────────────────────────────────────
    st.divider()
    st.markdown("<h3>Insights from previous campaigns</h3>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="background:{COLORS["yellow"]};border:1.5px solid {COLORS["black"]};'
        f'border-radius:6px;padding:7px 12px;margin-bottom:14px;'
        f'font-family:\'Barlow\',sans-serif;font-size:0.72rem;">'
        f'⚠️ <strong>Illustrative data</strong> — figures below are for directional '
        f'guidance only and do not represent actual campaign results.</div>',
        unsafe_allow_html=True,
    )

    _ASSETS = Path(__file__).parent.parent.parent / "image assets"
    _img_lifestyle   = _ASSETS / "Screenshot 2026-05-05 at 8.58.24 PM.png"
    _img_educational = _ASSETS / "Screenshot 2026-05-05 at 8.57.25 PM.png"

    ins1, ins2 = st.columns(2, gap="large")

    with ins1:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
            f'<span style="background:{COLORS["lime"]};border:1.5px solid {COLORS["black"]};'
            f'border-radius:4px;padding:2px 9px;font-family:\'Barlow Condensed\',sans-serif;'
            f'font-size:0.65rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;">'
            f'✓ WORKED WELL</span>'
            f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.78rem;'
            f'font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">'
            f'Curated ear stack · lifestyle imagery</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if _img_lifestyle.exists():
            st.image(str(_img_lifestyle), use_container_width=True)
        st.markdown(
            f'<div style="background:{COLORS["offwhite"]};border-radius:8px;'
            f'padding:10px 14px;margin-top:8px;">'
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px;">'
            f'<div style="text-align:center;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.1rem;'
            f'font-weight:800;">34.2%</div>'
            f'<div style="font-size:0.6rem;color:{COLORS["muted"]};'
            f'text-transform:uppercase;letter-spacing:0.07em;">Open rate</div>'
            f'</div>'
            f'<div style="text-align:center;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.1rem;'
            f'font-weight:800;">4.8%</div>'
            f'<div style="font-size:0.6rem;color:{COLORS["muted"]};'
            f'text-transform:uppercase;letter-spacing:0.07em;">CTR</div>'
            f'</div>'
            f'<div style="text-align:center;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.1rem;'
            f'font-weight:800;">1.9%</div>'
            f'<div style="font-size:0.6rem;color:{COLORS["muted"]};'
            f'text-transform:uppercase;letter-spacing:0.07em;">Conv rate</div>'
            f'</div>'
            f'</div>'
            f'<div style="font-size:0.7rem;color:{COLORS["muted"]};line-height:1.4;">'
            f'Warm + celebratory tone · personal "curated for you" framing · '
            f'product benefit callouts visible · +38% CTR vs category avg</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with ins2:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
            f'<span style="background:#f0f0f0;border:1.5px solid {COLORS["border"]};'
            f'border-radius:4px;padding:2px 9px;font-family:\'Barlow Condensed\',sans-serif;'
            f'font-size:0.65rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;'
            f'color:{COLORS["muted"]};">✗ BELOW AVG</span>'
            f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.78rem;'
            f'font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">'
            f'Educational / process content</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if _img_educational.exists():
            st.image(str(_img_educational), use_container_width=True)
        st.markdown(
            f'<div style="background:{COLORS["offwhite"]};border-radius:8px;'
            f'padding:10px 14px;margin-top:8px;">'
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px;">'
            f'<div style="text-align:center;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.1rem;'
            f'font-weight:800;color:{COLORS["muted"]};">22.1%</div>'
            f'<div style="font-size:0.6rem;color:{COLORS["muted"]};'
            f'text-transform:uppercase;letter-spacing:0.07em;">Open rate</div>'
            f'</div>'
            f'<div style="text-align:center;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.1rem;'
            f'font-weight:800;color:{COLORS["muted"]};">1.3%</div>'
            f'<div style="font-size:0.6rem;color:{COLORS["muted"]};'
            f'text-transform:uppercase;letter-spacing:0.07em;">CTR</div>'
            f'</div>'
            f'<div style="text-align:center;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.1rem;'
            f'font-weight:800;color:{COLORS["muted"]};">0.4%</div>'
            f'<div style="font-size:0.6rem;color:{COLORS["muted"]};'
            f'text-transform:uppercase;letter-spacing:0.07em;">Conv rate</div>'
            f'</div>'
            f'</div>'
            f'<div style="font-size:0.7rem;color:{COLORS["muted"]};line-height:1.4;">'
            f'Informational tone · "how we pierce" process focus · '
            f'no clear product hook · −27% CTR vs category avg</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    b3, b4 = st.columns(2)
    with b3:
        brief_ref = st.text_area(
            "Image references (Air/Dropbox links)",
            value=("• air.inc/glinta/may2026/mothersdaystyle\n"
                   "• dropbox.com/glinta-creative/stack-reference-2025\n"
                   "• Figma ref: figma.com/glinta/email-templates"),
            height=100
        )
    with b4:
        brief_notes = st.text_area(
            "Additional notes for design",
            value=("One round of consolidated revisions only before approval.\n"
                   "Mobile render required — test at 375px width.\n"
                   "Dark mode check required for email.\n"
                   "No stock photography."),
            height=100
        )

    # ── Send for review ───────────────────────────────────────────────────────
    st.divider()
    _brief_review_state = st.session_state.get(f"brief_review_{camp['id']}", {})
    _brief_is_in_review = _brief_review_state.get("status") in ("In Review", "Approved")

    st.markdown(
        '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.72rem;'
        'letter-spacing:0.1em;text-transform:uppercase;font-weight:700;'
        'border-bottom:1.5px solid #e0e0e0;padding-bottom:5px;margin-bottom:12px;">'
        'Send for review</div>',
        unsafe_allow_html=True,
    )

    if _brief_review_state.get("status") == "Approved":
        st.markdown(
            f'<div style="background:{COLORS["lime"]};border:1.5px solid {COLORS["black"]};'
            f'border-radius:8px;padding:9px 14px;font-family:\'Barlow\',sans-serif;'
            f'font-size:0.78rem;font-weight:600;">'
            f'✓ Brief approved by <strong>{_brief_review_state.get("approved_by", "—")}</strong>'
            f' · {_brief_review_state.get("approved_at", "")}</div>',
            unsafe_allow_html=True,
        )
        if st.button("Revoke brief approval", key=f"revoke_brief_{camp['id']}", type="secondary"):
            _brief_review_state["status"] = "In Review"
            _brief_review_state.pop("approved_by", None)
            _brief_review_state.pop("approved_at", None)
            st.session_state[f"brief_review_{camp['id']}"] = _brief_review_state
            st.rerun()

    elif _brief_review_state.get("status") == "In Review":
        st.markdown(
            f'<div style="background:{COLORS["yellow"]};border:1.5px solid {COLORS["black"]};'
            f'border-radius:8px;padding:9px 14px;font-family:\'Barlow\',sans-serif;'
            f'font-size:0.78rem;font-weight:600;margin-bottom:10px;">'
            f'⏳ In review — assigned to <strong>'
            f'{_brief_review_state.get("reviewer", "—")}</strong>'
            + (f' · <em style="font-weight:400;">'
               f'{_brief_review_state.get("note", "")}</em>'
               if _brief_review_state.get("note") else "")
            + f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Recall brief", key=f"recall_brief_{camp['id']}", type="secondary"):
            st.session_state.pop(f"brief_review_{camp['id']}", None)
            st.rerun()

    else:
        _BRIEF_OWNERS = [
            "Anna", "Marketing Director", "Marketing Strategy",
            "Brand & Social", "Growth Marketing", "Retail Marketing",
            "Merchandising & Planning", "Design", "Operations", "Data",
        ]
        _brev_col1, _brev_col2, _brev_col3 = st.columns([2, 3, 2])
        with _brev_col1:
            brief_reviewer = st.selectbox(
                "Reviewer (required)",
                ["— select reviewer —"] + _BRIEF_OWNERS,
                key=f"brief_reviewer_{camp['id']}",
            )
        with _brev_col2:
            brief_review_note = st.text_input(
                "Note for reviewer (optional)",
                placeholder="e.g. focus on hero image spec and CTA wording",
                key=f"brief_review_note_{camp['id']}",
            )
        with _brev_col3:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("Send for review", type="primary",
                         key=f"send_brief_review_{camp['id']}",
                         use_container_width=True):
                if brief_reviewer == "— select reviewer —":
                    st.error("A reviewer is required before sending.")
                else:
                    st.session_state[f"brief_review_{camp['id']}"] = {
                        "status":    "In Review",
                        "reviewer":  brief_reviewer,
                        "note":      brief_review_note,
                        "sent_at":   _today.strftime("%b %d"),
                    }
                    _log = st.session_state.get("copy_review_log", [])
                    _log.append({
                        "campaign_name": camp["name"],
                        "status":        "In Review",
                        "action":        "Brief sent for review",
                        "saved_by":      brief_reviewer,
                        "saved_at":      _today.strftime("%b %d"),
                        "reviewer":      brief_reviewer,
                    })
                    st.session_state["copy_review_log"] = _log
                    st.rerun()

    st.divider()
    export1, export2 = st.columns(2)
    with export1:
        _existing_doc_id = st.session_state.get(f"brief_doc_id_{camp['id']}")
        _btn_label = "Update brief in Drive" if _existing_doc_id else "Save brief to Drive"
        if st.button(_btn_label, type="primary", use_container_width=True):
            if not _DRIVE_AVAILABLE:
                st.error("Google Drive not available — check credentials.")
            else:
                try:
                    # Gather all brief field values for the doc
                    _brief_data = {
                        "objective":  st.session_state.get(f"brief_objective_{camp['id']}", ""),
                        "subject":    st.session_state.get(f"brief_subject_{camp['id']}",
                                          camp.get("subject_line_draft", "")),
                        "preview":    st.session_state.get(f"brief_preview_{camp['id']}", ""),
                        "tone":       st.session_state.get(f"brief_tone_{camp['id']}", ""),
                        "cta":        st.session_state.get("gen_cta", ""),
                        "offer":      st.session_state.get("gen_offer", ""),
                        "assets":     st.session_state.get(f"brief_assets_{camp['id']}", ""),
                        "refs":       st.session_state.get(f"brief_ref_{camp['id']}", ""),
                        "notes":      st.session_state.get(f"brief_notes_{camp['id']}", ""),
                        "audience":   f"{camp.get('audience_est', 0):,}",
                        "owner":      camp.get("assigned_to", "—"),
                        "email":      st.session_state.get("gen_email_text", ""),
                        "sms":        st.session_state.get("gen_sms_text", ""),
                        "review":     st.session_state.get(f"brief_review_{camp['id']}", {}),
                        "asana_task": st.session_state.get(f"asana_pushed_{camp['id']}"),
                    }
                    if _existing_doc_id:
                        _url = _gdrive.update_brief_doc(_existing_doc_id, camp, _brief_data)
                    else:
                        _doc_id, _url = _gdrive.create_brief_doc(camp, _brief_data)
                        st.session_state[f"brief_doc_id_{camp['id']}"] = _doc_id
                        st.session_state[f"brief_doc_url_{camp['id']}"] = _url
                    st.success(f"Brief saved to Google Drive — [open doc]({_url})")
                except Exception as _e:
                    st.error(f"Drive error: {_e}")

        _saved_url = st.session_state.get(f"brief_doc_url_{camp['id']}")
        if _saved_url:
            st.markdown(
                f'<div style="font-size:0.7rem;margin-top:4px;">'
                f'<a href="{_saved_url}" target="_blank">↗ Open in Google Drive</a></div>',
                unsafe_allow_html=True,
            )

    with export2:
        _bstatus_display = (
            st.session_state.get(f"brief_review_{camp['id']}", {}).get("status")
            or camp["brief_status"]
        )
        st.markdown(
            f'<div style="font-size:0.72rem;color:{COLORS["muted"]};padding:8px 0;">'
            f'Brief status: <strong>{_bstatus_display}</strong></div>',
            unsafe_allow_html=True,
        )


# ── Page nav ──────────────────────────────────────────────────────────────────
st.divider()
prev_col, _, next_col = st.columns([1, 5, 1])
with prev_col:
    st.page_link("pages/2_Decisioning.py", label="← Decisioning")
with next_col:
    st.page_link("pages/4_Design.py", label="Design →")
