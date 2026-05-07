import base64
import mimetypes
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from shared.styles import COLORS, inject_css, top_nav, phase_stepper, campaign_context_card
from shared.data import load_data, fmt_revenue


@st.cache_data
def _image_data_uri(path: str) -> str:
    """Encode an image as a base64 data URI so it can be embedded in markdown
    inside a fixed-size frame with aspect ratio preserved."""
    p = Path(path)
    if not p.exists():
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _image_frame(path: str, height_px: int = 340) -> str:
    """HTML frame: fixed height, white background, image centered with
    aspect ratio preserved (object-fit: contain)."""
    uri = _image_data_uri(path)
    if not uri:
        return (f'<div style="height:{height_px}px;background:{COLORS["offwhite"]};'
                f'border-radius:6px;display:flex;align-items:center;justify-content:center;'
                f'font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
                f'color:{COLORS["danger"]};">Missing image</div>')
    return (f'<div style="height:{height_px}px;background:{COLORS["offwhite"]};'
            f'border-radius:6px;display:flex;align-items:center;justify-content:center;'
            f'overflow:hidden;">'
            f'<img src="{uri}" style="max-height:100%;max-width:100%;'
            f'object-fit:contain;display:block;"/>'
            f'</div>')

inject_css()
top_nav("Design")

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

st.markdown("<h1>Design</h1>", unsafe_allow_html=True)

# ── Data connections ──────────────────────────────────────────────────────────
_DESIGN_CONNECTIONS = [
    {
        "name":   "Figma",
        "abbr":   "FG",
        "color":  "#a259ff",
        "status": "not connected",
        "what":   "Push pinned references and brief directly into a Figma mood board",
        "why":    "Gives the designer all context in one place — no copy-paste between tools",
    },
    {
        "name":   "Air",
        "abbr":   "AI",
        "color":  "#000000",
        "status": "not connected",
        "what":   "Pull prior campaign imagery from the creative library",
        "why":    "Replaces illustrative references with actual approved Glinta creative",
    },
    {
        "name":   "Klaviyo",
        "abbr":   "KL",
        "color":  "#1a1a1a",
        "status": "mock data",
        "what":   "Historical send performance used to rank reference creative",
        "why":    "Surfaces creative from campaigns that performed best for this category",
    },
    {
        "name":   "Brand Guidelines",
        "abbr":   "BG",
        "color":  "#888",
        "status": "tbd",
        "what":   "Do/don't photography rules, approved asset lists, tone standards",
        "why":    "Keeps brief constraints anchored to the latest Glinta brand standards",
    },
]
_STATUS_STYLE = {
    "mock data":     ("background:#f5f000;color:#000;",  "Mock data"),
    "connected":     ("background:#caf30b;color:#000;",  "Connected"),
    "not connected": ("background:#f2f2f2;color:#888;",  "Not connected"),
    "tbd":           ("background:#e8c5ff;color:#000;",  "TBD"),
}

st.markdown(
    '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
    'font-weight:800;letter-spacing:0.12em;text-transform:uppercase;'
    'color:#888;margin:4px 0 8px;">Data connections</div>',
    unsafe_allow_html=True,
)
_conn_html = '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px;">'
for _c in _DESIGN_CONNECTIONS:
    _st_css, _st_lbl = _STATUS_STYLE.get(_c["status"], ("background:#eee;color:#666;", _c["status"]))
    _conn_html += (
        f'<div style="border:1.5px solid #e4e4e4;border-radius:8px;padding:12px 14px;background:#fff;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        f'<span style="background:{_c["color"]};color:#fff;border-radius:5px;'
        f'width:26px;height:26px;display:inline-flex;align-items:center;justify-content:center;'
        f'font-family:\'Barlow Condensed\',sans-serif;font-size:10px;font-weight:900;'
        f'letter-spacing:0.04em;flex-shrink:0;">{_c["abbr"]}</span>'
        f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:13px;'
        f'font-weight:800;letter-spacing:0.04em;color:#000;">{_c["name"]}</span>'
        f'<span style="margin-left:auto;{_st_css}border-radius:4px;padding:1px 7px;'
        f'font-size:9px;font-weight:700;white-space:nowrap;font-family:Barlow,sans-serif;'
        f'letter-spacing:0.04em;text-transform:uppercase;">{_st_lbl}</span>'
        f'</div>'
        f'<div style="font-family:Barlow,sans-serif;font-size:11px;font-weight:600;'
        f'color:#000;margin-bottom:3px;line-height:1.4;">{_c["what"]}</div>'
        f'<div style="font-family:Barlow,sans-serif;font-size:10px;color:#888;line-height:1.4;">'
        f'{_c["why"]}</div>'
        f'</div>'
    )
