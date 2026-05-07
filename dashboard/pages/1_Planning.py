import sys, re as _re, json as _json, html as _html
import calendar as _cal_lib
from pathlib import Path
from datetime import date, timedelta, datetime as _datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

try:
    from shared.sheets import (
        upsert_campaign as _sheets_upsert,
        load_planned_campaigns as _sheets_load,
        load_all_campaigns as _sheets_load_all,
        remove_campaign as _sheets_remove,
        load_comments as _sheets_load_comments,
        post_comment as _sheets_post_comment,
        resolve_comment as _sheets_resolve_comment,
    )
    _SHEETS_ENABLED = True
except Exception as _sheets_import_err:
    print(f"[sheets] import failed: {_sheets_import_err}")
    import traceback; traceback.print_exc()
    _SHEETS_ENABLED = False
    _sheets_load = None
    _sheets_load_all = None
    _sheets_remove = None
    _sheets_load_comments = None
    _sheets_post_comment = None
    _sheets_resolve_comment = None

def _sync_to_sheet(campaign: dict):
    if _SHEETS_ENABLED:
        try:
            _sheets_upsert(campaign)
        except Exception as _e:
            st.toast(f"Sheet sync failed: {_e}", icon="⚠️")


def _archive_campaign(campaign: dict):
    """Move campaign to 'Removed Campaigns' sheet then remove from main sheet."""
    if not (_SHEETS_ENABLED and _sheets_remove is not None):
        return
    try:
        _sheets_remove(campaign)
    except Exception as _e:
        import traceback
        st.error(f"Could not archive campaign to sheet: {_e}\n\n```{traceback.format_exc()}```")

@st.cache_data(ttl=60, show_spinner=False)
def _fetch_sheet_campaigns():
    """
    Loads planned + draft campaigns from Google Sheets.
    Cached for 60 seconds. Returns (planned_list, drafts_list, error_msg).
    """
    if not (_SHEETS_ENABLED and _sheets_load_all is not None):
        return None, None, None  # sheets not configured
    try:
        planned, drafts = _sheets_load_all()
        return planned, drafts, None
    except Exception as _e:
        return None, None, str(_e)


def _invalidate_sheet_cache():
    """Clear the cached sheet data so next render re-fetches."""
    _fetch_sheet_campaigns.clear()


def _push_and_refresh(campaign: dict):
    """Upsert to sheet and invalidate cache."""
    _sync_to_sheet(campaign)
    _invalidate_sheet_cache()


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_comments() -> list:
    """Load comments from Google Sheets, cached for 30 s."""
    if not (_SHEETS_ENABLED and _sheets_load_comments):
        return []
    try:
        return _sheets_load_comments()
    except Exception:
        return []


def _invalidate_comments_cache():
    _fetch_comments.clear()


from shared.styles import inject_css, top_nav
from shared.data import load_data
from shared.owners import TEAMS, ROLES, render_assignment_widget, assignment_summary_html

inject_css()
top_nav("Planning")

# ── Identity selector — persists in session_state["_app_user"] ────────────────
_ALL_OWNERS = [
    "Anna", "Marketing Director", "Marketing Strategy",
    "Brand & Social", "Growth Marketing", "Retail Marketing",
    "Merchandising & Planning", "Design", "Operations", "Data",
]
with st.sidebar:
    st.markdown(
        '<div style="font-size:11px;font-weight:600;color:#888;'
        'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">'
        'Logged in as</div>',
        unsafe_allow_html=True,
    )
    st.selectbox(
        "Logged in as",
        _ALL_OWNERS,
        label_visibility="collapsed",
        key="_app_user",
    )

# ── Early session-state init (needed before tabs for quick-add processing) ────
if "plan_added"  not in st.session_state: st.session_state["plan_added"]  = []
if "plan_drafts" not in st.session_state: st.session_state["plan_drafts"] = []

