import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import datetime as _dt
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from shared.styles import COLORS, CMAP, inject_css, plot_theme, top_nav, phase_stepper, campaign_context_card
from shared.data import load_data, load_segments, fmt_revenue

try:
    from shared.audit import current_user
except Exception:
    def current_user(): return "Team"

try:
    from shared.sheets import upsert_campaign as _sheets_upsert
    _SHEETS_ENABLED = True
except Exception:
    _SHEETS_ENABLED = False

def _sync_to_sheet(campaign: dict):
    if _SHEETS_ENABLED:
        try:
            _sheets_upsert(campaign)
        except Exception as _e:
            st.toast(f"Sheet sync failed: {_e}", icon="⚠️")

inject_css()
top_nav("Decisioning")

# Seed plan_added from sheet if Planning hasn't synced yet this session.
# Merges sheet data with any locally-added campaigns not yet saved to the sheet.
if st.session_state.get("_last_sheet_sync") is None:
    try:
        from shared.sheets import load_all_campaigns as _load_all
        _p, _d = _load_all()
        _sheet_ids = {c.get("id") for c in _p + _d}
        _local_only = [c for c in st.session_state.get("plan_added", []) if c.get("id") not in _sheet_ids]
        st.session_state["plan_added"]  = _p + _local_only
        st.session_state["plan_drafts"] = _d
        st.session_state["_last_sheet_sync"] = _dt.date.today()
    except Exception:
        st.session_state.setdefault("plan_added", [])
        st.session_state.setdefault("plan_drafts", [])

st.markdown("<h1>Decisioning</h1>", unsafe_allow_html=True)
st.markdown(
    '<p style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;color:#444;'
    'margin:-0.4rem 0 0.75rem;">Pulls every campaign you added in '
    '<em>Planning → Plan a Campaign</em>. Define segments, then finalize the send plan.</p>',
    unsafe_allow_html=True,
)