_conn_html += '</div>'
st.markdown(_conn_html, unsafe_allow_html=True)

# ── Copilot note ──────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="background:{COLORS["offwhite"]};border:1px solid {COLORS["border"]};'
    f'border-radius:6px;padding:9px 14px;margin:0 0 20px;'
    f'display:flex;align-items:center;gap:10px;">'
    f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.6rem;'
    f'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;'
    f'background:{COLORS["muted"]};color:{COLORS["white"]};'
    f'padding:2px 8px;border-radius:3px;white-space:nowrap;">Copilot</span>'
    f'<span style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
    f'color:{COLORS["muted"]};line-height:1.4;">'
    f'Designed to provide references for images and layouts — '
    f'not a replacement for the design process itself. '
    f'Use these recommendations to brief your designer in Figma.</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# Real reference creative — prior Studs/Glinta assets used as the recommendation
# library. Each asset is paired with a category so it can be matched to the
# active campaign and ranked by that category's top historical send performance.
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "image assets"

REAL_ASSETS = [
    {
        "id":       "ra_flatbacks",
        "file":     "Screenshot 2026-05-05 at 8.59.00\u202fPM.png",
        "label":    "Standard Flatback Studs — detail",
        "concept":  "Product detail card · sizing explainer",
        "category": "Restock",
    },
    {
        "id":       "ra_clicker",
        "file":     "Screenshot 2026-05-05 at 8.58.36\u202fPM.png",
        "label":    "Clicker hoop — product feature",
        "concept":  "Single product hero with annotations",
        "category": "Restock",
    },
    {
        "id":       "ra_sensitive_stack",
        "file":     "Screenshot 2026-05-05 at 8.58.24\u202fPM.png",
        "label":    "Curated ear stack — sensitive ears",
        "concept":  "Lifestyle close-up with feature callouts",
        "category": "VIP/Loyalty",
    },
    {
        "id":       "ra_styles_shop",
        "file":     "Screenshot 2026-05-05 at 8.58.45\u202fPM.png",
        "label":    "Many styles — Shop now",
        "concept":  "Lifestyle stack with direct CTA",
        "category": "Promotional",
    },
    {
        "id":       "ra_needles",
        "file":     "Screenshot 2026-05-05 at 8.57.25\u202fPM.png",
        "label":    "Why we pierce with needles",
        "concept":  "Education · safety + brand trust",
        "category": "Editorial",
    },
    {
        "id":       "ra_press",
        "file":     "Screenshot 2026-05-05 at 8.59.45\u202fPM.png",
        "label":    "New Yorker — Goings On press feature",
        "concept":  "PR feature · NYC studios",
        "category": "Studio/Retail",
    },
]


# ── Load historical performance data ─────────────────────────────────────────
campaigns_df, *_ = load_data()
_cdf = campaigns_df.dropna(subset=["Send Date"]).copy()
_cdf["_date"] = _cdf["Send Date"].dt.date


# ── Build upcoming campaigns list (mirrors Generation) ───────────────────────
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
        "phase":       "design",
        "tags":        [],
        "segment":     ", ".join(auds) if auds else "—",
        "audience_est": int(recipients) if pd.notna(recipients) else 0,
        "subject_line_draft": str(row.get("Subject Line", "") or ""),
        "revenue_est": float(revenue) if pd.notna(revenue) else 0.0,
        "assigned_to": "—",
        "brief_status":  "Approved",
        "design_status": "In Progress",
        "qa_status":     "Not Started",
        "priority":      "Medium",
        "category_tag":  str(row.get("Category", "")).lower().replace(" ", "_"),
        "audiences":     auds,
        "product":       str(row.get("Primary Product", "") or ""),
        "studio":        str(row.get("Primary Studio", "") or ""),
        "goal":          "",
        "_source":       "scheduled",
    }