# ── Process quick-add submitted from the calendar empty-slot popup ────────────
_qa_raw = st.query_params.get("quick_add", "")
if _qa_raw:
    try:
        from datetime import datetime as _dt
        _qa = _json.loads(_qa_raw)
        _qa_date_str = _qa.get("send_date", "")
        _qa_date = (
            _dt.strptime(_qa_date_str, "%Y-%m-%d").date()
            if _qa_date_str else date.today() + timedelta(days=14)
        )
        _qa_entry = {
            "id":        f"P{len(st.session_state['plan_added']) + 1:03d}",
            "name":      _qa.get("name", "Untitled").strip() or "Untitled",
            "subject":   _qa.get("subject", "").strip(),
            "goal":      _qa.get("goal", "Conversion"),
            "category":  _qa.get("category", ""),
            "channel":   _qa.get("channel", "email"),
            "send_date": _qa_date,
            "audiences": [],
            "product":         "",
            "studio":          "",
            "status":          "planned",
            "owner":           st.session_state.get("_app_user", ""),
            "created_by":      st.session_state.get("_app_user", ""),
            "last_modified_by": st.session_state.get("_app_user", ""),
            "last_saved":      _datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        st.session_state["plan_added"].append(_qa_entry)
        _sync_to_sheet(_qa_entry)
        del st.query_params["quick_add"]
        st.toast(f"Added to plan: {_qa_entry['name']}", icon="✅")
    except Exception:
        if "quick_add" in st.query_params:
            del st.query_params["quick_add"]

# ── Data ──────────────────────────────────────────────────────────────────────
campaigns_df, flow_monthly, flow_msgs, benchmarks = load_data()
cal_df = campaigns_df.dropna(subset=["Send Date"]).copy()
cal_df["_date"] = cal_df["Send Date"].dt.date

st.markdown("<h1>Planning</h1>", unsafe_allow_html=True)

# ── Data Connections Banner ────────────────────────────────────────────────────
_CONNECTIONS = [
    {
        "name":   "Asana",
        "abbr":   "AS",
        "color":  "#f06a6a",       # Asana coral
        "status": "not connected",
        "what":   "Planned campaigns across platforms, product launches, studio openings",
        "why":    "Populates upcoming calendar with cross-team commitments before briefs are written",
    },
    {
        "name":   "Klaviyo",
        "abbr":   "KL",
        "color":  "#1a1a1a",
        "status": "mock data",
        "what":   "Past campaign performance, decisions on upcoming sends",
        "why":    "Drives all historical metrics (open, click, conv, revenue) and upcoming campaign state",
    },
    {
        "name":   "Shopify",
        "abbr":   "SH",
        "color":  "#96bf48",       # Shopify green
        "status": "not connected",
        "what":   "Live inventory for all products tied to campaigns",
        "why":    "Flags low-stock risk on planned sends so campaigns can be held or swapped",
    },
    {
        "name":   "Org Calendar",
        "abbr":   "OC",
        "color":  "#888",
        "status": "tbd",
        "what":   "Broader org priorities relevant to marketing (events, freezes, PR moments)",
        "why":    "Prevents conflicts between marketing sends and company-wide blackout windows",
    },
]

_STATUS_STYLE = {
    "mock data":       ("background:#f5f000;color:#000;",      "Mock data"),
    "connected":       ("background:#caf30b;color:#000;",      "Connected"),
    "not connected":   ("background:#f2f2f2;color:#888;",      "Not connected"),
    "tbd":             ("background:#e8c5ff;color:#000;",      "Connection Unknown"),
}

_conn_html = (
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;'
    'margin-bottom:18px;">'
)
for _c in _CONNECTIONS:
    _st_css, _st_lbl = _STATUS_STYLE.get(_c["status"], ("background:#eee;color:#666;", _c["status"]))
    _conn_html += (
        f'<div style="border:1.5px solid #e4e4e4;border-radius:8px;padding:12px 14px;'
        f'background:#fff;position:relative;">'
        # Top row: logo abbreviation + name + status pill
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
        # What it provides
        f'<div style="font-family:Barlow,sans-serif;font-size:11px;font-weight:600;'
        f'color:#000;margin-bottom:3px;line-height:1.4;">{_c["what"]}</div>'
        # Why it matters
        f'<div style="font-family:Barlow,sans-serif;font-size:10px;color:#888;line-height:1.4;">'
        f'{_c["why"]}</div>'
        f'</div>'
    )
_conn_html += '</div>'

# Pre-compute audience set (used in both Calendar filters and New Campaign form)
all_auds_set: set = set()
if "Audiences" in cal_df.columns:
    for _v in cal_df["Audiences"].dropna():
        for _a in str(_v).split(","):
            _a = _a.strip()
            if _a: all_auds_set.add(_a)

tab_cal, tab_upcoming, tab_plan = st.tabs([
    "Calendar", "Upcoming & Draft Campaigns", "Plan a Campaign"
])

# ── Shared performance lookup (used in Upcoming + Plan tabs) ──────────────────
hist_perf = (
    campaigns_df.groupby(["Category","Channel"]).agg(
        avg_open  = ("Open Rate",       "mean"),
        avg_click = ("Click Rate",      "mean"),
        avg_conv  = ("Conversion Rate", "mean"),
        avg_rev   = ("Revenue",         "mean"),
        avg_rpr   = ("RPR",             "mean"),
        count     = ("Campaign Name",   "count"),
    ).reset_index()
)

def _stat_html(label, value, help_txt=""):
    _t = f' title="{help_txt}"' if help_txt else ""
    return (
        f'<div style="padding:4px 8px 4px 0;"{_t}>'
        f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:9px;'
        f'font-weight:700;color:#888;text-transform:uppercase;letter-spacing:0.08em;'
        f'line-height:1.2;">{label}</div>'
        f'<div style="font-family:Barlow,sans-serif;font-size:14px;font-weight:800;'
        f'color:#000;line-height:1.3;margin-top:2px;">{value}</div>'
        f'</div>'
    )

def _lookup_perf(category, channel):
    ch  = channel.lower() if isinstance(channel, str) else ""
    row = hist_perf[
        (hist_perf["Category"] == category) &
        (hist_perf["Channel"].str.lower() == ch)
    ]
    if row.empty:
        row = hist_perf[hist_perf["Channel"].str.lower() == ch]
    if row.empty:
        return None
    r = row.iloc[0]
    return {"open": r["avg_open"], "click": r["avg_click"],
            "conv": r["avg_conv"], "rev": r["avg_rev"],
            "rpr":  r["avg_rpr"],  "n": r["count"]}

# ── Shared lookups (used in Upcoming + Plan tabs) ─────────────────────────────
all_cats_plan = sorted(campaigns_df["Category"].dropna().unique())
all_prods_plan = ["(none)"] + sorted(campaigns_df["Primary Product"].dropna().unique()) \
                 if "Primary Product" in campaigns_df.columns else ["(none)"]
all_stus_plan  = ["(none)"] + sorted(campaigns_df["Primary Studio"].dropna().unique()) \
                 if "Primary Studio" in campaigns_df.columns else ["(none)"]
all_auds_plan  = sorted(all_auds_set)

# ── Session state init for planned campaigns ──────────────────────────────────
if "plan_drafts" not in st.session_state:
    st.session_state["plan_drafts"] = []

if "plan_added" not in st.session_state:
    st.session_state["plan_added"] = []

# Restore decisioning state for any sheet-loaded campaign that has decisioning fields
if "decisioning_state" not in st.session_state:
    st.session_state["decisioning_state"] = {}
for _sc in st.session_state["plan_added"]:
    _did = _sc.get("id")
    if _did and "decisioning" in _sc and _did not in st.session_state["decisioning_state"]:
        st.session_state["decisioning_state"][_did] = _sc["decisioning"]

if "plan_edit_idx" not in st.session_state:
    st.session_state["plan_edit_idx"] = None
if "_last_sheet_sync" not in st.session_state:
    st.session_state["_last_sheet_sync"] = None
if "_sheet_sync_error" not in st.session_state:
    st.session_state["_sheet_sync_error"] = None

# Dict of campaign_id → list of assignment dicts {team, role, note}
if "_campaign_assignments" not in st.session_state:
    st.session_state["_campaign_assignments"] = {}

# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS — calendar / gantt
# ══════════════════════════════════════════════════════════════════════════════

CATEGORY_CODES = {
    "Holiday": "HOL", "Sale": "SALE", "Editorial": "EDIT",
    "Studio": "STU", "Mystery Set": "MYS", "Product Launch": "PLN",
    "Restock": "RST", "Educational": "EDU", "Winback": "WIN",
    "In-Studio": "INS", "NSO": "NSO", "Reminder": "REM",
    "Promo": "PRO", "Partnership": "PTN",
}
DOW_BG      = ["#e6f0fa","#e6f5ee","#faf0e6","#f0e6fa","#fae6ee","#eefae6","#faf5e6"]
DOW_BG_DARK = ["#b3ccee","#b3ddcc","#eeddb3","#ccb3ee","#eeb3cc","#b3eeb3","#eeddb3"]
DOW_NAME    = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
LABEL_W, WEEK_W = 62, 122

PIN_SVG = (
    '<svg width="9" height="12" viewBox="0 0 18 24" '
    'style="vertical-align:middle;margin-right:2px;flex-shrink:0;">'
    '<path d="M9 0C4 0 0 4 0 9c0 6.7 9 15 9 15s9-8.3 9-15C18 4 14 0 9 0z" '
    'fill="#caf30b" stroke="#000" stroke-width="1.5"/>'
    '<circle cx="9" cy="9" r="3.2" fill="white"/>'
    '</svg>'
)
STAR_SVG = (
    '<svg width="10" height="10" viewBox="0 0 20 20" '
    'style="vertical-align:middle;margin-right:2px;flex-shrink:0;">'
    '<polygon points="10,1 12.9,7 19.5,7.6 14.5,12 16.2,18.5 10,15 3.8,18.5 5.5,12 0.5,7.6 7.1,7" '
    'fill="#f5f000" stroke="#888" stroke-width="1"/>'
    '</svg>'
)

def _clean(name):
    if pd.isna(name): return ""
    s = str(name).strip()
    for pfx in ["Glinta – ","Glinta - ","Glinta: ","Glinta_","Glinta "]:
        if s.startswith(pfx): s = s[len(pfx):]
    s = _re.sub(r'^\d{2}\.\d{2}\.\d{2}\s*[-–]\s*', '', s)
    return s.replace("_"," ").strip()

def _week_mon(d):
    return d - timedelta(days=d.weekday())

def _us_events(years):
    evts = {}
    for yr in years:
        for mo, dy, nm in [
            (1,1,"New Year's Day"),
            (2,13,"Galentine's Day"),
            (2,14,"Valentine's Day"),
            (3,8,"International Women's Day"),
            (3,17,"St. Patrick's Day"),
            (3,20,"First Day of Spring"),
            (4,22,"Earth Day"),
            (6,21,"First Day of Summer"),
            (7,4,"Independence Day"),
            (8,25,"Back to School"),
            (9,22,"First Day of Fall"),
            (10,31,"Halloween"),
            (12,21,"First Day of Winter"),
            (12,25,"Christmas"),
            (12,31,"New Year's Eve"),
        ]:
            evts[date(yr,mo,dy)] = nm

        def _nth_wd(y, m, n, wd):
            matches = [date(y,m,1)+timedelta(days=i) for i in range(31)
                       if (date(y,m,1)+timedelta(days=i)).month==m
                       and (date(y,m,1)+timedelta(days=i)).weekday()==wd]
            return matches[n] if len(matches)>n else None

        # Mother's Day (2nd Sunday of May) — no Father's Day (women's brand)
        may_sun2 = _nth_wd(yr,5,1,6)
        if may_sun2: evts[may_sun2] = "Mother's Day"
        for i in range(6,-1,-1):
            d2 = date(yr,5,31) - timedelta(days=i)
            if d2.weekday()==0: evts[d2] = "Memorial Day"; break
        for i in range(7):
            d2 = date(yr,9,1) + timedelta(days=i)
            if d2.weekday()==0: evts[d2] = "Labor Day"; break
        nov_thu4 = _nth_wd(yr,11,3,3)
        if nov_thu4:
            evts[nov_thu4]                    = "Thanksgiving"
            evts[nov_thu4+timedelta(days=1)]  = "Black Friday"
            evts[nov_thu4+timedelta(days=4)]  = "Cyber Monday"
    return evts

def _subj(row):
    subj = row.get("Subject Line","")
    if pd.isna(subj) or str(subj).strip() == "":
        return _clean(row.get("Campaign Name",""))
    s = _re.sub(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE00-\uFE0F]+$', '', str(subj)).strip()
    return s

# ── Chip registry ─────────────────────────────────────────────────────────────
# All chip data lives in a Python list; each chip gets a plain integer index
# (data-cid).  The list is JSON-serialised once into a <script> variable so JS
# can look data up without touching HTML attributes at all.  Clicks are handled
# via document-level event delegation — no inline onclick needed.
_CHIP_REG: list = []   # reset before every Gantt render

def _chip_data(row) -> int:
    """Build chip data dict, register it, and return its integer index."""
    def _str(v): return "" if pd.isna(v) else str(v).strip()
    def _fr(v):
        try: return f"{float(v):.1%}" if pd.notna(v) and float(v) > 0 else "—"
        except: return "—"
    def _fi(v):
        try: return f"{int(float(v)):,}" if pd.notna(v) and float(v) > 0 else "—"
        except: return "—"
    def _frev(v):
        try: return f"${float(v):,.0f}" if pd.notna(v) and float(v) > 0 else "—"
        except: return "—"
    d: dict = {
        "name":       _str(row.get("Campaign Name", "")),
        "category":   _str(row.get("Category", "")),
        "audience":   _str(row.get("Audiences", "")),
        "product":    _str(row.get("Primary Product", "")),
        "studio":     _str(row.get("Primary Studio", "")),
        "send_date":  row["_date"].strftime("%B %-d, %Y"),
        "subject":    _subj(row),
        "sent":       _fi(row.get("Recipients", 0)),
        "open_rate":  _fr(row.get("Open Rate", 0)),
        "click_rate": _fr(row.get("Click Rate", 0)),
        "conv_rate":  _fr(row.get("Conversion Rate", 0)),
        "revenue":    _frev(row.get("Revenue", 0)),
    }
    _cid = row.get("_camp_id")
    _dec = st.session_state.get("decisioning_state", {}).get(_cid) if _cid else None
    if _dec:
        _custom_sup = _dec.get("suppressions_custom", []) or []
        d["decisioning"] = {
            "segments":      _dec.get("segments", []),
            "freq_cap":      _dec.get("freq_cap", ""),
            "suppressions":  list(_dec.get("suppressions", [])) + list(_custom_sup),
            "flow_target":   _dec.get("flow_target", ""),
            "flow_priority": _dec.get("flow_priority", ""),
            "refinements":   _dec.get("refinements", []),
        }
    _CHIP_REG.append(d)
    return len(_CHIP_REG) - 1

_CHIP_BASE = (
    "border-radius:4px;padding:3px 6px;margin:2px 0;font-size:11px;line-height:1.4;"
    + f"max-width:{WEEK_W-10}px;font-family:Barlow,sans-serif;cursor:pointer;"
    + "transition:filter 0.1s;"
)

def _chip(row, cat, d, channel):
    dow   = d.weekday()
    bg    = DOW_BG[dow]
    dlbl  = DOW_NAME[dow]
    code  = CATEGORY_CODES.get(cat, cat[:3].upper() if cat else "")
    label = _subj(row)
    label = label[:22] + "…" if len(label) > 22 else label
    idx   = _chip_data(row)
    return (
        f'<div data-cid="{idx}" class="clickable-chip" '
        f'style="background:{bg};color:#000;border:1px solid rgba(0,0,0,0.12);'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500;{_CHIP_BASE}">'
        f'<span style="opacity:0.45;font-size:7px;background:rgba(0,0,0,0.08);'
        f'border-radius:2px;padding:0 3px;margin-right:2px;">{dlbl} {code}</span>'
        f'{label}'
        f'</div>'
    )

def _evt_chip(name, d):
    dow   = d.weekday()
    bg    = DOW_BG_DARK[dow]
    label = name[:22] + "…" if len(name) > 22 else name
    return (
        f'<div title="{name} — {d.strftime("%b %d")}" '
        f'style="background:{bg};color:#000;border:1px solid rgba(0,0,0,0.18);'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600;{_CHIP_BASE}">'
        f'<span style="font-size:7px;opacity:0.6;">{d.strftime("%-m/%-d")}</span> {label}'
        f'</div>'
    )

def _nso_chip(row, d):
    sv     = row.get("Primary Studio", "")
    studio = "" if pd.isna(sv) else str(sv).strip()
    if not studio: studio = _clean(row.get("Campaign Name", ""))
    studio = studio[:18] + "…" if len(studio) > 18 else studio
    idx    = _chip_data(row)
    return (
        f'<div data-cid="{idx}" class="clickable-chip" '
        f'style="background:#f0fce8;color:#000;border:1.5px solid rgba(0,0,0,0.2);'
        f'display:flex;align-items:center;overflow:hidden;font-weight:600;{_CHIP_BASE}">'
        f'{PIN_SVG}'
        f'<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{studio}</span>'
        f'</div>'
    )

def _launch_chip(row, d):
    pv      = row.get("Primary Product", "")
    product = "" if pd.isna(pv) else str(pv).strip()
    if not product: product = _clean(row.get("Campaign Name", ""))
    product = product[:18] + "…" if len(product) > 18 else product
    idx     = _chip_data(row)
    return (
        f'<div data-cid="{idx}" class="clickable-chip" '
        f'style="background:#fffbe6;color:#000;border:1.5px solid rgba(0,0,0,0.2);'
        f'display:flex;align-items:center;overflow:hidden;font-weight:600;{_CHIP_BASE}">'
        f'{STAR_SVG}'
        f'<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{product}</span>'
        f'</div>'
    )

# ══════════════════════════════════════════════════════════════════════════════
# CALENDAR TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_cal:
    cal_sub_timeline, cal_sub_month = st.tabs(["Timeline", "Month"])

    # ── Month View ─────────────────────────────────────────────────────────────
    with cal_sub_month:
        today       = date.today()
        # Historical months from data + next 3 months forward so future campaigns are reachable
        _hist_periods  = set(cal_df["Send Date"].dt.to_period("M").unique())
        _future_periods = {pd.Period(today + timedelta(days=30 * i), "M") for i in range(0, 4)}
        all_months  = sorted(_hist_periods | _future_periods, reverse=True)
        month_opts  = [p.strftime("%B %Y") for p in all_months]
        default_idx = next((i for i, p in enumerate(all_months)
                            if p.year == today.year and p.month == today.month), 0)

        ca1, ca2, _ = st.columns([1, 1, 4])
        sel_mo_str  = ca1.selectbox("Month", month_opts, index=default_idx,
                                    label_visibility="collapsed", key="plan_cal_month")
        sel_period  = all_months[month_opts.index(sel_mo_str)]
        year, month = sel_period.year, sel_period.month
        sel_cal_ch  = ca2.selectbox("Channel", ["All","Email only","SMS only"],
                                    label_visibility="collapsed", key="plan_cal_ch")

        cal_month = cal_df[
            (cal_df["Send Date"].dt.year  == year) &
            (cal_df["Send Date"].dt.month == month)
        ].copy()
        if sel_cal_ch == "Email only": cal_month = cal_month[cal_month["Channel"] == "email"]
        if sel_cal_ch == "SMS only":   cal_month = cal_month[cal_month["Channel"] == "sms"]

        by_date = {}
        for _, row in cal_month.iterrows():
            by_date.setdefault(row["_date"], []).append(dict(row))

        # Inject user-planned campaigns from the Plan tab
        for _pc in st.session_state.get("plan_added", []):
            _sd = _pc.get("send_date", today)
            if _sd.year == year and _sd.month == month:
                _pch = _pc.get("channel", "email")
                if sel_cal_ch == "Email only" and _pch != "email": continue
                if sel_cal_ch == "SMS only"   and _pch != "sms":   continue
                _fake_row = {
                    "Campaign Name":   _pc.get("name", "Planned"),
                    "Channel":         _pch,
                    "Subject Line":    _pc.get("subject", ""),
                    "Category":        _pc.get("category", ""),
                    "Audiences":       ", ".join(_pc.get("audiences", [])),
                    "Primary Product": _pc.get("product", ""),
                    "Primary Studio":  _pc.get("studio", ""),
                    "Open Rate": None, "Click Rate": None,
                    "Conversion Rate": None, "Revenue": None,
                    "Recipients": None, "Unsub Rate": None,
                    "_date": _sd,
                    "_is_planned": True,
                }
                by_date.setdefault(_sd, []).append(_fake_row)

        n_hist_sends = len(cal_month)
        n_planned_sends = sum(
            1 for _pc in st.session_state.get("plan_added", [])
            if _pc.get("send_date", today).year == year
            and _pc.get("send_date", today).month == month
        )
        day_names   = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
        month_label = date(year, month, 1).strftime("%B %Y").upper()
        sends_label = f"{n_hist_sends} sends" + (f" + {n_planned_sends} planned" if n_planned_sends else "")

        CAL_MODAL_CSS = (
            "#mo-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.45);"
            "z-index:500;align-items:flex-start;justify-content:center;padding-top:32px;}"
            "#mo-box{background:#fff;border:1px solid #e4e4e4;border-radius:10px;"
            "padding:20px 22px 22px;max-width:420px;width:92%;max-height:78vh;"
            "overflow-y:auto;position:relative;box-shadow:0 4px 20px rgba(0,0,0,0.12);}"
            ".mo-close{position:absolute;top:10px;right:10px;background:#f0f0f0;color:#444;"
            "border:none;border-radius:50%;width:26px;height:26px;font-size:13px;"
            "cursor:pointer;font-weight:600;line-height:26px;text-align:center;"
            "font-family:Barlow,sans-serif;}"
            ".mo-cat{font-family:Barlow,sans-serif;font-size:10px;font-weight:600;"
            "letter-spacing:0.08em;text-transform:uppercase;color:#888;margin-bottom:4px;}"
            ".mo-name{font-family:Barlow,sans-serif;font-size:17px;font-weight:700;"
            "line-height:1.2;color:#000;margin-bottom:6px;}"
            ".mo-subj{font-family:Barlow,sans-serif;font-size:11px;color:#555;"
            "font-style:italic;margin-bottom:14px;padding-bottom:12px;"
            "border-bottom:1px solid #e8e8e8;}"
            ".mo-metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;"
            "margin-top:12px;padding-top:12px;border-top:1px solid #e4e4e4;}"
            ".mo-kpi{background:#f7f7f7;border:1px solid #e4e4e4;border-radius:6px;"
            "padding:8px 4px;text-align:center;}"
            ".mo-kpi-val{font-family:Barlow,sans-serif;font-size:13px;font-weight:700;color:#000;}"
            ".mo-kpi-lbl{font-family:Barlow,sans-serif;font-size:9px;font-weight:500;color:#888;"
            "text-transform:uppercase;letter-spacing:0.07em;margin-top:3px;}"
        )
        CAL_MODAL_HTML = (
            '<div id="mo-overlay" onclick="if(event.target===this)closeMo()">'
            '<div id="mo-box">'
            '<button class="mo-close" onclick="closeMo()">&#x2715;</button>'
            '<div id="mo-content"></div>'
            '</div></div>'
        )
        # Month view chip registry — same pattern as Gantt
        _mo_reg: list = []

        CAL_MODAL_JS = """<script>
function showMo(d) {
  if (!d) return;
  var auds = d.audience ? d.audience.split(',').map(function(a){return a.trim();}).filter(Boolean) : [];
  var audPills = auds.map(function(a) {
    return '<span style="display:inline-block;background:#f0f0f0;border:1px solid #ddd;border-radius:3px;' +
           'padding:1px 5px;margin:1px 2px 1px 0;font-size:9px;font-weight:600;">' + a + '</span>';
  }).join('');
  var isPlanned = d.is_planned;
  var metricStyle = isPlanned ? 'opacity:0.4' : '';
  document.getElementById('mo-content').innerHTML =
    '<div class="mo-cat">' + (d.category || '') + (d.category && d.send_date ? ' &middot; ' : '') + d.send_date + '</div>' +
    '<div class="mo-name">' + d.name + (isPlanned ? ' <span style="background:#caf30b;border-radius:3px;padding:1px 6px;font-size:10px;font-weight:700;vertical-align:middle;">PLANNED</span>' : '') + '</div>' +
    (d.subject ? '<div class="mo-subj">&ldquo;' + d.subject + '&rdquo;</div>' : '') +
    (audPills ? '<div style="margin-bottom:10px;font-size:10px;">' + audPills + '</div>' : '') +
    '<div class="mo-metrics" style="' + metricStyle + '">' +
      '<div class="mo-kpi"><div class="mo-kpi-val">' + d.sent + '</div><div class="mo-kpi-lbl"># Sent</div></div>' +
      '<div class="mo-kpi"><div class="mo-kpi-val">' + d.open_rate + '</div><div class="mo-kpi-lbl">% Open</div></div>' +
      '<div class="mo-kpi"><div class="mo-kpi-val">' + d.click_rate + '</div><div class="mo-kpi-lbl">% Click</div></div>' +
      '<div class="mo-kpi"><div class="mo-kpi-val">' + d.conv_rate + '</div><div class="mo-kpi-lbl">% Conv</div></div>' +
      '<div class="mo-kpi"><div class="mo-kpi-val" style="font-size:12px;">' + d.revenue + '</div><div class="mo-kpi-lbl">Revenue</div></div>' +
    '</div>';
  document.getElementById('mo-overlay').style.display = 'flex';
}
function closeMo() { document.getElementById('mo-overlay').style.display = 'none'; }
// Bind clicks directly on every chip element (most reliable across sandbox levels)
function _bindMoChips() {
  var chips = document.querySelectorAll('[data-cid]');
  if (!chips.length || !window._MOR) {
    setTimeout(_bindMoChips, 50);
    return;
  }
  chips.forEach(function(el) {
    el.style.cursor = 'pointer';
    el.onclick = function(e) {
      e.stopPropagation();
      var idx = parseInt(el.getAttribute('data-cid'), 10);
      if (!isNaN(idx) && window._MOR[idx]) showMo(window._MOR[idx]);
    };
  });
}
_bindMoChips();
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeMo(); });
</script>"""

        def _mo_chip_data(ev) -> int:
            """Register month-chip data and return its index."""
            def _fr(v):
                try: return f"{float(v):.1%}" if v is not None and pd.notna(v) and float(v) > 0 else "—"
                except: return "—"
            def _fi(v):
                try: return f"{int(float(v)):,}" if v is not None and pd.notna(v) and float(v) > 0 else "—"
                except: return "—"
            def _frev(v):
                try: return f"${float(v):,.0f}" if v is not None and pd.notna(v) and float(v) > 0 else "—"
                except: return "—"
            def _safe(v):
                raw = ev.get(v, "")
                return "" if (raw is None or (isinstance(raw, float) and pd.isna(raw))) else str(raw).strip()
            _d = ev.get("_date", today)
            d = {
                "name":       _safe("Campaign Name"),
                "category":   _safe("Category"),
                "audience":   _safe("Audiences"),
                "product":    _safe("Primary Product"),
                "studio":     _safe("Primary Studio"),
                "subject":    _safe("Subject Line"),
                "send_date":  _d.strftime("%B %-d, %Y") if isinstance(_d, date) else str(_d),
                "sent":       _fi(ev.get("Recipients")),
                "open_rate":  _fr(ev.get("Open Rate")),
                "click_rate": _fr(ev.get("Click Rate")),
                "conv_rate":  _fr(ev.get("Conversion Rate")),
                "revenue":    _frev(ev.get("Revenue")),
                "is_planned": bool(ev.get("_is_planned", False)),
            }
            _mo_reg.append(d)
            return len(_mo_reg) - 1

        cal_html = (
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&display=swap" rel="stylesheet">'
            '<style>'
            'body{font-family:Barlow,sans-serif;margin:0;padding:0;}'
            '.cal-grid{width:100%;border-collapse:collapse;table-layout:fixed;}'
            '.cal-grid th{font-family:Barlow,sans-serif;font-size:11px;'
            'letter-spacing:0.06em;text-transform:uppercase;padding:8px 10px;'
            'text-align:left;border-bottom:1px solid #e4e4e4;background:#f7f7f7;'
            'color:#888;font-weight:600;}'
            '.cal-cell{vertical-align:top;min-height:95px;padding:7px 8px;'
            'border:1px solid #e4e4e4;font-size:13px;background:#fff;}'
            '.cal-cell.today{background:#fffff5;border:1px solid #cccc00;}'
            '.cal-cell.other-month{background:#fafafa;opacity:0.55;}'
            '.cal-day-num{font-family:Barlow,sans-serif;font-size:13px;'
            'font-weight:500;color:#000;margin-bottom:4px;display:block;}'
            '.cal-day-num.today-num{background:#000;color:#fff;border-radius:50%;'
            'width:22px;height:22px;display:inline-flex;align-items:center;'
            'justify-content:center;font-size:11px;font-weight:600;}'
            '.cal-chip{display:block;margin-bottom:3px;padding:3px 7px;border-radius:4px;'
            'font-size:11px;font-weight:500;line-height:1.35;'
            'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;'
            'transition:filter 0.1s;}'
            '.cal-chip:hover{filter:brightness(0.9);}'
            '.chip-email{background:#1a1a1a;color:#ffffff;}'
            '.chip-sms{background:#e8c5ff;color:#000;border:1px solid #d0a0f0;}'
            '.chip-email-plan{background:#1a1a1a;color:#caf30b;border:2px dashed #caf30b;font-style:italic;}'
            '.chip-sms-plan{background:#e8c5ff;color:#000;border:2px dashed #a080c0;font-style:italic;}'
            '.chip-more{background:transparent;color:#aaa;font-size:10px;cursor:default;}'
            + CAL_MODAL_CSS +
            '</style>'
        )
        cal_html += (
            f'<p style="font-family:Barlow,sans-serif;font-size:1.1rem;'
            f'font-weight:700;letter-spacing:0.03em;text-transform:uppercase;'
            f'color:#000;margin:0 0 0.75rem;">{month_label}'
            f' <span style="font-size:0.75rem;color:#888;font-weight:400;">'
            f'— {sends_label}</span></p>'
        )
        cal_html += '<table class="cal-grid"><thead><tr>'
        for dn in day_names:
            cal_html += f'<th>{dn}</th>'
        cal_html += '</tr></thead><tbody>'

        # All categories from historical data for the quick-add dropdown
        # Raw JSON for use inside a <script> block — no HTML escaping
        _cats_json = _json.dumps(sorted(campaigns_df["Category"].dropna().unique().tolist())).replace('</', '<\\/')

        for week in _cal_lib.Calendar(firstweekday=6).monthdatescalendar(year, month):
            cal_html += '<tr>'
            for day in week:
                is_today       = (day == today)
                is_other_month = (day.month != month)
                day_events     = by_date.get(day, [])
                has_events     = len(day_events) > 0
                cls = "cal-cell" + (" today" if is_today else "") + (" other-month" if is_other_month else "")
                num = (f'<span class="cal-day-num today-num">{day.day}</span>'
                       if is_today else f'<span class="cal-day-num">{day.day}</span>')
                chips = ""
                for ev in day_events[:3]:
                    ch         = str(ev.get("Channel","")).lower()
                    is_planned = bool(ev.get("_is_planned", False))
                    if is_planned:
                        chip_cls = "chip-email-plan" if ch == "email" else "chip-sms-plan"
                    else:
                        chip_cls = "chip-email" if ch == "email" else "chip-sms"
                    label = str(ev.get("Campaign Name",""))
                    label = label[:24] + "…" if len(label) > 24 else label
                    idx   = _mo_chip_data(ev)   # register → integer index
                    chips += (
                        f'<div class="cal-chip {chip_cls}" data-cid="{idx}">'
                        f'{label}</div>'
                    )
                extra = len(day_events) - 3
                if extra > 0:
                    chips += f'<div class="cal-chip chip-more">+{extra} more</div>'
                # Empty-slot click to open quick-add (only in-month days, not in the past)
                date_iso    = day.strftime("%Y-%m-%d")
                empty_click = ""
                if not is_other_month and not has_events and day >= today:
                    empty_click = f' data-date="{date_iso}" onclick="openSlot(this)" title="Click to add a campaign"'
                    cls += " empty-slot"
                cal_html += f'<td class="{cls}"{empty_click}>{num}{chips}</td>'
            cal_html += '</tr>'
        cal_html += '</tbody></table>'
        cal_html += (
            '<div style="margin-top:0.75rem;display:flex;gap:0.75rem;align-items:center;flex-wrap:wrap;">'
            '<span style="font-family:Barlow,sans-serif;font-size:11px;'
            'letter-spacing:0.07em;text-transform:uppercase;color:#888;font-weight:500;">Legend</span>'
            '<span style="background:#1a1a1a;color:#fff;padding:2px 8px;border-radius:4px;'
            'font-size:11px;font-weight:600;font-family:Barlow,sans-serif;">Email</span>'
            '<span style="background:#e8c5ff;color:#000;padding:2px 8px;border-radius:4px;'
            'font-size:11px;font-weight:600;border:1px solid #d0a0f0;'
            'font-family:Barlow,sans-serif;">SMS</span>'
            '<span style="background:#1a1a1a;color:#caf30b;padding:2px 8px;border-radius:4px;'
            'font-size:11px;font-weight:600;border:2px dashed #caf30b;'
            'font-family:Barlow,sans-serif;font-style:italic;">Planned email</span>'
            '<span style="background:#e8c5ff;color:#000;padding:2px 8px;border-radius:4px;'
            'font-size:11px;font-weight:600;border:2px dashed #a080c0;'
            'font-family:Barlow,sans-serif;font-style:italic;">Planned SMS</span>'
            '<span style="font-size:10px;color:#aaa;font-family:Barlow,sans-serif;'
            'margin-left:6px;">— Click an empty future date to add</span>'
            '</div>'
        )

        # ── Quick-add modal (empty slot click) ─────────────────────────────────
        QUICK_ADD_CSS = (
            "#qa-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);"
            "z-index:600;align-items:center;justify-content:center;}"
            "#qa-box{background:#fff;border-radius:12px;padding:22px 24px;max-width:360px;"
            "width:92%;box-shadow:0 8px 32px rgba(0,0,0,0.15);font-family:Barlow,sans-serif;}"
            ".qa-title{font-size:16px;font-weight:700;color:#000;margin-bottom:4px;}"
            ".qa-date{font-size:11px;color:#888;margin-bottom:16px;font-weight:500;}"
            ".qa-label{font-size:10px;font-weight:700;text-transform:uppercase;"
            "letter-spacing:0.07em;color:#555;margin-bottom:4px;display:block;}"
            ".qa-input{width:100%;box-sizing:border-box;border:1.5px solid #e0e0e0;"
            "border-radius:6px;padding:8px 10px;font-size:13px;font-family:Barlow,sans-serif;"
            "outline:none;margin-bottom:12px;}"
            ".qa-input:focus{border-color:#000;}"
            ".qa-select{width:100%;box-sizing:border-box;border:1.5px solid #e0e0e0;"
            "border-radius:6px;padding:8px 10px;font-size:13px;font-family:Barlow,sans-serif;"
            "outline:none;margin-bottom:12px;background:#fff;}"
            ".qa-select:focus{border-color:#000;}"
            ".qa-btn-row{display:flex;gap:8px;margin-top:6px;}"
            ".qa-add{flex:1;background:#000;color:#fff;border:none;border-radius:6px;"
            "padding:10px;font-size:13px;font-weight:700;cursor:pointer;"
            "font-family:Barlow,sans-serif;transition:background 0.1s;}"
            ".qa-add:hover{background:#222;}"
            ".qa-cancel{background:#f0f0f0;color:#444;border:none;border-radius:6px;"
            "padding:10px 16px;font-size:13px;cursor:pointer;font-family:Barlow,sans-serif;}"
            ".empty-slot{cursor:pointer;}"
            ".empty-slot:hover{background:#f9fff0!important;}"
        )
        QUICK_ADD_HTML = (
            '<div id="qa-overlay" onclick="if(event.target===this)closeQa()">'
            '<div id="qa-box">'
            '<div class="qa-title">Add to Plan</div>'
            '<div class="qa-date" id="qa-date-label"></div>'
            '<label class="qa-label">Campaign name</label>'
            '<input id="qa-name" class="qa-input" placeholder="e.g. Mother\'s Day Hero Drop" />'
            '<label class="qa-label">Category (optional)</label>'
            '<select id="qa-cat" class="qa-select"><option value="">—</option></select>'
            '<label class="qa-label">Subject line (optional)</label>'
            '<input id="qa-subj" class="qa-input" placeholder="e.g. She deserves the whole collection ✨" />'
            '<label class="qa-label">Channel</label>'
            '<select id="qa-ch" class="qa-select">'
            '<option value="email">Email</option>'
            '<option value="sms">SMS</option>'
            '</select>'
            '<div class="qa-btn-row">'
            '<button class="qa-cancel" onclick="closeQa()">Cancel</button>'
            '<button class="qa-add" onclick="submitQa()">Add to Plan →</button>'
            '</div>'
            '</div></div>'
        )
        QUICK_ADD_JS = (
            '<script>'
            'var _qaDate = "";'
            'var _cats = ' + _cats_json + ';'
            '(function(){var sel=document.getElementById("qa-cat");'
            '_cats.forEach(function(c){var o=document.createElement("option");o.value=c;o.text=c;sel.appendChild(o);});})();'
            'function openSlot(td) {'
            '  _qaDate = td.getAttribute("data-date");'
            '  var parts = _qaDate.split("-");'
            '  var months=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];'
            '  document.getElementById("qa-date-label").textContent = months[parseInt(parts[1])-1]+" "+parseInt(parts[2])+", "+parts[0];'
            '  document.getElementById("qa-name").value = "";'
            '  document.getElementById("qa-subj").value = "";'
            '  document.getElementById("qa-cat").selectedIndex = 0;'
            '  document.getElementById("qa-ch").selectedIndex = 0;'
            '  document.getElementById("qa-overlay").style.display = "flex";'
            '  setTimeout(function(){document.getElementById("qa-name").focus();}, 80);'
            '}'
            'function closeQa() { document.getElementById("qa-overlay").style.display = "none"; }'
            'function submitQa() {'
            '  var name = document.getElementById("qa-name").value.trim();'
            '  if (!name) { document.getElementById("qa-name").focus(); return; }'
            '  var data = {'
            '    name: name,'
            '    subject: document.getElementById("qa-subj").value.trim(),'
            '    category: document.getElementById("qa-cat").value,'
            '    channel: document.getElementById("qa-ch").value,'
            '    send_date: _qaDate,'
            '    goal: "Conversion"'
            '  };'
            '  var url = new URL(window.top.location.href);'
            '  url.searchParams.set("quick_add", JSON.stringify(data));'
            '  window.top.location.href = url.toString();'
            '}'
            'document.addEventListener("keydown", function(e) {'
            '  if (e.key === "Escape") closeQa();'
            '  if (e.key === "Enter" && document.getElementById("qa-overlay").style.display==="flex") submitQa();'
            '});'
            '</script>'
        )
        # Inject month chip registry as a plain JS variable (no HTML encoding)
        _mor_json = _json.dumps(_mo_reg).replace('</', '<\\/')
        cal_html += (
            f'<script>window._MOR={_mor_json};</script>'
            + QUICK_ADD_HTML
            + f'<style>{QUICK_ADD_CSS}</style>'
            + CAL_MODAL_HTML
            + CAL_MODAL_JS
            + QUICK_ADD_JS
        )

        n_cal_rows = len(_cal_lib.Calendar(firstweekday=6).monthdatescalendar(year, month))
        components.html(
            '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>' + cal_html + '</body></html>',
            height=n_cal_rows * 110 + 145,
            scrolling=False,
        )

        s1, s2, s3 = st.columns(3)
        s1.metric("Sends this month",     n_hist_sends)
        _mo_rev = cal_month["Revenue"].sum() if "Revenue" in cal_month.columns else 0
        _mo_rec = cal_month["Recipients"].sum() if "Recipients" in cal_month.columns else 0
        s2.metric("Revenue this month",   f"${_mo_rev:,.0f}")
        s3.metric("Recipients this month",f"{_mo_rec:,.0f}")

    # ── Timeline (Gantt) View ──────────────────────────────────────────────────
    with cal_sub_timeline:
        # Filters
        tl_f1, tl_f2, tl_f3, tl_f4 = st.columns(4)
        all_cats_list  = sorted(cal_df["Category"].dropna().unique())
        all_prods_list = sorted(cal_df["Primary Product"].dropna().unique()) \
                         if "Primary Product" in cal_df.columns else []
        all_stus_list  = sorted(cal_df["Primary Studio"].dropna().unique()) \
                         if "Primary Studio" in cal_df.columns else []
        all_auds_set   = set()
        if "Audiences" in cal_df.columns:
            for _v in cal_df["Audiences"].dropna():
                for _a in str(_v).split(","):
                    _a = _a.strip()
                    if _a: all_auds_set.add(_a)
        all_auds_list = sorted(all_auds_set)

        sel_tl_cats  = tl_f1.multiselect("Category", all_cats_list,
                                          placeholder="All categories",
                                          label_visibility="collapsed", key="tl_cats")
        sel_tl_prods = tl_f2.multiselect("Product", all_prods_list,
                                          placeholder="All products",
                                          label_visibility="collapsed", key="tl_prods") \
                       if all_prods_list else []
        sel_tl_stus  = tl_f3.multiselect("Studio", all_stus_list,
                                          placeholder="All studios",
                                          label_visibility="collapsed", key="tl_stus") \
                       if all_stus_list else []
        sel_tl_auds  = tl_f4.multiselect("Audience", all_auds_list,
                                          placeholder="All audiences",
                                          label_visibility="collapsed", key="tl_auds") \
                       if all_auds_list else []

        tl_df = cal_df.copy()
        if sel_tl_cats: tl_df = tl_df[tl_df["Category"].isin(sel_tl_cats)]
        if sel_tl_prods and "Primary Product" in tl_df.columns:
            tl_df = tl_df[tl_df["Primary Product"].isin(sel_tl_prods)]
        if sel_tl_stus and "Primary Studio" in tl_df.columns:
            tl_df = tl_df[tl_df["Primary Studio"].isin(sel_tl_stus)]
        if sel_tl_auds and "Audiences" in tl_df.columns:
            tl_df = tl_df[tl_df["Audiences"].apply(
                lambda x: any(_a.strip() in sel_tl_auds for _a in str(x).split(","))
                if pd.notna(x) else False
            )]

        # Date range and weeks
        tl_start = _week_mon(cal_df["Send Date"].min().date())
        # Always show at least 12 weeks ahead from today so planned campaigns are visible
        tl_end   = max(
            _week_mon(cal_df["Send Date"].max().date()) + timedelta(days=13),
            _week_mon(date.today()) + timedelta(weeks=12),
        )
        weeks    = []
        _w = tl_start
        while _w <= tl_end:
            weeks.append(_w)
            _w += timedelta(days=7)

        years_in_range = list(range(tl_start.year, tl_end.year+1))
        us_evts = _us_events(years_in_range)

        def _by_week(df):
            r = {}
            for _, row in df.iterrows():
                wk = _week_mon(row["_date"])
                r.setdefault(wk, []).append(row)
            return r

        # Merge in any user-planned campaigns from Plan tab
        _planned = st.session_state.get("plan_added", [])
        if _planned:
            _plan_rows = []
            for _pc in _planned:
                _plan_rows.append({
                    "Campaign Name": _pc.get("name","Planned Campaign"),
                    "Category":      _pc.get("category",""),
                    "Channel":       _pc.get("channel","email"),
                    "Audiences":     ", ".join(_pc.get("audiences",[])),
                    "Primary Product": _pc.get("product",""),
                    "Primary Studio":  _pc.get("studio",""),
                    "Subject Line":  _pc.get("name",""),
                    "Open Rate": None, "Click Rate": None,
                    "Conversion Rate": None, "Revenue": None,
                    "Recipients": None, "Unsub Rate": None,
                    "_date": _pc.get("send_date", date.today()),
                    "_camp_id": _pc.get("id"),
                })
            _plan_df = pd.DataFrame(_plan_rows)
            _plan_df["Send Date"] = pd.to_datetime(_plan_df["_date"])
            if sel_tl_cats:
                _plan_df = _plan_df[_plan_df["Category"].isin(sel_tl_cats)]
            tl_df = pd.concat([tl_df, _plan_df], ignore_index=True)

        email_wk  = _by_week(tl_df[tl_df["Channel"]=="email"] if "Channel" in tl_df.columns else pd.DataFrame(columns=cal_df.columns))
        sms_wk    = _by_week(tl_df[tl_df["Channel"]=="sms"]   if "Channel" in tl_df.columns else pd.DataFrame(columns=cal_df.columns))
        studio_wk = _by_week(tl_df[tl_df["Category"].isin(["Studio","In-Studio"])] if "Category" in tl_df.columns else pd.DataFrame(columns=cal_df.columns))
        launch_wk = _by_week(cal_df[cal_df["Category"]=="Product Launch"] if "Category" in cal_df.columns else pd.DataFrame(columns=cal_df.columns))
        nso_wk    = _by_week(cal_df[cal_df["Category"]=="NSO"]            if "Category" in cal_df.columns else pd.DataFrame(columns=cal_df.columns))

        us_by_wk = {}
        for _ed, _en in us_evts.items():
            _wk = _week_mon(_ed)
            us_by_wk.setdefault(_wk, []).append((_ed, _en))

        # Month header groups
        mo_groups = []
        _cur_mo, _cnt = None, 0
        for _w in weeks:
            _mo = (_w.year, _w.month)
            if _mo != _cur_mo:
                if _cur_mo: mo_groups.append((_cur_mo, _cnt))
                _cur_mo, _cnt = _mo, 1
            else:
                _cnt += 1
        if _cur_mo: mo_groups.append((_cur_mo, _cnt))

        today_d  = date.today()
        today_wk = _week_mon(today_d)
        n_weeks  = len(weeks)
        TABLE_W  = LABEL_W + n_weeks * WEEK_W

        # Gantt CSS (no f-strings in CSS blocks)
        gantt_css = (
            "* { box-sizing: border-box; margin: 0; padding: 0; }"
            "body { background:#fff; font-family:Barlow,sans-serif; overflow-x:auto; }"
            "table { border-collapse:collapse; table-layout:fixed; width:" + str(TABLE_W) + "px; }"
            "th, td { border:1px solid #E8E8E8; padding:0; vertical-align:top; }"
            ".lbl { width:" + str(LABEL_W) + "px; min-width:" + str(LABEL_W) + "px;"
            " max-width:" + str(LABEL_W) + "px; position:sticky; left:0; z-index:5; background:#fff; }"
            ".wk  { width:" + str(WEEK_W) + "px; min-width:" + str(WEEK_W) + "px; }"
            ".mo-hdr     { background:#1a1a1a; color:#fff; font-family:Barlow,sans-serif;"
            "              font-size:11px; font-weight:600; letter-spacing:0.06em;"
            "              text-transform:uppercase; text-align:center; padding:7px 4px; border-right:1px solid #333; }"
            ".mo-hdr-lbl { background:#1a1a1a; color:#fff; font-family:Barlow,sans-serif;"
            "              font-size:11px; font-weight:600; text-align:left; padding:7px 10px;"
            "              border-right:1px solid #333; letter-spacing:0.04em; text-transform:uppercase; }"
            ".wk-hdr     { background:#f7f7f7; color:#555; font-family:Barlow,sans-serif;"
            "              font-size:10px; font-weight:500; text-align:center; padding:5px 2px; }"
            ".wk-hdr-lbl { background:#f7f7f7; font-size:10px; font-weight:500; color:#888;"
            "              font-family:Barlow,sans-serif; letter-spacing:0.04em;"
            "              text-transform:uppercase; padding:5px 10px; border-right:1px solid #e4e4e4; }"
            ".wk-hdr.now { background:#f5f000; color:#000; font-weight:700; }"
            ".sec-hdr td { background:#f7f7f7; border-top:1px solid #e4e4e4;"
            "              font-family:Barlow,sans-serif; font-size:10px; font-weight:600;"
            "              letter-spacing:0.07em; text-transform:uppercase; color:#888; padding:4px 10px; }"
            ".row-lbl    { font-family:Barlow,sans-serif; font-size:13px; font-weight:500;"
            "              letter-spacing:0.02em; color:#1a1a1a; padding:7px 8px;"
            "              border-right:1px solid #e4e4e4;"
            "              background:#fff; vertical-align:top;"
            "              white-space:normal; word-break:break-word; line-height:1.4; }"
            ".dot        { display:inline-block; width:7px; height:7px; border-radius:50%;"
            "              border:1px solid rgba(0,0,0,0.25); margin-right:4px; vertical-align:middle; }"
            ".cell       { padding:4px 5px; min-height:30px; background:#fff; vertical-align:top; }"
            ".cell.now   { background:#fffff5; }"
            ".cell.empty { background:#fafafa; }"
            ".overflow   { font-size:9px; color:#bbb; padding:1px 4px; }"
            "#modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.45);"
            "                 z-index:500; align-items:flex-start; justify-content:center; padding-top:32px; }"
            "#modal-box  { background:#fff; border:1px solid #E4E4E4; border-radius:10px;"
            "              padding:20px 22px 22px; max-width:440px; width:92%; max-height:78vh;"
            "              overflow-y:auto; position:relative; box-shadow:0 4px 20px rgba(0,0,0,0.10); }"
            ".m-close    { position:absolute; top:10px; right:10px; background:#f0f0f0; color:#444;"
            "              border:none; border-radius:50%; width:26px; height:26px; font-size:13px;"
            "              cursor:pointer; font-weight:600; line-height:26px; text-align:center;"
            "              font-family:Barlow,sans-serif; }"
            ".m-cat      { font-family:Barlow,sans-serif; font-size:10px; font-weight:600;"
            "              letter-spacing:0.08em; text-transform:uppercase; color:#888; margin-bottom:4px; }"
            ".m-name     { font-family:Barlow,sans-serif; font-size:17px; font-weight:700;"
            "              letter-spacing:0.01em; line-height:1.2; color:#000; margin-bottom:6px; }"
            ".m-subj     { font-family:Barlow,sans-serif; font-size:11px; color:#555;"
            "              font-style:italic; margin-bottom:14px; padding-bottom:12px;"
            "              border-bottom:1px solid #E8E8E8; }"
            ".m-meta     { display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px 10px;"
            "              font-family:Barlow,sans-serif; font-size:10px; margin-bottom:14px; }"
            ".m-meta-lbl { font-size:9px; font-weight:600; color:#888; text-transform:uppercase;"
            "              letter-spacing:0.07em; margin-bottom:2px; }"
            ".m-meta-val { font-size:12px; font-weight:600; color:#000; }"
            ".m-metrics  { display:grid; grid-template-columns:repeat(5,1fr); gap:6px; margin-top:14px;"
            "              padding-top:12px; border-top:1px solid #E4E4E4; }"
            ".m-kpi      { background:#f7f7f7; border:1px solid #E4E4E4; border-radius:6px;"
            "              padding:8px 4px; text-align:center; }"
            ".m-kpi-val  { font-family:Barlow,sans-serif; font-size:14px; font-weight:700;"
            "              color:#000; line-height:1.2; }"
            ".m-kpi-lbl  { font-family:Barlow,sans-serif; font-size:9px; font-weight:500; color:#888;"
            "              text-transform:uppercase; letter-spacing:0.07em; margin-top:3px; }"
        )

        # Clear chip registry before this render so indices start from 0
        _CHIP_REG.clear()

        gantt_parts = [
            '<!DOCTYPE html><html><head>'
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800;900'
            '&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">'
            f'<style>{gantt_css}</style>'
            '</head><body><table><thead>'
        ]

        # Month header row
        gantt_parts.append('<tr>')
        gantt_parts.append('<th class="lbl mo-hdr-lbl">Row</th>')
        for (_my, _mm), _cnt in mo_groups:
            _mlbl = date(_my, _mm, 1).strftime("%B %Y").upper()
            gantt_parts.append(f'<th colspan="{_cnt}" class="wk mo-hdr">{_mlbl}</th>')
        gantt_parts.append('</tr>')

        # Week header row
        gantt_parts.append('<tr>')
        gantt_parts.append('<th class="lbl wk-hdr-lbl">Wk →</th>')
        for _w in weeks:
            _nc = " now" if _w == today_wk else ""
            gantt_parts.append(f'<th class="wk wk-hdr{_nc}">{_w.strftime("%-m/%-d")}</th>')
        gantt_parts.append('</tr></thead><tbody>')

        total_cols = n_weeks + 1

        def _sec(label):
            return f'<tr class="sec-hdr"><td colspan="{total_cols}">{label}</td></tr>'

        def _evt_row(label, by_wk, dot_html=""):
            cells = [f'<tr><td class="lbl row-lbl">{dot_html}{label}</td>']
            for _w in weeks:
                _nc = " now" if _w == today_wk else ""
                items = by_wk.get(_w, [])
                c = f'<td class="wk cell{_nc}">'
                for (_ed, _en) in items[:3]:
                    c += _evt_chip(_en, _ed)
                if len(items) > 3:
                    c += f'<div class="overflow">+{len(items)-3}</div>'
                c += '</td>'
                cells.append(c)
            cells.append('</tr>')
            return "".join(cells)

        def _camp_row(label, by_wk, channel="email", empty=False, dot_html="", chip_fn=None):
            cells = [f'<tr><td class="lbl row-lbl">{dot_html}{label}</td>']
            for _w in weeks:
                _nc = " now" if _w == today_wk else ""
                _ec = " empty" if empty else ""
                items = by_wk.get(_w, [])
                c = f'<td class="wk cell{_nc}{_ec}">'
                for ev in items[:4]:
                    if chip_fn:
                        c += chip_fn(ev, ev["_date"])
                    else:
                        c += _chip(ev, ev.get("Category",""), ev["_date"], channel)
                if len(items) > 4:
                    c += f'<div class="overflow">+{len(items)-4}</div>'
                c += '</td>'
                cells.append(c)
            cells.append('</tr>')
            return "".join(cells)

        gantt_parts.append(_sec("MOMENTS"))
        gantt_parts.append(_evt_row("US Events", us_by_wk))
        gantt_parts.append(_camp_row("Product\nLaunches", launch_wk, chip_fn=_launch_chip))
        gantt_parts.append(_camp_row("Store\nOpenings",   nso_wk,    chip_fn=_nso_chip))

        e_dot = '<span class="dot" style="background:#000;"></span>'
        s_dot = '<span class="dot" style="background:#ebc5ff;"></span>'
        gantt_parts.append(_sec("MARKETING PLAN"))
        gantt_parts.append(_camp_row("Email",  email_wk,  "email", dot_html=e_dot))
        gantt_parts.append(_camp_row("SMS",    sms_wk,    "sms",   dot_html=s_dot))
        gantt_parts.append(_camp_row("Paid",   {},        empty=True))
        gantt_parts.append(_camp_row("Studio", studio_wk))

        gantt_parts.append('</tbody></table>')

        MODAL_HTML = (
            '<div id="modal-overlay" onclick="if(event.target===this)closeModal()">'
            '<div id="modal-box">'
            '<button class="m-close" onclick="closeModal()">&#x2715;</button>'
            '<div id="modal-content"></div>'
            '</div></div>'
        )
        MODAL_JS = """
<script>
function showModal(d) {
  if (!d) return;
  var auds = d.audience ? d.audience.split(',').map(function(a){return a.trim();}).filter(Boolean) : [];
  var audCount = auds.length;
  var audPills = auds.map(function(a) {
    return '<span style="display:inline-block;background:#f0f0f0;border:1px solid #ddd;border-radius:3px;' +
           'padding:1px 6px;margin:2px 3px 2px 0;font-size:9px;font-weight:600;white-space:nowrap;">' + a + '</span>';
  }).join('');
  document.getElementById('modal-content').innerHTML =
    '<div class="m-cat">' + d.category + ' &nbsp;&middot;&nbsp; ' + d.send_date + '</div>' +
    '<div class="m-name">' + d.name + '</div>' +
    '<div class="m-subj">&ldquo;' + d.subject + '&rdquo;</div>' +
    '<div class="m-meta">' +
      '<div style="grid-column:1/3">' +
        '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:4px;">' +
          '<span class="m-meta-lbl">Audiences</span>' +
          '<span style="background:#000;color:#feee35;border-radius:50%;width:18px;height:18px;' +
               'display:inline-flex;align-items:center;justify-content:center;' +
               'font-size:9px;font-weight:800;">' + audCount + '</span>' +
        '</div>' +
        '<div class="m-meta-val" style="font-size:10px;line-height:1.8;">' + (audPills || '&mdash;') + '</div>' +
      '</div>' +
      '<div><div class="m-meta-lbl">Product</div><div class="m-meta-val">' + (d.product || '&mdash;') + '</div></div>' +
      '<div><div class="m-meta-lbl">Studio</div><div class="m-meta-val">' + (d.studio || '&mdash;') + '</div></div>' +
    '</div>' +
    '<div class="m-metrics">' +
      '<div class="m-kpi"><div class="m-kpi-val">' + d.sent + '</div><div class="m-kpi-lbl"># Sent</div></div>' +
      '<div class="m-kpi"><div class="m-kpi-val">' + d.open_rate + '</div><div class="m-kpi-lbl">% Open</div></div>' +
      '<div class="m-kpi"><div class="m-kpi-val">' + d.click_rate + '</div><div class="m-kpi-lbl">% Click</div></div>' +
      '<div class="m-kpi"><div class="m-kpi-val">' + d.conv_rate + '</div><div class="m-kpi-lbl">% Convert</div></div>' +
      '<div class="m-kpi"><div class="m-kpi-val" style="font-size:13px;">' + d.revenue + '</div><div class="m-kpi-lbl">Revenue</div></div>' +
    '</div>' +
    (function() {
      var dec = d.decisioning;
      if (!dec) return '';
      function pills(arr) {
        return (arr || []).map(function(x) {
          return '<span style="display:inline-block;background:#f7f7f7;border:1px solid #ddd;' +
                 'border-radius:3px;padding:1px 6px;margin:2px 3px 2px 0;font-size:9px;' +
                 'font-weight:600;">' + x + '</span>';
        }).join('') || '<span style="color:#999;font-size:9px;">—</span>';
      }
      var refs = (dec.refinements || []).map(function(r) {
        return '<div style="font-size:9px;color:#555;font-style:italic;margin:2px 0;">&#8627; ' + r + '</div>';
      }).join('');
      return (
        '<div style="margin-top:10px;border-top:2px solid #000;padding-top:10px;">' +
          '<div style="font-family:Barlow Condensed,sans-serif;font-size:10px;' +
                'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:#000;' +
                'margin-bottom:6px;">Decisioning</div>' +
          '<div style="font-size:9px;font-weight:700;color:#888;text-transform:uppercase;' +
                'letter-spacing:0.06em;margin-top:4px;">Segments (' + (dec.segments||[]).length + ')</div>' +
          '<div>' + pills(dec.segments) + '</div>' +
          refs +
          '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:6px;">' +
            '<div><div style="font-size:9px;font-weight:700;color:#888;text-transform:uppercase;' +
                'letter-spacing:0.06em;">Freq cap</div>' +
              '<div style="font-size:10px;line-height:1.4;">' + (dec.freq_cap || '—') + '</div></div>' +
            '<div><div style="font-size:9px;font-weight:700;color:#888;text-transform:uppercase;' +
                'letter-spacing:0.06em;">Flow priority</div>' +
              '<div style="font-size:10px;line-height:1.4;">' + (dec.flow_priority || '—') + '</div></div>' +
          '</div>' +
          '<div style="font-size:9px;font-weight:700;color:#888;text-transform:uppercase;' +
                'letter-spacing:0.06em;margin-top:8px;">Suppressions</div>' +
          '<div>' + pills(dec.suppressions) + '</div>' +
        '</div>'
      );
    })();
  document.getElementById('modal-overlay').style.display = 'flex';
}
function closeModal() {
  document.getElementById('modal-overlay').style.display = 'none';
}
// Bind clicks directly on every chip element (most reliable across sandbox levels)
function _bindCrChips() {
  var chips = document.querySelectorAll('[data-cid]');
  if (!chips.length || !window._CR) {
    setTimeout(_bindCrChips, 50);
    return;
  }
  chips.forEach(function(el) {
    el.style.cursor = 'pointer';
    el.onclick = function(e) {
      e.stopPropagation();
      var idx = parseInt(el.getAttribute('data-cid'), 10);
      if (!isNaN(idx) && window._CR[idx]) showModal(window._CR[idx]);
    };
  });
}
_bindCrChips();
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeModal(); });
window.addEventListener('load', function() {
  var el = document.querySelector('.wk-hdr.now');
  if (el) { document.documentElement.scrollLeft = el.offsetLeft - 80; }
});
</script>
"""
        # Serialise the chip registry as a plain JS variable — no HTML encoding needed
        _cr_json = _json.dumps(_CHIP_REG).replace('</', '<\\/')
        gantt_parts.append(f'<script>window._CR={_cr_json};</script>')
        gantt_parts.append(MODAL_HTML)
        gantt_parts.append(MODAL_JS)
        gantt_parts.append('</body></html>')
        gantt_full = "".join(gantt_parts)

        # Legend + render
        leg = '<div style="display:flex;gap:5px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">'
        leg += ('<span style="font-size:9px;font-weight:700;letter-spacing:0.08em;'
                'text-transform:uppercase;color:#666;font-family:Barlow,sans-serif;'
                'margin-right:4px;">Color = Day sent:</span>')
        for _nm, _bg in zip(DOW_NAME, DOW_BG):
            leg += (f'<span style="background:{_bg};color:#000;border:1.5px solid rgba(0,0,0,0.2);'
                    f'border-radius:3px;padding:1px 7px;font-size:9px;font-weight:600;'
                    f'font-family:Barlow,sans-serif;">{_nm}</span>')
        leg += '</div>'
        st.markdown(leg, unsafe_allow_html=True)
        components.html(gantt_full, height=680, scrolling=True)

    # ── Review Section (below Month + Timeline tabs) ───────────────────────────
    st.divider()

    today_d   = date.today()
    cutoff_30 = today_d - timedelta(days=30)
    cutoff_90 = today_d - timedelta(days=90)

    # ── Helper: card renderer ─────────────────────────────────────────────────
    def _card(title, body, accent="#000"):
        return (
            f'<div style="border:2px solid #000;border-radius:10px;padding:14px 16px;'
            f'background:#fff;min-height:230px;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
            f'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:#000;'
            f'padding-bottom:8px;border-bottom:2px solid {accent};margin-bottom:10px;">{title}</div>'
            f'<div style="font-family:Barlow,sans-serif;font-size:11px;line-height:1.5;">{body}</div>'
            f'</div>'
        )

    def _delta(val, fmt="pct", good="up"):
        """Return coloured delta HTML. fmt: 'pct'|'rev'|'int'. good: 'up'|'down'"""
        if val is None: return '<span style="color:#aaa;">n/a</span>'
        pos = val >= 0
        col = ("#2ECC71" if pos else "#D0021B") if good == "up" else ("#D0021B" if pos else "#2ECC71")
        arrow = "↑" if pos else "↓"
        if fmt == "pct":
            s = f"{abs(val):.1%}"
        elif fmt == "rev":
            s = f"${abs(val)/1e3:.1f}K"
        else:
            s = str(abs(int(val)))
        return f'<span style="color:{col};font-weight:700;">{arrow}{s}</span>'

    # ── A: This Month vs Last Month ───────────────────────────────────────────
    cal_df_mo = cal_df.copy()
    cal_df_mo["_ym"] = cal_df_mo["Send Date"].dt.to_period("M")
    this_mo = cal_df_mo[cal_df_mo["_ym"] == pd.Period(today_d, "M")]
    last_mo = cal_df_mo[cal_df_mo["_ym"] == pd.Period(today_d - timedelta(days=today_d.day), "M")]

    def _mo_stats(df):
        ch_col = df["Channel"].str.lower() if "Channel" in df.columns else pd.Series([], dtype=str)
        return {
            "email":  int((ch_col == "email").sum()),
            "sms":    int((ch_col == "sms").sum()),
            "total":  len(df),
            "open":   df["Open Rate"].mean()        if "Open Rate"        in df.columns else None,
            "conv":   df["Conversion Rate"].mean()  if "Conversion Rate"  in df.columns else None,
            "unsub":  df["Unsub Rate"].mean()       if "Unsub Rate"       in df.columns else None,
            "rev":    df["Revenue"].sum()            if "Revenue"          in df.columns else 0,
        }

    tm = _mo_stats(this_mo)
    lm = _mo_stats(last_mo)
    this_mo_name = today_d.strftime("%B")
    last_mo_name = (today_d.replace(day=1) - timedelta(days=1)).strftime("%B")

    def _row(label, this_v, last_v, fmt="pct", good="up", suffix=""):
        this_s = (f"{this_v:.1%}" if fmt == "pct" else f"${this_v/1e3:.1f}K" if fmt == "rev" else str(int(this_v) if this_v else 0)) + suffix
        d = _delta((this_v - last_v) if (this_v is not None and last_v is not None) else None, fmt=fmt, good=good)
        lv = (f"{last_v:.1%}" if fmt == "pct" else f"${last_v/1e3:.1f}K" if fmt == "rev" else str(int(last_v) if last_v else 0)) + suffix if last_v is not None else "—"
        return (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:4px 0;border-bottom:1px solid #f2f2f2;">'
            f'<span style="color:#555;font-size:11px;">{label}</span>'
            f'<span style="display:flex;gap:8px;align-items:center;">'
            f'<span style="font-weight:700;font-size:12px;">{this_s}</span>'
            f'<span style="font-size:10px;color:#999;">{lv}</span>'
            f'{d}'
            f'</span></div>'
        )

    mo_body = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 16px;'
        f'margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #eee;">'
        f'<div style="font-size:10px;color:#888;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;">{this_mo_name}</div>'
        f'<div style="font-size:10px;color:#bbb;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;">{last_mo_name}</div>'
        f'<div style="font-size:22px;font-weight:900;">{tm["total"]}</div>'
        f'<div style="font-size:22px;font-weight:900;color:#bbb;">{lm["total"]}</div>'
        f'<div style="font-size:10px;color:#666;">{tm["email"]} email · {tm["sms"]} SMS</div>'
        f'<div style="font-size:10px;color:#bbb;">{lm["email"]} email · {lm["sms"]} SMS</div>'
        f'</div>'
        + _row("Open rate",   tm["open"],  lm["open"],  fmt="pct", good="up")
        + _row("Conv rate",   tm["conv"],  lm["conv"],  fmt="pct", good="up")
        + _row("Unsub rate",  tm["unsub"], lm["unsub"], fmt="pct", good="down")
        + _row("Revenue",     tm["rev"],   lm["rev"],   fmt="rev", good="up")
    )

    # ── B: Next 30 Days ───────────────────────────────────────────────────────
    upcoming_30_hist = cal_df[(cal_df["_date"] > today_d) & (cal_df["_date"] <= today_d + timedelta(days=30))].copy()
    upcoming_30_hist = upcoming_30_hist.sort_values("_date")
    planned_30 = [p for p in st.session_state.get("plan_added", [])
                  if today_d < p.get("send_date", today_d) <= today_d + timedelta(days=30)]
    planned_30.sort(key=lambda p: p.get("send_date", today_d))
    n30_email = int((upcoming_30_hist["Channel"].str.lower() == "email").sum()) + \
                sum(1 for p in planned_30 if p.get("channel","") == "email")
    n30_sms   = int((upcoming_30_hist["Channel"].str.lower() == "sms").sum()) + \
                sum(1 for p in planned_30 if p.get("channel","") == "sms")
    up30_rows = ""
    shown = 0
    for _, row in upcoming_30_hist.head(6).iterrows():
        ch = str(row.get("Channel","")).lower()
        chip_bg  = "#1a1a1a" if ch == "email" else "#e8c5ff"
        chip_col = "#fff"    if ch == "email" else "#000"
        chip_lbl = "EM"      if ch == "email" else "SMS"
        nm = _clean(row.get("Campaign Name",""))[:28]
        up30_rows += (
            f'<div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid #f2f2f2;">'
            f'<span style="font-size:9px;color:#888;white-space:nowrap;min-width:34px;">'
            f'{row["_date"].strftime("%-m/%-d")}</span>'
            f'<span style="background:{chip_bg};color:{chip_col};border-radius:3px;'
            f'padding:1px 4px;font-size:8px;font-weight:700;min-width:24px;text-align:center;">{chip_lbl}</span>'
            f'<span style="font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{nm}</span>'
            f'</div>'
        )
        shown += 1
    for p in planned_30[:max(0, 6 - shown)]:
        sd = p.get("send_date", today_d)
        ch = p.get("channel","email").lower()
        chip_bg  = "#caf30b" if True else ""  # planned = lime
        up30_rows += (
            f'<div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid #f2f2f2;">'
            f'<span style="font-size:9px;color:#888;white-space:nowrap;min-width:34px;">'
            f'{sd.strftime("%-m/%-d")}</span>'
            f'<span style="background:#caf30b;color:#000;border-radius:3px;'
            f'padding:1px 4px;font-size:8px;font-weight:700;min-width:24px;text-align:center;">PLAN</span>'
            f'<span style="font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
            f'{p.get("name","Planned")[:28]}</span>'
            f'</div>'
        )
    total_30 = len(upcoming_30_hist) + len(planned_30)
    up30_header = (
        f'<div style="display:flex;gap:12px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #eee;">'
        f'<div><span style="font-size:20px;font-weight:900;">{total_30}</span>'
        f'<span style="font-size:10px;color:#888;margin-left:4px;">sends</span></div>'
        f'<div style="font-size:10px;color:#666;align-self:flex-end;padding-bottom:2px;">'
        f'{n30_email} email · {n30_sms} SMS</div>'
        f'</div>'
    )
    if not up30_rows:
        up30_rows = '<span style="color:#aaa;font-size:11px;">No campaigns scheduled in next 30 days</span>'

    # ── C: vs Same Period Last Year ───────────────────────────────────────────
    cal_df_yr = cal_df.copy()
    cal_df_yr["_year"]  = cal_df_yr["Send Date"].dt.year
    cal_df_yr["_month"] = cal_df_yr["Send Date"].dt.month
    yr_agg = cal_df_yr.groupby(["_year","_month"]).agg(
        sends      = ("Campaign Name","count"),
        email_n    = ("Channel", lambda x: (x.str.lower()=="email").sum()),
        sms_n      = ("Channel", lambda x: (x.str.lower()=="sms").sum()),
        open_rate  = ("Open Rate","mean"),
        conv_rate  = ("Conversion Rate","mean"),
        unsub_rate = ("Unsub Rate","mean"),
        revenue    = ("Revenue","sum"),
    ).reset_index()
    this_yr = yr_agg[yr_agg["_year"]==2026].set_index("_month")
    last_yr = yr_agg[yr_agg["_year"]==2025].set_index("_month")
    common_months = sorted(set(this_yr.index) & set(last_yr.index))
    if common_months:
        def _yoy(col):
            try:
                a = this_yr.loc[common_months, col].mean()
                b = last_yr.loc[common_months, col].mean()
                return (a - b, a, b)
            except Exception:
                return (None, None, None)
        yoy_s_d, yoy_s_a, yoy_s_b = (
            sum(this_yr.loc[m,"sends"] for m in common_months) - sum(last_yr.loc[m,"sends"] for m in common_months),
            sum(this_yr.loc[m,"sends"] for m in common_months),
            sum(last_yr.loc[m,"sends"] for m in common_months),
        )
        yoy_r_d = sum(this_yr.loc[m,"revenue"] for m in common_months) - sum(last_yr.loc[m,"revenue"] for m in common_months)
        yoy_op_d, yoy_op_a, _ = _yoy("open_rate")
        yoy_cv_d, yoy_cv_a, _ = _yoy("conv_rate")
        yoy_us_d, yoy_us_a, _ = _yoy("unsub_rate")
        mo_range = f"{date(2026,common_months[0],1).strftime('%b')}–{date(2026,common_months[-1],1).strftime('%b')}"
        yoy_body = (
            f'<div style="font-size:9px;color:#888;margin-bottom:8px;">Comparing {mo_range} 2026 vs 2025</div>'
            + _row("Sends",      yoy_s_a,  yoy_s_b,  fmt="int", good="up")
            + _row("Open rate",  yoy_op_a, yoy_op_a - yoy_op_d if yoy_op_d else yoy_op_a, fmt="pct", good="up")
            + _row("Conv rate",  yoy_cv_a, yoy_cv_a - yoy_cv_d if yoy_cv_d else yoy_cv_a, fmt="pct", good="up")
            + _row("Unsub rate", yoy_us_a, yoy_us_a - yoy_us_d if yoy_us_d else yoy_us_a, fmt="pct", good="down")
        )
        rev_arrow = "↑" if yoy_r_d >= 0 else "↓"
        rev_col   = "#2ECC71" if yoy_r_d >= 0 else "#D0021B"
        yoy_body += (
            f'<div style="margin-top:10px;padding:8px;background:#f7f7f7;border-radius:6px;'
            f'display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-size:10px;color:#555;font-weight:600;">Revenue YoY</span>'
            f'<span style="font-weight:800;font-size:13px;color:{rev_col};">'
            f'{rev_arrow}${abs(yoy_r_d)/1e3:.1f}K</span>'
            f'</div>'
        )
    else:
        yoy_body = '<span style="color:#aaa;font-size:11px;">No overlapping months in dataset</span>'

    # ── D: Calendar Gaps ──────────────────────────────────────────────────────
    us_evts_all = _us_events([today_d.year, today_d.year+1])
    future_evts = {d: n for d, n in us_evts_all.items()
                   if today_d < d <= today_d + timedelta(days=90)}
    all_send_dates = set(cal_df["_date"])
    gaps = []
    for _ed, _en in sorted(future_evts.items()):
        _win = _ed - timedelta(days=14)
        if not any(_win <= _d <= _ed for _d in all_send_dates):
            gaps.append((_ed, _en))
    gaps_html = ""
    for _ed, _en in gaps[:5]:
        _days_away = (_ed - today_d).days
        gaps_html += (
            f'<div style="background:#fff9db;border-left:3px solid #F5A623;'
            f'padding:5px 8px;margin-bottom:6px;border-radius:0 4px 4px 0;">'
            f'<div style="font-weight:700;font-size:11px;">{_en}'
            f' <span style="color:#888;font-weight:400;">— {_ed.strftime("%b %-d")} '
            f'({_days_away}d away)</span></div>'
            f'<div style="color:#888;font-size:10px;">No send in the 14d window</div>'
            f'</div>'
        )
    if not gaps:
        gaps_html = '<span style="color:#2ECC71;font-size:12px;">All moments have planned sends ✓</span>'

    # ── E: Segment Overlap Frequency ──────────────────────────────────────────
    # Parse audiences (comma-separated) per campaign, group by week,
    # detect weeks where ≥2 campaigns share an audience vs fully distinct segments.
    def _parse_aud_set(v):
        if pd.isna(v) or str(v).strip() == "":
            return frozenset()
        return frozenset(a.strip().lower() for a in str(v).split(",") if a.strip())

    cal_df_seg = cal_df.copy()
    cal_df_seg["_week"]    = cal_df_seg["_date"].apply(lambda d: d.isocalendar()[:2])
    cal_df_seg["_aud_set"] = (cal_df_seg["Audiences"].apply(_parse_aud_set)
                               if "Audiences" in cal_df_seg.columns
                               else [frozenset()] * len(cal_df_seg))

    # Per week: classify as overlap (any two campaigns share ≥1 audience) or distinct
    overlap_weeks_set, overlap_segs_ctr = set(), {}
    for wk, grp in cal_df_seg.groupby("_week"):
        aud_list = list(grp["_aud_set"])
        names    = list(grp.get("Campaign Name", grp.index))
        for i in range(len(aud_list)):
            for j in range(i + 1, len(aud_list)):
                shared = aud_list[i] & aud_list[j]
                if shared:
                    overlap_weeks_set.add(wk)
                    for seg in shared:
                        overlap_segs_ctr[seg] = overlap_segs_ctr.get(seg, 0) + 1

    cal_df_seg["_in_overlap_wk"] = cal_df_seg["_week"].isin(overlap_weeks_set)

    # Aggregate unsub + conv for overlap-week sends vs distinct-week sends
    seg_agg = cal_df_seg.groupby("_in_overlap_wk").agg(
        n_sends   = ("Campaign Name", "count"),
        n_weeks   = ("_week",         "nunique"),
        avg_unsub = ("Unsub Rate",    "mean"),
        avg_conv  = ("Conversion Rate","mean"),
    ).reset_index()

    def _seg_stat_row(label, flag_val, bg="#fff"):
        row = seg_agg[seg_agg["_in_overlap_wk"] == flag_val]
        if row.empty:
            return f'<div style="padding:6px 8px;background:{bg};border-radius:5px;margin-bottom:5px;">' \
                   f'<span style="font-size:10px;font-weight:700;">{label}</span> ' \
                   f'<span style="font-size:10px;color:#aaa;">No data</span></div>'
        r = row.iloc[0]
        unsub_col = "#D0021B" if r["avg_unsub"] > 0.003 else "#2ECC71"
        conv_col  = "#2ECC71" if r["avg_conv"]  > 0.01  else "#888"
        return (
            f'<div style="padding:7px 8px;background:{bg};border-radius:5px;margin-bottom:5px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;">'
            f'<span style="font-size:10px;font-weight:700;color:#000;">{label}</span>'
            f'<span style="font-size:9px;color:#888;">{int(r["n_weeks"])} wks · {int(r["n_sends"])} sends</span>'
            f'</div>'
            f'<div style="display:flex;gap:12px;margin-top:3px;">'
            f'<span style="font-size:11px;">Unsub <b style="color:{unsub_col};">{r["avg_unsub"]:.3%}</b></span>'
            f'<span style="font-size:11px;">Conv <b style="color:{conv_col};">{r["avg_conv"]:.2%}</b></span>'
            f'</div>'
            f'</div>'
        )

    seg_body  = _seg_stat_row("Overlapping segments",  True,  bg="#fff5f5")
    seg_body += _seg_stat_row("Distinct segments",      False, bg="#f5fff8")

    # Most-doubled segments
    if overlap_segs_ctr:
        top_overlap = sorted(overlap_segs_ctr.items(), key=lambda x: -x[1])[:4]
        seg_body += (
            '<div style="margin-top:8px;padding-top:8px;border-top:1px solid #eee;">'
            '<div style="font-size:9px;font-weight:700;text-transform:uppercase;'
            'letter-spacing:0.07em;color:#888;margin-bottom:4px;">Most overlapping segments</div>'
        )
        for seg, cnt in top_overlap:
            seg_body += (
                f'<div style="display:flex;justify-content:space-between;'
                f'padding:2px 0;font-size:10px;">'
                f'<span style="color:#333;">{seg.title()}</span>'
                f'<span style="font-weight:700;color:#D0021B;">{cnt}× overlap</span>'
                f'</div>'
            )
        seg_body += '</div>'

    # ── F: Top Category Opportunities (90d) ──────────────────────────────────
    recent_cats_90 = set(cal_df[cal_df["_date"] >= cutoff_90]["Category"].dropna())
    cat_conv       = cal_df.groupby("Category")["Conversion Rate"].mean().sort_values(ascending=False)
    top_missing    = [(cat, rate) for cat, rate in cat_conv.items() if cat not in recent_cats_90][:5]
    opp_body = (
        '<div style="font-size:9px;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.07em;color:#888;margin-bottom:6px;">Not used in 90 days</div>'
    )
    for cat, rate in top_missing:
        code = CATEGORY_CODES.get(cat, cat[:3].upper())
        opp_body += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:4px 0;border-bottom:1px solid #f2f2f2;">'
            f'<span><span style="background:#feee35;padding:1px 5px;border-radius:3px;'
            f'font-size:9px;font-weight:700;margin-right:5px;">{code}</span>'
            f'<span style="font-size:11px;">{cat}</span></span>'
            f'<span style="font-weight:700;color:#2ECC71;font-size:11px;">{rate:.2%} conv</span>'
            f'</div>'
        )
    if not top_missing:
        opp_body += '<span style="color:#2ECC71;font-size:11px;">All top categories active ✓</span>'

    # ── G: Product & Studio Opportunities (90d) ───────────────────────────────
    recent_df_90 = cal_df[cal_df["_date"] >= cutoff_90]
    prod_opp_body = ""

    # Products not featured in 90 days
    if "Primary Product" in cal_df.columns:
        all_prods_ever   = set(cal_df["Primary Product"].dropna().unique())
        recent_prods_90  = set(recent_df_90["Primary Product"].dropna().unique()) \
                           if "Primary Product" in recent_df_90.columns else set()
        missing_prods    = sorted(all_prods_ever - recent_prods_90)
        # rank by historic avg conv
        prod_conv = (cal_df.groupby("Primary Product")["Conversion Rate"].mean()
                     .sort_values(ascending=False))
        missing_prods_ranked = [p for p in prod_conv.index if p in set(missing_prods)]
        other_missing_prods  = [p for p in missing_prods if p not in set(missing_prods_ranked)]
        missing_prods_final  = (missing_prods_ranked + other_missing_prods)[:6]
    else:
        missing_prods_final = []

    # Studios not featured in 90 days
    if "Primary Studio" in cal_df.columns:
        all_stus_ever   = set(cal_df["Primary Studio"].dropna().unique())
        recent_stus_90  = set(recent_df_90["Primary Studio"].dropna().unique()) \
                          if "Primary Studio" in recent_df_90.columns else set()
        missing_stus    = sorted(all_stus_ever - recent_stus_90)
    else:
        missing_stus = []

    prod_opp_body += (
        '<div style="font-size:9px;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.07em;color:#888;margin-bottom:5px;">Products (90d)</div>'
    )
    if missing_prods_final:
        for _p in missing_prods_final:
            _pc = prod_conv.get(_p, None) if "Primary Product" in cal_df.columns else None
            _pc_str = f'<span style="font-weight:700;color:#2ECC71;font-size:10px;">{_pc:.2%}</span>' if _pc else ""
            prod_opp_body += (
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:3px 0;border-bottom:1px solid #f5f5f5;">'
                f'<span style="font-size:10px;color:#333;">{_p}</span>{_pc_str}</div>'
            )
        _n_more_p = len(missing_prods_final) - 6
        if _n_more_p > 0:
            prod_opp_body += f'<span style="color:#999;font-size:10px;">+{_n_more_p} more</span>'
    else:
        prod_opp_body += '<span style="color:#2ECC71;font-size:10px;">All products featured ✓</span>'

    prod_opp_body += (
        '<div style="margin-top:10px;padding-top:7px;border-top:1px solid #eee;">'
        '<div style="font-size:9px;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.07em;color:#888;margin-bottom:5px;">Studios (90d)</div>'
    )
    if missing_stus:
        for _s in missing_stus[:6]:
            prod_opp_body += (
                f'<span style="display:inline-block;background:#f0f0ff;border:1px solid #c0c0e0;'
                f'border-radius:3px;padding:2px 7px;margin:2px 2px 2px 0;'
                f'font-size:10px;font-weight:600;">{_s}</span>'
            )
        if len(missing_stus) > 6:
            prod_opp_body += f'<span style="color:#999;font-size:10px;margin-left:4px;">+{len(missing_stus)-6} more</span>'
    else:
        prod_opp_body += '<span style="color:#2ECC71;font-size:10px;">All studios active ✓</span>'
    prod_opp_body += '</div>'

    # ── Render row 1: 2 cards (Activity) ─────────────────────────────────────
    st.markdown(
        '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
        'font-weight:800;letter-spacing:0.12em;text-transform:uppercase;'
        'color:#888;margin:4px 0 8px;">Activity — What\'s happened &amp; what\'s coming</div>',
        unsafe_allow_html=True,
    )
    rv1, rv2 = st.columns(2)
    rv1.markdown(_card("Next 30 Days",             up30_header + up30_rows), unsafe_allow_html=True)
    rv2.markdown(_card("vs Same Period Last Year",  yoy_body),                unsafe_allow_html=True)

    # ── Render row 2: 4 cards (Highlights) ───────────────────────────────────
    st.markdown(
        '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
        'font-weight:800;letter-spacing:0.12em;text-transform:uppercase;'
        'color:#888;margin:14px 0 8px;">Highlights — Gaps &amp; risks</div>',
        unsafe_allow_html=True,
    )
    rv3, rv4, rv5, rv6 = st.columns(4)
    rv3.markdown(_card("Calendar Gaps",                  gaps_html),    unsafe_allow_html=True)
    rv4.markdown(_card("Send Frequency by Segment",      seg_body),     unsafe_allow_html=True)
    rv5.markdown(_card("Top Category Opportunities",     opp_body),     unsafe_allow_html=True)
    rv6.markdown(_card("Product & Studio Opportunities", prod_opp_body),unsafe_allow_html=True)

    # ── Data connections ────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
        'font-weight:800;letter-spacing:0.12em;text-transform:uppercase;'
        'color:#888;margin:24px 0 8px;">Data connections</div>',
        unsafe_allow_html=True,
    )
    st.markdown(_conn_html, unsafe_allow_html=True)

    # ── Calendar Discussion ──────────────────────────────────────────────────
    # Session state for reply targeting
    if "_cm_reply_to_id"     not in st.session_state: st.session_state["_cm_reply_to_id"]     = ""
    if "_cm_reply_to_author" not in st.session_state: st.session_state["_cm_reply_to_author"] = ""

    _disc_hdr, _disc_toggle = st.columns([3, 1])
    with _disc_hdr:
        st.markdown(
            '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
            'font-weight:800;letter-spacing:0.12em;text-transform:uppercase;'
            'color:#888;margin:28px 0 4px;">Calendar discussion</div>',
            unsafe_allow_html=True,
        )
    with _disc_toggle:
        _show_resolved = st.checkbox("Show resolved", value=False, key="cm_show_resolved")

    # Load comments (cached 30 s, persists across sessions via Sheets)
    _all_comments    = _fetch_comments()
    _active_comments = (
        _all_comments if _show_resolved
        else [c for c in _all_comments if not c.get("resolved", "").strip()]
    )
    _resolved_count  = sum(1 for c in _all_comments if c.get("resolved", "").strip())
    # Build id → author lookup for showing parent author in reply threads
    _cm_id_to_author = {c["id"]: c.get("author", "someone") for c in _all_comments}

    # ── Thread display ───────────────────────────────────────────────────────
    _av_colors = ["#caf30b", "#e8c5ff", "#f5f000", "#b3e5fc", "#ffd0b0", "#d0f0c0"]

    if not _active_comments:
        _empty_msg = (
            "No comments yet — start the conversation below"
            if not _all_comments
            else f"All {_resolved_count} comment(s) resolved"
        )
        st.markdown(
            f'<div style="text-align:center;color:#bbb;font-family:Barlow,sans-serif;'
            f'font-size:13px;padding:32px 0;border:1.5px solid #e8e8e8;border-radius:10px;'
            f'background:#fafafa;">{_empty_msg}</div>',
            unsafe_allow_html=True,
        )
    else:
        for _i, _cm in enumerate(_active_comments):
            _is_resolved  = bool(_cm.get("resolved", "").strip())
            _reply_to_id  = _cm.get("reply_to", "").strip()
            _is_reply     = bool(_reply_to_id)
            _initials     = "".join(w[0].upper() for w in _cm["author"].split()[:2]) if _cm.get("author") else "?"
            _av_bg        = _av_colors[hash(_cm.get("author", "")) % len(_av_colors)]
            _ts_raw       = _cm.get("timestamp", "")
            try:
                _ts_str = _datetime.fromisoformat(_ts_raw).strftime("%-d %b %Y · %H:%M")
            except Exception:
                _ts_str = _ts_raw[:16] if _ts_raw else ""

            _border_top = "border-top:1px solid #efefef;" if _i > 0 else ""
            _bg         = "background:#f5fff8;" if _is_resolved else ("background:#f8f4ff;" if _is_reply else "background:#fafafa;")
            _indent_ml  = "margin-left:24px;" if _is_reply else ""

            # Reply-to attribution line
            _reply_attr = ""
            if _is_reply:
                _parent_author = _cm_id_to_author.get(_reply_to_id, "someone")
                _reply_attr = (
                    f'<div style="font-family:Barlow,sans-serif;font-size:10px;color:#999;'
                    f'margin-bottom:3px;">↩ replying to <b>{_parent_author}</b></div>'
                )

            # Row: text | reply btn | resolve btn
            _row_left, _row_reply, _row_resolve = st.columns([10, 1, 1])
            with _row_left:
                st.markdown(
                    f'<div style="{_border_top}{_bg}{_indent_ml}padding:10px 14px;'
                    f'display:flex;gap:10px;align-items:flex-start;">'
                    f'<div style="flex-shrink:0;width:28px;height:28px;border-radius:50%;'
                    f'background:{_av_bg};color:#000;display:flex;align-items:center;'
                    f'justify-content:center;font-family:\'Barlow Condensed\',sans-serif;'
                    f'font-size:11px;font-weight:900;">{_initials}</div>'
                    f'<div style="flex:1;">'
                    f'{_reply_attr}'
                    f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:2px;">'
                    f'<span style="font-family:Barlow,sans-serif;font-size:12px;font-weight:700;color:#000;">'
                    f'{_cm.get("author","Anonymous")}</span>'
                    f'<span style="font-family:Barlow,sans-serif;font-size:10px;color:#aaa;">{_ts_str}</span>'
                    + (f'<span style="font-size:9px;background:#e8f8ed;color:#2ECC71;border-radius:3px;'
                       f'padding:1px 5px;font-weight:700;">Resolved</span>' if _is_resolved else '')
                    + f'</div>'
                    f'<div style="font-family:Barlow,sans-serif;font-size:13px;color:#333;line-height:1.5;">'
                    f'{_cm.get("text","")}</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with _row_reply:
                if not _is_resolved:
                    st.markdown('<div style="padding-top:8px;">', unsafe_allow_html=True)
                    if st.button("↩", key=f"cm_reply_{_cm['id']}", help=f"Reply to {_cm.get('author','')}"):
                        st.session_state["_cm_reply_to_id"]     = _cm["id"]
                        st.session_state["_cm_reply_to_author"] = _cm.get("author", "someone")
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
            with _row_resolve:
                if not _is_resolved:
                    st.markdown('<div style="padding-top:8px;">', unsafe_allow_html=True)
                    if st.button("✓", key=f"cm_resolve_{_cm['id']}", help="Mark as resolved"):
                        if _SHEETS_ENABLED and _sheets_resolve_comment:
                            try:
                                _sheets_resolve_comment(_cm["id"])
                                # Clear reply target if we just resolved the parent
                                if st.session_state.get("_cm_reply_to_id") == _cm["id"]:
                                    st.session_state["_cm_reply_to_id"]     = ""
                                    st.session_state["_cm_reply_to_author"] = ""
                                _invalidate_comments_cache()
                                st.toast("Comment resolved", icon="✅")
                                st.rerun()
                            except Exception as _re:
                                st.error(f"Could not resolve: {_re}")
                    st.markdown('</div>', unsafe_allow_html=True)

    if _resolved_count and not _show_resolved:
        st.markdown(
            f'<div style="font-family:Barlow,sans-serif;font-size:11px;color:#aaa;'
            f'margin-top:4px;">{_resolved_count} resolved comment(s) hidden</div>',
            unsafe_allow_html=True,
        )

    # ── Reply banner ─────────────────────────────────────────────────────────
    st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
    _replying_to_id     = st.session_state.get("_cm_reply_to_id", "")
    _replying_to_author = st.session_state.get("_cm_reply_to_author", "")
    if _replying_to_id:
        _rb_col, _rx_col = st.columns([10, 1])
        with _rb_col:
            st.markdown(
                f'<div style="background:#f0ebff;border-left:3px solid #a080c0;'
                f'border-radius:0 6px 6px 0;padding:6px 12px;font-family:Barlow,sans-serif;'
                f'font-size:12px;color:#555;">↩ Replying to <b>{_replying_to_author}</b></div>',
                unsafe_allow_html=True,
            )
        with _rx_col:
            if st.button("✕", key="cm_cancel_reply", help="Cancel reply"):
                st.session_state["_cm_reply_to_id"]     = ""
                st.session_state["_cm_reply_to_author"] = ""
                st.rerun()

    # ── Post form ─────────────────────────────────────────────────────────────
    _cc1, _cc2 = st.columns([1, 3])
    with _cc1:
        _cm_author = st.text_input(
            "Your name",
            value=st.session_state.get("_cm_author_saved", ""),
            placeholder="Name",
            key="cm_author_input",
            label_visibility="collapsed",
        )
    with _cc2:
        _placeholder = f"Reply to {_replying_to_author}…" if _replying_to_id else "Add a comment…"
        _cm_text = st.text_input(
            "Comment",
            placeholder=_placeholder,
            key="cm_text_input",
            label_visibility="collapsed",
        )

    _post_col, _refresh_col, _ = st.columns([1, 1, 5])
    with _post_col:
        if st.button("Post", key="cm_post_btn", use_container_width=True):
            _cm_author_v = _cm_author.strip()
            _cm_text_v   = _cm_text.strip()
            if not _cm_author_v:
                st.warning("Please enter your name before posting.")
            elif not _cm_text_v:
                st.warning("Comment cannot be empty.")
            else:
                st.session_state["_cm_author_saved"] = _cm_author_v
                _new_comment = {
                    "id":        f"C{_datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}",
                    "author":    _cm_author_v,
                    "text":      _cm_text_v,
                    "timestamp": _datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "reply_to":  st.session_state.get("_cm_reply_to_id", ""),
                }
                if _SHEETS_ENABLED and _sheets_post_comment:
                    try:
                        _sheets_post_comment(_new_comment)
                        _invalidate_comments_cache()
                        # Clear reply state after posting
                        st.session_state["_cm_reply_to_id"]     = ""
                        st.session_state["_cm_reply_to_author"] = ""
                        st.toast(f"Comment posted by {_cm_author_v}", icon="💬")
                        st.rerun()
                    except Exception as _ce:
                        st.error(f"Could not save comment: {_ce}")
                else:
                    st.info("Sheets not connected — comment not saved permanently.")
    with _refresh_col:
        if st.button("↻ Refresh", key="cm_refresh_btn", use_container_width=True):
            _invalidate_comments_cache()
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# UPCOMING & DRAFT CAMPAIGNS TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_upcoming:
    st.markdown("<h2>Upcoming & Draft Campaigns</h2>", unsafe_allow_html=True)

    _GOAL_OPTIONS    = ["Awareness", "Conversion", "Flash Sale", "Launch",
                        "Re-engagement", "Retention"]
    _CHANNEL_OPTIONS = ["email", "sms"]

    # ── Sheet sync helper ─────────────────────────────────────────────────────
    def _do_sheet_sync(show_toast=False):
        """Pull latest from sheet → update session state. Returns True on success."""
        _planned, _drafts, _err = _fetch_sheet_campaigns()
        if _err:
            st.session_state["_sheet_sync_error"] = _err
            return False
        if _planned is None:
            return False  # sheets not configured
        st.session_state["plan_added"]  = _planned
        st.session_state["plan_drafts"] = _drafts
        st.session_state["_last_sheet_sync"] = date.today()
        st.session_state["_sheet_sync_error"] = None
        # Restore decisioning state for newly loaded campaigns
        for _sc in _planned + _drafts:
            _did = _sc.get("id")
            if _did and "decisioning" in _sc:
                if "decisioning_state" not in st.session_state:
                    st.session_state["decisioning_state"] = {}
                if _did not in st.session_state["decisioning_state"]:
                    st.session_state["decisioning_state"][_did] = _sc["decisioning"]
        if show_toast:
            st.toast("Synced from Google Sheets ✓", icon="🔄")
        return True

    # Auto-sync on first render of this tab, then rerun so data is visible
    if st.session_state.get("_last_sheet_sync") is None:
        if _do_sheet_sync():
            st.rerun()

    # ── Sync status bar ───────────────────────────────────────────────────────
    _sync_err = st.session_state.get("_sheet_sync_error")
    _sync_bar_left, _sync_bar_right = st.columns([5, 1])
    if _sync_err:
        _sync_bar_left.error(f"Sheet sync error: {_sync_err}")
    elif _SHEETS_ENABLED:
        _last_str = (st.session_state["_last_sheet_sync"].strftime("%b %-d")
                     if st.session_state.get("_last_sheet_sync") else "never")
        _sync_bar_left.markdown(
            f'<div style="font-size:11px;color:#999;padding:4px 0;">'
            f'Connected to Google Sheets · Last synced {_last_str}</div>',
            unsafe_allow_html=True,
        )
    else:
        _sync_bar_left.warning("Google Sheets not connected — check logs for import error")
        _sync_bar_left.markdown(
            '<div style="font-size:11px;color:#bbb;padding:4px 0;">Google Sheets not connected</div>',
            unsafe_allow_html=True,
        )
    if _SHEETS_ENABLED and _sync_bar_right.button("↻ Sync", use_container_width=True):
        _invalidate_sheet_cache()
        _do_sheet_sync(show_toast=True)
        st.rerun()

    # ── Full edit dialog ──────────────────────────────────────────────────────
    @st.dialog("Edit Campaign", width="large")
    def _edit_campaign_dialog(target_id: str):
        _entry = next(
            (c for c in st.session_state.get("plan_added", [])
             if c.get("id") == target_id),
            next(
                (c for c in st.session_state.get("plan_drafts", [])
                 if c.get("id") == target_id),
                None
            )
        )
        if not _entry:
            st.warning("Campaign not found.")
            return

        _is_draft = _entry.get("status") == "draft"
        _draft_pill = ('  <span style="background:#f0f0f0;border:1px solid #ccc;'
                       'border-radius:3px;padding:1px 6px;font-size:9px;">DRAFT</span>'
                       if _is_draft else "")
        st.markdown(
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
            f'font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#888;'
            f'margin-bottom:14px;">Editing: <span style="color:#000;">'
            f'{_entry.get("name","")}</span>{_draft_pill}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("**Campaign details**")
        _e_name = st.text_input("Campaign name", value=_entry.get("name",""),
                                key=f"_edit_name_{target_id}")
        _e_subj = st.text_input("Subject / SMS copy", value=_entry.get("subject",""),
                                key=f"_edit_subj_{target_id}")
        _c1, _c2 = st.columns(2)
        with _c1:
            _g_default = _entry.get("goal","Conversion") or "Conversion"
            _g_idx = _GOAL_OPTIONS.index(_g_default) if _g_default in _GOAL_OPTIONS else 1
            _e_goal = st.selectbox("Goal", _GOAL_OPTIONS, index=_g_idx,
                                   key=f"_edit_goal_{target_id}")
            _cat_default = _entry.get("category","")
            _cat_idx = all_cats_plan.index(_cat_default) if _cat_default in all_cats_plan else 0
            _e_cat = st.selectbox("Category", all_cats_plan, index=_cat_idx,
                                  key=f"_edit_cat_{target_id}")
        with _c2:
            _ch_default = _entry.get("channel","email")
            _ch_idx = _CHANNEL_OPTIONS.index(_ch_default) if _ch_default in _CHANNEL_OPTIONS else 0
            _e_ch = st.selectbox("Channel", _CHANNEL_OPTIONS, index=_ch_idx,
                                 format_func=lambda x: x.upper(),
                                 key=f"_edit_ch_{target_id}")
            _date_default = _entry.get("send_date", date.today())
            if not isinstance(_date_default, date):
                _date_default = date.today()
            _e_date = st.date_input("Send date", value=_date_default,
                                    key=f"_edit_date_{target_id}")
        _e_auds = st.multiselect("Audiences", all_auds_plan,
                                 default=[a for a in _entry.get("audiences",[]) if a in all_auds_plan],
                                 key=f"_edit_auds_{target_id}")
        _c3, _c4 = st.columns(2)
        with _c3:
            _prod_default = _entry.get("product","(none)") or "(none)"
            _prod_idx = all_prods_plan.index(_prod_default) if _prod_default in all_prods_plan else 0
            _e_prod = st.selectbox("Primary product", all_prods_plan, index=_prod_idx,
                                   key=f"_edit_prod_{target_id}")
        with _c4:
            _stu_default = _entry.get("studio","(none)") or "(none)"
            _stu_idx = all_stus_plan.index(_stu_default) if _stu_default in all_stus_plan else 0
            _e_stu = st.selectbox("Primary studio", all_stus_plan, index=_stu_idx,
                                  key=f"_edit_stu_{target_id}")

        st.divider()
        st.markdown("**Tasks & owners**")
        _existing_assign = st.session_state["_campaign_assignments"].get(target_id, [])
        _new_assignments = render_assignment_widget(
            key=f"assign_{target_id}",
            label="",
            allow_multiple=True,
            existing=_existing_assign if _existing_assign else None,
            show_task=True,
        )

        st.markdown("")
        _b1, _b2, _b3 = st.columns([1, 1, 1])
        if _b1.button("Cancel", use_container_width=True):
            st.session_state.pop("_upcoming_edit_id", None)
            st.rerun()

        def _build_updated(status):
            return {
                **_entry,
                "name":      _e_name.strip() or _entry.get("name",""),
                "subject":   _e_subj.strip(),
                "goal":      _e_goal, "category": _e_cat, "channel": _e_ch,
                "send_date": _e_date, "audiences": _e_auds,
                "product":   _e_prod if _e_prod != "(none)" else "",
                "studio":    _e_stu  if _e_stu  != "(none)" else "",
                "status":    status,
            }

        if _is_draft:
            if _b2.button("Keep as Draft", use_container_width=True, type="secondary"):
                _upd = _build_updated("draft")
                for _j, _d in enumerate(st.session_state["plan_drafts"]):
                    if _d.get("id") == target_id:
                        st.session_state["plan_drafts"][_j] = _upd; break
                st.session_state["_campaign_assignments"][target_id] = _new_assignments
                _push_and_refresh(_upd)
                _do_sheet_sync()
                st.session_state.pop("_upcoming_edit_id", None); st.rerun()
            if _b3.button("Add to Calendar", use_container_width=True, type="primary"):
                _upd = _build_updated("planned")
                st.session_state["plan_drafts"] = [
                    d for d in st.session_state["plan_drafts"] if d.get("id") != target_id]
                st.session_state["plan_added"].append(_upd)
                st.session_state["_campaign_assignments"][target_id] = _new_assignments
                _push_and_refresh(_upd)
                _do_sheet_sync()
                st.session_state.pop("_upcoming_edit_id", None); st.rerun()
        else:
            if _b2.button("Save changes", use_container_width=True, type="primary"):
                _upd = _build_updated("planned")
                for _j, _c in enumerate(st.session_state["plan_added"]):
                    if _c.get("id") == target_id:
                        st.session_state["plan_added"][_j] = _upd
                        _push_and_refresh(_upd); break
                st.session_state["_campaign_assignments"][target_id] = _new_assignments
                _do_sheet_sync()
                st.session_state.pop("_upcoming_edit_id", None); st.rerun()

    # ── Lightweight assign-task dialog ────────────────────────────────────────
    @st.dialog("Assign Task", width="large")
    def _assign_task_dialog(target_id: str):
        _entry = next(
            (c for c in st.session_state.get("plan_added", [])
             if c.get("id") == target_id),
            next(
                (c for c in st.session_state.get("plan_drafts", [])
                 if c.get("id") == target_id),
                None
            )
        )
        name = _entry.get("name", target_id) if _entry else target_id
        st.markdown(
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
            f'font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#888;'
            f'margin-bottom:14px;">Tasks for: <span style="color:#000;">{name}</span></div>',
            unsafe_allow_html=True,
        )
        _existing = st.session_state["_campaign_assignments"].get(target_id, [])
        _new_assignments = render_assignment_widget(
            key=f"quick_assign_{target_id}",
            label="",
            allow_multiple=True,
            existing=_existing if _existing else None,
            show_task=True,
        )
        st.markdown("")
        _ab1, _ab2 = st.columns([1, 1])
        if _ab1.button("Cancel", use_container_width=True):
            st.session_state.pop("_upcoming_assign_id", None); st.rerun()
        if _ab2.button("Save", use_container_width=True, type="primary"):
            st.session_state["_campaign_assignments"][target_id] = _new_assignments
            st.session_state.pop("_upcoming_assign_id", None); st.rerun()

    # ── Build combined list ───────────────────────────────────────────────────
    _today = date.today()
    _data_upcoming = cal_df[cal_df["_date"] >= _today].copy()

    _combined = []
    for _, _row in _data_upcoming.iterrows():
        _combined.append({
            "name":      _clean(_row.get("Campaign Name","")),
            "subject":   "",
            "goal":      "",
            "category":  _row.get("Category",""),
            "channel":   str(_row.get("Channel","email")).lower(),
            "send_date": _row["_date"],
            "source":    "data",
        })
    for _pc in st.session_state.get("plan_added", []):
        _combined.append({**_pc, "source": "planned"})
    for _dr in st.session_state.get("plan_drafts", []):
        _combined.append({**_dr, "source": "draft"})

    # ── Helper: render one campaign row ──────────────────────────────────────
    def _render_campaign_row(pc, i):
        _cid         = pc.get("id","")
        _is_editable = pc["source"] in ("planned","draft")
        _d_str       = pc["send_date"].strftime("%b %-d, %Y") if isinstance(pc.get("send_date"), date) else "—"
        _p           = _lookup_perf(pc["category"], pc["channel"])
        _assigns     = st.session_state["_campaign_assignments"].get(_cid, [])

        # Status badge
        if pc["source"] == "planned":
            _badge = ('<span style="background:#caf30b;border:1px solid #000;border-radius:3px;'
                      'padding:1px 6px;font-size:9px;font-weight:700;">PLANNED</span>')
        elif pc["source"] == "draft":
            _badge = ('<span style="background:#f5f000;border:1px solid #888;border-radius:3px;'
                      'padding:1px 6px;font-size:9px;font-weight:700;">DRAFT</span>')
        else:
            _badge = ('<span style="background:#f0f0f0;border:1px solid #ccc;border-radius:3px;'
                      'padding:1px 6px;font-size:9px;font-weight:700;">SCHEDULED</span>')

        _ch_icon = "📧" if pc["channel"] == "email" else "📱"
        _ch_lbl  = "Email" if pc["channel"] == "email" else "SMS"
        _subj    = pc.get("subject","")
        _goal    = pc.get("goal","")
        _cat     = pc.get("category","")

        # ── 4-column main row ─────────────────────────────────────────────────
        if _is_editable:
            col_info, col_meta, col_tasks, col_actions = st.columns([3.2, 1.6, 2.8, 1.0])
        else:
            col_info, col_meta, col_tasks = st.columns([3.2, 1.6, 3.8])

        # Col 1 — Campaign name + subject + goal + created_by
        _creator     = pc.get("created_by", "")
        _creator_html = (
            f'<div style="font-size:10px;color:#aaa;margin-top:4px;">Added by {_creator}</div>'
            if _creator else ""
        )
        col_info.markdown(
            f'<div style="padding:4px 0 8px;">'
            f'<div style="margin-bottom:5px;">{_badge}</div>'
            f'<div style="font-weight:700;font-size:14px;line-height:1.3;margin-bottom:3px;">{pc["name"]}</div>'
            + (f'<div style="font-size:11px;color:#444;font-style:italic;margin-bottom:2px;">'
               f'&ldquo;{_subj}&rdquo;</div>' if _subj else "")
            + (f'<div style="font-size:11px;color:#666;">Goal: {_goal}</div>' if _goal else "")
            + _creator_html
            + f'</div>',
            unsafe_allow_html=True,
        )

        # Col 2 — Date, channel, category, owner, last modified
        _owner        = pc.get("owner", "")
        _last_mod_by  = pc.get("last_modified_by", "")
        _last_saved   = pc.get("last_saved", "")
        # Format last_saved as "May 7, 2:34 PM" if it's a full timestamp
        try:
            _ls_dt = _datetime.strptime(_last_saved, "%Y-%m-%d %H:%M:%S")
            _ls_fmt = _ls_dt.strftime("%-m/%-d, %-I:%M %p")
        except Exception:
            _ls_fmt = _last_saved
        _last_mod_html = ""
        if _last_mod_by:
            _ts_part = f" · {_ls_fmt}" if _ls_fmt else ""
            _last_mod_html = (
                f'<div style="font-size:9px;color:#bbb;margin-top:3px;line-height:1.3;">'
                f'Last edit: {_last_mod_by}{_ts_part}</div>'
            )
        col_meta.markdown(
            f'<div style="padding:4px 0 8px;font-family:Barlow,sans-serif;">'
            f'<div style="font-size:13px;font-weight:700;margin-bottom:4px;">{_d_str}</div>'
            f'<div style="font-size:11px;color:#555;margin-bottom:2px;">{_ch_icon} {_ch_lbl}</div>'
            + (f'<div style="font-size:11px;color:#777;margin-bottom:1px;">{_cat}</div>' if _cat else "")
            + (f'<div style="font-size:10px;color:#999;margin-bottom:1px;">👤 {_owner}</div>' if _owner else "")
            + _last_mod_html
            + f'</div>',
            unsafe_allow_html=True,
        )

        # Col 3 — Tasks & owners
        with col_tasks:
            if _assigns:
                st.markdown(assignment_summary_html(_assigns), unsafe_allow_html=True)
            else:
                st.markdown(
                    '<span style="color:#bbb;font-size:11px;font-style:italic;">'
                    'No tasks assigned</span>',
                    unsafe_allow_html=True,
                )
            if _is_editable:
                st.button(
                    "+ Assign task",
                    key=f"assign_btn_{_cid or i}",
                    on_click=lambda cid=_cid: st.session_state.update({"_upcoming_assign_id": cid}),
                    type="secondary",
                )

        # Col 4 — Edit / Remove
        if _is_editable:
            with col_actions:
                st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)
                if st.button("Edit", key=f"edit_up_{_cid or i}", use_container_width=True):
                    st.session_state["_upcoming_edit_id"] = _cid
                    st.rerun()
                if st.button("Remove", key=f"rm_up_{_cid or i}", use_container_width=True):
                    if pc["source"] == "planned":
                        st.session_state["plan_added"] = [
                            c for c in st.session_state["plan_added"] if c.get("id") != _cid]
                    else:
                        st.session_state["plan_drafts"] = [
                            c for c in st.session_state["plan_drafts"] if c.get("id") != _cid]
                    _archive_campaign(pc)
                    _invalidate_sheet_cache()
                    st.toast("Campaign moved to Removed Campaigns.", icon="🗑️")
                    st.rerun()

        # ── Forecasted metrics strip ──────────────────────────────────────────
        if _p:
            _open_v = "—" if pc["channel"] == "sms" else f"{_p['open']:.1%}"
            st.markdown(
                f'<div style="background:#f7f7f7;border-radius:6px;padding:5px 10px;'
                f'margin-bottom:2px;display:flex;gap:20px;align-items:center;'
                f'font-family:Barlow,sans-serif;">'
                f'<span style="font-size:9px;font-weight:700;color:#aaa;'
                f'text-transform:uppercase;letter-spacing:0.08em;white-space:nowrap;">'
                f'Forecasted</span>'
                f'<span style="font-size:11px;color:#555;">'
                f'Open&nbsp;<strong>{_open_v}</strong></span>'
                f'<span style="font-size:11px;color:#555;">'
                f'Click&nbsp;<strong>{_p["click"]:.2%}</strong></span>'
                f'<span style="font-size:11px;color:#555;">'
                f'Conv&nbsp;<strong>{_p["conv"]:.2%}</strong></span>'
                f'<span style="font-size:11px;color:#555;">'
                f'RPR&nbsp;<strong>${_p["rpr"]:.2f}</strong></span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Render list ──────────────────────────────────────────────────────────
    if not _combined:
        st.markdown(
            '<p style="font-family:\'Barlow\',sans-serif;font-size:0.9rem;color:#888;'
            'font-style:italic;">No upcoming or draft campaigns. Use '
            '<em>Plan a Campaign</em> to add one.</p>',
            unsafe_allow_html=True,
        )
    else:
        _combined.sort(key=lambda c: (c["source"] == "draft", c["send_date"]))
        for _i, _pc in enumerate(_combined):
            _render_campaign_row(_pc, _i)
            st.divider()

    # Trigger dialogs after rendering all rows
    _open_edit_id   = st.session_state.get("_upcoming_edit_id")
    _open_assign_id = st.session_state.get("_upcoming_assign_id")
    if _open_edit_id:
        _edit_campaign_dialog(_open_edit_id)
    elif _open_assign_id:
        _assign_task_dialog(_open_assign_id)

with tab_plan:

    # ── "Plan for me" auto-suggestion helpers ────────────────────────────────
    EVENT_CAT_HINT = {
        "Mother's Day": "Holiday", "Valentine's Day": "Holiday",
        "Galentine's Day": "Holiday", "Christmas": "Holiday",
        "New Year's Day": "Holiday", "New Year's Eve": "Holiday",
        "Halloween": "Holiday", "St. Patrick's Day": "Holiday",
        "Thanksgiving": "Holiday", "International Women's Day": "Editorial",
        "Black Friday": "Sale", "Cyber Monday": "Sale",
        "Memorial Day": "Sale", "Independence Day": "Sale",
        "Labor Day": "Sale", "Back to School": "Sale",
        "Earth Day": "Editorial",
        "First Day of Spring": "Editorial", "First Day of Summer": "Editorial",
        "First Day of Fall": "Editorial", "First Day of Winter": "Editorial",
    }
    GOAL_BY_CAT = {
        "Holiday": "Conversion", "Sale": "Flash Sale",
        "Editorial": "Awareness", "Studio": "Awareness",
        "Mystery Set": "Conversion", "Product Launch": "Launch",
        "Restock": "Conversion", "Educational": "Awareness",
        "Winback": "Re-engagement", "In-Studio": "Awareness",
        "NSO": "Awareness", "Reminder": "Conversion",
        "Promo": "Retention", "Partnership": "Awareness",
    }
    NAME_TMPL_EVT = {
        "Holiday":         "{e} Hero Drop",
        "Sale":            "{e} Flash Sale",
        "Editorial":       "{e} Edit",
        "Studio":          "{e} Studio Spotlight",
        "Mystery Set":     "Mystery Box — {e}",
        "Product Launch":  "Launch — {e}",
        "Restock":         "Back in Stock — {e}",
        "Educational":     "{e} Style Guide",
        "Winback":         "We Miss You — {e}",
        "In-Studio":       "In-Studio: {e}",
        "Reminder":        "{e} — Last Call",
        "Promo":           "{e} Promo",
        "Partnership":     "Glinta x {e}",
    }
    SUBJ_KEYED = {
        ("Holiday", "Mother's Day"):     "She deserves the whole collection ✨",
        ("Holiday", "Valentine's Day"):  "Treat yourself (or someone else) 💕",
        ("Holiday", "Galentine's Day"):  "For your favorite humans 💛",
        ("Holiday", "Christmas"):        "The gift list is ready 🎁",
        ("Holiday", "Halloween"):        "A little something wicked 🖤",
        ("Sale", "Black Friday"):        "BFCM is here — up to 40% off",
        ("Sale", "Cyber Monday"):        "Cyber deals — last chance",
        ("Sale", "Memorial Day"):        "Long weekend, big savings",
        ("Sale", "Labor Day"):           "Labor Day weekend — 25% off",
        ("Sale", "Back to School"):      "Back-to-school edit — 20% off",
        ("Editorial", "Earth Day"):      "Mindful pieces for Earth Day",
    }
    SUBJ_DEFAULT = {
        "Holiday": "Special edition just dropped",
        "Sale": "Flash sale — 24 hours only",
        "Editorial": "The new edit is here",
        "Studio": "Inside the studio",
        "Mystery Set": "Mystery box — what's inside?",
        "Product Launch": "Just landed",
        "Restock": "It's back in stock",
        "Educational": "Here's how to wear it",
        "Winback": "We've missed you",
        "In-Studio": "Come visit us this weekend",
        "Reminder": "Last call — don't miss out",
        "Promo": "A little something for you",
        "Partnership": "A new collaboration",
    }

    def _suggest_plan(picked_cat, picked_evt_label, upcoming_evts):
        today_d = date.today()
        rationale = []  # list of (field_label, html_text)

        evt_name, evt_date = None, None
        if picked_evt_label and picked_evt_label != "(none)":
            for d_, n_ in upcoming_evts:
                if f"{n_} ({d_.strftime('%b %-d')})" == picked_evt_label:
                    evt_name, evt_date = n_, d_
                    break

        # ── Category ─────────────────────────────────────────────────────────
        if picked_cat and picked_cat != "(any)":
            cat = picked_cat
            rationale.append(("Category", f"You selected <b>{cat}</b>."))
        elif evt_name and EVENT_CAT_HINT.get(evt_name) in all_cats_plan:
            cat = EVENT_CAT_HINT[evt_name]
            rationale.append(("Category",
                f"<b>{evt_name}</b> is typically a <b>{cat}</b> moment."))
        else:
            scores = (
                campaigns_df.groupby("Category").agg(
                    c=("Click Rate","mean"), v=("Conversion Rate","mean"),
                    r=("RPR","mean"),
                ).reset_index().dropna()
            )
            scores["s"] = scores["c"].rank() + scores["v"].rank() + scores["r"].rank()
            if not scores.empty:
                top = scores.sort_values("s", ascending=False).iloc[0]
                cat = top["Category"]
                rationale.append(("Category",
                    f"<b>{cat}</b> ranks highest across click ({top['c']:.1%}) · "
                    f"conv ({top['v']:.2%}) · RPR (${top['r']:.2f}) historically."))
            else:
                cat = all_cats_plan[0] if all_cats_plan else ""
                rationale.append(("Category", f"Default fallback: <b>{cat}</b>."))

        # ── Date ─────────────────────────────────────────────────────────────
        if evt_date:
            offset_days = 0 if cat in ("Sale", "Promo") else 2
            send_date = evt_date - timedelta(days=offset_days)
            if send_date < today_d + timedelta(days=1):
                send_date = today_d + timedelta(days=1)
            if offset_days == 0:
                rationale.append(("Date",
                    f"Send day-of <b>{evt_name}</b> ({evt_date.strftime('%b %-d')}) "
                    f"to capture peak intent."))
            else:
                rationale.append(("Date",
                    f"<b>{offset_days}d before {evt_name}</b> "
                    f"({evt_date.strftime('%b %-d')}) — gives recipients lead time."))
        else:
            _dow_df = cal_df[cal_df["Category"]==cat].dropna(subset=["Conversion Rate"]).copy()
            if not _dow_df.empty:
                _dow_df["_dow"] = _dow_df["_date"].apply(lambda d: d.weekday())
                grp = _dow_df.groupby("_dow")["Conversion Rate"].mean()
                best_dow = int(grp.idxmax())
                rationale.append(("Date",
                    f"<b>{DOW_NAME[best_dow]}</b> has the highest avg conv "
                    f"({grp.max():.2%}) for <b>{cat}</b> across {len(_dow_df)} past sends."))
            else:
                best_dow = 1
                rationale.append(("Date", "No history — defaulting to Tuesday."))
            send_date = today_d + timedelta(days=7)
            while send_date.weekday() != best_dow:
                send_date += timedelta(days=1)

        # ── Channel ──────────────────────────────────────────────────────────
        _ch_df = campaigns_df[campaigns_df["Category"]==cat].dropna(subset=["Conversion Rate"])
        channel = "Email"
        if not _ch_df.empty and "Channel" in _ch_df.columns:
            ch_grp = _ch_df.groupby(_ch_df["Channel"].astype(str).str.lower())["Conversion Rate"].mean()
            if not ch_grp.empty:
                top_ch = str(ch_grp.idxmax())
                channel = "SMS" if "sms" in top_ch else "Email"
                if len(ch_grp) > 1:
                    other_v = ch_grp.drop(top_ch).iloc[0]
                    rationale.append(("Channel",
                        f"<b>{channel}</b> avg conv ({ch_grp.max():.2%}) beats "
                        f"the alternative ({other_v:.2%}) for <b>{cat}</b>."))
                else:
                    rationale.append(("Channel",
                        f"<b>{channel}</b> is the only channel used for "
                        f"<b>{cat}</b> ({ch_grp.max():.2%} avg conv)."))
            else:
                rationale.append(("Channel", "No category history — defaulting to Email."))
        else:
            rationale.append(("Channel", "No category history — defaulting to Email."))

        # ── Audiences ────────────────────────────────────────────────────────
        _cat_df = campaigns_df[campaigns_df["Category"]==cat]
        aud_counts = {}
        if "Audiences" in _cat_df.columns:
            for v_ in _cat_df["Audiences"].dropna():
                for a_ in str(v_).split(","):
                    a_ = a_.strip()
                    if a_: aud_counts[a_] = aud_counts.get(a_, 0) + 1
        sorted_auds = [(a, c) for a, c in sorted(aud_counts.items(), key=lambda x: -x[1])
                       if a in all_auds_plan]
        suggested_auds = [a for a, _ in sorted_auds[:2]]
        if suggested_auds:
            parts = " · ".join(f"<b>{a}</b> ({c}×)" for a, c in sorted_auds[:2])
            rationale.append(("Audiences",
                f"Most-targeted in past <b>{cat}</b> sends: {parts}."))
        else:
            rationale.append(("Audiences",
                f"No clear audience pattern in past <b>{cat}</b> sends — left empty."))

        # ── Product / Studio ────────────────────────────────────────────────
        sug_prod = "(none)"
        if "Primary Product" in _cat_df.columns:
            pc = _cat_df["Primary Product"].dropna().value_counts()
            if not pc.empty and str(pc.idxmax()) in all_prods_plan:
                sug_prod = str(pc.idxmax())
                rationale.append(("Product",
                    f"<b>{sug_prod}</b> appeared in {int(pc.max())} of "
                    f"{int(pc.sum())} past <b>{cat}</b> sends."))
        sug_stu = "(none)"
        if "Primary Studio" in _cat_df.columns:
            sc = _cat_df["Primary Studio"].dropna().value_counts()
            if not sc.empty and str(sc.idxmax()) in all_stus_plan:
                sug_stu = str(sc.idxmax())
                rationale.append(("Studio",
                    f"<b>{sug_stu}</b> appeared in {int(sc.max())} of "
                    f"{int(sc.sum())} past <b>{cat}</b> sends."))

        # ── Name / Subject / Goal ───────────────────────────────────────────
        if evt_name:
            tmpl = NAME_TMPL_EVT.get(cat, "{e} — " + cat)
            name = tmpl.format(e=evt_name)
        else:
            no_evt = {
                "Holiday": "Seasonal Hero Drop",
                "Sale": "Limited-Time Sale",
                "Editorial": "Editorial Drop",
                "Studio": "Studio Spotlight",
                "Mystery Set": "Mystery Box Reveal",
                "Product Launch": (f"Introducing {sug_prod}" if sug_prod != "(none)" else "New Launch"),
                "Restock": (f"Back in Stock — {sug_prod}" if sug_prod != "(none)" else "Back in Stock"),
                "Educational": "How-To Guide",
                "Winback": "We Miss You",
                "In-Studio": (f"In-Studio: {sug_stu}" if sug_stu != "(none)" else "In-Studio This Weekend"),
                "Reminder": "Last Call",
                "Promo": "Members-Only Promo",
                "Partnership": "Brand Collaboration",
            }
            name = no_evt.get(cat, f"{cat} Campaign")

        subj = SUBJ_KEYED.get((cat, evt_name)) or SUBJ_DEFAULT.get(cat, "")
        if (cat, evt_name) in SUBJ_KEYED:
            rationale.append(("Subject",
                f"Curated copy for <b>{cat}</b> + <b>{evt_name}</b> — refine before send."))
        else:
            rationale.append(("Subject",
                f"Default <b>{cat}</b> hook — refine before send."))

        goal = GOAL_BY_CAT.get(cat, "Conversion")
        rationale.append(("Goal", f"Standard goal for <b>{cat}</b> campaigns."))

        return {
            "values": {
                "nc_name": name, "nc_subj": subj, "nc_goal": goal,
                "nc_cat":  cat,  "nc_ch":   channel, "nc_date": send_date,
                "nc_auds": suggested_auds,
                "nc_prod": sug_prod, "nc_stu":  sug_stu,
            },
            "rationale": rationale,
        }

    # Apply pending "Plan for me" suggestion BEFORE form widgets render
    _pending = st.session_state.pop("_pending_plan", None)
    if _pending:
        for _k, _v in _pending.get("values", {}).items():
            st.session_state[_k] = _v
        st.session_state["_last_plan_rationale"] = _pending.get("rationale", [])
        st.session_state["plan_edit_idx"] = None

    # Apply pending form clear BEFORE form widgets render (Streamlit forbids
    # writing widget-keyed session state after the widget has rendered)
    if st.session_state.pop("_pending_clear", False):
        st.session_state["nc_name"]  = ""
        st.session_state["nc_subj"]  = ""
        st.session_state["nc_goal"]  = "Conversion"
        st.session_state["nc_cat"]   = all_cats_plan[0] if all_cats_plan else ""
        st.session_state["nc_ch"]    = "Email"
        st.session_state["nc_date"]  = date.today() + timedelta(days=14)
        st.session_state["nc_auds"]  = []
        st.session_state["nc_prod"]  = "(none)"
        st.session_state["nc_stu"]   = "(none)"
        st.session_state["nc_owner"] = st.session_state.get("_app_user", "Anna")
        st.session_state["plan_edit_idx"] = None

    # ── Handle "Use category" button clicks from the right panel ─────────────
    # These set session state keys that pre-fill the form widgets below
    # (handled before form widgets render, so they take effect immediately)
    _preset = st.session_state.pop("_preset_cat", None)
    if _preset and _preset in all_cats_plan:
        st.session_state["nc_cat"] = _preset

    # ── Layout: form (left 3) + context panels (right 2) ─────────────────────
    form_col, ctx_col = st.columns([3, 2], gap="large")

    # ── LEFT: Campaign form ───────────────────────────────────────────────────
    with form_col:
        st.markdown("<h2>Plan a Campaign</h2>", unsafe_allow_html=True)

        # ── "Plan for me" auto-suggest ───────────────────────────────────────
        _today_pfm = date.today()
        _upcoming_evts = sorted(
            [(d_, n_) for d_, n_ in _us_events([_today_pfm.year, _today_pfm.year+1]).items()
             if d_ >= _today_pfm and d_ <= _today_pfm + timedelta(days=240)],
            key=lambda x: x[0]
        )
        _evt_labels = ["(none)"] + [f"{n_} ({d_.strftime('%b %-d')})" for d_, n_ in _upcoming_evts]

        with st.expander("✨ Plan for me — auto-fill the form", expanded=False):
            st.caption(
                "Pick a category and/or upcoming event. We'll suggest a name, subject, "
                "audience, channel, and timing using your historical performance."
            )
            _pfm1, _pfm2 = st.columns(2)
            with _pfm1:
                st.selectbox(
                    "Category",
                    ["(any)"] + all_cats_plan,
                    key="pfm_cat",
                )
            with _pfm2:
                st.selectbox(
                    "Upcoming event",
                    _evt_labels,
                    key="pfm_evt",
                )
            if st.button("✨ Plan for me", type="primary",
                         use_container_width=True, key="pfm_go"):
                _sugg = _suggest_plan(
                    st.session_state.get("pfm_cat", "(any)"),
                    st.session_state.get("pfm_evt", "(none)"),
                    _upcoming_evts,
                )
                st.session_state["_pending_plan"] = _sugg
                st.rerun()

        # ── "Why these picks?" rationale (shown after generation) ────────────
        _rat = st.session_state.get("_last_plan_rationale")
        if _rat:
            _items = "".join(
                f'<div style="padding:5px 0;border-bottom:1px solid #f0f0f0;'
                f'font-family:Barlow,sans-serif;font-size:11px;line-height:1.45;">'
                f'<span style="display:inline-block;background:#caf30b;'
                f'border-radius:3px;padding:2px 6px;font-size:9px;font-weight:800;'
                f'letter-spacing:0.06em;text-transform:uppercase;'
                f'font-family:\'Barlow Condensed\',sans-serif;margin-right:6px;'
                f'min-width:60px;text-align:center;">{_lbl}</span>'
                f'<span>{_txt}</span></div>'
                for _lbl, _txt in _rat
            )
            st.markdown(
                '<div style="border:2px solid #000;border-radius:10px;padding:12px 14px;'
                'background:#fff;margin:6px 0 12px;">'
                '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
                'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;'
                'padding-bottom:6px;border-bottom:2px solid #000;margin-bottom:6px;">'
                '✨ Why these picks?'
                '</div>'
                f'{_items}</div>',
                unsafe_allow_html=True,
            )
            if st.button("Dismiss rationale", key="dismiss_rationale"):
                st.session_state.pop("_last_plan_rationale", None)
                st.rerun()

        # If editing a draft, pre-fill from that draft
        _edit = st.session_state.get("plan_edit_idx")
        _draft_prefill = st.session_state["plan_drafts"][_edit] if _edit is not None and _edit < len(st.session_state["plan_drafts"]) else None

        # Pre-fill from draft if editing (set session state before widget renders)
        if _draft_prefill and "nc_name" not in st.session_state:
            st.session_state["nc_name"] = _draft_prefill.get("name", "")

        # Campaign name
        nc_name = st.text_input(
            "Campaign name",
            placeholder="e.g. Mother's Day Hero Drop",
            key="nc_name",
        )

        if _draft_prefill and "nc_subj" not in st.session_state:
            st.session_state["nc_subj"] = _draft_prefill.get("subject", "")

        # Subject line (optional)
        nc_subj = st.text_input(
            "Subject line (optional)",
            placeholder="e.g. She deserves the whole collection ✨",
            key="nc_subj",
        )

        # Goal
        _goal_opts = ["Conversion", "Awareness", "Re-engagement", "Launch", "Retention", "Flash Sale"]
        if _draft_prefill and "nc_goal" not in st.session_state:
            _goal_prefill = _draft_prefill.get("goal", "Conversion")
            st.session_state["nc_goal"] = _goal_prefill if _goal_prefill in _goal_opts else "Conversion"
        nc_goal = st.selectbox("Goal", _goal_opts, key="nc_goal")

        # Category
        _cat_default_idx = (
            all_cats_plan.index(_draft_prefill["category"])
            if _draft_prefill and _draft_prefill["category"] in all_cats_plan
            else (all_cats_plan.index(st.session_state["nc_cat"])
                  if st.session_state.get("nc_cat") in all_cats_plan else 0)
        )
        nc_cat = st.selectbox("Category", all_cats_plan,
                              index=_cat_default_idx, key="nc_cat")

        # Channel
        _ch_opts = ["Email", "SMS", "Both"]
        _ch_default = _draft_prefill["channel"].title() if _draft_prefill else "Email"
        _ch_default = _ch_default if _ch_default in _ch_opts else "Email"
        nc_ch = st.selectbox("Channel (email, SMS, both)", _ch_opts,
                             index=_ch_opts.index(_ch_default), key="nc_ch")

        # Date
        _date_default = (_draft_prefill["send_date"]
                         if _draft_prefill and isinstance(_draft_prefill.get("send_date"), date)
                         else date.today() + timedelta(days=14))
        nc_date = st.date_input("Date", value=_date_default, key="nc_date",
                                min_value=date.today())

        # Audiences (optional)
        _aud_default = _draft_prefill.get("audiences", []) if _draft_prefill else []
        nc_auds = st.multiselect("Audiences (optional)", all_auds_plan,
                                 default=_aud_default, key="nc_auds",
                                 placeholder="Select audience segments")

        # Product (optional)
        _prod_default_idx = (
            all_prods_plan.index(_draft_prefill["product"])
            if _draft_prefill and _draft_prefill.get("product") in all_prods_plan else 0
        )
        nc_prod = st.selectbox("Product (optional)", all_prods_plan,
                               index=_prod_default_idx, key="nc_prod")

        # Studio (optional)
        _stu_default_idx = (
            all_stus_plan.index(_draft_prefill["studio"])
            if _draft_prefill and _draft_prefill.get("studio") in all_stus_plan else 0
        )
        nc_stu = st.selectbox("Studio (optional)", all_stus_plan,
                              index=_stu_default_idx, key="nc_stu")

        # Owner
        _OWNERS = [
            "Anna", "Marketing Director", "Marketing Strategy",
            "Brand & Social", "Growth Marketing", "Retail Marketing",
            "Merchandising & Planning", "Design", "Operations", "Data",
        ]
        _app_user_now = st.session_state.get("_app_user", _OWNERS[0])
        _owner_default = (
            _draft_prefill.get("owner", _app_user_now) if _draft_prefill
            else st.session_state.get("nc_owner", _app_user_now)
        )
        _owner_default = _owner_default if _owner_default in _OWNERS else _app_user_now
        nc_owner = st.selectbox("Owner", _OWNERS,
                                index=_OWNERS.index(_owner_default),
                                key="nc_owner")

        # Live expected performance
        _ch_lower = nc_ch.lower() if nc_ch != "Both" else "email"
        _perf = _lookup_perf(nc_cat, _ch_lower)
        if _perf:
            _is_sms = (_ch_lower == "sms")
            _open_v = "—" if _is_sms else f"{_perf['open']:.1%}"
            _rpr_help = (f"Revenue per recipient — based on {_perf['n']:.0f} "
                         f"historical {nc_cat} campaigns")
            ep1, ep2, ep3, ep4 = st.columns(4)
            ep1.markdown(_stat_html("Exp. Open",  _open_v,
                                    "SMS opens aren't tracked" if _is_sms else ""),
                         unsafe_allow_html=True)
            ep2.markdown(_stat_html("Exp. Click", f"{_perf['click']:.2%}"),
                         unsafe_allow_html=True)
            ep3.markdown(_stat_html("Exp. Conv",  f"{_perf['conv']:.2%}"),
                         unsafe_allow_html=True)
            ep4.markdown(_stat_html("Exp. RPR",   f"${_perf['rpr']:.2f}", _rpr_help),
                         unsafe_allow_html=True)

        # Best day hint
        _dow_df = cal_df.copy()
        _dow_df["_dow"] = _dow_df["_date"].apply(lambda d: d.weekday())
        _dow_grp = (
            _dow_df[_dow_df["Category"]==nc_cat]
            .dropna(subset=["Conversion Rate"])
            .groupby("_dow")["Conversion Rate"].mean()
        )
        if not _dow_grp.empty:
            _best_dow = int(_dow_grp.idxmax())
            if isinstance(nc_date, date) and nc_date.weekday() != _best_dow:
                st.caption(
                    f"💡 Best conv rate for **{nc_cat}** historically on **{DOW_NAME[_best_dow]}**"
                    f" — current date is {DOW_NAME[nc_date.weekday()]}"
                )

        # Action buttons
        st.markdown("")
        b1, b2, b3 = st.columns(3)

        def _build_entry(status):
            channels = (["email","sms"] if nc_ch == "Both"
                        else ["email"] if nc_ch == "Email" else ["sms"])
            _base_name = nc_name.strip() if nc_name.strip() else f"{nc_cat} — {nc_date.strftime('%b %-d')}"
            # Derive next ID from the actual max across all existing IDs
            _all_ids = (
                [c.get("id","") for c in st.session_state.get("plan_added",[])]
                + [c.get("id","") for c in st.session_state.get("plan_drafts",[])]
            )
            _nums = [int(_i[1:]) for _i in _all_ids if _i.startswith("P") and _i[1:].isdigit()]
            _next_num = max(_nums, default=0) + 1
            entries = []
            for _ch in channels:
                _display_name = f"{_base_name} ({_ch.upper()})" if nc_ch == "Both" else _base_name
                entries.append({
                    "id":        f"P{_next_num + len(entries):03d}",
                    "name":      _display_name,
                    "subject":   nc_subj.strip(),
                    "goal":      nc_goal,
                    "category":  nc_cat,
                    "channel":   _ch,
                    "send_date": nc_date,
                    "audiences": nc_auds,
                    "product":   nc_prod if nc_prod != "(none)" else "",
                    "studio":    nc_stu  if nc_stu  != "(none)" else "",
                    "owner":            nc_owner,
                    "status":           status,
                    "created_by":       st.session_state.get("_app_user", nc_owner),
                    "last_modified_by": st.session_state.get("_app_user", nc_owner),
                    "last_saved":       _datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
            return entries

        def _clear_form():
            # Defer the actual reset to the next script run, BEFORE widgets
            # render — Streamlit forbids mutating widget session_state keys
            # after the widget with that key has been instantiated.
            st.session_state["_pending_clear"] = True

        if b1.button("Clear", use_container_width=True):
            _clear_form()
            st.rerun()

        if b2.button("Save Draft", use_container_width=True, type="secondary"):
            entries = _build_entry("draft")
            # If editing, replace; otherwise append
            if _edit is not None and _edit < len(st.session_state["plan_drafts"]):
                st.session_state["plan_drafts"][_edit:_edit+1] = entries
            else:
                st.session_state["plan_drafts"].extend(entries)
            for _draft_entry in entries:
                _push_and_refresh(_draft_entry)
            _clear_form()
            st.rerun()

        if b3.button("Add to Calendar", use_container_width=True, type="primary"):
            entries = _build_entry("planned")
            # If editing a draft, remove the draft and add to planned
            if _edit is not None and _edit < len(st.session_state["plan_drafts"]):
                st.session_state["plan_drafts"].pop(_edit)
            st.session_state["plan_added"].extend(entries)
            for _e in entries:
                _sync_to_sheet(_e)
            _clear_form()
            st.rerun()

    # ── RIGHT: Context panels ─────────────────────────────────────────────────
    with ctx_col:
        today_d = date.today()

        # ── Panel 1: Same month last year ─────────────────────────────────────
        _sel_month = nc_date.month if isinstance(nc_date, date) else today_d.month
        _sel_year  = nc_date.year  if isinstance(nc_date, date) else today_d.year
        _lyr       = _sel_year - 1
        _lyr_df    = cal_df[
            (cal_df["Send Date"].dt.month == _sel_month) &
            (cal_df["Send Date"].dt.year  == _lyr)
        ].copy()

        _mon_name = date(_sel_year, _sel_month, 1).strftime("%B")

        if "lyr_expanded" not in st.session_state:
            st.session_state["lyr_expanded"] = False

        with st.container(border=True):
            _lyr_h1, _lyr_h2 = st.columns([3, 1])
            _lyr_h1.markdown(
                f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
                f'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;">'
                f'LAST YEAR IN {_mon_name.upper()}</div>',
                unsafe_allow_html=True,
            )

            if _lyr_df.empty:
                st.caption("No campaigns found for this month last year.")
            else:
                _lyr_sorted = _lyr_df.sort_values("Revenue", ascending=False).reset_index(drop=True)
                _lyr_total  = len(_lyr_sorted)
                _expanded   = st.session_state["lyr_expanded"]

                _toggle_lbl = "Collapse ↑" if _expanded else f"All {_lyr_total} →"
                if _lyr_h2.button(_toggle_lbl, key="lyr_toggle", use_container_width=True):
                    st.session_state["lyr_expanded"] = not _expanded
                    st.rerun()

                # Summary stats
                _lyr_open = _lyr_sorted["Open Rate"].mean()
                _lyr_conv = _lyr_sorted["Conversion Rate"].mean()
                _lyr_rev  = _lyr_sorted["Revenue"].sum()
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;'
                    f'gap:4px 6px;margin:4px 0 8px;">'
                    f'<div>{_stat_html("Sends", str(_lyr_total))}</div>'
                    f'<div>{_stat_html("Revenue", f"${_lyr_rev/1e3:.1f}K")}</div>'
                    f'<div>{_stat_html("Avg Open", f"{_lyr_open:.1%}")}</div>'
                    f'<div>{_stat_html("Avg Conv", f"{_lyr_conv:.2%}")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown('<div style="height:1px;background:#eee;margin-bottom:4px;"></div>',
                            unsafe_allow_html=True)

                # Campaign rows — top 3 collapsed, all when expanded
                _rows_to_show = _lyr_sorted if _expanded else _lyr_sorted.head(3)

                for _ri, _r in _rows_to_show.iterrows():
                    _ch_raw   = str(_r.get("Channel","")).lower()
                    _ch_dot   = "📧" if "email" in _ch_raw else "📱"
                    _ch_disp  = "Email" if "email" in _ch_raw else "SMS"
                    _cname    = _clean(str(_r.get("Campaign Name","")))
                    _subj_raw = _r.get("Subject Line","")
                    _subj     = ("" if pd.isna(_subj_raw) or str(_subj_raw).strip()==""
                                 else str(_subj_raw).strip())
                    _rev_txt  = f'${_r["Revenue"]:,.0f}' if pd.notna(_r.get("Revenue")) else "—"
                    _conv_txt = f'{_r["Conversion Rate"]:.2%}' if pd.notna(_r.get("Conversion Rate")) else "—"
                    _open_txt = ("—" if "sms" in _ch_raw or not pd.notna(_r.get("Open Rate"))
                                 else f'{_r["Open Rate"]:.1%}')
                    _disp_name = (_cname[:28]+"…") if len(_cname) > 28 else _cname

                    _rc1, _rc2 = st.columns([5, 2])
                    with _rc1:
                        st.markdown(
                            f'<div style="padding:3px 0;font-family:Barlow,sans-serif;">'
                            f'<div style="font-size:11px;font-weight:700;line-height:1.3;">'
                            f'{_ch_dot} {_disp_name}</div>'
                            f'<div style="font-size:9px;color:#777;margin-top:1px;">'
                            f'{_rev_txt} rev &nbsp;·&nbsp; {_conv_txt} conv'
                            f'&nbsp;·&nbsp; {_open_txt} open</div>'
                            + (f'<div style="font-size:9px;color:#aaa;font-style:italic;'
                               f'margin-top:1px;white-space:nowrap;overflow:hidden;'
                               f'text-overflow:ellipsis;max-width:155px;">"{_subj}"</div>'
                               if _subj else "")
                            + f'</div>',
                            unsafe_allow_html=True,
                        )
                    with _rc2:
                        if st.button("Replicate →", key=f"rep_{_ri}",
                                     use_container_width=True):
                            _rep_ch   = "Email" if "email" in _ch_raw else "SMS"
                            _orig_d   = _r["_date"]
                            try:
                                _rep_date = _orig_d.replace(year=_sel_year)
                            except ValueError:
                                _rep_date = _orig_d.replace(year=_sel_year, day=28)
                            if _rep_date <= today_d:
                                _rep_date = today_d + timedelta(days=14)
                            _rep_auds = []
                            _aud_raw  = _r.get("Audiences","")
                            if pd.notna(_aud_raw) and str(_aud_raw).strip():
                                _rep_auds = [a.strip() for a in str(_aud_raw).split(",")
                                             if a.strip() in all_auds_plan]
                            _rep_cat  = str(_r.get("Category","")) if pd.notna(_r.get("Category")) else ""
                            _rep_prod = str(_r.get("Primary Product","")) if pd.notna(_r.get("Primary Product")) else ""
                            _rep_stu  = str(_r.get("Primary Studio",""))  if pd.notna(_r.get("Primary Studio"))  else ""
                            st.session_state["_pending_plan"] = {
                                "values": {
                                    "nc_name": _cname,
                                    "nc_subj": _subj,
                                    "nc_goal": GOAL_BY_CAT.get(_rep_cat, "Conversion"),
                                    "nc_cat":  _rep_cat  if _rep_cat  in all_cats_plan  else (all_cats_plan[0] if all_cats_plan else ""),
                                    "nc_ch":   _rep_ch,
                                    "nc_date": _rep_date,
                                    "nc_auds": _rep_auds,
                                    "nc_prod": _rep_prod if _rep_prod in all_prods_plan else "(none)",
                                    "nc_stu":  _rep_stu  if _rep_stu  in all_stus_plan  else "(none)",
                                },
                                "rationale": [("Replicated",
                                    f"Pre-filled from <b>{_cname}</b> ({_ch_disp}, "
                                    f"{_orig_d.strftime('%b %-d, %Y')}). "
                                    f"Date shifted to {_rep_date.strftime('%b %-d, %Y')} — adjust as needed."
                                )],
                            }
                            st.rerun()

                if not _expanded and _lyr_total > 3:
                    st.caption(f"Top 3 of {_lyr_total} — click \"{_toggle_lbl}\" to see all.")

        # ── Panel 2: Upcoming calendar events ────────────────────────────────
        _us_evts_ctx = _us_events([today_d.year, today_d.year+1])
        # Show events in selected month
        _month_evts = sorted(
            [(d, n) for d, n in _us_evts_ctx.items()
             if d.month == _sel_month and d.year in (_sel_year, _lyr+1)],
            key=lambda x: x[0]
        )
        _evt_html = (
            '<div style="border:2px solid #000;border-radius:10px;padding:14px;'
            'background:#fff;margin-bottom:12px;">'
            '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
            'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;'
            'padding-bottom:8px;border-bottom:2px solid #000;margin-bottom:10px;">'
            f'EVENTS IN {_mon_name.upper()}'
            '</div>'
        )
        if not _month_evts:
            _evt_html += '<div style="font-size:11px;color:#888;">No major events this month.</div>'
        else:
            for _ed, _en in _month_evts:
                _days = (_ed - today_d).days
                _days_str = (f"in {_days}d" if _days > 0
                             else ("today" if _days == 0 else f"{abs(_days)}d ago"))
                _bg_dot = DOW_BG_DARK[_ed.weekday()]
                _evt_html += (
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:5px 0;border-bottom:1px solid #eee;font-family:Barlow,sans-serif;">'
                    f'<span style="font-size:11px;font-weight:600;">'
                    f'<span style="background:{_bg_dot};border-radius:3px;padding:1px 5px;'
                    f'font-size:9px;margin-right:4px;">{_ed.strftime("%-m/%-d")}</span>'
                    f'{_en}</span>'
                    f'<span style="font-size:10px;color:#888;">{_days_str}</span>'
                    f'</div>'
                )
        _evt_html += '</div>'
        st.markdown(_evt_html, unsafe_allow_html=True)

        # ── Panel 3: Priority categories to target ────────────────────────────
        _cutoff_30 = today_d - timedelta(days=30)
        _recent_cats = set(cal_df[cal_df["_date"] >= _cutoff_30]["Category"].dropna())

        # Score = avg_click rank + avg_conv rank + avg_rpr rank (higher = better)
        _cat_scores = (
            campaigns_df.groupby("Category").agg(
                avg_click = ("Click Rate",      "mean"),
                avg_conv  = ("Conversion Rate", "mean"),
                avg_rpr   = ("RPR",             "mean"),
            ).reset_index().dropna()
        )
        _cat_scores["score"] = (
            _cat_scores["avg_click"].rank() +
            _cat_scores["avg_conv"].rank() +
            _cat_scores["avg_rpr"].rank()
        )
        _priority_cats = (
            _cat_scores[~_cat_scores["Category"].isin(_recent_cats)]
            .sort_values("score", ascending=False)
        )

        with st.container(border=True):
            st.markdown(
                '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:11px;'
                'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;'
                'padding-bottom:6px;border-bottom:2px solid #000;margin-bottom:8px;">'
                'Priority Categories to Target'
                '<div style="font-size:8px;font-weight:600;color:#888;margin-top:2px;'
                'letter-spacing:0.04em;text-transform:none;font-family:Barlow,sans-serif;">'
                'Not sent in 30d &nbsp;·&nbsp; ranked by click + conv + RPR'
                '</div></div>',
                unsafe_allow_html=True
            )
            if _priority_cats.empty:
                st.caption("All high-performing categories were sent recently.")
            else:
                for _, _pr in _priority_cats.head(7).iterrows():
                    _code = CATEGORY_CODES.get(_pr["Category"], _pr["Category"][:3].upper())
                    _pcol1, _pcol2 = st.columns([5, 1])
                    with _pcol1:
                        st.markdown(
                            f'<div style="padding:6px 0;border-bottom:1px solid #f0f0f0;'
                            f'display:flex;align-items:center;gap:8px;">'
                            f'<span style="background:#feee35;padding:2px 6px;border-radius:3px;'
                            f'font-size:9px;font-weight:800;font-family:\'Barlow Condensed\',sans-serif;'
                            f'letter-spacing:0.05em;flex-shrink:0;">{_code}</span>'
                            f'<span style="font-size:12px;font-weight:600;">{_pr["Category"]}</span>'
                            f'<span style="color:#999;font-size:10px;white-space:nowrap;">'
                            f'{_pr["avg_click"]:.1%} click &nbsp;·&nbsp; {_pr["avg_conv"]:.2%} conv &nbsp;·&nbsp; {_pr["avg_rpr"]:.2f} RPR'
                            f'</span></div>',
                            unsafe_allow_html=True
                        )
                    with _pcol2:
                        if st.button("Use →", key=f"preset_{_pr['Category']}",
                                     use_container_width=True):
                            st.session_state["_preset_cat"] = _pr["Category"]
                            st.rerun()

    # ── Drafts list ───────────────────────────────────────────────────────────
    _drafts = st.session_state.get("plan_drafts", [])
    if _drafts:
        st.divider()
        st.markdown("<h3>Drafts</h3>", unsafe_allow_html=True)
        for _i, _dr in enumerate(_drafts):
            _ch_badge = "📧 Email" if _dr["channel"]=="email" else "📱 SMS"
            _d_str = _dr["send_date"].strftime("%b %-d, %Y") if isinstance(_dr.get("send_date"), date) else "—"
            _dc1, _dc2, _dc3 = st.columns([4, 1, 1])
            _dr_subj     = _dr.get("subject","")
            _dr_goal     = _dr.get("goal","")
            _dr_owner    = _dr.get("owner","")
            _dr_last_mod = _dr.get("last_modified_by","")
            _dr_last_ts  = _dr.get("last_saved","")
            try:
                _dr_ts_fmt = _datetime.strptime(_dr_last_ts, "%Y-%m-%d %H:%M:%S").strftime("%-m/%-d, %-I:%M %p")
            except Exception:
                _dr_ts_fmt = _dr_last_ts
            _dr_meta_parts = []
            if _dr_owner:
                _dr_meta_parts.append(f"👤 {_dr_owner}")
            if _dr_last_mod:
                _ts_sfx = f" · {_dr_ts_fmt}" if _dr_ts_fmt else ""
                _dr_meta_parts.append(f"Last edit: {_dr_last_mod}{_ts_sfx}")
            _dr_meta_html = (
                f'<div style="font-size:9px;color:#bbb;margin-top:3px;">'
                + " &nbsp;·&nbsp; ".join(_dr_meta_parts) + "</div>"
            ) if _dr_meta_parts else ""
            _dc1.markdown(
                f'<div style="padding:4px 0;">'
                f'<span style="background:#f0f0f0;border:1px solid #ccc;border-radius:3px;'
                f'padding:1px 6px;font-size:9px;font-weight:700;margin-right:6px;">DRAFT</span>'
                f'<strong>{_dr["name"]}</strong>'
                f'<span style="color:#888;font-size:11px;margin-left:8px;">{_ch_badge} · {_d_str}</span>'
                + (f'<div style="font-size:10px;color:#555;font-style:italic;margin-top:2px;margin-left:4px;">"{_dr_subj}"</div>' if _dr_subj else "")
                + (f'<div style="font-size:10px;color:#888;margin-left:4px;">Goal: {_dr_goal}</div>' if _dr_goal else "")
                + _dr_meta_html
                + f'</div>',
                unsafe_allow_html=True
            )
            if _dc2.button("Edit", key=f"edit_draft_{_i}"):
                # Pre-fill form from this draft
                st.session_state["nc_name"] = _dr.get("name","")
                st.session_state["nc_subj"] = _dr.get("subject","")
                st.session_state["nc_goal"] = _dr.get("goal","Conversion")
                st.session_state["nc_cat"]  = _dr.get("category","")
                st.session_state["nc_ch"]   = _dr.get("channel","email").title()
                st.session_state["nc_date"] = _dr.get("send_date", date.today())
                st.session_state["nc_auds"] = _dr.get("audiences",[])
                st.session_state["nc_prod"]  = _dr.get("product","(none)") or "(none)"
                st.session_state["nc_stu"]   = _dr.get("studio","(none)")  or "(none)"
                st.session_state["nc_owner"] = _dr.get("owner","Anna") or "Anna"
                st.session_state["plan_edit_idx"] = _i
                st.rerun()
            if _dc3.button("Add to Calendar", key=f"promote_draft_{_i}"):
                _entry = dict(
                    _dr,
                    status="planned",
                    last_modified_by=st.session_state.get("_app_user", ""),
                    last_saved=_datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                st.session_state["plan_added"].append(_entry)
                st.session_state["plan_drafts"].pop(_i)
                _sync_to_sheet(_entry)
                st.rerun()



# ── Page nav ──────────────────────────────────────────────────────────────────
st.divider()
_, next_col = st.columns([5, 1])
with next_col:
    st.page_link("pages/2_Decisioning.py", label="Decisioning →")