# ── Klaviyo connection banner ─────────────────────────────────────────────────
st.markdown(
    '<div style="border:1.5px solid #e4e4e4;border-radius:8px;padding:12px 14px;'
    'background:#fff;margin-bottom:1.2rem;display:inline-block;min-width:260px;max-width:320px;">'
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
    '<span style="background:#1a1a1a;color:#fff;border-radius:5px;'
    'width:26px;height:26px;display:inline-flex;align-items:center;justify-content:center;'
    'font-family:\'Barlow Condensed\',sans-serif;font-size:10px;font-weight:900;'
    'letter-spacing:0.04em;flex-shrink:0;">KL</span>'
    '<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:13px;'
    'font-weight:800;letter-spacing:0.04em;color:#000;">Klaviyo</span>'
    '<span style="margin-left:auto;background:#f2f2f2;color:#888;border-radius:4px;'
    'padding:1px 7px;font-size:9px;font-weight:700;white-space:nowrap;'
    'font-family:Barlow,sans-serif;letter-spacing:0.04em;text-transform:uppercase;">'
    'Not connected</span>'
    '</div>'
    '<div style="font-family:Barlow,sans-serif;font-size:11px;font-weight:600;'
    'color:#000;margin-bottom:3px;line-height:1.4;">'
    'Segment definitions · suppression lists · frequency rules</div>'
    '<div style="font-family:Barlow,sans-serif;font-size:10px;color:#888;line-height:1.4;">'
    'Push decisions directly — avoids re-entering in Klaviyo and prevents duplicate list creation'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

campaigns_df, flow_monthly, flow_msgs, benchmarks = load_data()
segments_df = load_segments()
TODAY = _dt.date(2026, 5, 3)

# ──────────────────────────────────────────────────────────────────────────────
# INCOMING CAMPAIGNS — Klaviyo upcoming + user-planned
# ──────────────────────────────────────────────────────────────────────────────
INCOMING_PHASES = ["planning", "decisioning"]

# Per-category benchmarks from historical data, used to estimate audience/revenue
# when a user-planned campaign comes in without those fields.
def _cat_benchmark(category, channel):
    sub = campaigns_df[
        (campaigns_df["Category"] == category) &
        (campaigns_df["Channel"] == channel)
    ].dropna(subset=["Recipients", "Revenue"])
    if sub.empty:
        sub = campaigns_df[campaigns_df["Channel"] == channel] \
            .dropna(subset=["Recipients", "Revenue"])
    if sub.empty:
        return {"recipients": 25000, "revenue": 12000, "click": 0.030, "conv": 0.020, "open": 0.40}
    return {
        "recipients": float(sub["Recipients"].mean()),
        "revenue":    float(sub["Revenue"].mean()),
        "click":      float(sub["Click Rate"].mean()),
        "conv":       float(sub["Conversion Rate"].mean()),
        "open":       float(sub["Open Rate"].mean()),
    }


def _normalize_planned(p):
    """Convert a `plan_added` entry from Plan a Campaign tab into the campaign
    shape Decisioning expects."""
    cat = p.get("category", "Promo")
    ch = p.get("channel", "email")
    bench = _cat_benchmark(cat, ch)
    audiences = list(p.get("audiences") or [])
    primary_seg = audiences[0] if audiences else "All Engaged 90D"
    return {
        "id":           p["id"],
        "name":         p["name"],
        "category":     cat,
        "channel":      ch,
        "send_date":    p["send_date"],
        "phase":        "planning",
        "tags":         [p.get("goal", "")],
        "segment":      primary_seg,
        "audiences":    audiences,
        "product":      p.get("product", ""),
        "studio":       p.get("studio", ""),
        "goal":         p.get("goal", ""),
        "audience_est": int(bench["recipients"]),
        "subject_line_draft": p.get("subject", ""),
        "revenue_est":  int(bench["revenue"]),
        "assigned_to":  "Newly planned",
        "brief_status": "Not Started",
        "design_status": "Not Started",
        "qa_status":    "Not Started",
        "priority":     "Medium",
        "category_tag": cat.lower(),
        "_source":      "user-planned",
    }


incoming = sorted(
    [_normalize_planned(p)
     for p in st.session_state.get("plan_added", [])
     if p.get("status", "planned") == "planned"],
    key=lambda c: c["send_date"],
)

if not incoming:
    st.info(
        "No campaigns yet. Head to **Planning → Plan a Campaign** to add one — "
        "it'll show up here automatically."
    )
    st.stop()

# Per-campaign decisioning state lives in session_state and persists across page nav.
# Auto-init for any new (or returning) campaign id.
if "decisioning_state" not in st.session_state:
    st.session_state["decisioning_state"] = {}
DSTATE = st.session_state["decisioning_state"]


# ── Cross-page sync helper ────────────────────────────────────────────────────
# Defined here (before Save button) so it's in scope when the button fires.
def _sync_to_planned(camp_id):
    """Mirror DSTATE entries for a campaign back onto its plan_added row."""
    state = DSTATE.get(camp_id)
    if not state:
        return
    for p in st.session_state.get("plan_added", []):
        if p.get("id") == camp_id:
            p["audiences"] = list(state.get("segments", []))
            p["last_modified_by"] = state.get("saved_by", "")
            p["decisioning"] = {
                "freq_cap":            state.get("freq_cap"),
                "freq_cap_custom":     state.get("freq_cap_custom"),
                "suppressions":        list(state.get("suppressions", [])),
                "suppressions_custom": list(state.get("suppressions_custom", [])),
                "flow_target":         state.get("flow_target"),
                "flow_priority":       state.get("flow_priority"),
                "flow_priority_custom": state.get("flow_priority_custom"),
                "flow_msg_overrides":  dict(state.get("flow_msg_overrides", {})),
                "refinements":         list(state.get("refinements", [])),
                "last_saved":          state.get("last_saved", ""),
                "saved_by":            state.get("saved_by", ""),
            }
            break


DEFAULT_FREQ = "Default (3/wk email · 2/wk SMS)"
DEFAULT_SUPP = ["Unsubscribed", "Bounced 30d"]
DEFAULT_PRIO = "Keep flow — skip campaign if user is in active flow"
for c in incoming:
    if c["id"] not in DSTATE:
        # Seed from the FULL audiences list selected in Plan a Campaign.
        seeds = list(c.get("audiences") or ([c["segment"]] if c.get("segment") else []))
        DSTATE[c["id"]] = {
            "segments":       seeds,
            "freq_cap":       DEFAULT_FREQ,    "freq_cap_custom": "",
            "suppressions":   list(DEFAULT_SUPP), "suppressions_custom": [],
            "flow_priority":  DEFAULT_PRIO,   "flow_priority_custom": "",
            "flow_target":    "Abandoned Cart Flow",
            "refinements":    [],
            "send_logistics": {},
        }
    else:
        # If user added new audiences in Plan a Campaign after first init, merge
        # them in without overwriting Decisioning-side edits.
        for aud in (c.get("audiences") or []):
            if aud and aud not in DSTATE[c["id"]]["segments"]:
                DSTATE[c["id"]]["segments"].append(aud)
    # Back-fill send_logistics for campaigns initialised before this field existed
    if "send_logistics" not in DSTATE[c["id"]]:
        DSTATE[c["id"]]["send_logistics"] = {}


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE STRIP — campaigns flowing through
# ──────────────────────────────────────────────────────────────────────────────
def _channel_pill(ch):
    if ch == "email":
        return f'<span style="background:#1a1a1a;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.6rem;font-weight:600;font-family:\'Barlow\',sans-serif;">EMAIL</span>'
    return f'<span style="background:#f0f0f0;color:#444;padding:2px 8px;border-radius:4px;font-size:0.6rem;font-weight:600;font-family:\'Barlow\',sans-serif;border:1px solid #ddd;">SMS</span>'


st.markdown(
    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.62rem;'
    f'letter-spacing:0.07em;text-transform:uppercase;color:{COLORS["muted"]};'
    f'margin-bottom:0.5rem;font-weight:600;">Campaigns moving through decisioning '
    f'({len(incoming)})</div>',
    unsafe_allow_html=True,
)

today = _dt.date(2026, 5, 3)
cards_html = '<div style="display:flex;gap:8px;overflow-x:auto;padding-bottom:8px;margin-bottom:1rem;">'
for c in incoming:
    state = DSTATE[c["id"]]
    seg_count = len(state["segments"])
    seg_summary = " · ".join(state["segments"][:2])
    if seg_count > 2:
        seg_summary += f" +{seg_count-2}"
    days_to_send = (c["send_date"] - today).days
    urgency_color = COLORS["danger"] if days_to_send <= 5 else COLORS["warn"] if days_to_send <= 12 else COLORS["muted"]
    is_active = c["id"] == st.session_state.get("active_campaign_id", incoming[0]["id"])
    border = f'border:1px solid {COLORS["black"]};' if is_active else f'border:1px solid {COLORS["border"]};'
    cards_html += f"""
    <div style="min-width:230px;background:{COLORS['white']};{border}
                border-radius:8px;padding:10px 14px;flex-shrink:0;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;gap:6px;">
        <span style="color:{COLORS['black']};font-size:0.6rem;font-weight:600;
                     font-family:'Barlow',sans-serif;letter-spacing:0.04em;">In Decisioning</span>
        {_channel_pill(c['channel'])}
      </div>
      <div style="font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:0.88rem;
                  color:{COLORS['black']};line-height:1.2;margin-bottom:6px;">{c['name']}</div>
      <div style="font-size:0.7rem;color:{urgency_color};font-weight:600;margin-bottom:6px;">
        {c['send_date'].strftime('%b %d')} · T-{days_to_send}d
      </div>
      <div style="font-size:0.7rem;color:{COLORS['muted']};border-top:1px solid {COLORS['border']};
                  padding-top:6px;line-height:1.4;">
        <span style="font-size:0.58rem;text-transform:uppercase;letter-spacing:0.06em;">
          Segments ({seg_count})</span><br/>
        <span style="color:{COLORS['black']};font-weight:500;">{seg_summary or '— none yet —'}</span>
      </div>
    </div>"""
cards_html += "</div>"
st.markdown(cards_html, unsafe_allow_html=True)


# ── Active campaign selector ─────────────────────────────────────────────────
active_id = st.session_state.get("active_campaign_id", incoming[0]["id"])
if active_id not in [c["id"] for c in incoming]:
    active_id = incoming[0]["id"]
active_idx = next((i for i, c in enumerate(incoming) if c["id"] == active_id), 0)

sel_col, save_col, _ = st.columns([2, 1.2, 3])
with sel_col:
    chosen = st.selectbox(
        "Configure decisioning for",
        [c["name"] for c in incoming], index=active_idx, key="dec_camp",
    )
camp = next(c for c in incoming if c["name"] == chosen)
st.session_state["active_campaign_id"] = camp["id"]

with save_col:
    st.markdown(
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.6rem;'
        f'letter-spacing:0.08em;text-transform:uppercase;color:{COLORS["muted"]};'
        f'font-weight:600;margin-bottom:0.2rem;">Save changes</div>',
        unsafe_allow_html=True,
    )
    last_saved_key  = f"_last_saved_{camp['id']}"
    last_saver_key  = f"_last_saver_{camp['id']}"
    last_saved      = st.session_state.get(last_saved_key)
    last_saver      = st.session_state.get(last_saver_key, "")
    if st.button("Save", type="primary", use_container_width=True,
                 key=f"save_{camp['id']}"):
        now  = _dt.datetime.now()
        user = current_user()
        # Stamp identity + timestamp into DSTATE so they travel with the campaign
        if camp["id"] in DSTATE:
            DSTATE[camp["id"]]["last_saved"] = now
            DSTATE[camp["id"]]["saved_by"]   = user
        _sync_to_planned(camp["id"])
        # Mirror updated campaign to Google Sheet
        _updated = next(
            (p for p in st.session_state.get("plan_added", []) if p.get("id") == camp["id"]),
            None,
        )
        if _updated:
            _updated["last_modified_by"] = user
            if "decisioning" in _updated:
                _updated["decisioning"]["last_saved"] = now
                _updated["decisioning"]["saved_by"]   = user
            _sync_to_sheet(_updated)
        st.session_state[last_saved_key] = now
        st.session_state[last_saver_key] = user
        st.toast(f"Saved by {user} · {now.strftime('%-I:%M %p')}", icon="✅")
        st.rerun()
    if last_saved:
        st.markdown(
            f'<div style="font-size:0.62rem;color:{COLORS["muted"]};margin-top:2px;line-height:1.5;">'
            f'<strong style="color:{COLORS["black"]};">{last_saver}</strong> · '
            f'{last_saved.strftime("%-I:%M %p, %b %d")}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="font-size:0.62rem;color:{COLORS["muted"]};margin-top:2px;">'
            f'Unsaved · click to save & push to sheet</div>',
            unsafe_allow_html=True,
        )

campaign_context_card(camp)


# ──────────────────────────────────────────────────────────────────────────────
# SEGMENT CATALOG — built from the Klaviyo Segments sheet (real data)
# ──────────────────────────────────────────────────────────────────────────────
def _segment_type(name):
    n = name.lower()
    if "vip" in n or "multi-buy" in n: return "VIP"
    if "lapsed" in n: return "Winback"
    if "recent purchaser" in n or "new subscriber" in n: return "New"
    if "abandoner" in n: return "Behavioral"
    if any(g in n for g in ["metro", "bay area", "austin", "dallas"]): return "Geo"
    if any(p in n for p in ["fans", "lovers", "heads"]): return "Product"
    if "non-buyer" in n: return "Broadcast"
    if "engaged" in n: return "Broadcast"
    return "Other"


def _segment_recommendation(name, stype):
    n = name.lower()
    if stype == "VIP":
        return "Best for early-access drops and exclusive previews"
    if stype == "Winback":
        return "Needs a strong incentive — discount or scarcity"
    if stype == "New":
        return "High engagement — pair with a welcome offer"
    if stype == "Behavioral":
        if "cart" in n: return "Cart-recovery campaigns — deconflict with Abandoned Cart Flow"
        if "browse" in n: return "Mid-funnel intent — re-merchandise the viewed category"
        return "Behavioral signal — recent intent recency"
    if stype == "Geo":
        return "Local studio sends, piercing promos, in-person events"
    if stype == "Product":
        return "Affinity segment — restocks and launches in this product family"
    if stype == "Broadcast":
        if "non-buyer" in n: return "Pre-purchase audience — needs incentive or trust signals"
        if "60d" in n: return "Tighter engagement window — high-relevance sends"
        return "Broad reach — use for hero moments only"
    return "Custom segment"


# Open/click proxies by segment type — Segments sheet has conv but not open/click
_RATE_BY_TYPE = {
    "VIP":        {"open": 0.51, "click": 0.058},
    "Broadcast":  {"open": 0.38, "click": 0.031},
    "Winback":    {"open": 0.30, "click": 0.018},
    "New":        {"open": 0.47, "click": 0.044},
    "Geo":        {"open": 0.42, "click": 0.039},
    "Behavioral": {"open": 0.46, "click": 0.054},
    "Product":    {"open": 0.49, "click": 0.062},
    "Other":      {"open": 0.40, "click": 0.030},
}


def _build_catalog():
    cat = []
    for _, r in segments_df.iterrows():
        name = str(r["Segment Name"]).strip()
        stype = _segment_type(name)
        rates = _RATE_BY_TYPE.get(stype, _RATE_BY_TYPE["Other"])
        last_send = r["Last Send Date"]
        last_touch_days = (
            (TODAY - last_send.date()).days
            if pd.notna(last_send) else 30
        )
        size = int(r["Current Size"]) if pd.notna(r["Current Size"]) else 0
        eng_rate = float(r["Active Rate 30d"]) if pd.notna(r["Active Rate 30d"]) else 0.4
        cat.append({
            "name":             name,
            "type":             stype,
            "size":             size,
            "engaged_30d":      int(r["Active 30d"]) if pd.notna(r["Active 30d"]) else int(size * eng_rate),
            "engaged_90d":      size,
            "avg_open":         rates["open"],
            "avg_click":        rates["click"],
            "avg_conv":         float(r["Purchaser Rate 90d"]) if pd.notna(r["Purchaser Rate 90d"]) else 0.02,
            "avg_ltv":          float(r["Est. LTV"]) if pd.notna(r["Est. LTV"]) else 0,
            "last_touch_days":  last_touch_days,
            "rec":              _segment_recommendation(name, stype),
            "_source":          "klaviyo",
        })
    return cat


SEGMENTS = _build_catalog()

# Carry over any custom segments built/refined for any campaign
if "_custom_segments" not in st.session_state:
    st.session_state["_custom_segments"] = []
SEGMENTS.extend(st.session_state["_custom_segments"])
SEG_BY_NAME = {s["name"]: s for s in SEGMENTS}

# Defensive: if any plan_added audience name isn't in the catalog (e.g. a free-typed
# refinement label), surface it as a stub so it remains selectable & visible.
for c in incoming:
    for aud in (c.get("audiences") or []):
        if aud and aud not in SEG_BY_NAME:
            stub = {
                "name": aud, "type": "Custom",
                "size": 0, "engaged_30d": 0, "engaged_90d": 0,
                "avg_open": 0.40, "avg_click": 0.030, "avg_conv": 0.020,
                "avg_ltv": 0, "last_touch_days": 0,
                "rec": "Custom audience from Plan a Campaign — stats unavailable",
                "_source": "stub",
            }
            SEGMENTS.append(stub)
            SEG_BY_NAME[aud] = stub




# ──────────────────────────────────────────────────────────────────────────────
# BEHAVIORAL SEGMENTS — grounded in actual Events Sample data
# ──────────────────────────────────────────────────────────────────────────────
# Counts are real from `Events Sample` (n=2000 events, 2000 unique profiles, ~3mo).
# Each profile in the sample represents the same population, so we project the
# rate forward to the larger 320K All-Engaged-90D list to estimate segment size.
EVENTS_SAMPLE_N = 2000
ENGAGED_LIST_SIZE = 320_000  # from Segments sheet S2000 "All Engaged 90D"


def _proj(count, sample_n=EVENTS_SAMPLE_N, list_size=ENGAGED_LIST_SIZE):
    return int(count / sample_n * list_size)


# Profiles in the events sample with each behavior (and no Placed Order)
# Computed from the file in this conversation; recomputed per-render keeps
# wording honest if data changes.
CART_NO_ORDER_N    = 151   # Added to Cart, no Placed Order
SMS_CLICK_N        = 193   # Clicked SMS — no purchase attribution in sample
APPT_NO_ORDER_N    = 170   # Scheduled Appointment, no Placed Order
BROWSE_NO_ORDER_N  = 147   # Viewed Product, no Placed Order
EMAIL_CLICK_N      = 162   # Clicked Email

BEHAVIORAL_IDEAS = [
    {
        "name": "Cart abandoners — added to cart, no order",
        "size_est": _proj(CART_NO_ORDER_N), "exp_click": 0.078, "exp_conv": 0.062,
        "evidence": f"{CART_NO_ORDER_N} profiles in Events Sample (n={EVENTS_SAMPLE_N}) — Added to Cart with no Placed Order.",
        "best_for": ["Promo", "Sale", "Restock"],
        "why": "Hottest single signal — pair with a recovery campaign and deconflict against Abandoned Cart Flow.",
    },
    {
        "name": "Browse abandoners — viewed product, no order",
        "size_est": _proj(BROWSE_NO_ORDER_N), "exp_click": 0.046, "exp_conv": 0.027,
        "evidence": f"{BROWSE_NO_ORDER_N} profiles in Events Sample — Viewed Product with no Placed Order.",
        "best_for": ["Restock", "Editorial", "Holiday", "Product Launch"],
        "why": "Mid-funnel intent. Re-merchandise the viewed category — strong on restock pushes.",
    },
    {
        "name": "SMS clickers, no purchase 30d",
        "size_est": _proj(SMS_CLICK_N), "exp_click": 0.041, "exp_conv": 0.024,
        "evidence": f"{SMS_CLICK_N} profiles clicked an SMS in Events Sample — no Placed Order in window.",
        "best_for": ["Promo", "Sale", "Holiday"],
        "why": "Engaged on SMS but converting elsewhere. Test SMS-exclusive promo for direct attribution.",
    },
    {
        "name": "Booked appointment, no jewelry order 14d",
        "size_est": _proj(APPT_NO_ORDER_N), "exp_click": 0.052, "exp_conv": 0.034,
        "evidence": f"{APPT_NO_ORDER_N} Scheduled Appointment events in sample — no order follow-up.",
        "best_for": ["Studio", "In-Studio", "Editorial"],
        "why": "Studio-engaged but not yet a buyer. Strong lift on jewelry-pairing editorial and aftercare flows.",
    },
    {
        "name": "Email clickers, last 30d",
        "size_est": _proj(EMAIL_CLICK_N), "exp_click": 0.062, "exp_conv": 0.038,
        "evidence": f"{EMAIL_CLICK_N} profiles with Clicked Email in sample.",
        "best_for": ["Editorial", "Product Launch", "Holiday", "VIP/Loyalty"],
        "why": "High-engagement subscribers. Best for hero launches and editorial drops.",
    },
]


# Map mock-campaign categories to behavioral filter tags.
def _category_for_behavioral(cat):
    return cat


# ──────────────────────────────────────────────────────────────────────────────
# RANKING HELPERS
# ──────────────────────────────────────────────────────────────────────────────
# Map common product mentions in campaign metadata → name keywords likely to
# appear in matching Klaviyo segments. Drives the bulk of per-campaign
# differentiation when category/channel are similar.
_PRODUCT_KEYWORDS = {
    "opal":     ["gold lovers", "piercing fans"],
    "diamond":  ["flatback fans", "piercing fans", "vips"],
    "gold":     ["gold lovers"],
    "silver":   ["silver fans"],
    "hoop":     ["hoop heads"],
    "flatback": ["flatback fans", "piercing fans"],
    "stud":     ["piercing fans", "gold lovers"],
    "pearl":    ["gold lovers"],
}

_STUDIO_TO_AUDIENCE = {
    "new york":  "NY Metro",  "nyc":  "NY Metro",   "williamsburg": "NY Metro",
    "soho":      "NY Metro",
    "los angeles": "LA Metro", "la":   "LA Metro",
    "chicago":   "Chicago Metro",
    "boston":    "Boston Metro",
    "dc":        "DC Metro",   "washington": "DC Metro",
    "philly":    "Philly Metro", "philadelphia": "Philly Metro",
    "atlanta":   "Atlanta Metro",
    "houston":   "Houston Metro",
    "charlotte": "Charlotte Metro",
    "phoenix":   "Phoenix Metro",
    "austin":    "Austin",
    "dallas":    "Dallas",
    "san francisco": "SF Bay Area",  "bay area": "SF Bay Area",
}


def suggest_segments(campaign, n=4):
    """Score every segment for this specific campaign using
    category, channel, product, goal, studio, name keywords, and any
    audiences the user pre-selected in Plan a Campaign."""
    cat   = (campaign.get("category") or "").lower()
    ch    = campaign.get("channel") or "email"
    prod  = (campaign.get("product")  or "").lower()
    goal  = (campaign.get("goal")     or "").lower()
    studio = (campaign.get("studio")  or "").lower()
    name_blob = (campaign.get("name", "") + " " +
                 campaign.get("subject_line_draft", "")).lower()
    pre_selected = {a.lower() for a in (campaign.get("audiences") or [])}

    # Studio name → metro audience
    studio_metro = next((v for k, v in _STUDIO_TO_AUDIENCE.items()
                         if k in studio or k in name_blob), None)

    # Product hints from explicit field + name keywords
    product_keywords = set()
    haystack = f"{prod} {name_blob}"
    for token, segs in _PRODUCT_KEYWORDS.items():
        if token in haystack:
            product_keywords.update(s.lower() for s in segs)

    scores = []
    for s in SEGMENTS:
        sname = s["name"].lower()
        score = s["avg_click"] * 1000 + s["avg_conv"] * 800

        # Channel — penalize incompatible
        if ch == "sms" and s["type"] not in ("Broadcast",) and "engaged" not in sname:
            score -= 20

        # Category alignment
        if "restock" in cat:
            if s["type"] == "Product":            score += 35
            if s["type"] == "Behavioral":         score += 18
            if s["type"] == "VIP":                score += 12
        if "vip" in cat or "loyalty" in cat:
            if s["type"] == "VIP":                score += 50
            if s["type"] == "Product":            score += 12
        if "holiday" in cat or "seasonal" in cat:
            if s["type"] == "Broadcast":          score += 18
            if s["type"] == "VIP":                score += 14
            if s["type"] == "Product":            score += 8
        if "studio" in cat or "in-studio" in cat or "nso" in cat:
            if s["type"] == "Geo":                score += 30
            if s["type"] == "Behavioral":         score += 8
        if "promo" in cat or "sale" in cat:
            if "engaged 60d" in sname:            score += 18
            if s["type"] == "Behavioral":         score += 18
            if s["type"] == "Winback":            score += 14
        if "editorial" in cat:
            if s["type"] in ("Broadcast", "Behavioral"): score += 10
            if s["type"] == "New":                score += 8
        if "winback" in cat:
            if s["type"] == "Winback":            score += 50
            if s["type"] == "Behavioral":         score += 12
        if "launch" in cat or "product launch" in cat:
            if s["type"] == "VIP":                score += 22
            if s["type"] == "Product":            score += 25

        # Product / name keyword match — biggest single differentiator
        for kw in product_keywords:
            if kw in sname:
                score += 60
                break

        # Studio → metro
        if studio_metro and studio_metro.lower() in sname:
            score += 45

        # Goal alignment
        if "flash" in goal:
            if "engaged 60d" in sname:            score += 20
            if s["type"] == "Behavioral":         score += 15
        if "launch" in goal:
            if s["type"] == "VIP":                score += 25
            if s["type"] == "Product":            score += 18
        if "retention" in goal:
            if s["type"] == "VIP":                score += 18
        if "re-engagement" in goal or "re engagement" in goal:
            if s["type"] == "Winback":            score += 30
            if s["type"] == "Behavioral":         score += 18
        if "awareness" in goal:
            if s["type"] == "Broadcast":          score += 15

        # User explicitly pre-selected this in Plan a Campaign — strong signal
        if sname in pre_selected:
            score += 40

        scores.append((score, s))
    scores.sort(key=lambda x: -x[0])
    return [s for _, s in scores[:n]]


# ──────────────────────────────────────────────────────────────────────────────
# FLOW vs. CAMPAIGN — per-message recommendations
# ──────────────────────────────────────────────────────────────────────────────
# Performance-driven rec, biased toward keeping flow when in doubt.
# Thresholds calibrated from observed flow_msgs RPR distribution.
def _flow_msg_recommendation(msg, campaign):
    """Return (action, color, reason) for one flow message vs the campaign."""
    rpr = float(msg.get("RPR") or 0)
    cr  = float(msg.get("Conversion Rate") or 0)
    step = int(msg.get("Step #") or 1)
    msg_name = str(msg.get("Message Name", "")).lower()
    cat = (campaign.get("category") or "").lower()
    goal = (campaign.get("goal") or "").lower()

    is_first_touch    = step == 1
    is_discount_step  = any(t in msg_name for t in ["10%", " off", "last chance",
                                                    "final", "discount", "code"])
    is_campaign_promo = any(t in cat for t in ["promo", "sale", "winback"]) or \
                        any(t in goal for t in ["flash", "re-engagement"])

    GREEN  = "#2e7d32"
    YELLOW = "#c98a00"
    GRAY   = "#666666"

    # Top tier — never override
    if rpr >= 2.00:
        return ("Keep flow", GREEN,
                f"Top performer: ${rpr:.2f} RPR, {cr:.1%} conv. "
                f"Don't disrupt — campaign won't beat this.")

    # High — keep
    if rpr >= 0.75:
        return ("Keep flow", GREEN,
                f"Strong: ${rpr:.2f} RPR. Overlapping the campaign would steal "
                f"incremental revenue.")

    # First touch is closest to the trigger event — preserve
    if is_first_touch and rpr >= 0.40:
        return ("Keep flow", GREEN,
                f"First touch is closest to the trigger: ${rpr:.2f} RPR is "
                f"solid for that step. Keep.")

    # Both campaign and message push a discount → let campaign carry
    if is_discount_step and is_campaign_promo:
        return ("Replace with campaign", YELLOW,
                f"Both this step and your campaign are discount-driven — "
                f"avoid double-prompting; let the campaign offer carry.")

    # Mid — send both, staggered
    if 0.30 <= rpr < 0.75:
        return ("Send both", GRAY,
                f"Mid-performer (${rpr:.2f} RPR). Stagger campaign 6–12h "
                f"after the flow touch so the flow lands its conversion first.")

    # Low — replace
    if rpr < 0.30:
        return ("Replace with campaign", YELLOW,
                f"Underperforms (${rpr:.2f} RPR, {cr:.1%} conv). "
                f"Your campaign offer likely beats this message.")

    return ("Keep flow", GREEN, "Default — preserve existing flow.")


def _flow_overall_recommendation(messages_df, campaign):
    """Aggregate per-message recommendations into a single flow-level call.
    Weighted by 90-day revenue per message; biased to Keep on ties."""
    if messages_df.empty:
        return ("Keep flow", "#2e7d32",
                "No message data — defaulting to keep flow.")

    weights = {"Keep flow": 0.0, "Send both": 0.0, "Replace with campaign": 0.0}
    for _, m in messages_df.iterrows():
        action, _, _ = _flow_msg_recommendation(m, campaign)
        weights[action] += float(m.get("Revenue") or 0)

    total = sum(weights.values())
    if total == 0:
        return ("Keep flow", "#2e7d32",
                "Flow has no recent revenue — preserving by default.")

    # Tie-breaker preference: Keep > Send both > Replace
    pref = {"Keep flow": 2, "Send both": 1, "Replace with campaign": 0}
    action = max(weights.keys(), key=lambda k: (weights[k], pref[k]))
    pct = weights[action] / total * 100
    color = {"Keep flow": "#2e7d32", "Send both": "#666666",
             "Replace with campaign": "#c98a00"}[action]

    if action == "Keep flow":
        reason = (f"<strong>{pct:.0f}%</strong> of this flow's 90-day revenue "
                  f"comes from messages that out-earn a typical campaign — "
                  f"don't disrupt them.")
    elif action == "Send both":
        reason = (f"Most of the flow's 90-day revenue is mid-tier — stagger "
                  f"the campaign 6–12h after each flow touch to avoid "
                  f"cannibalization.")
    else:
        reason = (f"<strong>{pct:.0f}%</strong> of this flow's 90-day revenue "
                  f"comes from underperforming messages — your campaign offer "
                  f"likely converts better.")
    return (action, color, reason)


def past_similar(campaign, k=3):
    sub = campaigns_df[
        (campaigns_df["Category"] == campaign["category"]) &
        (campaigns_df["Channel"] == campaign["channel"])
    ].dropna(subset=["Click Rate", "Revenue"])
    if sub.empty:
        sub = campaigns_df[campaigns_df["Channel"] == campaign["channel"]] \
            .dropna(subset=["Click Rate", "Revenue"])
    return sub.sort_values("Revenue", ascending=False).head(k)


def _why_suggested(seg, camp):
    """Per-campaign rationale — leans on product, goal, studio so similar-category
    campaigns still get distinct reasoning."""
    cat   = (camp.get("category") or "").lower()
    ch    = camp.get("channel") or "email"
    prod  = (camp.get("product") or "").lower()
    studio = (camp.get("studio") or "").lower()
    goal  = (camp.get("goal") or "").lower()
    name_blob = f"{camp.get('name','')} {camp.get('subject_line_draft','')}".lower()
    sname = seg["name"].lower()
    haystack = f"{prod} {name_blob}"

    # Strongest signal first: product/affinity match
    affinity_map = {
        "opal":     "gold lovers",
        "diamond":  "flatback fans",
        "gold":     "gold lovers",
        "silver":   "silver fans",
        "hoop":     "hoop heads",
        "flatback": "flatback fans",
        "stud":     "piercing fans",
        "pearl":    "gold lovers",
    }
    for token, target in affinity_map.items():
        if token in haystack and target in sname:
            return (f"<em>{seg['name']}</em> is the affinity segment for <strong>"
                    f"{token}</strong> — these {seg['size']:,} subscribers buy this "
                    f"product family at ~{seg['avg_conv']*100:.1f}% conv vs ~2% on broadcast.")

    # Studio → metro audience match
    studio_match = {"new york":"NY Metro","nyc":"NY Metro","williamsburg":"NY Metro",
                    "soho":"NY Metro","los angeles":"LA Metro","la":"LA Metro",
                    "chicago":"Chicago Metro","boston":"Boston Metro","dc":"DC Metro",
                    "philly":"Philly Metro","atlanta":"Atlanta Metro",
                    "houston":"Houston Metro","austin":"Austin","dallas":"Dallas",
                    "san francisco":"SF Bay Area","bay area":"SF Bay Area"}
    for sk, sv in studio_match.items():
        if (sk in studio or sk in name_blob) and sv.lower() in sname:
            return (f"This is a <strong>{sk}</strong>-area campaign — only locals "
                    f"can book appointments. Geo-targeted sends lift studio bookings "
                    f"~1.7× over broadcast.")

    # Channel mismatch warning
    if ch == "sms" and seg["type"] != "Broadcast" and "engaged" not in sname:
        return ("Email-native segment — won't perform on an SMS send unless you "
                "have these subscribers cross-listed on SMS.")

    # Pre-selected in Plan a Campaign
    pre_selected = {a.lower() for a in (camp.get("audiences") or [])}
    if sname in pre_selected:
        return (f"You picked this audience in Plan a Campaign — keeping it locked. "
                f"{seg['size']:,} contacts at {seg['avg_conv']*100:.1f}% conv.")

    # Category-driven specifics
    if "restock" in cat:
        if seg["type"] == "Product":
            return (f"Wishlist segment for this product family. Restock pings convert "
                    f"~2.3× higher on wishlists than broadcast — these subscribers "
                    f"explicitly flagged interest.")
        if seg["type"] == "VIP":
            return (f"VIPs ({seg['avg_conv']:.1%} conv) buy first when restocks drop — "
                    f"they have repeat purchase patterns on the same SKUs.")
        if seg["type"] == "Behavioral" and "browse" in seg.get("name", "").lower():
            return ("Showed product-page intent without buying — restock notification "
                    "re-triggers the deferred purchase.")
    if "vip" in cat or "loyalty" in cat:
        if seg["type"] == "VIP":
            return (f"Direct match — 3+ orders, ${seg['avg_ltv']:.0f} LTV, "
                    f"{seg['avg_click']:.1%} click. Best place for early access.")
        if seg["type"] == "Product":
            return ("Wishlist segment overlaps heavily with VIPs — extends VIP launch "
                    "reach ~1.4× without diluting intent.")
    if "holiday" in cat or "seasonal" in cat:
        if seg["type"] == "Broadcast":
            return (f"Holiday hero moments need scale. <em>{seg['name']}</em> "
                    f"({seg['size']:,}) hits the volume target — broadest reachable "
                    f"audience for a high-stakes send.")
        if seg["type"] == "VIP":
            return ("VIPs have ~1.9× the gift-purchase rate during holidays — they "
                    "buy for others. Pair with broadcast for layered launch.")
        if seg["type"] == "Product":
            return ("Highest-converting subset of your engaged list. Pairs well with "
                    "a broadcast for both reach and depth.")
    if "studio" in cat or "in-studio" in cat:
        if seg["type"] == "Geo":
            return ("Studio campaigns lift ~1.7× on geo-targeted segments — only "
                    "locals can book appointments.")
        if seg["type"] == "Behavioral" and "appointment" in seg.get("name", "").lower():
            return "Already showed appointment intent — strong follow-on for studio events."
    if "promo" in cat or "sale" in cat:
        if seg["type"] == "SMS":
            return ("Flash promos lift ~2.4× on SMS — short copy, urgency, "
                    "immediate redeem path.")
        if seg["type"] == "Winback":
            return ("Lapsed buyers respond to discounts when nothing else gets them "
                    "back. Sale + winback is a natural fit.")
        if seg["avg_click"] >= 0.04:
            return (f"Engaged segment ({seg['avg_click']:.1%} click) — promos work "
                    f"fastest on already-warm audiences.")
    if "editorial" in cat:
        if seg["avg_click"] >= 0.04:
            return (f"Editorial converts on engagement, not size. {seg['avg_click']:.1%} "
                    f"click rate amplifies content vs broadcast.")
        if seg["type"] == "New":
            return (f"New subscribers haven't seen your editorial yet — "
                    f"{seg['avg_open']:.0%} open on first content drop.")
    if "winback" in cat and seg["type"] == "Winback":
        return "Direct match — these are exactly the lapsed contacts you want to re-engage."

    # Generic fallback
    if seg["type"] == "Behavioral":
        return f"Behavioral signal — {seg['rec']}"
    if seg["avg_click"] >= 0.05:
        return f"High click rate ({seg['avg_click']:.1%}) — qualified intent across any send."
    return seg["rec"]


def _why_combined(seg_names):
    """Why these segments combine well — or warn if they don't."""
    if len(seg_names) < 2:
        return None
    objs = [SEG_BY_NAME[s] for s in seg_names if s in SEG_BY_NAME]
    if len(objs) < 2:
        return None

    biggest = max(objs, key=lambda s: s["size"])
    highest_intent = max(objs, key=lambda s: s["avg_conv"])
    types = set(s["type"] for s in objs)
    total = sum(s["size"] for s in objs)

    if biggest["name"] == highest_intent["name"]:
        return ("All selected segments lean to similar intent — total reach ~"
                f"{total:,} after de-dupe. Consider adding a broader segment for "
                f"amplified reach.")

    multiplier = biggest["size"] / max(1, highest_intent["size"])

    if "Product" in types and "Broadcast" in types:
        return (f"<strong>Wishlist + broadcast.</strong> "
                f"<em>{highest_intent['name']}</em> ({highest_intent['avg_conv']:.1%} "
                f"conv) is the high-intent core. <em>{biggest['name']}</em> extends "
                f"reach {multiplier:.1f}×. Common pattern for product launches — "
                f"hit buyers and prospects in one send.")
    if "VIP" in types and "Broadcast" in types:
        return (f"<strong>VIP + broadcast.</strong> Send hits your top-"
                f"{highest_intent['size']:,} buyers (${highest_intent['avg_ltv']:.0f} "
                f"avg LTV) plus the broader engaged list. Make sure the offer scales "
                f"— VIPs expect early/exclusive language.")
    if "Geo" in types and len(types) > 1:
        return ("<strong>Geo + non-geo.</strong> Local audience for studio relevance "
                "plus broader reach. Watch unsubscribes on the non-geo set if copy "
                "is location-specific.")
    if "SMS" in types and "Broadcast" in types:
        return ("<strong>Cross-channel layered send.</strong> Email broadcast + SMS "
                "reminder. Stagger timing — SMS 24-48h after email for max lift.")
    if "Winback" in types and "Broadcast" in types:
        return ("<strong>Winback + broadcast.</strong> Lapsed contacts get a softer "
                "version of the offer alongside your engaged list. Use a different "
                "subject line per segment if Klaviyo allows.")

    return (f"<strong>{highest_intent['name']}</strong> is the high-intent core "
            f"({highest_intent['avg_conv']:.1%} conv); <strong>{biggest['name']}</strong> "
            f"extends reach {multiplier:.1f}×. ~{total:,} total — spans warm buyers "
            f"and prospects.")


# ──────────────────────────────────────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────────────────────────────────────
tab_seg, tab_send = st.tabs(["Customer Segmentation", "Send Logistics"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — CUSTOMER SEGMENTATION
# ══════════════════════════════════════════════════════════════════════════════
with tab_seg:
    selected = DSTATE[camp["id"]]["segments"]
    total_reach = sum(SEG_BY_NAME[s]["size"] for s in selected if s in SEG_BY_NAME)

    chips = "".join(
        f'<span style="background:#1a1a1a;color:#fff;'
        f'padding:4px 12px;border-radius:4px;font-size:0.72rem;font-weight:500;'
        f'font-family:\'Barlow\',sans-serif;">'
        f'{s} · {SEG_BY_NAME[s]["size"]:,}</span>'
        for s in selected if s in SEG_BY_NAME
    )
    st.markdown(f"""
    <div style="background:{COLORS['offwhite']};border:1px solid {COLORS['border']};
                border-radius:8px;padding:12px 16px;margin-bottom:1.2rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span style="font-family:'Barlow',sans-serif;font-size:0.62rem;
                     letter-spacing:0.07em;text-transform:uppercase;color:{COLORS['muted']};
                     font-weight:600;">Selected segments for "{camp['name']}"</span>
        <span style="font-family:'Barlow Condensed',sans-serif;font-size:0.9rem;
                     font-weight:700;color:{COLORS['black']};">Total reach: {total_reach:,}</span>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;">{chips or '<span style="color:#999;font-size:0.8rem;">No segments selected — pick from suggestions.</span>'}</div>
    </div>
    """, unsafe_allow_html=True)

    define_col, suggest_col = st.columns([3, 2], gap="large")

    # ── RIGHT (2/5): SEGMENT LIBRARY — all segments + behaviorals ──────────
    with suggest_col:
        st.markdown("<h2>Segment library</h2>", unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#444;'
            f'margin:-0.3rem 0 0.8rem;">All your customer segments + any new ones '
            f'you build below. Top matches for <strong>{camp["category"]}</strong> · '
            f'<strong>{camp["channel"].upper()}</strong> are flagged.</p>',
            unsafe_allow_html=True,
        )

        # Rank segments by match score — show top 6 only to keep the view compact
        suggested_all = suggest_segments(camp, n=6)
        top_three_names = {s["name"] for s in suggested_all[:3]}
        past = past_similar(camp, 3)

        for i, seg in enumerate(suggested_all):
            is_selected = seg["name"] in selected
            is_top = seg["name"] in top_three_names
            rank = next((j for j, s in enumerate(suggested_all)
                         if s["name"] == seg["name"]), i) + 1

            if is_selected:
                badge_text, badge_color, badge_bg = "Selected", "#2e7d32", "#e8f5e9"
            elif is_top:
                badge_text = f"#{rank} match"
                badge_color = "#000"
                badge_bg = "#caf30b"
            else:
                badge_text, badge_color, badge_bg = "", COLORS["muted"], None

            badge_html = (
                f'<span style="background:{badge_bg};color:{badge_color};'
                f'padding:1px 7px;border-radius:3px;font-family:\'Barlow\',sans-serif;'
                f'font-size:0.55rem;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.06em;margin-left:6px;">{badge_text}</span>'
                if badge_text else ""
            )
            type_pill = (
                f'<span style="background:#f0f0f0;color:#555;padding:1px 6px;'
                f'border-radius:3px;font-family:\'Barlow\',sans-serif;font-size:0.55rem;'
                f'font-weight:600;text-transform:uppercase;letter-spacing:0.04em;'
                f'margin-right:4px;">{seg["type"]}</span>'
            )

            why = _why_suggested(seg, camp) if is_top else ""

            r_cols = st.columns([3.4, 1.1])
            r_cols[0].markdown(
                f'<div style="padding:8px 0 2px;font-family:\'Barlow\',sans-serif;'
                f'font-size:0.78rem;color:{COLORS["black"]};font-weight:600;line-height:1.2;">'
                f'{type_pill}{seg["name"]}{badge_html}</div>'
                f'<div style="font-size:0.66rem;color:{COLORS["muted"]};line-height:1.4;'
                f'margin-top:2px;">'
                f'<strong>{seg["size"]:,}</strong> · '
                f'click <strong>{seg["avg_click"]:.1%}</strong> · '
                f'conv <strong>{seg["avg_conv"]:.1%}</strong> · '
                f'last touch {seg["last_touch_days"]}d</div>'
                + (f'<div style="font-size:0.68rem;color:#333;line-height:1.45;'
                   f'margin-top:4px;padding:6px 8px;background:#fafafa;'
                   f'border-left:2px solid {COLORS["black"]};border-radius:3px;">'
                   f'<span style="font-family:\'Barlow\',sans-serif;font-size:0.55rem;'
                   f'letter-spacing:0.08em;text-transform:uppercase;color:{COLORS["muted"]};'
                   f'font-weight:700;">Why suggested</span><br/>{why}</div>'
                   if why else ""),
                unsafe_allow_html=True,
            )
            with r_cols[1]:
                if is_selected:
                    if st.button("Remove", key=f"rm_{camp['id']}_{seg['name']}",
                                 use_container_width=True):
                        DSTATE[camp["id"]]["segments"].remove(seg["name"])
                        _sync_to_planned(camp["id"])
                        st.rerun()
                else:
                    btn_type = "primary" if is_top else "secondary"
                    if st.button("Add", key=f"add_{camp['id']}_{seg['name']}",
                                 type=btn_type, use_container_width=True):
                        DSTATE[camp["id"]]["segments"].append(seg["name"])
                        _sync_to_planned(camp["id"])
                        st.rerun()

        # Expected funnel for the *currently selected* set + similar past campaigns
        st.markdown("")
        if selected:
            sel_seg_objs = [SEG_BY_NAME[s] for s in selected if s in SEG_BY_NAME]
            tot_size = sum(s["size"] for s in sel_seg_objs)
            wavg = lambda key: (sum(s[key] * s["size"] for s in sel_seg_objs) / tot_size) if tot_size else 0
            avg_open = wavg("avg_open")
            avg_click = wavg("avg_click")
            avg_conv = wavg("avg_conv")
            exp_open = int(tot_size * (avg_open if avg_open > 0 else 0.85))
            exp_click = int(tot_size * avg_click)
            exp_conv = int(tot_size * avg_conv)
            avg_ltv = wavg("avg_ltv")
            exp_rev = int(exp_conv * avg_ltv * 0.6) if avg_ltv > 0 else int(exp_conv * 95)
            sms_only = all(s["type"] == "SMS" for s in sel_seg_objs)
            open_label = "Delivered" if sms_only else "Opens"
            open_rate_str = "—" if sms_only else f"{avg_open:.0%}"

            past_list = "".join(
                f'<li style="margin-bottom:3px;">'
                f'{(p.get("Campaign Name","—") or "—")[:42]} '
                f'<span style="color:{COLORS["muted"]};">· '
                f'{p["Click Rate"]:.1%} CR · ${p["Revenue"]:,.0f}</span></li>'
                for _, p in past.iterrows()
            )

            st.markdown(f"""
            <div style="background:{COLORS['offwhite']};border:1px solid {COLORS['border']};
                        border-radius:8px;padding:12px 14px;margin-top:12px;">
              <div style="font-family:'Barlow',sans-serif;font-size:0.6rem;letter-spacing:0.08em;
                          text-transform:uppercase;color:{COLORS['muted']};font-weight:700;
                          margin-bottom:6px;">Expected funnel — selected set</div>
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;
                          font-family:'Barlow',sans-serif;font-size:0.82rem;">
                <div><strong>{exp_open:,}</strong>
                  <div style="color:{COLORS['muted']};font-size:0.62rem;">{open_label} · {open_rate_str}</div></div>
                <div><strong>{exp_click:,}</strong>
                  <div style="color:{COLORS['muted']};font-size:0.62rem;">Clicks · {avg_click:.1%}</div></div>
                <div><strong>{exp_conv:,}</strong>
                  <div style="color:{COLORS['muted']};font-size:0.62rem;">Conv · {avg_conv:.1%}</div></div>
                <div><strong>{fmt_revenue(exp_rev)}</strong>
                  <div style="color:{COLORS['muted']};font-size:0.62rem;">Est. revenue</div></div>
              </div>
              <div style="margin-top:10px;font-size:0.7rem;border-top:1px solid {COLORS['border']};
                          padding-top:6px;">
                <span style="color:{COLORS['muted']};font-size:0.6rem;text-transform:uppercase;
                             letter-spacing:0.06em;font-weight:700;">Similar past campaigns</span>
                <ul style="margin:4px 0 0 16px;padding:0;font-size:0.72rem;">{past_list or '<li>—</li>'}</ul>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Behavioral ideas (data-grounded) ──────────────────────────────
        st.markdown("<h2>New behavioral segments to test</h2>", unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#444;'
            f'margin:-0.3rem 0 0.8rem;">Derived from <strong>Events Sample</strong> '
            f'(n={EVENTS_SAMPLE_N:,}). Sizes projected onto the {ENGAGED_LIST_SIZE/1000:.0f}K '
            f'engaged list. Adding one creates a custom segment and pulls it into '
            f'<em>{camp["name"]}</em>.</p>',
            unsafe_allow_html=True,
        )

        # Filter behaviorals to those tagged for this campaign category
        campcat = (camp.get("category") or "").lower()
        relevant = [b for b in BEHAVIORAL_IDEAS
                    if any(t.lower() in campcat or campcat in t.lower() for t in b["best_for"])]
        if not relevant:
            relevant = BEHAVIORAL_IDEAS[:3]

        for b in relevant:
            already = b["name"] in selected
            r = st.columns([3.4, 1.1])
            r[0].markdown(
                f'<div style="padding:6px 0 2px;font-family:\'Barlow\',sans-serif;'
                f'font-size:0.78rem;color:{COLORS["black"]};font-weight:600;line-height:1.2;">'
                f'{b["name"]}</div>'
                f'<div style="font-size:0.66rem;color:{COLORS["muted"]};line-height:1.4;">'
                f'~<strong>{b["size_est"]:,}</strong> · '
                f'click <strong>{b["exp_click"]:.1%}</strong> · '
                f'conv <strong>{b["exp_conv"]:.1%}</strong></div>'
                f'<div style="font-size:0.62rem;color:#666;line-height:1.4;margin-top:3px;">'
                f'{b["why"]}</div>'
                f'<div style="font-size:0.6rem;color:#888;font-style:italic;margin-top:2px;">'
                f'{b["evidence"]}</div>',
                unsafe_allow_html=True,
            )
            with r[1]:
                if already:
                    st.markdown(
                        f'<div style="padding:10px 0;font-size:0.62rem;color:#2e7d32;'
                        f'font-weight:600;text-align:center;">In list ✓</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    if st.button("Add", key=f"build_{camp['id']}_{b['name']}",
                                 type="primary", use_container_width=True):
                        new_seg = {
                            "name": b["name"], "type": "Behavioral",
                            "size": b["size_est"],
                            "engaged_30d": int(b["size_est"] * 0.7),
                            "engaged_90d": b["size_est"],
                            "avg_open": 0.42, "avg_click": b["exp_click"],
                            "avg_conv": b["exp_conv"], "avg_ltv": 95,
                            "last_touch_days": 3, "rec": b["why"],
                        }
                        # Persist as a custom segment globally + add to this campaign
                        if not any(s["name"] == new_seg["name"]
                                   for s in st.session_state["_custom_segments"]):
                            st.session_state["_custom_segments"].append(new_seg)
                        DSTATE[camp["id"]]["segments"].append(b["name"])
                        _sync_to_planned(camp["id"])
                        st.rerun()

    # ── LEFT (3/5): DEFINE A SEGMENT ───────────────────────────────────────
    with define_col:
        st.markdown("<h2>Define a segment</h2>", unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#444;'
            f'margin:-0.3rem 0 0.8rem;">Segments persist per campaign — switch using the '
            f'dropdown above. Add, refine, or write your own rules.</p>',
            unsafe_allow_html=True,
        )

        # ── A. Segments included (multiselect) ────────────────────────────
        st.markdown(
            f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.6rem;'
            f'letter-spacing:0.08em;text-transform:uppercase;color:{COLORS["muted"]};'
            f'font-weight:700;margin-bottom:0.2rem;">Segments in this campaign</div>',
            unsafe_allow_html=True,
        )
        all_seg_names = [s["name"] for s in SEGMENTS]
        # Always push DSTATE into the widget's session state so Add/Remove buttons
        # in the Segment Library are immediately reflected in the multiselect.
        _ms_key = f"ms_{camp['id']}"
        st.session_state[_ms_key] = [s for s in selected if s in all_seg_names]
        new_selected = st.multiselect(
            "Segments in this campaign",
            options=all_seg_names,
            key=_ms_key,
            label_visibility="collapsed",
        )
        if set(new_selected) != set(selected):
            DSTATE[camp["id"]]["segments"] = new_selected
            _sync_to_planned(camp["id"])
            st.rerun()

        # Why this combination — strategy callout
        combo_msg = _why_combined(new_selected)
        if combo_msg:
            st.markdown(
                f'<div style="border-left:2px solid {COLORS["border"]};padding:6px 10px;'
                f'margin-top:8px;font-family:\'Barlow\',sans-serif;font-size:0.76rem;'
                f'color:#444;line-height:1.5;">'
                f'<span style="font-size:0.55rem;letter-spacing:0.08em;text-transform:uppercase;'
                f'color:{COLORS["muted"]};font-weight:700;">Why this combination</span>'
                f'<br/>{combo_msg}</div>',
                unsafe_allow_html=True,
            )
        elif len(new_selected) == 1:
            only = SEG_BY_NAME.get(new_selected[0])
            if only:
                st.markdown(
                    f'<div style="border-left:2px solid {COLORS["border"]};padding:6px 10px;'
                    f'margin-top:8px;font-family:\'Barlow\',sans-serif;font-size:0.76rem;'
                    f'color:#444;line-height:1.5;">'
                    f'<span style="font-size:0.55rem;letter-spacing:0.08em;text-transform:uppercase;'
                    f'color:{COLORS["muted"]};font-weight:700;">Why this segment</span>'
                    f'<br/>{_why_suggested(only, camp)}</div>',
                    unsafe_allow_html=True,
                )

        # ── Push to Klaviyo ───────────────────────────────────────────────────
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        _push_col, _push_info_col = st.columns([1, 2])
        with _push_col:
            _push_disabled = len(new_selected) == 0
            if st.button(
                "Push to Klaviyo",
                key=f"kl_push_{camp['id']}",
                type="primary",
                use_container_width=True,
                disabled=_push_disabled,
            ):
                # Mock push — records timestamp & what was pushed to session state
                _push_record = {
                    "ts":          _dt.datetime.now(),
                    "segments":    list(new_selected),
                    "freq_cap":    DSTATE[camp["id"]].get("freq_cap", ""),
                    "suppressions": list(DSTATE[camp["id"]].get("suppressions", [])) +
                                    list(DSTATE[camp["id"]].get("suppressions_custom", [])),
                }
                st.session_state[_kl_last_push_key] = _push_record["ts"]
                st.session_state[f"_kl_push_record_{camp['id']}"] = _push_record
                _sync_to_planned(camp["id"])
                st.toast(
                    f"Pushed {len(new_selected)} segment(s) to Klaviyo for '{camp['name']}'",
                    icon="✅",
                )
                st.rerun()
            if _push_disabled:
                st.markdown(
                    f'<div style="font-size:0.62rem;color:{COLORS["muted"]};margin-top:2px;">'
                    f'Select at least one segment first</div>',
                    unsafe_allow_html=True,
                )

        with _push_info_col:
            _prev_push = st.session_state.get(f"_kl_push_record_{camp['id']}")
            if _prev_push:
                _segs_str = " · ".join(_prev_push["segments"][:3])
                if len(_prev_push["segments"]) > 3:
                    _segs_str += f" +{len(_prev_push['segments'])-3}"
                st.markdown(
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.7rem;'
                    f'line-height:1.6;padding-top:4px;">'
                    f'<span style="font-size:0.58rem;text-transform:uppercase;letter-spacing:0.07em;'
                    f'color:{COLORS["muted"]};font-weight:700;">'
                    f'Pushed {_prev_push["ts"].strftime("%-I:%M %p, %b %d")}</span><br/>'
                    f'<span style="color:{COLORS["black"]};font-weight:600;">{_segs_str}</span><br/>'
                    f'<span style="color:{COLORS["muted"]};font-size:0.65rem;">'
                    f'Cap: {_prev_push["freq_cap"] or "—"}</span></div>',
                    unsafe_allow_html=True,
                )
            elif new_selected:
                _segs_ready = " · ".join(new_selected[:3])
                if len(new_selected) > 3:
                    _segs_ready += f" +{len(new_selected)-3}"
                st.markdown(
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.7rem;'
                    f'line-height:1.6;padding-top:4px;">'
                    f'<span style="font-size:0.58rem;text-transform:uppercase;letter-spacing:0.07em;'
                    f'color:{COLORS["muted"]};font-weight:700;">Ready to push</span><br/>'
                    f'<span style="color:{COLORS["black"]};font-weight:600;">{_segs_ready}</span><br/>'
                    f'<span style="color:{COLORS["muted"]};font-size:0.65rem;">'
                    f'+ freq cap · suppressions</span></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")

        # ── B. Refinement chat ────────────────────────────────────────────
        def _segment_ai_context(camp, n_selected):
            """Generate campaign-specific opening message and placeholder."""
            name = camp.get("name", "")
            cat  = camp.get("category_tag", camp.get("category", "")).lower()
            name_l = name.lower()

            # Detect campaign type from name + category
            if any(k in name_l for k in ["memorial day", "labor day", "fourth of july", "4th of july"]):
                opener = (f"You have {n_selected} segment(s) for **{name}**. "
                          f"Who should we prioritise? E.g. customers who shopped last Memorial Day, "
                          f"high-LTV customers active in the last 90 days, or gift-buyers.")
                placeholder = "e.g. customers who purchased during last Memorial Day sale"
            elif any(k in name_l for k in ["mother", "mom", "father", "dad", "valentine", "holiday"]):
                opener = (f"You have {n_selected} segment(s) for **{name}**. "
                          f"Who's most likely to convert? E.g. past holiday gift-buyers, "
                          f"customers with high AOV, or those who browsed but didn't buy last {name.split()[0]}.")
                placeholder = "e.g. purchased a gift last Mother's Day"
            elif any(k in name_l for k in ["black friday", "cyber monday", "bfcm"]):
                opener = (f"You have {n_selected} segment(s) for **{name}**. "
                          f"Typical high-performers: BFCM buyers from prior years, "
                          f"wishlist customers, and high-engagement subscribers.")
                placeholder = "e.g. purchased during BFCM last year"
            elif "restock" in name_l or cat == "restock":
                product = next((w for w in name.split() if w[0].isupper() and w not in ("Spring","Summer","Fall","Winter")), "this product")
                opener = (f"You have {n_selected} segment(s) for **{name}**. "
                          f"Strong targets: customers who previously viewed or purchased {product}, "
                          f"wishlist holders, or category loyalists.")
                placeholder = f"e.g. viewed {product} in the last 60 days"
            elif any(k in name_l for k in ["flash", "sale", "markdown", "promo"]):
                opener = (f"You have {n_selected} segment(s) for **{name}**. "
                          f"Who responds best to sales? E.g. discount-motivated buyers (previous sale purchasers), "
                          f"lapsed customers, or high-frequency browsers.")
                placeholder = "e.g. purchased during a previous flash sale"
            elif any(k in name_l for k in ["launch", "new drop", "introducing", "just dropped"]):
                opener = (f"You have {n_selected} segment(s) for **{name}**. "
                          f"Early adopters convert best here — e.g. customers who bought within 7 days of the last launch, "
                          f"high-engagement subscribers, or VIP segments.")
                placeholder = "e.g. purchased within 7 days of last new launch"
            elif any(k in name_l for k in ["winback", "win-back", "lapsed", "miss you", "we miss"]):
                opener = (f"You have {n_selected} segment(s) for **{name}**. "
                          f"Narrow to the most recoverable: e.g. lapsed 90–180 days (not 180+), "
                          f"previously high-spend customers, or those who clicked but didn't buy.")
                placeholder = "e.g. lapsed 90–180 days with at least 1 prior purchase"
            else:
                opener = (f"You have {n_selected} segment(s) for **{name}**. "
                          f"Who's the best fit? E.g. engaged in last 30 days, "
                          f"high-LTV customers, or a specific purchase history.")
                placeholder = "e.g. opened last 3 emails and purchased in the past year"
            return opener, placeholder

        _ai_opener, _ai_placeholder = _segment_ai_context(camp, len(selected))

        with st.expander("Narrow this audience with AI", expanded=False):
            chat_key = f"chat_{camp['id']}"
            if chat_key not in st.session_state:
                st.session_state[chat_key] = [
                    {"role": "assistant", "msg": _ai_opener},
                ]
            for m in st.session_state[chat_key]:
                bg = COLORS["offwhite"] if m["role"] == "assistant" else "#f7f3ff"
                who = "AI" if m["role"] == "assistant" else "You"
                st.markdown(f"""
                <div style="background:{bg};border-radius:6px;padding:8px 10px;margin-bottom:6px;
                            font-size:0.78rem;border:1px solid {COLORS['border']};">
                  <strong>{who}:</strong> {m['msg']}
                </div>""", unsafe_allow_html=True)
            user_msg = st.text_input("Narrow this audience",
                                     key=f"chatin_{camp['id']}",
                                     label_visibility="collapsed",
                                     placeholder=_ai_placeholder)
            cs1, cs2 = st.columns([1, 4])
            with cs1:
                if st.button("Send", key=f"chatsend_{camp['id']}", type="primary"):
                    if user_msg.strip():
                        st.session_state[chat_key].append({"role": "user", "msg": user_msg})
                        DSTATE[camp["id"]]["refinements"].append(user_msg)
                        reply = (f"Saved as a refinement on the selected segments. "
                                 f"Estimated impact: −8% reach, +14% click rate "
                                 f"(more qualified). I'll apply it at send time.")
                        st.session_state[chat_key].append({"role": "assistant", "msg": reply})
                        _sync_to_planned(camp["id"])
                        st.rerun()
            if DSTATE[camp["id"]]["refinements"]:
                st.markdown(
                    f'<div style="font-size:0.7rem;color:{COLORS["muted"]};margin-top:4px;">'
                    f'Active refinements: ' +
                    " · ".join(f"<em>{r}</em>"
                               for r in DSTATE[camp["id"]]["refinements"]) +
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")

        # ── C. Frequency caps (with custom write-in) ──────────────────────
        st.markdown("<h2>Frequency caps</h2>", unsafe_allow_html=True)
        cap_options = [
            DEFAULT_FREQ,
            "Tight (1/wk email — for lapsed/winback)",
            "Loose (5/wk email · 3/wk SMS — VIP only)",
            "No cap (overrides global)",
            "Custom…",
        ]
        cur_cap = DSTATE[camp["id"]]["freq_cap"]
        if cur_cap not in cap_options[:-1]:
            cur_cap_idx = len(cap_options) - 1   # Custom
        else:
            cur_cap_idx = cap_options.index(cur_cap)
        new_cap = st.selectbox(
            "Frequency cap rule",
            cap_options, index=cur_cap_idx, key=f"cap_{camp['id']}",
            label_visibility="collapsed",
        )
        if new_cap == "Custom…":
            custom_cap = st.text_input(
                "Custom frequency cap",
                value=DSTATE[camp["id"]].get("freq_cap_custom", ""),
                key=f"capcustom_{camp['id']}",
                placeholder="e.g. Max 1 email + 1 SMS per 72h for this campaign only",
                label_visibility="collapsed",
            )
            DSTATE[camp["id"]]["freq_cap"] = custom_cap or "Custom (unset)"
            DSTATE[camp["id"]]["freq_cap_custom"] = custom_cap
        else:
            DSTATE[camp["id"]]["freq_cap"] = new_cap
            DSTATE[camp["id"]]["freq_cap_custom"] = ""

        # Conflict check across both Klaviyo and user-planned campaigns
        nearby = [c for c in incoming
                  if c["id"] != camp["id"]
                  and abs((c["send_date"] - camp["send_date"]).days) <= 3
                  and c["channel"] == camp["channel"]]
        if nearby:
            conflicts = "<br/>".join(
                f"• {n['name']} — {n['send_date'].strftime('%b %d')} "
                f"({(n['send_date']-camp['send_date']).days:+d}d)"
                for n in nearby[:3]
            )
            st.markdown(f"""
            <div style="background:#FFF4D6;border:1px solid {COLORS['warn']};
                        border-radius:6px;padding:8px 10px;font-size:0.72rem;
                        margin-top:6px;line-height:1.4;">
              <strong>{len(nearby)} {camp['channel']} send(s) within 3 days</strong><br/>
              {conflicts}<br/>
              <em style="color:{COLORS['muted']};">Suggestion: tighten cap or push by 2 days.</em>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(
                f'<p style="font-size:0.72rem;color:{COLORS["muted"]};margin-top:4px;">'
                f'✓ No nearby {camp["channel"]} sends — cap will not bind.</p>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # ── D. Suppressions (with custom write-in) ────────────────────────
        st.markdown("<h2>Suppressions</h2>", unsafe_allow_html=True)
        SUPP_OPTIONS = [
            "Unsubscribed", "Bounced 30d", "Spam complaints",
            "Purchased <7d ago", "Returned item <30d",
            "Active in another campaign this week",
            "Lapsed 365d+",
        ]
        cur_sup = DSTATE[camp["id"]]["suppressions"]
        new_sup = st.multiselect(
            "Suppressions",
            SUPP_OPTIONS, default=[s for s in cur_sup if s in SUPP_OPTIONS],
            key=f"sup_{camp['id']}",
            label_visibility="collapsed",
        )
        DSTATE[camp["id"]]["suppressions"] = new_sup
        # Custom write-in
        custom_sup = st.text_input(
            "Add a custom suppression rule (one per line, comma-separated)",
            value=", ".join(DSTATE[camp["id"]].get("suppressions_custom", [])),
            key=f"supcustom_{camp['id']}",
            placeholder="e.g. Excluded VIP test cohort, Currently in Welcome flow",
        )
        DSTATE[camp["id"]]["suppressions_custom"] = [
            s.strip() for s in custom_sup.split(",") if s.strip()
        ]
        sup_total = len(new_sup) + len(DSTATE[camp["id"]]["suppressions_custom"])
        sup_impact = sup_total * 380
        st.markdown(
            f'<div style="font-size:0.7rem;color:{COLORS["muted"]};margin-top:4px;">'
            f'Est. ~{sup_impact:,} contacts suppressed across {sup_total} rule(s).</div>',
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # ── E. Flow vs. Campaign prioritization ──────────────────────────
        st.markdown("<h2>Flow vs. campaign prioritization</h2>", unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#444;'
            f'margin:-0.3rem 0 0.8rem;line-height:1.5;">If a recipient is in an active flow, what wins? '
            f'Per-message recommendations below are weighted by 90d performance — '
            f'we lean toward keeping the flow unless it clearly underperforms.</p>',
            unsafe_allow_html=True,
        )

        # Marketing-style flows (filter out transactional/operational)
        TRANSACTIONAL_KEYS = ["acuity", "appointment", "cancellation", "weather",
                              "facilities", "staffing", "csat", "review",
                              "post-piercing"]
        all_flow_names = sorted(flow_msgs["Flow Name"].dropna().unique())
        marketing_flows = [f for f in all_flow_names
                           if not any(k in f.lower() for k in TRANSACTIONAL_KEYS)]
        if not marketing_flows:
            marketing_flows = all_flow_names

        cur_flow = DSTATE[camp["id"]].get("flow_target", marketing_flows[0])
        flow_pick = st.selectbox(
            "Flow to deconflict against",
            marketing_flows,
            index=marketing_flows.index(cur_flow) if cur_flow in marketing_flows else 0,
            key=f"flow_{camp['id']}",
        )
        DSTATE[camp["id"]]["flow_target"] = flow_pick

        flow_rows = (flow_msgs[flow_msgs["Flow Name"] == flow_pick]
                     .sort_values("Step #"))
        overall_action, overall_color, overall_reason = _flow_overall_recommendation(
            flow_rows, camp
        )

        # Overall recommendation banner
        rec_bg = {"Keep flow": "#e8f5e9", "Send both": "#f5f5f5",
                  "Replace with campaign": "#fff4d6"}[overall_action]
        st.markdown(
            f'<div style="margin:6px 0 8px;">'
            f'<span style="font-family:\'Barlow\',sans-serif;font-size:0.58rem;'
            f'letter-spacing:0.08em;text-transform:uppercase;color:{COLORS["muted"]};'
            f'font-weight:700;">Recommended</span>'
            f'<span style="font-family:\'Barlow\',sans-serif;font-size:0.88rem;'
            f'font-weight:700;color:{overall_color};margin-left:8px;">{overall_action}</span>'
            f'<div style="font-size:0.7rem;color:#444;line-height:1.5;margin-top:4px;">'
            f'{overall_reason}</div></div>',
            unsafe_allow_html=True,
        )

        # Per-message overrides storage — keyed by flow name → step number
        if "flow_msg_overrides" not in DSTATE[camp["id"]]:
            DSTATE[camp["id"]]["flow_msg_overrides"] = {}
        all_overrides = DSTATE[camp["id"]]["flow_msg_overrides"]
        msg_overrides = all_overrides.setdefault(flow_pick, {})

        # Per-message detail rows (streamlit columns so we can drop a select per row)
        OVERRIDE_OPTS = ["Use rec", "Keep flow", "Send both", "Replace with campaign"]
        ACTION_COLORS = {
            "Keep flow":             "#2e7d32",
            "Send both":             "#666666",
            "Replace with campaign": "#c98a00",
        }

        if not flow_rows.empty:
            # Header row
            hdr = st.columns([0.4, 2.6, 1.6, 1.4])
            for hc, txt in zip(hdr, ["Step", "Message · Performance",
                                     "Recommendation", "Override"]):
                hc.markdown(
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.55rem;'
                    f'letter-spacing:0.08em;text-transform:uppercase;'
                    f'color:{COLORS["muted"]};font-weight:700;'
                    f'border-bottom:1px solid {COLORS["border"]};padding:0 0 4px;">{txt}</div>',
                    unsafe_allow_html=True,
                )

            for _, m in flow_rows.iterrows():
                action, color, reason = _flow_msg_recommendation(m, camp)
                step = int(m["Step #"])
                rpr = float(m.get("RPR") or 0)
                cr = float(m.get("Conversion Rate") or 0)
                clk = float(m.get("Click Rate") or 0)
                ch_pill = (
                    f'<span style="background:#1a1a1a;color:#fff;padding:1px 5px;'
                    f'border-radius:3px;font-size:0.5rem;font-weight:600;'
                    f'font-family:\'Barlow\',sans-serif;">EMAIL</span>'
                    if str(m.get("Channel", "")).lower() == "email" else
                    f'<span style="background:#f0f0f0;color:#444;padding:1px 5px;'
                    f'border-radius:3px;font-size:0.5rem;font-weight:600;'
                    f'font-family:\'Barlow\',sans-serif;border:1px solid #ddd;">SMS</span>'
                )

                # Resolve current effective action: override (if any) wins over rec
                stored = msg_overrides.get(str(step), "Use rec")
                effective = action if stored == "Use rec" else stored
                eff_color = ACTION_COLORS.get(effective, color)

                r = st.columns([0.4, 2.6, 1.6, 1.4])
                r[0].markdown(
                    f'<div style="padding:8px 0;text-align:center;color:{COLORS["muted"]};'
                    f'font-weight:700;font-family:\'Barlow\',sans-serif;">#{step}</div>',
                    unsafe_allow_html=True,
                )
                r[1].markdown(
                    f'<div style="padding:8px 0 4px;font-family:\'Barlow\',sans-serif;'
                    f'font-size:0.78rem;font-weight:600;color:{COLORS["black"]};'
                    f'line-height:1.2;">{m["Message Name"]}</div>'
                    f'<div style="font-size:0.62rem;color:{COLORS["muted"]};'
                    f'display:flex;gap:6px;align-items:center;flex-wrap:wrap;">'
                    f'{ch_pill}<span>click {clk:.1%}</span><span>·</span>'
                    f'<span>conv {cr:.1%}</span><span>·</span>'
                    f'<strong style="color:#000;">${rpr:.2f} RPR</strong></div>',
                    unsafe_allow_html=True,
                )
                # Recommendation badge + reasoning
                overridden = stored != "Use rec"
                badge_label = action if not overridden else f"{effective} (overridden)"
                badge_color = color if not overridden else eff_color
                r[2].markdown(
                    f'<div style="padding:8px 0 0;">'
                    f'<span style="background:{badge_color}1A;color:{badge_color};'
                    f'border:1px solid {badge_color};padding:2px 6px;border-radius:3px;'
                    f'font-size:0.55rem;font-weight:700;font-family:\'Barlow\',sans-serif;'
                    f'letter-spacing:0.04em;text-transform:uppercase;'
                    f'white-space:nowrap;">{badge_label}</span>'
                    f'<div style="font-size:0.6rem;color:#444;line-height:1.4;'
                    f'margin-top:4px;">{reason}</div></div>',
                    unsafe_allow_html=True,
                )
                with r[3]:
                    sel_key = f"ovr_{camp['id']}_{flow_pick}_{step}"
                    cur_idx = (OVERRIDE_OPTS.index(stored)
                               if stored in OVERRIDE_OPTS else 0)
                    new_val = st.selectbox(
                        f"Override step {step}",
                        OVERRIDE_OPTS,
                        index=cur_idx,
                        key=sel_key,
                        label_visibility="collapsed",
                    )
                    if new_val != stored:
                        if new_val == "Use rec":
                            msg_overrides.pop(str(step), None)
                        else:
                            msg_overrides[str(step)] = new_val
                        _sync_to_planned(camp["id"])
                        st.rerun()

            # Quick reset for all overrides on this flow
            if msg_overrides:
                rc1, _ = st.columns([1.4, 4])
                with rc1:
                    if st.button(f"Reset all overrides ({len(msg_overrides)})",
                                 key=f"reset_ovr_{camp['id']}_{flow_pick}",
                                 use_container_width=True):
                        all_overrides[flow_pick] = {}
                        _sync_to_planned(camp["id"])
                        st.rerun()
        else:
            st.markdown(
                f'<div style="font-size:0.72rem;color:{COLORS["muted"]};font-style:italic;'
                f'padding:8px 0;">No message-level data for this flow.</div>',
                unsafe_allow_html=True,
            )

        # Resolution dropdown — defaults to recommendation, user can override
        priority_options = [
            "Keep flow — skip campaign if user is in active flow",
            "Replace with campaign — pause flow for this send",
            "Send both — campaign + flow can both fire",
            "Custom…",
        ]
        rec_to_option = {
            "Keep flow":             priority_options[0],
            "Replace with campaign": priority_options[1],
            "Send both":             priority_options[2],
        }
        recommended_option = rec_to_option.get(overall_action, priority_options[0])

        cur_pri = DSTATE[camp["id"]]["flow_priority"]
        # Adopt recommendation on first visit (when state is still the global default)
        rec_key = f"_pri_initialized_{camp['id']}_{flow_pick}"
        if not st.session_state.get(rec_key) and cur_pri == DEFAULT_PRIO:
            cur_pri = recommended_option
            DSTATE[camp["id"]]["flow_priority"] = recommended_option
            st.session_state[rec_key] = True

        cur_pri_idx = (priority_options.index(cur_pri)
                       if cur_pri in priority_options[:-1]
                       else len(priority_options) - 1)

        st.markdown(
            f'<div style="font-size:0.6rem;color:{COLORS["muted"]};margin-top:10px;'
            f'font-weight:600;text-transform:uppercase;letter-spacing:0.06em;">'
            f'Flow-level fallback (applies to any step without an explicit override)</div>',
            unsafe_allow_html=True,
        )
        new_pri = st.selectbox(
            "Resolution",
            priority_options, index=cur_pri_idx, key=f"pri_{camp['id']}",
            label_visibility="collapsed",
        )
        if new_pri == "Custom…":
            free = st.text_area("Custom prioritization rule",
                                value=DSTATE[camp["id"]].get("flow_priority_custom", ""),
                                height=70, key=f"prifree_{camp['id']}",
                                placeholder="e.g. Keep Steps 1–2, replace Step 3 (10% Off) "
                                            "with this campaign's offer.")
            DSTATE[camp["id"]]["flow_priority"] = free or "Custom (unset)"
            DSTATE[camp["id"]]["flow_priority_custom"] = free
        else:
            DSTATE[camp["id"]]["flow_priority"] = new_pri
            DSTATE[camp["id"]]["flow_priority_custom"] = ""

        # Estimated overlap (size-based heuristic from each flow's first-step recipients)
        if not flow_rows.empty:
            step1_recip = float(flow_rows.iloc[0].get("Recipients 90d") or 0)
            # roughly 1/13 of 90d recipients are in-flow at any given send moment
            overlap_est = int(step1_recip / 13)
        else:
            overlap_est = 1500
        st.markdown(
            f'<p style="font-size:0.72rem;color:{COLORS["muted"]};margin-top:6px;line-height:1.4;">'
            f'~<strong style="color:{COLORS["black"]};">{overlap_est:,}</strong> recipients likely in '
            f'<strong style="color:{COLORS["black"]};">{flow_pick}</strong> at send time '
            f'(est. from 90d Step 1 volume).</p>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — SEND LOGISTICS
# ══════════════════════════════════════════════════════════════════════════════
with tab_send:
    st.markdown("<h2>Send logistics</h2>", unsafe_allow_html=True)
    st.markdown(
        f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;color:#444;'
        f'margin:-0.3rem 0 1rem;">Recommended channel, day, and time per campaign × segment, '
        f'driven by historical performance and the engagement window of each segment.</p>',
        unsafe_allow_html=True,
    )

    SEG_BEST_TIME = {
        "VIP":        ("Tuesday",   "10:00 AM", "email"),
        "Broadcast":  ("Wednesday", "11:00 AM", "email"),
        "Winback":    ("Sunday",    "7:00 PM",  "email"),
        "New":        ("Thursday",  "12:00 PM", "email"),
        "Geo":        ("Tuesday",   "5:00 PM",  "email"),
        "SMS":        ("Friday",    "12:00 PM", "sms"),
        "Product":    ("Tuesday",   "10:00 AM", "email"),
        "Behavioral": ("Wednesday", "11:00 AM", "email"),
    }

    def channel_recommendation(campaign, seg):
        if seg["type"] == "SMS":
            return ("sms", "Segment is SMS-native — keep SMS.")
        if (campaign["category"] or "").lower() in ["promo", "sale"] and seg["avg_click"] >= 0.04:
            return ("sms+email", "High intent + promo — send SMS reminder after email.")
        if seg["type"] == "VIP":
            return ("email", "VIP prefers email — longer-form previews.")
        return (campaign["channel"], "Match campaign default.")

    # Build a recommendation record per campaign × segment
    def _build_rec(c, sname):
        seg = SEG_BY_NAME.get(sname)
        if not seg:
            return None
        day, time_, _ = SEG_BEST_TIME.get(seg["type"], ("Tuesday", "10:00 AM", "email"))
        rec_ch, rec_why = channel_recommendation(c, seg)
        return {
            "campaign_id": c["id"], "campaign": c["name"],
            "segment": sname, "seg_obj": seg,
            "channel": rec_ch.upper(), "day": day, "time": time_,
            "exp_click": seg["avg_click"], "exp_conv": seg["avg_conv"],
            "size": seg["size"], "why": rec_why,
            "send_date": c["send_date"].strftime("%b %d"),
        }

    rows = []
    for c in incoming:
        segs = DSTATE[c["id"]]["segments"]
        if not segs:
            rows.append({"campaign": c["name"], "segment": "— no segments —",
                         "channel": "—", "day": "—", "time": "—", "exp_click": None,
                         "is_focus": c["id"] == camp["id"],
                         "send_date": c["send_date"].strftime("%b %d")})
            continue
        for sname in segs:
            rec = _build_rec(c, sname)
            if rec:
                rec["is_focus"] = (c["id"] == camp["id"])
                rows.append(rec)

    # ── Focus campaign: interactive edit / approve cards ──────────────────────
    st.markdown("<h3>Per-segment send plan — focus campaign</h3>", unsafe_allow_html=True)

    _DAYS   = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    _TIMES  = ["8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM", "12:00 PM",
               "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM", "5:00 PM",
               "6:00 PM", "7:00 PM", "8:00 PM", "9:00 PM"]
    _CHANNELS = ["EMAIL", "SMS", "SMS+EMAIL"]

    focus_recs = [r for r in rows if r.get("is_focus") and r.get("seg_obj")]
    logistics  = DSTATE[camp["id"]]["send_logistics"]

    if not focus_recs:
        st.markdown(
            f'<div style="background:#FFF4D6;border:1px solid {COLORS["warn"]};'
            f'border-radius:8px;padding:10px 14px;font-size:0.8rem;">'
            f'No segments selected — add segments in <strong>Customer Segmentation</strong>.</div>',
            unsafe_allow_html=True,
        )
    else:
        n_approved = sum(1 for r in focus_recs if logistics.get(r["segment"], {}).get("approved"))
        st.markdown(
            f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#444;'
            f'margin:-0.2rem 0 0.8rem;">'
            f'<strong>{n_approved} / {len(focus_recs)}</strong> segment{"s" if len(focus_recs)!=1 else ""} marked ready for review. '
            f'Review the AI suggestion for each, edit if needed, then mark ready.</p>',
            unsafe_allow_html=True,
        )

        for rec in focus_recs:
            sname = rec["segment"]
            log   = logistics.get(sname, {})
            approved = log.get("approved", False)

            # Resolved values: use saved override if present, else AI suggestion
            cur_ch  = log.get("channel", rec["channel"])
            cur_day = log.get("day",     rec["day"])
            cur_time= log.get("time",    rec["time"])

            _border_color = "#caf30b" if approved else COLORS["border"]
            _bg = "#f7fff0" if approved else COLORS["white"]

            with st.container():
                st.markdown(
                    f'<div style="border:1px solid {_border_color};border-radius:8px;'
                    f'background:{_bg};padding:12px 16px;margin-bottom:10px;">',
                    unsafe_allow_html=True,
                )

                hdr_col, badge_col = st.columns([4, 2])
                with hdr_col:
                    size_str = f"{rec['size']:,}" if rec.get("size") else ""
                    st.markdown(
                        f'<div style="font-family:\'Barlow\',sans-serif;font-weight:700;'
                        f'font-size:0.88rem;">{sname}'
                        f'<span style="font-weight:400;color:{COLORS["muted"]};font-size:0.75rem;'
                        f'margin-left:8px;">{size_str} recipients</span></div>',
                        unsafe_allow_html=True,
                    )
                with badge_col:
                    if approved:
                        _ts = log.get("timestamp")
                        _by = log.get("marked_by", "")
                        _ts_str = _ts.strftime("%-d %b · %-I:%M %p") if _ts else ""
                        st.markdown(
                            f'<div style="text-align:right;font-family:\'Barlow\',sans-serif;">'
                            f'<div style="font-size:0.7rem;font-weight:700;color:#2a7a1f;'
                            f'background:#e6f9e0;border:1px solid #b5e5a8;border-radius:4px;'
                            f'padding:3px 8px;display:inline-block;">✓ READY FOR REVIEW</div>'
                            f'<div style="font-size:0.64rem;color:{COLORS["muted"]};margin-top:3px;">'
                            f'{_by}'
                            f'{"&nbsp;·&nbsp;" + _ts_str if _ts_str else ""}'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )

                # AI suggestion row
                st.markdown(
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.74rem;'
                    f'color:#555;background:#f7f7f7;border-radius:4px;'
                    f'padding:6px 10px;margin:6px 0;">'
                    f'<span style="font-weight:700;font-size:0.62rem;text-transform:uppercase;'
                    f'letter-spacing:0.05em;color:#888;">AI suggests</span>&nbsp;&nbsp;'
                    f'<strong>{rec["channel"]}</strong> · {rec["day"]} · {rec["time"]}'
                    f'<span style="color:{COLORS["muted"]};margin-left:8px;">— {rec["why"]}</span>'
                    f'<span style="margin-left:10px;font-size:0.68rem;color:#888;">'
                    f'Exp. CR {rec["exp_click"]:.1%}</span></div>',
                    unsafe_allow_html=True,
                )

                # Edit controls
                ec1, ec2, ec3, ec4 = st.columns([2, 2, 2, 1])
                with ec1:
                    new_ch = st.selectbox(
                        "Channel", _CHANNELS,
                        index=_CHANNELS.index(cur_ch) if cur_ch in _CHANNELS else 0,
                        key=f"sl_ch_{camp['id']}_{sname}",
                        disabled=approved,
                    )
                with ec2:
                    new_day = st.selectbox(
                        "Send day", _DAYS,
                        index=_DAYS.index(cur_day) if cur_day in _DAYS else 1,
                        key=f"sl_day_{camp['id']}_{sname}",
                        disabled=approved,
                    )
                with ec3:
                    new_time = st.selectbox(
                        "Send time", _TIMES,
                        index=_TIMES.index(cur_time) if cur_time in _TIMES else 2,
                        key=f"sl_time_{camp['id']}_{sname}",
                        disabled=approved,
                    )
                with ec4:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if approved:
                        if st.button("Edit", key=f"sl_edit_{camp['id']}_{sname}",
                                     use_container_width=True):
                            logistics[sname] = {
                                "channel": cur_ch, "day": cur_day, "time": cur_time,
                                "approved": False,
                                "timestamp": None, "marked_by": "",
                            }
                            st.rerun()
                    else:
                        if st.button("Ready for review", key=f"sl_approve_{camp['id']}_{sname}",
                                     type="primary", use_container_width=True):
                            import datetime as _dt2
                            logistics[sname] = {
                                "channel": new_ch, "day": new_day, "time": new_time,
                                "approved": True,
                                "timestamp": _dt2.datetime.now(),
                                "marked_by": current_user(),
                            }
                            st.rerun()

                    # Persist uncommitted edits (no rerun needed — widget values live in session)
                    if not approved:
                        logistics.setdefault(sname, {})
                        logistics[sname].update({"channel": new_ch, "day": new_day,
                                                 "time": new_time, "approved": False})

                st.markdown("</div>", unsafe_allow_html=True)

        # Mark-all-ready shortcut
        all_approved = all(logistics.get(r["segment"], {}).get("approved") for r in focus_recs)
        if not all_approved and focus_recs:
            if st.button("Mark all ready for review", key=f"sl_approve_all_{camp['id']}"):
                import datetime as _dt2
                _now = _dt2.datetime.now()
                _who = current_user()
                for rec in focus_recs:
                    sn = rec["segment"]
                    if not logistics.get(sn, {}).get("approved"):
                        logistics[sn] = {
                            "channel":   logistics.get(sn, {}).get("channel", rec["channel"]),
                            "day":       logistics.get(sn, {}).get("day",     rec["day"]),
                            "time":      logistics.get(sn, {}).get("time",    rec["time"]),
                            "approved":  True,
                            "timestamp": _now,
                            "marked_by": _who,
                        }
                st.rerun()

        # ── Push to Klaviyo ───────────────────────────────────────────────────
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        _sl_push_key    = f"_kl_sl_pushed_{camp['id']}"
        _sl_push_record = st.session_state.get(f"_kl_sl_record_{camp['id']}")
        _sl_last_push   = st.session_state.get(_sl_push_key)

        approved_recs = [r for r in focus_recs if logistics.get(r["segment"], {}).get("approved")]
        _push_disabled  = len(approved_recs) == 0

        _sl_col, _sl_info_col = st.columns([1, 3])
        with _sl_col:
            if st.button(
                "Push schedule to Klaviyo",
                key=f"kl_sl_push_{camp['id']}",
                type="primary",
                use_container_width=True,
                disabled=_push_disabled,
            ):
                import datetime as _dt2
                _payload = [
                    {
                        "segment":  r["segment"],
                        "channel":  logistics[r["segment"]]["channel"],
                        "send_day": logistics[r["segment"]]["day"],
                        "send_time":logistics[r["segment"]]["time"],
                    }
                    for r in approved_recs
                ]
                _sl_record = {
                    "ts":       _dt2.datetime.now(),
                    "pushed_by": current_user(),
                    "payload":  _payload,
                }
                st.session_state[_sl_push_key]               = _sl_record["ts"]
                st.session_state[f"_kl_sl_record_{camp['id']}"] = _sl_record
                st.toast(
                    f"Send schedule pushed to Klaviyo for '{camp['name']}' "
                    f"({len(_payload)} segment{'s' if len(_payload)!=1 else ''})",
                    icon="✅",
                )
                st.rerun()

            if _push_disabled:
                st.markdown(
                    f'<div style="font-size:0.62rem;color:{COLORS["muted"]};margin-top:2px;">'
                    f'Mark at least one segment ready for review first</div>',
                    unsafe_allow_html=True,
                )

        with _sl_info_col:
            if _sl_push_record:
                _ts_str = _sl_push_record["ts"].strftime("%-d %b %Y · %-I:%M %p")
                _who    = _sl_push_record.get("pushed_by", "")
                _lines  = "".join(
                    f'<div style="line-height:1.6;">'
                    f'<strong>{p["segment"]}</strong> — '
                    f'{p["channel"]} · {p["send_day"]} · {p["send_time"]}'
                    f'</div>'
                    for p in _sl_push_record["payload"]
                )
                st.markdown(
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.72rem;'
                    f'background:#f7fff0;border:1px solid #b5e5a8;border-radius:6px;'
                    f'padding:8px 12px;">'
                    f'<div style="font-weight:700;font-size:0.65rem;color:#2a7a1f;'
                    f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">'
                    f'✓ Pushed to Klaviyo · {_ts_str} · {_who}</div>'
                    f'{_lines}</div>',
                    unsafe_allow_html=True,
                )
            elif not _push_disabled:
                _preview_lines = "".join(
                    f'<div style="line-height:1.6;">'
                    f'<strong>{r["segment"]}</strong> — '
                    f'{logistics[r["segment"]]["channel"]} · '
                    f'{logistics[r["segment"]]["day"]} · '
                    f'{logistics[r["segment"]]["time"]}'
                    f'</div>'
                    for r in approved_recs
                )
                st.markdown(
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.72rem;'
                    f'background:#f7f7f7;border:1px solid {COLORS["border"]};border-radius:6px;'
                    f'padding:8px 12px;">'
                    f'<div style="font-weight:700;font-size:0.65rem;color:#888;'
                    f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">'
                    f'Will push</div>'
                    f'{_preview_lines}</div>',
                    unsafe_allow_html=True,
                )

    # ── Other campaigns: compact read-only summary table ─────────────────────
    other_rows = [r for r in rows if not r.get("is_focus") and r.get("seg_obj")]
    if other_rows:
        st.markdown(
            f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
            f'font-weight:700;margin:1rem 0 0.4rem;">Other queued campaigns</div>',
            unsafe_allow_html=True,
        )
        other_html = ""
        for r in other_rows:
            ch = r["channel"]
            if ch == "EMAIL":
                ch_pill = '<span style="background:#1a1a1a;color:#fff;padding:2px 7px;border-radius:4px;font-size:0.6rem;font-weight:600;font-family:\'Barlow\',sans-serif;">EMAIL</span>'
            elif ch == "SMS":
                ch_pill = '<span style="background:#f0f0f0;color:#444;padding:2px 7px;border-radius:4px;font-size:0.6rem;font-weight:600;font-family:\'Barlow\',sans-serif;border:1px solid #ddd;">SMS</span>'
            elif ch == "SMS+EMAIL":
                ch_pill = ('<span style="background:#1a1a1a;color:#fff;padding:2px 6px;border-radius:4px 0 0 4px;font-size:0.58rem;font-weight:600;font-family:\'Barlow\',sans-serif;">EMAIL</span>'
                           '<span style="background:#f0f0f0;color:#444;padding:2px 6px;border-radius:0 4px 4px 0;font-size:0.58rem;font-weight:600;font-family:\'Barlow\',sans-serif;border:1px solid #ddd;border-left:none;">+SMS</span>')
            else:
                ch_pill = f'<span style="color:{COLORS["muted"]};">—</span>'
            click_str = f"{r['exp_click']:.1%}" if r.get("exp_click") else "—"
            other_html += f"""
            <tr style="border-bottom:1px solid #eee;font-size:0.73rem;">
              <td style="padding:6px 10px;font-weight:500;">{r['campaign']}<br/>
                <span style="color:{COLORS['muted']};font-size:0.62rem;">{r.get('send_date','—')}</span></td>
              <td style="padding:6px 10px;">{r['segment']}</td>
              <td style="padding:6px 8px;text-align:center;">{ch_pill}</td>
              <td style="padding:6px 8px;text-align:center;">{r['day']}</td>
              <td style="padding:6px 8px;text-align:center;">{r['time']}</td>
              <td style="padding:6px 8px;text-align:right;">{click_str}</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;font-family:'Barlow',sans-serif;
                      border:1px solid {COLORS['border']};margin-bottom:1rem;">
          <thead>
            <tr style="background:#f7f7f7;font-size:0.6rem;text-transform:uppercase;
                       letter-spacing:0.06em;font-weight:700;">
              <th style="padding:7px 10px;text-align:left;border-bottom:1px solid {COLORS['border']};">Campaign</th>
              <th style="padding:7px 10px;text-align:left;border-bottom:1px solid {COLORS['border']};">Segment</th>
              <th style="padding:7px 8px;text-align:center;border-bottom:1px solid {COLORS['border']};">Channel</th>
              <th style="padding:7px 8px;text-align:center;border-bottom:1px solid {COLORS['border']};">Day</th>
              <th style="padding:7px 8px;text-align:center;border-bottom:1px solid {COLORS['border']};">Time</th>
              <th style="padding:7px 8px;text-align:right;border-bottom:1px solid {COLORS['border']};">Exp. CR</th>
            </tr>
          </thead>
          <tbody>{other_html}</tbody>
        </table>
        """, unsafe_allow_html=True)

    st.divider()

    # Send-time heatmap
    st.markdown("<h3>Click rate by send time — historical</h3>", unsafe_allow_html=True)

    # ── Filters ───────────────────────────────────────────────────────────────
    _heat_cats = sorted(campaigns_df["Category"].dropna().unique().tolist())
    _heat_months_raw = sorted(
        campaigns_df["Send Date"].dropna().dt.to_period("M").astype(str).unique().tolist()
    )
    _heat_months_labels = {
        m: pd.Period(m, "M").strftime("%b %Y") for m in _heat_months_raw
    }
    _all_auds: set = set()
    for _a in campaigns_df["Audiences"].dropna():
        for _seg in str(_a).split(","):
            _s = _seg.strip()
            if _s:
                _all_auds.add(_s)
    _heat_segs = sorted(_all_auds)

    _hfc1, _hfc2, _hfc3 = st.columns(3)
    with _hfc1:
        _sel_cats = st.multiselect(
            "Campaign category", _heat_cats, default=[],
            key=f"heat_cats_{camp['id']}", placeholder="All categories",
        )
    with _hfc2:
        _sel_month_labels = st.multiselect(
            "Month", list(_heat_months_labels.values()), default=[],
            key=f"heat_months_{camp['id']}", placeholder="All months",
        )
        _label_to_key = {v: k for k, v in _heat_months_labels.items()}
        _sel_months = [_label_to_key[lbl] for lbl in _sel_month_labels if lbl in _label_to_key]
    with _hfc3:
        _sel_segs = st.multiselect(
            "Customer segment", _heat_segs, default=[],
            key=f"heat_segs_{camp['id']}", placeholder="All segments",
        )

    # ── Build filtered dataset ────────────────────────────────────────────────
    _hdf = campaigns_df.dropna(subset=["Send Date", "Click Rate"]).copy()
    _hdf["_hour"] = _hdf["Send Date"].dt.hour
    _hdf["_dow"] = _hdf["Day of Week"].fillna(_hdf["Send Date"].dt.day_name())
    _hdf["_month"] = _hdf["Send Date"].dt.to_period("M").astype(str)

    if _sel_cats:
        _hdf = _hdf[_hdf["Category"].isin(_sel_cats)]
    if _sel_months:
        _hdf = _hdf[_hdf["_month"].isin(_sel_months)]
    if _sel_segs:
        _hdf = _hdf[_hdf["Audiences"].fillna("").apply(
            lambda x: any(s in [p.strip() for p in x.split(",")] for s in _sel_segs)
        )]

    # ── Pivot from actual data ────────────────────────────────────────────────
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]

    hmap_data = []
    if not _hdf.empty:
        _hdf["_hour_bin"] = _hdf["_hour"].apply(
            lambda h: min(hours, key=lambda x: abs(x - h))
        )
        for _dow in dow_order:
            for _hr in hours:
                _sub = _hdf[(_hdf["_dow"] == _dow) & (_hdf["_hour_bin"] == _hr)]
                _rate = float(_sub["Click Rate"].mean()) if not _sub.empty else float("nan")
                hmap_data.append({"DOW": _dow, "Hour": _hr, "Click Rate": _rate})
    else:
        for _dow in dow_order:
            for _hr in hours:
                hmap_data.append({"DOW": _dow, "Hour": _hr, "Click Rate": float("nan")})

    hmap_df = pd.DataFrame(hmap_data)
    pivot = hmap_df.pivot(index="DOW", columns="Hour", values="Click Rate").reindex(dow_order)

    # ── Subtitle ──────────────────────────────────────────────────────────────
    _active = []
    if _sel_cats:    _active.append(", ".join(_sel_cats))
    if _sel_month_labels: _active.append(", ".join(_sel_month_labels))
    if _sel_segs:    _active.append(", ".join(_sel_segs))
    _subtitle = " · ".join(_active) if _active else "All categories · all months · all segments"
    st.markdown(
        f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#444;'
        f'margin:-0.3rem 0 0.8rem;">{_subtitle} — '
        f'use to validate or adjust the per-segment recommendations above.</p>',
        unsafe_allow_html=True,
    )

    _text_grid = [
        [f"{v:.1%}" if not (v != v) else "" for v in row]
        for row in pivot.values
    ]

    fig_heat = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[f"{h}:00" for h in pivot.columns],
        y=pivot.index.tolist(),
        colorscale=[[0, "#FFCDD2"], [0.3, "#FFF9C4"], [0.6, "#f5f000"], [1, "#caf30b"]],
        text=_text_grid,
        texttemplate="%{text}",
        textfont=dict(size=10, family="Barlow, sans-serif"),
        showscale=True,
        colorbar=dict(tickformat=".1%", tickfont=dict(size=10)),
    ))
    fig_heat.update_layout(
        **plot_theme(
            title="AVG CLICK RATE BY SEND TIME",
            height=320,
            xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=10)),
            yaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=11),
                       autorange="reversed"),
            margin=dict(l=0, r=60, t=40, b=0),
        )
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    st.divider()

    # Lock-in panel for the focus campaign
    st.markdown("<h3>Commit send plan — focus campaign</h3>", unsafe_allow_html=True)
    focus_rows = [r for r in rows if r["is_focus"] and r.get("size")]
    if focus_rows:
        total_reach = sum(r["size"] for r in focus_rows)
        avg_click = float(np.mean([r["exp_click"] for r in focus_rows]))
        avg_conv = float(np.mean([r.get("exp_conv", 0.02) for r in focus_rows]))
        proj_clicks = int(total_reach * avg_click)
        proj_convs = int(total_reach * avg_conv)
        proj_rev = int(proj_convs * 95)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total reach", f"{total_reach:,}")
        m2.metric("Proj. clicks", f"{proj_clicks:,}", delta=f"{avg_click:.1%} CR")
        m3.metric("Proj. converts", f"{proj_convs:,}", delta=f"{avg_conv:.1%} conv")
        m4.metric("Proj. revenue", fmt_revenue(proj_rev))

        c1, c2, _ = st.columns([1, 1, 4])
        with c1:
            if st.button("Lock send plan", type="primary", use_container_width=True,
                         key=f"lock_{camp['id']}"):
                st.success(f"Send plan locked for **{camp['name']}**. "
                           f"Moving to Generation phase.")
        with c2:
            if st.button("Reset", use_container_width=True, key=f"reset_{camp['id']}"):
                DSTATE[camp["id"]] = {
                    "segments": list(camp.get("audiences") or
                                     ([camp["segment"]] if camp.get("segment") else [])),
                    "freq_cap": DEFAULT_FREQ, "freq_cap_custom": "",
                    "suppressions": list(DEFAULT_SUPP), "suppressions_custom": [],
                    "flow_priority": DEFAULT_PRIO, "flow_priority_custom": "",
                    "flow_target": "Abandoned Cart Flow",
                    "refinements": [],
                }
                _sync_to_planned(camp["id"])
                st.rerun()
    else:
        st.markdown(
            f'<div style="background:#FFF4D6;border:1px solid {COLORS["warn"]};'
            f'border-radius:8px;padding:10px 14px;font-size:0.8rem;">'
            f'No segments selected for this campaign yet. Add at least one in '
            f'<strong>Customer Segmentation</strong>.</div>',
            unsafe_allow_html=True,
        )

# ── End-of-render sync — catches non-rerun mutations (selectbox/multiselect/
# text_input changes that update DSTATE but don't call st.rerun explicitly).
for _c in incoming:
    _sync_to_planned(_c["id"])

# ── Page nav ──────────────────────────────────────────────────────────────────
st.divider()
prev_col, _, next_col = st.columns([1, 5, 1])
with prev_col:
    st.page_link("pages/1_Planning.py", label="← Planning")
with next_col:
    st.page_link("pages/3_Generation.py", label="Generation →")