def _normalize_planned(p):
    auds = p.get("audiences", []) or []
    return {
        "id":           p["id"],
        "name":         p["name"],
        "category":     p.get("category", "Editorial"),
        "channel":      p.get("channel", "email"),
        "send_date":    p["send_date"],
        "phase":        "design",
        "tags":         [p.get("goal", "")],
        "segment":      ", ".join(auds) if auds else "—",
        "audience_est": 0,
        "subject_line_draft": p.get("subject", ""),
        "revenue_est":  0.0,
        "assigned_to":  "Unassigned",
        "brief_status":  "Approved",
        "design_status": "In Progress",
        "qa_status":     "Not Started",
        "priority":      "Medium",
        "category_tag":  p.get("category", "ed").lower().replace(" ", "_"),
        "audiences":     auds,
        "product":       p.get("product", ""),
        "studio":        p.get("studio", ""),
        "goal":          p.get("goal", ""),
        "_source":       "planned",
    }


_today = date.today()
_data_upcoming = _cdf[_cdf["_date"] >= _today].sort_values("Send Date")
all_campaigns = (
    [_normalize_data_row(r, i) for i, (_, r) in enumerate(_data_upcoming.iterrows())]
    + [_normalize_planned(p) for p in st.session_state.get("plan_added", [])]
)
all_campaigns.sort(key=lambda c: c["send_date"])


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
        f'Design pulls from Planning → Upcoming Campaigns. '
        f'Add a campaign there first, then come back to review visuals.</div>'
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

sel_col, _ = st.columns([3, 3])
with sel_col:
    chosen_label = st.selectbox(
        "Designing campaign",
        camp_labels,
        index=active_idx,
        key="design_camp",
        help="Pulls from Planning → Upcoming Campaigns: scheduled sends from your "
             "campaign data plus anything you added in Plan a Campaign.",
    )
camp = all_campaigns[camp_labels.index(chosen_label)]
st.session_state["active_campaign_id"] = camp["id"]

campaign_context_card(camp)


# ── Final brief recap (mirrors Generation → Design Brief auto-fill) ──────────
def _brief_subject(camp, df):
    draft = (camp.get("subject_line_draft") or "").strip()
    if draft:
        return draft
    pool = df[df["Subject Line"].notna()].copy()
    if camp.get("category"):
        cp = pool[pool["Category"] == camp["category"]]
        if len(cp) >= 1:
            pool = cp
    pool["_score"] = (
        pd.to_numeric(pool.get("Open Rate"),       errors="coerce").fillna(0)
        + 4  * pd.to_numeric(pool.get("Click Rate"),      errors="coerce").fillna(0)
        + 12 * pd.to_numeric(pool.get("Conversion Rate"), errors="coerce").fillna(0)
    )
    if pool.empty:
        return ""
    return str(pool.sort_values("_score", ascending=False).iloc[0]["Subject Line"])


def _brief_objective(camp):
    return (f"Drive revenue for {camp['category']} send. "
            f"Target {fmt_revenue(camp['revenue_est'])} revenue. "
            f"Segment: {camp['segment']}.")


def _brief_tone(camp):
    cat = (camp.get("category") or "").lower()
    nm  = (camp.get("name") or "").lower()
    if "holiday" in cat or "mother" in nm or "graduation" in nm:
        return ("Warm and celebratory. Curated stack with gold studs + opal hoops. "
                "Clean white background. Models with minimal makeup. No text on hero image.")
    if "vip" in cat or "loyal" in cat:
        return ("Exclusive, insider feel. Editorial styling, high-end product close-ups. "
                "Restrained typography. Darker palette acceptable.")
    if "restock" in cat:
        return ("Direct and product-forward. Emphasize the returning piece. "
                "Clean white background, single-focus hero shot.")
    if "promo" in cat or "sale" in cat or "flash" in cat:
        return ("Bold and urgent. Strong typography with offer code. "
                "High-contrast lifestyle shot. Black/yellow accents acceptable.")
    if "studio" in cat:
        return ("Local and inviting. Studio environment shots, candid moments, "
                "warm lighting.")
    if "editorial" in cat:
        return ("Editorial and curated. Lifestyle storytelling, layered styling, "
                "soft natural light.")
    return ("Brand-default — clean, confident, product-forward. "
            "White background, Barlow Condensed type.")


def _brief_assets(camp):
    lead = camp.get("product") or "lead product"
    return (f"Hero image (600×400px): stack shot featuring {lead}\n"
            "Product tiles (300×300px): 3–4 individual products\n"
            "CTA button: black, Barlow Condensed 700, 'Shop the edit'")


def _brief_image_refs(camp):
    yymm = camp["send_date"].strftime("%Y%m")
    slug = (camp["name"].lower()
            .replace(" — ", "-").replace(" ", "-").replace(":", "")[:40])
    return (f"• air.inc/glinta/{yymm}/{slug}\n"
            "• dropbox.com/glinta-creative/stack-reference-2025\n"
            "• Figma ref: figma.com/glinta/email-templates")


def _brief_notes(camp):
    notes = [
        "One round of consolidated revisions only before approval.",
        "Mobile render required — test at 375px width.",
    ]
    if camp.get("channel") == "email":
        notes.append("Dark mode check required for email.")
    notes.append("No stock photography.")
    return "\n".join(notes)


brief = {
    "objective": _brief_objective(camp),
    "subject":   _brief_subject(camp, _cdf) or "—",
    "tone":      _brief_tone(camp),
    "assets":    _brief_assets(camp),
    "refs":      _brief_image_refs(camp),
    "notes":     _brief_notes(camp),
}


def _brief_field(label, value):
    return (f'<div style="margin-bottom:11px;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.62rem;'
            f'letter-spacing:0.09em;text-transform:uppercase;color:{COLORS["muted"]};'
            f'font-weight:700;margin-bottom:3px;">{label}</div>'
            f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;'
            f'color:{COLORS["black"]};line-height:1.45;white-space:pre-wrap;">{value}</div>'
            f'</div>')


brief_status = camp.get("brief_status", "Approved")
badge_bg = (COLORS["good"] if brief_status == "Approved"
            else COLORS["warn"] if brief_status in ("In Review", "Draft")
            else COLORS["muted"])

with st.expander(f"Final brief — {camp['name']}  ·  Brief: {brief_status}", expanded=False):
    st.markdown(
        f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
        f'color:{COLORS["muted"]};margin:0 0 12px;">'
        f'Read-only summary of the approved brief from Generation. '
        f'Edit in Generation → Design Brief.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:28px;">'
        f'<div>'
        f'{_brief_field("Objective", brief["objective"])}'
        f'{_brief_field("Subject line (approved)", brief["subject"])}'
        f'{_brief_field("Tone &amp; style direction", brief["tone"])}'
        f'</div>'
        f'<div>'
        f'{_brief_field("Required assets", brief["assets"])}'
        f'{_brief_field("Image references", brief["refs"])}'
        f'{_brief_field("Notes for design", brief["notes"])}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# MOOD BOARD — recommendations grounded in past campaign performance
# ══════════════════════════════════════════════════════════════════════════════
# Each tile is real prior creative. Engagement comes from the top-performing
# historical campaign in that asset's category — so the recommendation is
# anchored in actual data even though the asset itself is reference imagery.

@st.cache_data
def _category_anchor(df):
    pool = df.dropna(subset=["Campaign Name", "Category"]).copy()
    pool["_open"]  = pd.to_numeric(pool.get("Open Rate"),       errors="coerce").fillna(0)
    pool["_click"] = pd.to_numeric(pool.get("Click Rate"),      errors="coerce").fillna(0)
    pool["_conv"]  = pd.to_numeric(pool.get("Conversion Rate"), errors="coerce").fillna(0)
    pool["_score"] = pool["_open"] + 4 * pool["_click"] + 12 * pool["_conv"]
    out = {}
    for cat, grp in pool.groupby("Category"):
        top = grp.sort_values("_score", ascending=False).iloc[0]
        out[cat] = {
            "campaign":  str(top["Campaign Name"]),
            "open":      float(top["_open"]),
            "click":     float(top["_click"]),
            "score":     float(top["_score"]),
            "send_date": top.get("Send Date"),
        }
    # Overall top send used as fallback when an asset's category has no history
    if not pool.empty:
        top = pool.sort_values("_score", ascending=False).iloc[0]
        out["__overall__"] = {
            "campaign":  str(top["Campaign Name"]),
            "open":      float(top["_open"]),
            "click":     float(top["_click"]),
            "score":     float(top["_score"]),
            "send_date": top.get("Send Date"),
            "category":  str(top.get("Category", "")),
        }
    return out


cat_anchor = _category_anchor(_cdf)
active_cat = camp.get("category") or ""


def _anchor_for(asset):
    return cat_anchor.get(asset["category"]) or cat_anchor.get("__overall__") or {}


def _asset_score(a):
    return _anchor_for(a).get("score", 0.0)


def _build_recommendations():
    in_cat  = sorted([a for a in REAL_ASSETS if a["category"] == active_cat],
                     key=_asset_score, reverse=True)
    out_cat = sorted([a for a in REAL_ASSETS if a["category"] != active_cat],
                     key=_asset_score, reverse=True)
    return in_cat + out_cat


recommendations = _build_recommendations()


# Selection state per campaign (preserve pin order)
sel_key = f"design_selected_{camp['id']}"
if sel_key not in st.session_state:
    st.session_state[sel_key] = []
selected_ids = st.session_state[sel_key]


def _asset_path(asset):
    return str(ASSETS_DIR / asset["file"])


def _engagement_caption(asset, active_cat):
    anchor = cat_anchor.get(asset["category"])
    fallback = anchor is None
    if fallback:
        anchor = cat_anchor.get("__overall__")
    if not anchor:
        return ""
    when = (pd.Timestamp(anchor["send_date"]).strftime("%b %Y")
            if pd.notna(anchor.get("send_date")) else "—")
    camp_clip = anchor["campaign"]
    if len(camp_clip) > 34:
        camp_clip = camp_clip[:32] + "…"
    label = (f"Top {asset['category']} send" if not fallback
             else "Top historical send (no in-category history)")
    return (f'{label}: "{camp_clip}"<br>'
            f'{when} · {anchor["open"]:.0%} open · {anchor["click"]:.1%} click')


def _category_chip(asset, active_cat):
    same = (asset["category"] == active_cat)
    bg   = COLORS["black"] if same else COLORS["offwhite"]
    fg   = "#ffffff" if same else COLORS["muted"]
    suffix = " · MATCH" if same else ""
    return (f'<span style="background:{bg};color:{fg};'
            f'font-family:\'Barlow Condensed\',sans-serif;font-size:0.6rem;'
            f'font-weight:700;letter-spacing:0.07em;padding:2px 7px;'
            f'border-radius:3px;text-transform:uppercase;">'
            f'{asset["category"]}{suffix}</span>')


tab_board, tab_review = st.tabs(["Mood board · Recommendations", "Selected board · Review"])


# ── Tab: Recommendations ─────────────────────────────────────────────────────
with tab_board:
    st.markdown("<h2>Recommended references</h2>", unsafe_allow_html=True)
    st.markdown(
        f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
        f'color:{COLORS["muted"]};margin:-0.4rem 0 0.8rem;">'
        f'Real prior creative ranked for this <strong>{active_cat or "all"}</strong> campaign. '
        f'Each reference is anchored to its category\'s top-performing historical send '
        f'(open + click + conversion). In-category matches surface first.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="background:{COLORS["yellow"]};border:1px solid {COLORS["black"]};'
        f'border-radius:6px;padding:7px 14px;margin:0 0 14px;'
        f'display:flex;align-items:center;gap:10px;">'
        f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.6rem;'
        f'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;'
        f'background:{COLORS["black"]};color:{COLORS["white"]};'
        f'padding:2px 7px;border-radius:3px;white-space:nowrap;">Illustrative data</span>'
        f'<span style="font-family:\'Barlow\',sans-serif;font-size:0.75rem;'
        f'color:{COLORS["black"]};">'
        f'Reference imagery and engagement numbers are illustrative — '
        f'final version will pull from prior Glinta campaign assets.</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not recommendations:
        st.info("No prior reference creative available.")
    else:
        cols = st.columns(3)
        for i, asset in enumerate(recommendations):
            with cols[i % 3]:
                is_sel = asset["id"] in selected_ids
                with st.container(border=True):
                    st.markdown(_image_frame(_asset_path(asset), height_px=340),
                                unsafe_allow_html=True)
                    st.markdown(
                        f'<div style="margin-top:8px;">{_category_chip(asset, active_cat)}</div>'
                        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;'
                        f'font-weight:600;color:{COLORS["black"]};line-height:1.25;'
                        f'margin-top:6px;">{asset["label"]}</div>'
                        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.7rem;'
                        f'color:{COLORS["muted"]};line-height:1.4;margin-top:3px;">'
                        f'{asset["concept"]}</div>'
                        f'<div style="border-top:1px solid {COLORS["border"]};'
                        f'margin-top:8px;padding-top:6px;'
                        f'font-family:\'Barlow\',sans-serif;font-size:0.66rem;'
                        f'color:{COLORS["muted"]};line-height:1.4;">'
                        f'{_engagement_caption(asset, active_cat)}</div>',
                        unsafe_allow_html=True,
                    )
                    btn_label = "✓ Pinned" if is_sel else "Pin to mood board"
                    if st.button(btn_label, key=f"pin_{camp['id']}_{asset['id']}",
                                 type="primary" if is_sel else "secondary",
                                 use_container_width=True):
                        if is_sel:
                            st.session_state[sel_key] = [
                                x for x in selected_ids if x != asset["id"]
                            ]
                        else:
                            st.session_state[sel_key] = selected_ids + [asset["id"]]
                        st.rerun()


# ── Tab: Selected board · Review & comments ──────────────────────────────────
with tab_review:
    st.markdown("<h2>Selected mood board</h2>", unsafe_allow_html=True)

    by_id = {a["id"]: a for a in REAL_ASSETS}
    selected = [by_id[aid] for aid in selected_ids if aid in by_id]

    if not selected:
        st.markdown(
            f'<div style="border:2px dashed {COLORS["border"]};border-radius:10px;'
            f'padding:32px 24px;text-align:center;background:{COLORS["offwhite"]};'
            f'margin-top:8px;">'
            f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;'
            f'color:{COLORS["muted"]};">'
            f'No references pinned yet. Pin tiles from the Recommendations tab '
            f'to build a mood board.</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
            f'color:{COLORS["muted"]};margin:-0.4rem 0 0.8rem;">'
            f'{len(selected)} reference(s) pinned. Add comments to guide the designer.</p>',
            unsafe_allow_html=True,
        )

        cols = st.columns(3)
        for i, asset in enumerate(selected):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(_image_frame(_asset_path(asset), height_px=300),
                                unsafe_allow_html=True)
                    st.markdown(
                        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;'
                        f'font-weight:600;color:{COLORS["black"]};line-height:1.25;'
                        f'margin-top:8px;">{asset["label"]}</div>'
                        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.7rem;'
                        f'color:{COLORS["muted"]};line-height:1.4;margin-top:3px;">'
                        f'{asset["concept"]}</div>',
                        unsafe_allow_html=True,
                    )

                    cmt_key = f"cmt_{camp['id']}_{asset['id']}"
                    if cmt_key not in st.session_state:
                        st.session_state[cmt_key] = []
                    cmts = st.session_state[cmt_key]

                    with st.expander(f"Comments ({len(cmts)})", expanded=False):
                        for c in cmts:
                            st.markdown(
                                f'<div style="background:{COLORS["offwhite"]};'
                                f'border-radius:6px;padding:6px 10px;margin-bottom:4px;">'
                                f'<div style="font-family:\'Barlow Condensed\',sans-serif;'
                                f'font-size:0.6rem;font-weight:700;letter-spacing:0.06em;'
                                f'text-transform:uppercase;color:{COLORS["muted"]};">'
                                f'{c["author"]}</div>'
                                f'<div style="font-family:\'Barlow\',sans-serif;'
                                f'font-size:0.78rem;line-height:1.35;">{c["text"]}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                        new_cmt = st.text_input(
                            "Add comment",
                            key=f"new_{camp['id']}_{asset['id']}",
                            placeholder="e.g. Try the muted opal stack instead",
                            label_visibility="collapsed",
                        )
                        if st.button("Post", key=f"post_{camp['id']}_{asset['id']}",
                                     use_container_width=True):
                            if new_cmt.strip():
                                cmts.append({
                                    "author": camp.get("assigned_to") or "You",
                                    "text":   new_cmt.strip(),
                                })
                                st.rerun()

                    if st.button("Unpin", key=f"unpin_{camp['id']}_{asset['id']}",
                                 use_container_width=True):
                        st.session_state[sel_key] = [
                            x for x in selected_ids if x != asset["id"]
                        ]
                        st.rerun()

        st.divider()
        ap_col, fg_col, sh_col, _ = st.columns([1.3, 1.3, 1.3, 3])
        with ap_col:
            if st.button("Approve mood board", type="primary",
                         use_container_width=True):
                st.success("Mood board approved — designer notified (mock)")
        with fg_col:
            if st.button("Export to Figma", type="secondary",
                         use_container_width=True):
                slug = (camp["name"].lower()
                        .replace(" — ", "-").replace(" ", "-").replace(":", "")[:40])
                st.info(
                    f"Exported {len(selected)} reference(s) to Figma: "
                    f"figma.com/glinta/{slug}-moodboard (mock)"
                )
        with sh_col:
            if st.button("Share with team", type="secondary",
                         use_container_width=True):
                owner = camp.get("assigned_to") or "team"
                st.info(f"Shared with {owner} via Slack (mock)")


# ── Page nav ──────────────────────────────────────────────────────────────────
st.divider()
prev_col, _, next_col = st.columns([1, 5, 1])
with prev_col:
    st.page_link("pages/3_Generation.py", label="← Generation")
with next_col:
    st.page_link("pages/5_Execution.py", label="Execution →")
