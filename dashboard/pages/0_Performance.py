import sys, re as _re
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from shared.styles import COLORS, CMAP, inject_css, plot_theme, top_nav
import numpy as np
from collections import Counter
from shared.data import load_data, load_product_studio, load_list_growth, fmt_revenue

inject_css()
top_nav("Performance")

st.markdown(f"""
<style>
  .kpi-group-wrap {{
    display: flex;
    gap: 0;
    align-items: stretch;
  }}
  .kpi-group {{
    display: flex;
    flex-direction: column;
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    overflow: hidden;
    flex: 1;
  }}
  .kpi-group-label {{
    font-family: 'Barlow', sans-serif;
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {COLORS['muted']};
    background: {COLORS['offwhite']};
    border-bottom: 1px solid {COLORS['border']};
    padding: 5px 12px;
  }}
  .kpi-group-cells {{
    display: flex;
    flex: 1;
  }}
  .kpi-cell {{
    flex: 1;
    padding: 10px 14px;
    border-right: 1px solid {COLORS['border']};
    background: {COLORS['white']};
  }}
  .kpi-cell:last-child {{ border-right: none; }}
  .kpi-label {{
    font-family: 'Barlow', sans-serif;
    font-size: 0.6rem;
    font-weight: 500;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: {COLORS['muted']};
    margin-bottom: 4px;
    white-space: nowrap;
  }}
  .kpi-value {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: {COLORS['black']};
    line-height: 1;
    white-space: nowrap;
    letter-spacing: 0.01em;
  }}
  .kpi-value.issues {{ color: {COLORS['danger']}; }}
  .kpi-group-divider {{ width: 12px; flex-shrink: 0; }}
</style>
""", unsafe_allow_html=True)

# ── Data Connections Banner (Performance) ─────────────────────────────────────
_PERF_CONNECTIONS = [
    {
        "name":   "Klaviyo",
        "abbr":   "KL",
        "color":  "#1a1a1a",
        "status": "mock data",
        "what":   "Historical campaign performance data",
        "why":    "Drives all metrics shown — open, click, conversion, revenue, unsub, RPR across campaigns and flows",
    },
    {
        "name":   "Klaviyo Events",
        "abbr":   "KE",
        "color":  "#555",
        "status": "not connected",
        "what":   "All customer events data (optional)",
        "why":    "Enables deeper attribution — links individual open/click/purchase events to specific campaigns and segments",
    },
]
_PERF_STATUS_STYLE = {
    "mock data":     ("background:#f5f000;color:#000;", "Mock data"),
    "connected":     ("background:#caf30b;color:#000;", "Connected"),
    "not connected": ("background:#f2f2f2;color:#888;", "Not connected"),
    "tbd":           ("background:#e8c5ff;color:#000;", "Connection Unknown"),
}
_perf_conn_html = (
    '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:18px;">'
)
for _pc in _PERF_CONNECTIONS:
    _pst_css, _pst_lbl = _PERF_STATUS_STYLE.get(_pc["status"], ("background:#eee;color:#666;", _pc["status"]))
    _perf_conn_html += (
        f'<div style="border:1.5px solid #e4e4e4;border-radius:8px;padding:12px 14px;background:#fff;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        f'<span style="background:{_pc["color"]};color:#fff;border-radius:5px;'
        f'width:26px;height:26px;display:inline-flex;align-items:center;justify-content:center;'
        f'font-family:\'Barlow Condensed\',sans-serif;font-size:10px;font-weight:900;'
        f'letter-spacing:0.04em;flex-shrink:0;">{_pc["abbr"]}</span>'
        f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:13px;'
        f'font-weight:800;letter-spacing:0.04em;color:#000;">{_pc["name"]}</span>'
        f'<span style="margin-left:auto;{_pst_css}border-radius:4px;padding:1px 7px;'
        f'font-size:9px;font-weight:700;white-space:nowrap;font-family:Barlow,sans-serif;'
        f'letter-spacing:0.04em;text-transform:uppercase;">{_pst_lbl}</span>'
        f'</div>'
        f'<div style="font-family:Barlow,sans-serif;font-size:11px;font-weight:600;'
        f'color:#000;margin-bottom:3px;line-height:1.4;">{_pc["what"]}</div>'
        f'<div style="font-family:Barlow,sans-serif;font-size:10px;color:#888;line-height:1.4;">'
        f'{_pc["why"]}</div>'
        f'</div>'
    )
_perf_conn_html += '</div>'

st.markdown("<h1>Performance</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style=\"font-family:'Barlow',sans-serif;font-size:0.78rem;color:#888;"
    "margin:-0.4rem 0 0.75rem;font-style:italic;line-height:1.5;\">"
    "Prototype dashboard — not designed to replace current performance dashboards (Power BI etc.) "
    "but to back suggestions during campaign planning. Open question during scoping phase.</p>",
    unsafe_allow_html=True,
)

campaigns_df, flow_monthly, flow_msgs, benchmarks = load_data()

# ── Data connection (shown above all tabs) ────────────────────────────────────
st.markdown(
    "<div style=\"font-family:'Barlow Condensed',sans-serif;font-size:11px;font-weight:700;"
    "letter-spacing:0.08em;text-transform:uppercase;"
    "color:#888;margin:0 0 6px;\">Data connections</div>",
    unsafe_allow_html=True,
)
st.markdown(_perf_conn_html, unsafe_allow_html=True)

tab_camp, tab_flow, tab_ps, tab_channels = st.tabs(
    ["Campaigns", "Flows", "Products & Studios", "Channels"]
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def kpi_cell(label, value, issue=False):
    cls = "kpi-value issues" if issue else "kpi-value"
    return (f'<div class="kpi-cell"><div class="kpi-label">{label}</div>'
            f'<div class="{cls}">{value}</div></div>')

def kpi_group(group_label, cells_html):
    return (f'<div class="kpi-group"><div class="kpi-group-label">{group_label}</div>'
            f'<div class="kpi-group-cells">{cells_html}</div></div>')

def fmt_pct(val, decimals=1):
    return "—" if pd.isna(val) else f"{val * 100:.{decimals}f}%"

def fmt_rev_consistent(vals):
    mx = vals.max() if hasattr(vals, "max") else vals
    if mx >= 1_000_000:
        return lambda v: f"${v/1e6:.1f}M"
    return lambda v: f"${v/1e3:.1f}K"

def _bg(val, ind, good, great, lower_better=False):
    """4-tier: red=below industry / yellow=ind→good / light-green=good→great / dark-green=above great"""
    if pd.isna(val) or ind is None or good is None or great is None:
        return ""
    if lower_better:
        if val <= great: return "#81C784"
        if val <= good:  return "#C8F7C5"
        if val <= ind:   return "#FFF9C4"
        return "#FFCDD2"
    else:
        if val >= great: return "#81C784"
        if val >= good:  return "#C8F7C5"
        if val >= ind:   return "#FFF9C4"
        return "#FFCDD2"

def _sent_fmt(n):
    return f"{n/1e6:.1f}M" if n >= 1e6 else f"{n/1e3:.0f}K"

def _pill(ch):
    if ch == "email":
        return ('<span style="background:#1a1a1a;color:#ffffff;padding:2px 8px;'
                'border-radius:4px;font-size:0.63rem;font-weight:600;'
                'font-family:\'Barlow\',sans-serif;">EMAIL</span>')
    return ('<span style="background:#f0f0f0;color:#444;padding:2px 8px;'
            'border-radius:4px;font-size:0.63rem;font-weight:600;'
            'border:1px solid #ddd;font-family:\'Barlow\',sans-serif;">SMS</span>')

THEME_PATTERNS = [
    ("Urgency",          r'today only|flash|\d+\s*hr\b|ends |last chance|tmrw|tonight'),
    ("Discount/Promo",   r'\d+\s*%\s*off|save|sale\b|markdowns|free '),
    ("New / Launch",     r'new drop|now open|opens soon|launch|introducing|just dropped'),
    ("Restock",          r'back in stock|it.s back|back:'),
    ("FOMO / Winback",   r'forget|forgot|skip|miss|you didn|you clicked|left behind|really skip'),
    ("Question",         r'\?'),
    ("Has Emoji",        r'[\U0001F300-\U0001FAFF\u2600-\u27BF]'),
    ("Product-Specific", r'flatback|hoop|huggi|clicker|pearl|opal|diamond|stud|earring'),
    ("Studio / Appt",    r'appt|appointment|studio|piercing at|free.*pierc|pierc.*free'),
    ("Editorial",        r'trend|the edit|wellness|101|anatomy|guide|how to'),
]

def detect_themes(text):
    t = str(text)
    tags = [name for name, pat in THEME_PATTERNS
            if _re.search(pat, t, flags=_re.IGNORECASE)]
    return tags if tags else ["Other"]

CAT_PALETTE = [
    "#1a1a1a","#555555","#888888","#AAAAAA","#CCCCCC",
    "#4A7FA5","#7BAFD4","#A8C8E0","#6B8F71","#9BBE9F",
    "#C4956A","#E2B48A","#B87D6B","#D4A999",
]

# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGNS TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_camp:
    df = campaigns_df.copy()

    # ── Filters ─────────────────────────────────────────────────────────────
    f1, f2, f3, _ = st.columns([1.5, 1.5, 1.5, 5])
    years     = sorted(df["Send Date"].dt.year.dropna().unique().astype(int).tolist(), reverse=True)
    ch_opts   = ["All Channels", "Email", "SMS"]
    cat_opts  = ["All Categories"] + sorted(df["Category"].dropna().unique().tolist())

    with f1: sel_year = st.selectbox("Year", ["All Years"] + [str(y) for y in years], key="pc_yr")
    with f2: sel_ch   = st.selectbox("Channel", ch_opts, key="pc_ch")
    with f3: sel_cat  = st.selectbox("Category", cat_opts, key="pc_cat")

    filt = df.copy()
    if sel_year != "All Years":           filt = filt[filt["Send Date"].dt.year == int(sel_year)]
    if sel_ch == "Email":                 filt = filt[filt["Channel"] == "email"]
    elif sel_ch == "SMS":                 filt = filt[filt["Channel"] == "sms"]
    if sel_cat != "All Categories":       filt = filt[filt["Category"] == sel_cat]

    # ── Pull benchmark values ─────────────────────────────────────────────────
    def _bval(metric, col):
        row = benchmarks[benchmarks["Metric"] == metric]
        return float(row[col].iloc[0]) if not row.empty else None

    BM = {
        "open":   {"ind": _bval("Open Rate (Campaign)",       "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Open Rate (Campaign)",      "Good"),
                   "great": _bval("Open Rate (Campaign)",     "Great")},
        "click":  {"ind": _bval("Click Rate (Campaign)",      "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Click Rate (Campaign)",     "Good"),
                   "great": _bval("Click Rate (Campaign)",    "Great")},
        "ctor":   {"ind": _bval("CTOR (Campaign)",            "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("CTOR (Campaign)",           "Good"),
                   "great": _bval("CTOR (Campaign)",          "Great")},
        "conv":   {"ind": _bval("Conversion Rate (Campaign)", "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Conversion Rate (Campaign)","Good"),
                   "great": _bval("Conversion Rate (Campaign)","Great")},
        "rpr":    {"ind": _bval("RPR (Campaign)",             "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("RPR (Campaign)",            "Good"),
                   "great": _bval("RPR (Campaign)",           "Great")},
        "del":    {"ind": _bval("Delivery Rate",              "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Delivery Rate",             "Good"),
                   "great": _bval("Delivery Rate",            "Great")},
        "unsub":  {"ind": _bval("Unsub Rate (Campaign)",      "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Unsub Rate (Campaign)",     "Good"),
                   "great": _bval("Unsub Rate (Campaign)",    "Great")},
        "spam":   {"ind": _bval("Spam Rate (Campaign)",       "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Spam Rate (Campaign)",      "Good"),
                   "great": _bval("Spam Rate (Campaign)",     "Great")},
    }

    # SMS-specific benchmarks (fall back to email benchmarks where no SMS value)
    BM_SMS = {
        "open":  None,  # not tracked for SMS
        "click": {"ind": _bval("SMS Click Rate", "Industry Median (DTC Jewelry/Beauty)"),
                  "good": _bval("SMS Click Rate", "Good"),
                  "great": _bval("SMS Click Rate", "Great")},
        "ctor":  None,  # not tracked for SMS
        "conv":  {"ind": _bval("SMS Conv Rate",  "Industry Median (DTC Jewelry/Beauty)"),
                  "good": _bval("SMS Conv Rate",  "Good"),
                  "great": _bval("SMS Conv Rate",  "Great")},
        "rpr":   BM["rpr"],
        "del":   BM["del"],
        "unsub": {"ind": _bval("SMS Unsub Rate", "Industry Median (DTC Jewelry/Beauty)"),
                  "good": _bval("SMS Unsub Rate", "Good"),
                  "great": _bval("SMS Unsub Rate", "Great")},
        "spam":  None,  # not tracked for SMS
    }

    # ── KPI computations (weighted averages: sum numerator / sum denominator) ─
    total_camps   = len(filt)
    months_span   = filt["Send Date"].dt.to_period("M").nunique()
    avg_per_month = total_camps / months_span if months_span else 0
    total_rev     = filt["Revenue"].sum()
    avg_camp_rev  = total_rev / total_camps if total_camps else 0

    _sent_sum  = filt["Recipients"].sum()
    _del_sum   = filt["Delivered"].sum()
    _opens_sum = filt["Unique Opens"].sum()
    _clicks_sum= filt["Unique Clicks"].sum()
    _conv_sum  = filt["Unique Conversions"].sum()
    _unsub_sum = filt["Unsubscribes"].sum()

    avg_rpr   = total_rev    / _del_sum    if _del_sum   else 0
    avg_aov   = total_rev    / _conv_sum   if _conv_sum  else 0
    avg_open  = _opens_sum   / _del_sum    if _del_sum   else 0
    avg_click = _clicks_sum  / _del_sum    if _del_sum   else 0
    avg_conv  = _conv_sum    / _del_sum    if _del_sum   else 0
    avg_unsub = _unsub_sum   / _del_sum    if _del_sum   else 0

    rfmt = fmt_rev_consistent(pd.Series([total_rev, avg_camp_rev]))

    # ── KPI Strip ────────────────────────────────────────────────────────────
    strip_html = (
        '<div class="kpi-group-wrap">'
        + kpi_group("Volume",
            kpi_cell("Campaigns", f"{total_camps:,}") +
            kpi_cell("Avg / Month", f"{avg_per_month:.1f}"))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Financials",
            kpi_cell("Revenue", rfmt(total_rev)) +
            kpi_cell("Avg Campaign Rev", rfmt(avg_camp_rev)) +
            kpi_cell("Avg RPR", f"${avg_rpr:.2f}") +
            kpi_cell("AOV", f"${avg_aov:,.0f}"))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Performance",
            kpi_cell("Open Rate", "—" if sel_ch == "SMS" else fmt_pct(avg_open)) +
            kpi_cell("Click Rate", fmt_pct(avg_click)) +
            kpi_cell("Conv. Rate", fmt_pct(avg_conv)))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Issues", kpi_cell("Unsub Rate", fmt_pct(avg_unsub), issue=True))
        + '</div>'
    )
    st.markdown(strip_html, unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Benchmarks banner ────────────────────────────────────────────────────
    # benchmark tier helper — used inside the table row below
    def _bm_tier(ind, good, great, fmt_fn):
        s = "font-family:'Barlow',sans-serif;font-size:0.6rem;display:block;line-height:1.55;"
        return (
            f'<span style="{s}color:#999;">{fmt_fn(ind)}</span>'
            f'<span style="{s}color:#E07B00;">{fmt_fn(good)}</span>'
            f'<span style="{s}color:#1a9e3f;">{fmt_fn(great)}</span>'
        )
    def _pct(v):  return f"{v*100:.1f}%"
    def _pct2(v): return f"{v*100:.2f}%"
    def _dollar(v): return f"${v:.2f}"

    # ── Click rate by category + Revenue pie ─────────────────────────────────
    st.markdown("<h2>Revenue by Category</h2>", unsafe_allow_html=True)

    filt_dated = filt.dropna(subset=["Send Date", "Revenue"]).copy()
    filt_dated["Month"] = filt_dated["Send Date"].dt.to_period("M").dt.to_timestamp()

    cat_rev_total = filt_dated.groupby("Category")["Revenue"].sum().sort_values(ascending=False)
    cat_order_rev = cat_rev_total.index.tolist()
    cat_color_map = {cat: CAT_PALETTE[i % len(CAT_PALETTE)] for i, cat in enumerate(cat_order_rev)}

    # Monthly revenue per category — used for anomaly detection
    monthly_cat = filt_dated.groupby(["Month", "Category"])["Revenue"].sum().reset_index()

    # Click rate by category (weighted average: sum unique clicks / sum delivered)
    click_cat = (
        filt.dropna(subset=["Category"])
        .groupby("Category").agg(
            Campaigns  = ("Campaign Name", "count"),
            _Clicks    = ("Unique Clicks", "sum"),
            _Delivered = ("Delivered",     "sum"),
        ).reset_index()
    )
    click_cat["Click_Rate"] = click_cat["_Clicks"] / click_cat["_Delivered"].replace(0, pd.NA)
    click_cat = click_cat.dropna(subset=["Click_Rate"]).sort_values("Click_Rate", ascending=False)

    rv1, rv2 = st.columns([3, 2])
    with rv1:
        fig_cat = px.bar(
            click_cat,
            x="Click_Rate", y="Category", orientation="h",
            color="Click_Rate",
            color_continuous_scale=[[0,"#FFCDD2"],[0.4,"#FFF9C4"],[1,"#C8F7C5"]],
            title="AVG CLICK RATE BY CATEGORY",
            height=380,
            text=click_cat["Click_Rate"].apply(lambda v: f"{v:.2%}"),
            labels={"Click_Rate": "Avg Click Rate", "Category": ""},
            hover_data={"Campaigns": True, "Click_Rate": ":.2%",
                        "_Clicks": False, "_Delivered": False},
        )
        fig_cat.update_layout(**plot_theme(
            yaxis=dict(autorange="reversed", tickfont=dict(size=10),
                       showgrid=False, zeroline=False),
            xaxis=dict(showgrid=True, gridcolor=COLORS["border"],
                       zeroline=False, tickformat=".1%", tickfont=dict(size=10)),
            coloraxis_showscale=False,
        ))
        fig_cat.update_traces(textposition="outside",
                              textfont=dict(size=10, family="Barlow, sans-serif"),
                              marker_line_width=1, marker_line_color=COLORS["black"])
        st.plotly_chart(fig_cat, use_container_width=True)

    with rv2:
        pie_df = cat_rev_total.reset_index()
        pie_df.columns = ["Category", "Revenue"]
        fig_pie = px.pie(
            pie_df, values="Revenue", names="Category",
            color="Category", color_discrete_map=cat_color_map,
            title="REVENUE SHARE BY CATEGORY", height=300, hole=0.38,
        )
        fig_pie.update_layout(
            paper_bgcolor=COLORS["white"],
            font=dict(family="Barlow, sans-serif", size=11),
            title_font=dict(family="Barlow Condensed, sans-serif", size=13, color=COLORS["black"]),
            title_x=0, margin=dict(l=0, r=0, t=40, b=0),
            legend=dict(font=dict(size=9), orientation="v",
                        yanchor="middle", y=0.5, xanchor="left", x=1.01),
            showlegend=True,
        )
        fig_pie.update_traces(
            textposition="inside", textinfo="percent",
            textfont=dict(size=9, family="Barlow, sans-serif"),
            marker=dict(line=dict(color=COLORS["white"], width=1.5)),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        # ── Revenue spike / anomaly detection ────────────────────────────────
        _SEASONAL = {
            2: "likely Valentine's Day",  5: "likely Mother's Day",
            6: "likely Father's Day",    11: "likely BFCM",
            12: "likely holiday gifting",
        }
        anomalies = []
        for cat, grp in monthly_cat.groupby("Category"):
            if len(grp) < 3:
                continue
            mean_rev = grp["Revenue"].mean()
            std_rev  = grp["Revenue"].std()
            if not std_rev or pd.isna(std_rev):
                continue
            spike_mask = (grp["Revenue"] > mean_rev + 1.5 * std_rev) &                          (grp["Revenue"] > mean_rev * 1.5)
            for _, s in grp[spike_mask].iterrows():
                label = _SEASONAL.get(s["Month"].month, "likely seasonal event")
                anomalies.append((cat, s["Month"], s["Revenue"], s["Revenue"] / mean_rev, label))

        if anomalies:
            anomalies.sort(key=lambda x: x[3], reverse=True)
            items_html = ""
            for cat, month_ts, rev, mult, label in anomalies[:6]:
                mstr = month_ts.strftime("%b %Y")
                items_html += (
                    f"<div style=\"padding:5px 0;border-bottom:1px solid #f0f0f0;line-height:1.4;\">"
                    f"<span style=\"font-family:'Barlow',sans-serif;font-size:0.73rem;"
                    f"font-weight:600;color:#333;\">{mstr} · {cat}</span>&nbsp;"
                    f"<span style=\"font-family:'Barlow',sans-serif;font-size:0.7rem;color:#666;\">"
                    f"${rev/1e3:.0f}K ({mult:.1f}× avg)</span><br>"
                    f"<span style=\"font-family:'Barlow',sans-serif;font-size:0.62rem;"
                    f"color:#999;font-style:italic;\">{label} — discount when benchmarking</span>"
                    f"</div>"
                )
            st.markdown(
                f"<div style=\"margin-top:2px;\">"
                f"<div style=\"font-family:'Barlow Condensed',sans-serif;font-size:0.6rem;"
                f"letter-spacing:0.09em;text-transform:uppercase;color:#888;margin-bottom:5px;\">"
                f"⚠ Revenue spikes to discount</div>{items_html}</div>",
                unsafe_allow_html=True,
            )

    # ── Performance & Issues by Category ─────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h2>Performance & Issues by Category</h2>", unsafe_allow_html=True)

    perf_df = filt.copy()

    # Sum raw count columns per Category+Channel, then derive rates (weighted averages)
    perf_tbl = (
        perf_df.groupby(["Category", "Channel"]).agg(
            Campaigns    = ("Campaign Name",      "count"),
            Sent         = ("Recipients",         "sum"),
            _Delivered   = ("Delivered",          "sum"),
            _UniqueOpens = ("Unique Opens",       "sum"),
            _UniqueClicks= ("Unique Clicks",      "sum"),
            _UniqueConv  = ("Unique Conversions", "sum"),
            Revenue      = ("Revenue",            "sum"),
            _Unsubs      = ("Unsubscribes",       "sum"),
            _Spam        = ("Spam Complaints",    "sum"),
        ).reset_index().sort_values(["Category", "Channel"])
    )
    _D  = perf_tbl["_Delivered"].replace(0, pd.NA)
    _S  = perf_tbl["Sent"].replace(0, pd.NA)
    _O  = perf_tbl["_UniqueOpens"].replace(0, pd.NA)
    perf_tbl["Del_Rate"]   = perf_tbl["_Delivered"]    / _S
    perf_tbl["Open_Rate"]  = perf_tbl["_UniqueOpens"]  / _D
    perf_tbl["Click_Rate"] = perf_tbl["_UniqueClicks"] / _D
    perf_tbl["CTOR"]       = perf_tbl["_UniqueClicks"] / _O
    perf_tbl["Conv_Rate"]  = perf_tbl["_UniqueConv"]   / _D
    perf_tbl["RPR"]        = perf_tbl["Revenue"]       / _D
    perf_tbl["Unsub_Rate"] = perf_tbl["_Unsubs"]       / _D
    perf_tbl["Spam_Rate"]  = perf_tbl["_Spam"]         / _D
    # Email rows first, then SMS; alphabetical within each channel
    perf_tbl["_ch_ord"] = perf_tbl["Channel"].map({"email": 0, "sms": 1})
    perf_tbl = perf_tbl.sort_values(["_ch_ord", "Category"]).drop(columns="_ch_ord").reset_index(drop=True)

    # 13 cols: Category(11%) | Channel(7%) | 11 equal numeric cols (no Bounce Rate)
    GCOLS = "11% 7% " + " ".join(["7.5%"] * 10) + " auto"

    def _cell(val, bg="", align="center", bold=False, sep=False):
        b = "font-weight:600;" if bold else ""
        s = "border-right:3px solid rgba(0,0,0,0.12);" if sep else ""
        bg_s = f"background:{bg};" if bg else ""
        return (f'<div style="padding:7px 5px;text-align:{align};display:flex;align-items:center;'
                f'{"justify-content:center;" if align=="center" else ""}'
                f'{bg_s}{b}{s}">{val}</div>')

    def _campaign_rows(cat, ch, bm_set):
        def _b(key, level):
            d = bm_set.get(key)
            return d.get(level) if d else None
        sub = filt[(filt["Category"] == cat) & (filt["Channel"] == ch)]\
              .dropna(subset=["Click Rate", "Subject Line"]).copy()
        if sub.empty:
            return "<p style='padding:8px;font-size:0.75rem;color:#888'>No campaigns</p>"

        # Sum raw counts per subject line, derive rates (weighted averages)
        grp = (
            sub.groupby("Subject Line").agg(
                Uses         = ("Campaign Name",      "count"),
                Sent         = ("Recipients",         "sum"),
                _Delivered   = ("Delivered",          "sum"),
                _UniqueOpens = ("Unique Opens",       "sum"),
                _UniqueClicks= ("Unique Clicks",      "sum"),
                _UniqueConv  = ("Unique Conversions", "sum"),
                Revenue      = ("Revenue",            "sum"),
                _Unsubs      = ("Unsubscribes",       "sum"),
                _Spam        = ("Spam Complaints",    "sum"),
            ).reset_index()
        )
        _D  = grp["_Delivered"].replace(0, pd.NA)
        _S  = grp["Sent"].replace(0, pd.NA)
        _O  = grp["_UniqueOpens"].replace(0, pd.NA)
        grp["Del_Rate"]   = grp["_Delivered"]    / _S
        grp["Open_Rate"]  = grp["_UniqueOpens"]  / _D
        grp["Click_Rate"] = grp["_UniqueClicks"] / _D
        grp["CTOR"]       = grp["_UniqueClicks"] / _O
        grp["Conv_Rate"]  = grp["_UniqueConv"]   / _D
        grp["RPR"]        = grp["Revenue"]       / _D
        grp["Unsub_Rate"] = grp["_Unsubs"]       / _D
        grp["Spam_Rate"]  = grp["_Spam"]         / _D
        grp = grp.sort_values("Click_Rate", ascending=False)
        cat_avg = grp["Click_Rate"].mean()

        # shared grid style — same GCOLS as parent so columns align exactly
        grid_style = f"display:grid;grid-template-columns:{GCOLS};align-items:center;"

        # map bg color → text color for the inner rows (colored text, neutral bg)
        _BG_TO_TEXT = {
            "#FFCDD2": "#C0392B",  # red
            "#FFF9C4": "#9A7D00",  # dark yellow
            "#C8F7C5": "#1e7e34",  # light green
            "#81C784": "#145a23",  # dark green
        }

        def _dc(val, bg="", bold=False, sep=False):
            """Inner data cell — colored text on neutral bg instead of colored bg."""
            txt_color = _BG_TO_TEXT.get(bg, "#222")
            fw  = "font-weight:700;" if (bg or bold) else "font-weight:400;"
            br  = "border-right:3px solid rgba(0,0,0,0.08);" if sep else ""
            return (f'<div style="padding:5px 4px;text-align:center;font-size:0.73rem;'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'color:{txt_color};{fw}{br}">{val}</div>')

        # column-header row (inherits same grid)
        lbl = ("font-family:'Barlow Condensed',sans-serif;font-size:0.6rem;"
               "letter-spacing:0.08em;text-transform:uppercase;color:#999;padding:4px 4px;text-align:center;")
        _inner_tips = {
            "Sent":     "Total recipients (sends)",
            "Revenue":  "Sum of revenue attributed ($K)",
            "RPR":      "Revenue ÷ Delivered",
            "Del.":     "Delivered ÷ Recipients",
            "Open":     "Unique Opens ÷ Delivered",
            "Click ★":  "Unique Clicks ÷ Delivered",
            "CTOR":     "Unique Clicks ÷ Unique Opens",
            "Conv":     "Unique Conversions ÷ Delivered",
            "Unsub":    "Unsubscribes ÷ Delivered",
            "Spam":     "Spam Complaints ÷ Delivered",
        }
        hdr = (
            f'<div style="{grid_style}background:#f0f0f0;border-bottom:1px solid #ddd;">'
            f'<div style="{lbl}text-align:left;padding-left:8px;grid-column:span 2;">Subject Line</div>'
            f'<div title="Number of times this subject line was used" style="{lbl}border-right:3px solid #ddd;cursor:help;"># Uses</div>'
            + "".join(f'<div title="{_inner_tips.get(h,"")}" style="{lbl}cursor:help;">{h}</div>'
                      for h in ["Sent","Revenue","RPR","Del.","Open","Click ★","CTOR","Conv","Unsub","Spam"])
            + '</div>'
        )

        rows_html = ""
        for _, c in grp.iterrows():
            themes = detect_themes(c["Subject Line"])
            theme_html = " ".join(
                f'<span style="background:#f0f0f0;color:#666;padding:1px 4px;border-radius:3px;'
                f'font-size:0.56rem;font-weight:500;">{t}</span>'
                for t in themes if t != "Other"
            )
            # adaptive font size: shrink long subject lines, clamp to 2 lines
            sl_len  = len(c["Subject Line"])
            sl_fs   = "0.65rem" if sl_len > 45 else "0.72rem"
            sl_html = (
                f'<div style="padding:5px 6px 5px 8px;font-size:{sl_fs};line-height:1.3;'
                f'overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;'
                f'-webkit-box-orient:vertical;word-break:break-word;grid-column:span 2;">'
                f'{c["Subject Line"]}'
                f'<span style="display:block;margin-top:2px;">{theme_html}</span></div>'
            )
            click_bg  = _bg(c["Click_Rate"], _b("click","ind"), _b("click","good"), _b("click","great"))
            open_cell = _dc("—") if ch == "sms" else \
                        _dc(f'{c["Open_Rate"]:.1%}', bg=_bg(c["Open_Rate"], _b("open","ind"), _b("open","good"), _b("open","great")))

            rows_html += (
                f'<div style="{grid_style}border-bottom:1px solid #eee;">'
                + sl_html
                + _dc(int(c["Uses"]), bold=True, sep=True)
                + _dc(f'{c["Sent"]/1e3:.0f}K')
                + _dc(f'${c["Revenue"]/1e3:.1f}K')
                + _dc(f'${c["RPR"]:.2f}',       bg=_bg(c["RPR"],        _b("rpr","ind"),   _b("rpr","good"),   _b("rpr","great")),  sep=True)
                + _dc(f'{c["Del_Rate"]:.1%}',   bg=_bg(c["Del_Rate"],   _b("del","ind"),   _b("del","good"),   _b("del","great")))
                + open_cell
                + _dc(f'{c["Click_Rate"]:.2%}', bg=click_bg, bold=True)
                + (_dc("—") if ch == "sms" else _dc(f'{c["CTOR"]:.1%}', bg=_bg(c["CTOR"], _b("ctor","ind"), _b("ctor","good"), _b("ctor","great"))))
                + _dc(f'{c["Conv_Rate"]:.2%}',  bg=_bg(c["Conv_Rate"],  _b("conv","ind"),  _b("conv","good"),  _b("conv","great")),  sep=True)
                + _dc(f'{c["Unsub_Rate"]:.2%}', bg=_bg(c["Unsub_Rate"], _b("unsub","ind"), _b("unsub","good"), _b("unsub","great"), True))
                + (_dc("—") if ch == "sms" else _dc(f'{c["Spam_Rate"]:.2%}', bg=_bg(c["Spam_Rate"], _b("spam","ind"), _b("spam","good"), _b("spam","great"), True)))
                + '</div>'
            )

        return hdr + rows_html

    # ── SMS benchmark row (injected above first SMS data row) ────────────────
    _dash_bm = ('<div style="padding:7px 5px;text-align:center;font-family:\'Barlow\',sans-serif;'
                'color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>')
    def _sms_bm_cell(key, fmt_fn, lower_better=False, sep=False):
        d = BM_SMS.get(key)
        sep_s = "border-right:3px solid #4a90d9;" if sep else ""
        if not d or d.get("ind") is None:
            return f'<div style="padding:7px 5px;text-align:center;{sep_s}font-family:\'Barlow\',sans-serif;color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>'
        if lower_better:
            content = _bm_tier(d["ind"], d["good"], d["great"], fmt_fn)
        else:
            content = _bm_tier(d["ind"], d["good"], d["great"], fmt_fn)
        return f'<div style="padding:7px 5px;text-align:center;{sep_s}">{content}</div>'

    sms_bm_html = f"""
    <div style="display:grid;grid-template-columns:{GCOLS};
                background:#f0f5ff;border-bottom:2px solid #4a90d9;
                border-left:4px solid #4a90d9;">
      <div style="padding:7px 9px;font-family:'Barlow Condensed',sans-serif;font-size:0.68rem;
                  font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:#2a5090;
                  display:flex;align-items:center;">SMS BENCHMARK</div>
      <div style="padding:7px 8px;font-family:'Barlow',sans-serif;font-size:0.6rem;
                  color:#999;border-right:3px solid #4a90d9;display:flex;flex-direction:column;
                  justify-content:center;line-height:1.55;">
        <span style="color:#999;">Industry</span>
        <span style="color:#E07B00;">Good</span>
        <span style="color:#1a9e3f;">Great</span>
      </div>
      {_dash_bm}{_dash_bm}{_dash_bm}
      <div style="padding:7px 5px;text-align:center;border-right:3px solid #4a90d9;">{_bm_tier(BM["rpr"]["ind"], BM["rpr"]["good"], BM["rpr"]["great"], _dollar)}<span style="display:block;font-size:0.52rem;color:#aaa;font-style:italic;margin-top:1px;">email</span></div>
      <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["del"]["ind"], BM["del"]["good"], BM["del"]["great"], _pct)}<span style="display:block;font-size:0.52rem;color:#aaa;font-style:italic;margin-top:1px;">email</span></div>
      {_dash_bm}
      {_sms_bm_cell("click", _pct2)}
      {_dash_bm}
      <div style="padding:7px 5px;text-align:center;border-right:3px solid #4a90d9;">{_bm_tier(BM_SMS["conv"]["ind"], BM_SMS["conv"]["good"], BM_SMS["conv"]["great"], _pct2) if BM_SMS["conv"] and BM_SMS["conv"].get("ind") else "—"}</div>
      {_sms_bm_cell("unsub", _pct2, lower_better=True)}
      {_dash_bm}
    </div>"""

    detail_rows_html = ""
    sms_bm_injected  = False
    for _, r in perf_tbl.iterrows():
        is_sms  = r["Channel"] == "sms"
        bm_set  = BM_SMS if is_sms else BM
        def _br(key, level, _bm=bm_set):
            d = _bm.get(key)
            return d.get(level) if d else None

        # Inject SMS benchmark row once, before first SMS data row
        if is_sms and not sms_bm_injected:
            detail_rows_html += sms_bm_html
            sms_bm_injected = True

        detail_rows_html += f"""
        <details class="perf-row" style="border-bottom:1px solid #e8e8e8;">
          <summary style="cursor:pointer;display:block;">
            <div class="row-grid" style="display:grid;grid-template-columns:{GCOLS};
                        align-items:stretch;font-size:0.8rem;min-height:40px;">
              {_cell('<span class="toggle-icon"></span>' + r["Category"], align="left", bold=True)}
              {_cell(_pill(r["Channel"]), align="left", sep=True)}
              {_cell(str(int(r["Campaigns"])))}
              {_cell(f'{r["Sent"]/1e6:.1f}M')}
              {_cell(f'${r["Revenue"]/1e6:.1f}M')}
              {_cell(f'${r["RPR"]:.2f}',       bg=_bg(r["RPR"],        _br("rpr","ind"),   _br("rpr","good"),   _br("rpr","great")),  sep=True)}
              {_cell(f'{r["Del_Rate"]:.1%}',   bg=_bg(r["Del_Rate"],   _br("del","ind"),   _br("del","good"),   _br("del","great")))}
              {_cell("—") if is_sms else _cell(f'{r["Open_Rate"]:.1%}', bg=_bg(r["Open_Rate"], _br("open","ind"), _br("open","good"), _br("open","great")))}
              {_cell(f'{r["Click_Rate"]:.2%}', bg=_bg(r["Click_Rate"], _br("click","ind"), _br("click","good"), _br("click","great")))}
              {_cell("—") if is_sms else _cell(f'{r["CTOR"]:.1%}', bg=_bg(r["CTOR"], _br("ctor","ind"), _br("ctor","good"), _br("ctor","great")))}
              {_cell(f'{r["Conv_Rate"]:.2%}',  bg=_bg(r["Conv_Rate"],  _br("conv","ind"),  _br("conv","good"),  _br("conv","great")),  sep=True)}
              {_cell(f'{r["Unsub_Rate"]:.2%}', bg=_bg(r["Unsub_Rate"], _br("unsub","ind"), _br("unsub","good"), _br("unsub","great"), True))}
              {_cell("—") if is_sms else _cell(f'{r["Spam_Rate"]:.2%}', bg=_bg(r["Spam_Rate"], _br("spam","ind"), _br("spam","good"), _br("spam","great"), True))}
            </div>
          </summary>
          <div style="background:#f8f8f8;padding:10px 16px 14px;border-top:1px solid #ddd;">
            <p style="font-family:'Barlow Condensed',sans-serif;font-size:0.67rem;
                      letter-spacing:0.1em;text-transform:uppercase;color:#888;margin:0 0 8px;">
              {r["Category"].upper()} &mdash; {r["Channel"].upper()}
              &nbsp;&middot;&nbsp; &#9733; click rate colour vs. category average
            </p>
            {_campaign_rows(r["Category"], r["Channel"], bm_set)}
          </div>
        </details>"""

    n_rows = len(perf_tbl)
    perf_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800;900&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
      *, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0; }}
      body {{ font-family:'Barlow',sans-serif; background:#fff; font-size:0.82rem; }}
      details summary {{ list-style:none; }}
      details summary::-webkit-details-marker {{ display:none; }}
      .perf-row summary:hover .row-grid {{ background:#fffde0; }}
      .perf-row[open] summary .row-grid {{ background:#fffde0; }}
      .perf-row[open] summary .toggle-icon::before {{ content:"▼"; }}
      .toggle-icon::before {{ content:"▶"; color:#aaa; font-size:0.6rem; margin-right:5px; }}
    </style></head><body>
    <div style="border:2px solid #000;border-radius:12px;overflow:hidden;">
      <div style="padding:6px 12px;background:#fafafa;border-bottom:1px solid #e8e8e8;
                  display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
        <span style="font-family:'Barlow',sans-serif;font-size:0.6rem;font-weight:700;
                     letter-spacing:0.08em;text-transform:uppercase;color:#888;">Color key</span>
        <span style="background:#FFCDD2;padding:2px 10px;border-radius:3px;font-family:'Barlow',sans-serif;font-size:0.62rem;color:#333;">&#9679; Below industry</span>
        <span style="background:#FFF9C4;padding:2px 10px;border-radius:3px;font-family:'Barlow',sans-serif;font-size:0.62rem;color:#333;">&#9679; Industry → Good</span>
        <span style="background:#C8F7C5;padding:2px 10px;border-radius:3px;font-family:'Barlow',sans-serif;font-size:0.62rem;color:#333;">&#9679; Good → Great</span>
        <span style="background:#81C784;padding:2px 10px;border-radius:3px;font-family:'Barlow',sans-serif;font-size:0.62rem;color:#fff;">&#9679; Above great</span>
      </div>
      <div style="display:grid;grid-template-columns:18% 30% 37.5% auto;background:#000;color:#feee35;">
        <div style="padding:9px 10px;font-family:'Barlow Condensed',sans-serif;font-size:0.72rem;
                    letter-spacing:0.1em;text-transform:uppercase;border-right:3px solid #333;">
          &#9660; Click any row to expand
        </div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;
                    border-right:3px solid #333;">&#x24; Financials</div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;
                    border-right:3px solid #feee35;">&#9650; Performance</div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;">&#9888; Issues</div>
      </div>
      <div style="display:grid;grid-template-columns:{GCOLS};background:#222;color:#fff;font-size:0.67rem;">
        <div style="padding:6px 9px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;">Category</div>
        <div style="padding:6px 8px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;border-right:3px solid #444;">Channel</div>
        <div title="Number of campaigns in this group" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;"># Camp</div>
        <div title="Total recipients (sends)" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Sent</div>
        <div title="Sum of revenue attributed to campaigns" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Revenue</div>
        <div title="Revenue ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #555;cursor:help;">RPR</div>
        <div title="Delivered ÷ Recipients" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Del. Rate</div>
        <div title="Unique Opens ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Open Rate</div>
        <div title="Unique Clicks ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Click Rate</div>
        <div title="Unique Clicks ÷ Unique Opens" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">CTOR</div>
        <div title="Unique Conversions ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #555;cursor:help;">Conv. Rate</div>
        <div title="Unsubscribes ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Unsub Rate</div>
        <div title="Spam Complaints ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Spam Rate</div>
      </div>
      <div style="display:grid;grid-template-columns:{GCOLS};
                  background:#fffff0;border-bottom:2px solid #e8d800;
                  border-left:4px solid #f5f000;">
        <div style="padding:7px 9px;font-family:'Barlow Condensed',sans-serif;font-size:0.68rem;
                    font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:#7a6e00;
                    display:flex;align-items:center;">Campaign Benchmarks</div>
        <div style="padding:7px 8px;font-family:'Barlow',sans-serif;font-size:0.6rem;
                    color:#999;border-right:3px solid #e8d800;display:flex;flex-direction:column;
                    justify-content:center;line-height:1.55;">
          <span style="color:#999;">Industry</span>
          <span style="color:#E07B00;">Good</span>
          <span style="color:#1a9e3f;">Great</span>
        </div>
        <div style="padding:7px 5px;text-align:center;font-family:'Barlow',sans-serif;color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>
        <div style="padding:7px 5px;text-align:center;font-family:'Barlow',sans-serif;color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>
        <div style="padding:7px 5px;text-align:center;font-family:'Barlow',sans-serif;color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>
        <div style="padding:7px 5px;text-align:center;border-right:3px solid #e8d800;">{_bm_tier(BM["rpr"]["ind"],   BM["rpr"]["good"],   BM["rpr"]["great"],   _dollar)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["del"]["ind"],   BM["del"]["good"],   BM["del"]["great"],   _pct)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["open"]["ind"],  BM["open"]["good"],  BM["open"]["great"],  _pct)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["click"]["ind"], BM["click"]["good"], BM["click"]["great"], _pct2)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["ctor"]["ind"],  BM["ctor"]["good"],  BM["ctor"]["great"],  _pct)}</div>
        <div style="padding:7px 5px;text-align:center;border-right:3px solid #e8d800;">{_bm_tier(BM["conv"]["ind"],  BM["conv"]["good"],  BM["conv"]["great"],  _pct2)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["unsub"]["ind"],  BM["unsub"]["good"],  BM["unsub"]["great"], _pct2)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["spam"]["ind"],   BM["spam"]["good"],   BM["spam"]["great"],  _pct2)}</div>
      </div>
      {detail_rows_html}
    </div></body></html>"""
    components.html(perf_html, height=n_rows * 44 + 210, scrolling=True)

    # ── Subject Line Themes ───────────────────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h2>Subject Line Themes</h2>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;color:#666;'
        'margin:-0.5rem 0 1rem;">What subject line approaches work across all categories</p>',
        unsafe_allow_html=True,
    )

    theme_df = filt.dropna(subset=["Subject Line", "Click Rate"]).copy()
    theme_df["Themes"] = theme_df["Subject Line"].apply(detect_themes)
    theme_rows_exp = theme_df.explode("Themes")
    theme_agg = (
        theme_rows_exp.groupby("Themes").agg(
            Count      = ("Campaign Name",   "count"),
            Click_Rate = ("Click Rate",      "mean"),
            Conv_Rate  = ("Conversion Rate", "mean"),
            Revenue    = ("Revenue",         "mean"),
            Open_Rate  = ("Open Rate",       "mean"),
        ).reset_index().sort_values("Click_Rate", ascending=False)
    )

    th1, th2 = st.columns([3, 2])
    with th1:
        fig_themes = px.bar(
            theme_agg, x="Click_Rate", y="Themes", orientation="h",
            color="Click_Rate",
            color_continuous_scale=[[0,"#FFCDD2"],[0.4,"#FFF9C4"],[1,"#C8F7C5"]],
            title="AVG CLICK RATE BY SUBJECT LINE THEME", height=360,
            text=theme_agg["Click_Rate"].apply(lambda v: f"{v:.1%}"),
            labels={"Click_Rate":"Avg Click Rate","Themes":""},
            hover_data={"Count":True,"Conv_Rate":":.2%","Revenue":":$,.0f","Click_Rate":":.2%"},
        )
        fig_themes.update_layout(**plot_theme(
            yaxis=dict(autorange="reversed", tickfont=dict(size=10), showgrid=False, zeroline=False),
            xaxis=dict(showgrid=True, gridcolor=COLORS["border"], zeroline=False,
                       tickformat=".1%", tickfont=dict(size=10)),
            coloraxis_showscale=False,
        ))
        fig_themes.update_traces(textposition="outside",
                                  textfont=dict(size=10, family="Barlow, sans-serif"),
                                  marker_line_width=1, marker_line_color=COLORS["black"])
        st.plotly_chart(fig_themes, use_container_width=True)

    with th2:
        st.markdown(
            '<p style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.75rem;'
            'letter-spacing:0.1em;text-transform:uppercase;color:#666;margin-bottom:0.5rem;">'
            'Theme performance summary</p>',
            unsafe_allow_html=True,
        )
        theme_display = theme_agg.rename(columns={
            "Click_Rate":"Click Rate","Conv_Rate":"Conv Rate",
            "Open_Rate":"Open Rate","Revenue":"Avg Revenue",
        })

        def _style_theme_row(row):
            cr = row["Click Rate"]
            if cr >= theme_agg["Click_Rate"].quantile(0.66): bg = "background-color:#C8F7C5"
            elif cr >= theme_agg["Click_Rate"].quantile(0.33): bg = "background-color:#FFF9C4"
            else: bg = "background-color:#FFCDD2"
            return [bg] * len(row)

        st.dataframe(
            theme_display[["Themes","Count","Click Rate","Conv Rate","Avg Revenue"]]
            .style.apply(_style_theme_row, axis=1)
            .format({"Click Rate":"{:.2%}","Conv Rate":"{:.2%}","Avg Revenue":"${:,.0f}"}),
            use_container_width=True, hide_index=True, height=360,
        )

# ══════════════════════════════════════════════════════════════════════════════
# FLOWS TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_flow:
    fm_all = flow_monthly.copy()
    fmsg   = flow_msgs.copy()

    fm_all["Month"] = pd.to_datetime(fm_all["Month"], errors="coerce")
    avail_min = fm_all["Month"].min()
    avail_max = fm_all["Month"].max()
    today = pd.Timestamp.today().normalize()

    # ── Time period + channel filter ────────────────────────────────────────
    period_opts = ["Year to date", "Last 12 months", "Last 6 months", "Custom range"]
    fp1, fp2, fp3 = st.columns([2, 2, 4])
    with fp1:
        sel_period = st.selectbox("Select time period", period_opts, key="pf_period")
    with fp2:
        sel_fch = st.selectbox("Channel", ["All Channels", "Email", "SMS"], key="pf_ch")

    if sel_period == "Custom range":
        cr1, cr2, _cr3 = st.columns([2, 2, 4])
        with cr1:
            cr_start = st.date_input("Start month", value=avail_min.date(), key="pf_start",
                                      min_value=avail_min.date(), max_value=avail_max.date())
        with cr2:
            cr_end = st.date_input("End month", value=avail_max.date(), key="pf_end",
                                    min_value=avail_min.date(), max_value=avail_max.date())
        d_start = pd.Timestamp(cr_start).normalize()
        d_end   = pd.Timestamp(cr_end).normalize()
    elif sel_period == "Year to date":
        d_start = pd.Timestamp(today.year, 1, 1)
        d_end   = avail_max
    elif sel_period == "Last 12 months":
        d_end   = avail_max
        d_start = (d_end - pd.DateOffset(months=11)).normalize()
    else:  # Last 6 months
        d_end   = avail_max
        d_start = (d_end - pd.DateOffset(months=5)).normalize()

    fm = fm_all[(fm_all["Month"] >= d_start) & (fm_all["Month"] <= d_end)].copy()
    if sel_fch == "Email": fm = fm[fm["Channel"] == "email"]
    elif sel_fch == "SMS": fm = fm[fm["Channel"] == "sms"]

    period_label = f"{d_start.strftime('%b %Y')} – {d_end.strftime('%b %Y')}"
    st.markdown(
        f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#666;'
        f'margin:0 0 0.6rem;">Showing <b>{period_label}</b></p>',
        unsafe_allow_html=True,
    )

    if fm.empty:
        st.info("No flow data in the selected period.")
        st.stop()

    # ── Flow benchmarks (reuse campaign benchmark thresholds) ────────────────
    def _bvf(metric, col):
        row = benchmarks[benchmarks["Metric"] == metric]
        return float(row[col].iloc[0]) if not row.empty else None

    def _bm_row(metric):
        return {
            "ind":   _bvf(metric, "Industry Median (DTC Jewelry/Beauty)"),
            "good":  _bvf(metric, "Good"),
            "great": _bvf(metric, "Great"),
        }
    ALL_BMS = {k: _bm_row(k) for k in [
        "Open Rate (Campaign)", "Click Rate (Campaign)", "CTOR (Campaign)",
        "Conversion Rate (Campaign)", "RPR (Campaign)", "Unsub Rate (Campaign)",
        "Welcome Flow Conv Rate", "Abandoned Cart Conv Rate",
        "Abandoned Checkout Conv Rate", "Back In Stock Conv Rate",
        "Flow RPR (Welcome)", "Flow RPR (Cart)", "Flow RPR (Checkout)",
        "SMS Click Rate", "SMS Conv Rate", "SMS Unsub Rate",
    ]}

    def _bm_for(flow_name, channel, metric):
        fn = (flow_name or "").lower()
        is_sms = channel == "sms"
        if metric == "open":
            return ALL_BMS["Open Rate (Campaign)"]
        if metric == "click":
            return ALL_BMS["SMS Click Rate"] if is_sms else ALL_BMS["Click Rate (Campaign)"]
        if metric == "ctor":
            return ALL_BMS["CTOR (Campaign)"]
        if metric == "conv":
            if "welcome" in fn:                              return ALL_BMS["Welcome Flow Conv Rate"]
            if "back in stock" in fn or "bis" in fn:         return ALL_BMS["Back In Stock Conv Rate"]
            if "checkout" in fn:                             return ALL_BMS["Abandoned Checkout Conv Rate"]
            if "cart" in fn:                                 return ALL_BMS["Abandoned Cart Conv Rate"]
            return ALL_BMS["SMS Conv Rate"] if is_sms else ALL_BMS["Conversion Rate (Campaign)"]
        if metric == "rpr":
            if "welcome" in fn:    return ALL_BMS["Flow RPR (Welcome)"]
            if "checkout" in fn:   return ALL_BMS["Flow RPR (Checkout)"]
            if "cart" in fn:       return ALL_BMS["Flow RPR (Cart)"]
            return ALL_BMS["RPR (Campaign)"]
        if metric == "unsub":
            return ALL_BMS["SMS Unsub Rate"] if is_sms else ALL_BMS["Unsub Rate (Campaign)"]
        return None

    # 4-tier color (matches module-level _bg): red → yellow → light green → dark green
    BG_RED, BG_YELLOW, BG_LIGHT, BG_DARK = "#FFCDD2", "#FFF9C4", "#C8F7C5", "#81C784"

    # Per-metric format functions
    def _f_pct1(v): return "—" if pd.isna(v) else f"{v*100:.1f}%"
    def _f_pct2(v): return "—" if pd.isna(v) else f"{v*100:.2f}%"
    def _f_pct3(v): return "—" if pd.isna(v) else f"{v*100:.3f}%"
    def _f_dol(v):  return "—" if pd.isna(v) else f"${v:.2f}"

    def _bm_tip(bm, fmt_fn):
        if not bm or bm.get("ind") is None: return ""
        return (f'<span class="bm-tip">'
                f'<span class="bm-tip-hdr">Industry &middot; Good &middot; Great</span>'
                f'<span class="bm-tip-vals">{fmt_fn(bm["ind"])} | {fmt_fn(bm["good"])} | {fmt_fn(bm["great"])}</span>'
                f'</span>')

    def _bm_cell(value, bm, fmt_fn, lower_better=False, sep=False, bold=False):
        """Grid cell with hover tooltip showing benchmark, colored by benchmark."""
        if value is None or pd.isna(value):
            bg, val_html, tip = "", "—", ""
        else:
            bg = _bg(value, bm["ind"], bm["good"], bm["great"], lower_better=lower_better) if bm else ""
            val_html = fmt_fn(value)
            tip = _bm_tip(bm, fmt_fn)
        s = "border-right:3px solid rgba(0,0,0,0.12);" if sep else ""
        bg_s = f"background:{bg};" if bg else ""
        fw = "700" if bold else "400"
        return (f'<div class="bm-cell" style="padding:7px 5px;text-align:center;display:flex;'
                f'align-items:center;justify-content:center;position:relative;{bg_s}{s}">'
                f'<span style="font-weight:{fw};">{val_html}</span>{tip}</div>')

    def _bm_td(value, bm, fmt_fn, lower_better=False):
        """Subtable td with hover tooltip showing benchmark."""
        if value is None or pd.isna(value):
            return '<td style="padding:5px 6px;text-align:center;">—</td>'
        bg   = _bg(value, bm["ind"], bm["good"], bm["great"], lower_better=lower_better) if bm else ""
        bg_s = f"background:{bg};" if bg else ""
        tip  = _bm_tip(bm, fmt_fn)
        return (f'<td class="bm-cell" style="padding:5px 6px;text-align:center;position:relative;{bg_s}">'
                f'<span style="font-weight:600;">{fmt_fn(value)}</span>{tip}</td>')

    # ── KPI strip (computed from totals over selected window) ───────────────
    flow_count       = fm["Flow ID"].nunique()
    months_count     = fm["Month"].dt.to_period("M").nunique()
    f_total_rev      = fm["Revenue"].sum()
    f_avg_mo_rev     = fm.groupby(fm["Month"].dt.to_period("M"))["Revenue"].sum().mean() if months_count else 0
    f_total_recip    = fm["Recipients"].sum()
    f_total_deliv    = fm["Delivered"].sum()
    f_total_opens    = fm["Unique Opens"].sum()
    f_total_clicks   = fm["Unique Clicks"].sum()
    f_total_conv     = fm["Unique Conversions"].sum()
    f_total_unsubs   = fm["Unsubscribes"].sum()

    f_rpr   = (f_total_rev    / f_total_recip) if f_total_recip else 0
    f_open  = (f_total_opens  / f_total_deliv) if f_total_deliv else 0
    f_click = (f_total_clicks / f_total_deliv) if f_total_deliv else 0
    f_conv  = (f_total_conv   / f_total_deliv) if f_total_deliv else 0
    f_unsub = (f_total_unsubs / f_total_recip) if f_total_recip else 0

    flow_rfmt = fmt_rev_consistent(pd.Series([f_total_rev, f_avg_mo_rev]))

    f_strip = (
        '<div class="kpi-group-wrap">'
        + kpi_group("Volume",
            kpi_cell("Active Flows", f"{flow_count:,}") +
            kpi_cell("Months in Period", f"{months_count:,}"))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Financials",
            kpi_cell("Revenue", flow_rfmt(f_total_rev)) +
            kpi_cell("Avg Monthly Rev", flow_rfmt(f_avg_mo_rev)) +
            kpi_cell("Avg RPR", f"${f_rpr:.2f}"))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Performance",
            kpi_cell("Open Rate", "—" if sel_fch == "SMS" else fmt_pct(f_open)) +
            kpi_cell("Click Rate", fmt_pct(f_click)) +
            kpi_cell("Conv. Rate", fmt_pct(f_conv)))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Issues", kpi_cell("Unsub Rate", fmt_pct(f_unsub), issue=True))
        + '</div>'
    )
    st.markdown(f_strip, unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Flow groupings (defined early — used by both chart and table) ───────────
    FLOW_GROUPS = {
        "Welcome":                       ["F001", "F002"],
        "Abandonment":                   ["F003", "F004", "F005", "F006", "F007"],
        "Post-purchase":                 ["F009", "F015", "F010", "F011", "F012", "F013"],
        "Appointments & Cancellations":  ["F016", "F017", "F018", "F019", "F020", "F021", "F022", "F023"],
        "Winback":                       ["F028", "F029"],
        "Back in stock":                 ["F008"],
        "Birthday & Anniversary":        ["F014", "F030"],
        "Other":                         ["F024", "F025", "F026", "F027"],
    }
    flow_to_group   = {fid: g for g, fids in FLOW_GROUPS.items() for fid in fids}
    group_order_idx = {g: i for i, g in enumerate(FLOW_GROUPS)}
    fm["Group"] = fm["Flow ID"].map(flow_to_group).fillna("Other")

    # Display labels — keep short for horizontal bar charts
    _CAT_LABEL = {
        "Welcome":                      "Welcome",
        "Abandonment":                  "Abandonment",
        "Post-purchase":                "Post-purchase",
        "Appointments & Cancellations": "Appts & Cancellations",
        "Winback":                      "Winback",
        "Back in stock":                "Back in Stock",
        "Birthday & Anniversary":       "Birthday & Anniv.",
        "Other":                        "Other",
    }

    # ── Category-level weighted aggregation ──────────────────────────────────
    _cat_agg = fm.groupby("Group", as_index=False).agg(
        Delivered    = ("Delivered",         "sum"),
        Clicks       = ("Unique Clicks",     "sum"),
        Conversions  = ("Unique Conversions","sum"),
        Revenue      = ("Revenue",           "sum"),
        Recipients   = ("Recipients",        "sum"),
    )
    _cat_agg["Click Rate"] = _cat_agg["Clicks"]      / _cat_agg["Delivered"].replace(0, pd.NA)
    _cat_agg["Conv Rate"]  = _cat_agg["Conversions"] / _cat_agg["Delivered"].replace(0, pd.NA)
    _cat_agg["RPR"]        = _cat_agg["Revenue"]     / _cat_agg["Recipients"].replace(0, pd.NA)
    _cat_agg["_g"]         = _cat_agg["Group"].map(group_order_idx).fillna(99)
    _cat_agg = _cat_agg.sort_values("_g")
    _cat_agg["Label"]      = _cat_agg["Group"].map(_CAT_LABEL).fillna(_cat_agg["Group"])

    # ── Performance by Category charts ───────────────────────────────────────
    st.markdown("<h2>Performance by Flow Category</h2>", unsafe_allow_html=True)

    _cc1, _cc2, _cc3 = st.columns(3)
    _bar_opts = dict(orientation="h", marker_color="#1a1a1a",
                     marker_line_width=0, text=None)

    def _hbar(col, vals, labels, title, fmt_fn, tick_fmt, theme_overrides=None):
        fig = go.Figure(go.Bar(
            y=labels, x=vals,
            orientation="h",
            marker_color="#1a1a1a",
            marker_line_width=0,
            customdata=[[fmt_fn(v)] for v in vals],
            hovertemplate="%{y}<br>" + title + ": %{customdata[0]}<extra></extra>",
        ))
        overrides = dict(
            margin=dict(t=32, b=10, l=0, r=10),
            height=260,
            xaxis=dict(tickformat=tick_fmt, showgrid=True,
                       gridcolor=COLORS["border"], zeroline=False,
                       tickfont=dict(size=9)),
            yaxis=dict(showgrid=False, tickfont=dict(size=10), autorange="reversed"),
            title=dict(text=f"<b>{title}</b>", font_size=11, x=0),
            bargap=0.35,
            showlegend=False,
        )
        if theme_overrides:
            overrides.update(theme_overrides)
        fig.update_layout(**plot_theme(**overrides))
        return fig

    _labels = _cat_agg["Label"].tolist()

    _cc1.plotly_chart(
        _hbar("click", _cat_agg["Click Rate"].fillna(0).tolist(), _labels,
              "Click Rate", lambda v: f"{v*100:.2f}%", ".2%"),
        use_container_width=True,
    )
    _cc2.plotly_chart(
        _hbar("conv", _cat_agg["Conv Rate"].fillna(0).tolist(), _labels,
              "Conv. Rate", lambda v: f"{v*100:.2f}%", ".2%"),
        use_container_width=True,
    )
    _cc3.plotly_chart(
        _hbar("rpr", _cat_agg["RPR"].fillna(0).tolist(), _labels,
              "RPR", lambda v: f"${v:.2f}", "$,.2f"),
        use_container_width=True,
    )

    # ── Performance by Flow (expandable table) ───────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h2>Performance by Flow</h2>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#666;'
        f'margin:-0.5rem 0 1rem;">Click any flow to see per-message performance. '
        f'Top-level metrics summarize <b>{period_label}</b>; message rows are a 90-day snapshot.</p>',
        unsafe_allow_html=True,
    )

    flow_perf = (
        fm.groupby(["Flow ID","Flow Name","Trigger Type","# Messages","Channel"], as_index=False)
          .agg(Recipients=("Recipients","sum"),
               Delivered=("Delivered","sum"),
               Opens=("Unique Opens","sum"),
               Clicks=("Unique Clicks","sum"),
               Conversions=("Unique Conversions","sum"),
               Revenue=("Revenue","sum"),
               Unsubs=("Unsubscribes","sum"))
    )
    flow_perf["Open Rate"]  = flow_perf["Opens"]       / flow_perf["Delivered"].replace(0, pd.NA)
    flow_perf["Click Rate"] = flow_perf["Clicks"]      / flow_perf["Delivered"].replace(0, pd.NA)
    flow_perf["CTOR"]       = flow_perf["Clicks"]      / flow_perf["Opens"].replace(0, pd.NA)
    flow_perf["Conv Rate"]  = flow_perf["Conversions"] / flow_perf["Delivered"].replace(0, pd.NA)
    flow_perf["RPR"]        = flow_perf["Revenue"]     / flow_perf["Recipients"].replace(0, pd.NA)
    flow_perf["Unsub Rate"] = flow_perf["Unsubs"]      / flow_perf["Recipients"].replace(0, pd.NA)
    flow_perf["Group"]      = flow_perf["Flow ID"].map(flow_to_group).fillna("Other")
    flow_perf["_g"]         = flow_perf["Group"].map(group_order_idx).fillna(99)
    flow_perf = flow_perf.sort_values(["_g", "Recipients"], ascending=[True, False])

    # Group-level weighted aggregation (sum/sum, not mean of rates)
    group_agg = (
        fm.groupby("Group", as_index=False).agg(
            Recipients=("Recipients","sum"),
            Delivered=("Delivered","sum"),
            Opens=("Unique Opens","sum"),
            Clicks=("Unique Clicks","sum"),
            Conversions=("Unique Conversions","sum"),
            Revenue=("Revenue","sum"),
            Unsubs=("Unsubscribes","sum"),
            NumFlows=("Flow ID","nunique"),
        )
    )
    # Email-only delivered for accurate open rate (SMS has no opens)
    fm_email = fm[fm["Channel"] == "email"]
    if not fm_email.empty:
        email_deliv = fm_email.groupby("Group", as_index=False).agg(EmailDelivered=("Delivered","sum"))
    else:
        email_deliv = pd.DataFrame({"Group": [], "EmailDelivered": []})
    group_perf = group_agg.merge(email_deliv, on="Group", how="left")
    group_perf["EmailDelivered"] = group_perf["EmailDelivered"].fillna(0)

    group_perf["Open Rate"]  = group_perf["Opens"]       / group_perf["EmailDelivered"].replace(0, pd.NA)
    group_perf["Click Rate"] = group_perf["Clicks"]      / group_perf["Delivered"].replace(0, pd.NA)
    group_perf["CTOR"]       = group_perf["Clicks"]      / group_perf["Opens"].replace(0, pd.NA)
    group_perf["Conv Rate"]  = group_perf["Conversions"] / group_perf["Delivered"].replace(0, pd.NA)
    group_perf["RPR"]        = group_perf["Revenue"]     / group_perf["Recipients"].replace(0, pd.NA)
    group_perf["Unsub Rate"] = group_perf["Unsubs"]      / group_perf["Recipients"].replace(0, pd.NA)
    group_perf["_g"]         = group_perf["Group"].map(group_order_idx).fillna(99)
    group_perf = group_perf.sort_values("_g")

    # Identity 40% | 8 equal-width metric columns at 7.5% each = 60%
    GCOLS_F = "18% 6% 11% 5% " + " ".join(["7.5%"] * 7) + " auto"

    # Map bg color → text color (matches campaigns tab inner rows)
    _BG_TO_TEXT = {
        "#FFCDD2": "#C0392B",  # red
        "#FFF9C4": "#9A7D00",  # dark yellow
        "#C8F7C5": "#1e7e34",  # light green
        "#81C784": "#145a23",  # dark green
    }
    def _dc(val, bg="", bold=False, sep=False, span=1):
        """Inner data cell — colored text on neutral bg (matches campaigns tab)."""
        txt = _BG_TO_TEXT.get(bg, "#222")
        fw  = "font-weight:700;" if (bg or bold) else "font-weight:400;"
        br  = "border-right:3px solid rgba(0,0,0,0.08);" if sep else ""
        sp  = f"grid-column:span {span};" if span > 1 else ""
        return (f'<div style="padding:5px 4px;text-align:center;font-size:0.73rem;'
                f'display:flex;align-items:center;justify-content:center;'
                f'color:{txt};{fw}{br}{sp}">{val}</div>')

    def _dc_bm(value, bm, fmt_fn, lower_better=False, bold=False, sep=False):
        if pd.isna(value) or value is None:
            return _dc("—", sep=sep)
        bg = _bg(value, bm["ind"], bm["good"], bm["great"], lower_better=lower_better) if bm else ""
        return _dc(fmt_fn(value), bg=bg, bold=bold, sep=sep)

    def _msg_rows(flow_id, flow_name, parent_channel):
        """Render messages as grid rows aligned with parent — colored TEXT, neutral bg."""
        sub = fmsg[fmsg["Flow ID"] == flow_id].copy()
        if sub.empty:
            return ("<div style='padding:10px 16px;font-size:0.75rem;color:#888;"
                    "background:#fafafa;'>No message-level data available.</div>")
        sub = sub.sort_values("Step #")

        bm_open  = _bm_for(flow_name, parent_channel, "open")
        bm_click = _bm_for(flow_name, parent_channel, "click")
        bm_conv  = _bm_for(flow_name, parent_channel, "conv")
        bm_rpr   = _bm_for(flow_name, parent_channel, "rpr")

        rows = ""
        for _, m in sub.iterrows():
            ch         = m["Channel"] if pd.notna(m.get("Channel")) else parent_channel
            recipients = m["Recipients 90d"] if pd.notna(m["Recipients 90d"]) else 0
            rev        = m["Revenue"] if pd.notna(m["Revenue"]) else 0
            open_rate  = None if (ch == "sms" or pd.isna(m.get("Open Rate"))) else m["Open Rate"]
            step_badge = (f'<span style="background:#dadada;color:#222;border-radius:50%;'
                          f'width:16px;height:16px;display:inline-flex;align-items:center;'
                          f'justify-content:center;font-size:0.58rem;font-weight:700;'
                          f'margin-right:6px;flex-shrink:0;">{int(m["Step #"])}</span>')
            name_html = (
                f'<div style="padding:5px 8px 5px 26px;display:flex;align-items:center;'
                f'min-width:0;grid-column:span 4;">'
                f'{step_badge}'
                f'<span class="clamp2" style="font-size:0.72rem;line-height:1.25;color:#222;">'
                f'{m["Message Name"]}</span></div>'
            )
            rows += (
                f'<div class="msg-row" style="display:grid;grid-template-columns:{GCOLS_F};'
                f'align-items:stretch;border-bottom:1px solid #ececec;background:#fafafa;'
                f'min-height:34px;">'
                + name_html
                + _dc(f'{recipients/1e3:.0f}K')
                + _dc(f'${rev/1e3:.1f}K')
                + _dc_bm(m["RPR"], bm_rpr, _f_dol, sep=True)
                + _dc_bm(open_rate, bm_open, _f_pct1)
                + _dc_bm(m["Click Rate"], bm_click, _f_pct2, bold=True)
                + _dc("—")
                + _dc_bm(m["Conversion Rate"], bm_conv, _f_pct2, sep=True)
                + _dc("—")
                + '</div>'
            )
        return rows

    def _group_header(g):
        n_flows = int(g["NumFlows"])
        recip_m = (g['Recipients']/1e6) if g['Recipients'] else 0
        rev_m   = (g['Revenue']/1e6) if g['Revenue'] else 0
        cell_st = ("padding:8px 5px;display:flex;align-items:center;justify-content:center;"
                   "font-weight:700;color:#000;font-size:0.78rem;")
        return f"""
        <div class="group-header" style="display:grid;grid-template-columns:{GCOLS_F};
                    background:#ebebeb;border-top:1px solid #bbb;border-bottom:1px solid #bbb;
                    border-left:4px solid #caf30b;min-height:40px;align-items:stretch;">
          <div style="padding:9px 10px;display:flex;align-items:center;
                      grid-column:span 4;border-right:2px solid rgba(0,0,0,0.15);">
            <span style="font-family:'Barlow Condensed',sans-serif;font-size:0.92rem;
                         font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#000;">
              {g['Group']}</span>
            <span style="margin-left:10px;font-size:0.62rem;font-weight:500;color:#666;
                         font-family:'Barlow',sans-serif;">
              {n_flows} flow{'s' if n_flows != 1 else ''}
            </span>
          </div>
          <div style="{cell_st}">{f'{recip_m:.1f}M' if recip_m else '—'}</div>
          <div style="{cell_st}">{f'${rev_m:.1f}M' if rev_m else '—'}</div>
          <div style="{cell_st}border-right:2px solid rgba(0,0,0,0.15);">{_f_dol(g['RPR'])}</div>
          <div style="{cell_st}">{_f_pct1(g['Open Rate'])}</div>
          <div style="{cell_st}">{_f_pct2(g['Click Rate'])}</div>
          <div style="{cell_st}">{_f_pct1(g['CTOR'])}</div>
          <div style="{cell_st}border-right:2px solid rgba(0,0,0,0.15);">{_f_pct2(g['Conv Rate'])}</div>
          <div style="{cell_st}">{_f_pct2(g['Unsub Rate'])}</div>
        </div>"""

    detail_rows_html_f = ""
    for _, gp in group_perf.iterrows():
        flows_in_group = flow_perf[flow_perf["Group"] == gp["Group"]]
        if flows_in_group.empty:
            continue
        detail_rows_html_f += _group_header(gp)

        for _, r in flows_in_group.iterrows():
            ch         = r["Channel"]
            fname      = r["Flow Name"]
            recipients = r["Recipients"] if pd.notna(r["Recipients"]) else 0
            rev        = r["Revenue"]    if pd.notna(r["Revenue"]) else 0
            open_v     = None if (ch == "sms" or pd.isna(r["Open Rate"])) else r["Open Rate"]

            bm_open  = _bm_for(fname, ch, "open")
            bm_click = _bm_for(fname, ch, "click")
            bm_ctor  = _bm_for(fname, ch, "ctor")
            bm_conv  = _bm_for(fname, ch, "conv")
            bm_rpr   = _bm_for(fname, ch, "rpr")
            bm_unsub = _bm_for(fname, ch, "unsub")

            flow_name_html = (
                f'<div style="padding:5px 5px 5px 14px;display:flex;align-items:center;min-width:0;">'
                f'<span class="toggle-icon" style="flex-shrink:0;"></span>'
                f'<span class="clamp2" style="font-weight:600;font-size:0.72rem;line-height:1.25;">'
                f'{fname}</span></div>'
            )

            detail_rows_html_f += f"""
            <details class="perf-row" style="border-bottom:1px solid #e8e8e8;">
              <summary style="cursor:pointer;display:block;">
                <div class="row-grid" style="display:grid;grid-template-columns:{GCOLS_F};
                            align-items:stretch;font-size:0.8rem;min-height:40px;">
                  {flow_name_html}
                  {_cell(_pill(ch), align="left")}
                  {_cell(r["Trigger Type"], align="left")}
                  {_cell(str(int(r["# Messages"])), sep=True)}
                  {_cell(f'{recipients/1e6:.1f}M')}
                  {_cell(f'${rev/1e6:.1f}M')}
                  {_bm_cell(r["RPR"],        bm_rpr,   _f_dol,  sep=True)}
                  {_bm_cell(open_v,          bm_open,  _f_pct1)}
                  {_bm_cell(r["Click Rate"], bm_click, _f_pct2, bold=True)}
                  {_bm_cell(r["CTOR"],       bm_ctor,  _f_pct1)}
                  {_bm_cell(r["Conv Rate"],  bm_conv,  _f_pct2, sep=True)}
                  {_bm_cell(r["Unsub Rate"], bm_unsub, _f_pct2, lower_better=True)}
                </div>
              </summary>
              <div style="background:#fafafa;border-top:1px solid #ddd;">
                <div style="padding:6px 26px 4px;font-family:'Barlow Condensed',sans-serif;
                            font-size:0.62rem;letter-spacing:0.1em;text-transform:uppercase;color:#888;">
                  Messages &middot; 90-day snapshot
                </div>
                {_msg_rows(r["Flow ID"], fname, ch)}
              </div>
            </details>"""

    n_flows = len(flow_perf)
    flow_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800;900&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
      *, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0; }}
      body {{ font-family:'Barlow',sans-serif; background:#fff; font-size:0.82rem; }}
      details summary {{ list-style:none; }}
      details summary::-webkit-details-marker {{ display:none; }}
      .perf-row summary:hover .row-grid {{ background:#fffde0; }}
      .perf-row[open] summary .row-grid {{ background:#fffde0; }}
      .perf-row[open] summary .toggle-icon::before {{ content:"▼"; }}
      .toggle-icon::before {{ content:"▶"; color:#aaa; font-size:0.6rem; margin-right:5px; }}
      .legend-pill {{ display:inline-flex; align-items:center; gap:5px; margin-right:14px;
                      font-size:0.65rem; color:#444; font-family:'Barlow',sans-serif;
                      white-space:nowrap; }}
      .legend-swatch {{ width:11px; height:11px; border-radius:3px; border:1px solid #00000022;
                        display:inline-block; flex-shrink:0; }}
      .bm-cell {{ position:relative; }}
      .bm-tip {{
        visibility:hidden; opacity:0;
        position:absolute; bottom:calc(100% + 6px); left:50%;
        transform:translateX(-50%);
        background:#1a1a1a; color:#fff;
        padding:6px 10px; border-radius:5px;
        white-space:nowrap; pointer-events:none;
        z-index:9999; transition:opacity 0.12s ease-out;
        display:flex; flex-direction:column; align-items:center; gap:2px;
        box-shadow:0 3px 10px rgba(0,0,0,0.18);
      }}
      .bm-tip-hdr {{ font-family:'Barlow Condensed',sans-serif; font-size:0.58rem;
                     letter-spacing:0.1em; text-transform:uppercase; color:#feee35; }}
      .bm-tip-vals {{ font-family:'Barlow',sans-serif; font-size:0.72rem; font-weight:600;
                      font-feature-settings:'tnum'; }}
      .bm-tip::after {{
        content:""; position:absolute; top:100%; left:50%; margin-left:-5px;
        border:5px solid transparent; border-top-color:#1a1a1a;
      }}
      .bm-cell:hover .bm-tip {{ visibility:visible; opacity:1; }}
      .clamp2 {{
        display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
        overflow:hidden; text-overflow:ellipsis; word-break:break-word;
      }}
      .msg-row:hover {{ background:#eee !important; }}
    </style></head><body>
    <div style="border:2px solid #000;border-radius:12px;overflow:hidden;">
      <div style="padding:7px 12px;background:#f7f7f7;border-bottom:1px solid #ddd;
                  display:flex;flex-wrap:wrap;align-items:center;row-gap:4px;">
        <span style="font-family:'Barlow Condensed',sans-serif;font-size:0.65rem;
                     letter-spacing:0.1em;text-transform:uppercase;color:#666;
                     margin-right:14px;">Color vs. benchmarks</span>
        <span class="legend-pill"><span class="legend-swatch" style="background:{BG_RED};"></span>Below industry</span>
        <span class="legend-pill"><span class="legend-swatch" style="background:{BG_YELLOW};"></span>Industry → Good</span>
        <span class="legend-pill"><span class="legend-swatch" style="background:{BG_LIGHT};"></span>Good → Great</span>
        <span class="legend-pill"><span class="legend-swatch" style="background:{BG_DARK};"></span>Above great</span>
        <span style="margin-left:18px;font-size:0.62rem;color:#555;font-family:'Barlow',sans-serif;">
          Hover any metric to see <b>Industry | Good | Great</b> &middot; benchmarks vary by flow type
        </span>
      </div>
      <div style="display:grid;grid-template-columns:40% 20.5% 24.5% auto;background:#000;color:#feee35;">
        <div style="padding:9px 10px;font-family:'Barlow Condensed',sans-serif;font-size:0.72rem;
                    letter-spacing:0.1em;text-transform:uppercase;border-right:3px solid #333;">
          &#9660; Click any flow to expand
        </div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;
                    border-right:3px solid #333;">&#x24; Financials</div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;
                    border-right:3px solid #feee35;">&#9650; Performance</div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;">&#9888; Issues</div>
      </div>
      <div style="display:grid;grid-template-columns:{GCOLS_F};background:#222;color:#fff;font-size:0.67rem;">
        <div style="padding:6px 9px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;">Flow</div>
        <div style="padding:6px 6px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;">Channel</div>
        <div style="padding:6px 6px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;">Trigger</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #444;"># Msgs</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Recipients</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Revenue</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #555;">RPR</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Open Rate</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Click Rate</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">CTOR</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #555;">Conv. Rate</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Unsub Rate</div>
      </div>
      {detail_rows_html_f}
    </div></body></html>"""
    n_groups = len(group_perf)
    components.html(flow_html, height=n_flows * 44 + n_groups * 42 + 220, scrolling=True)


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTS & STUDIOS TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_ps:
    product_df, studio_df = load_product_studio()

    # ── Quartile-tinted cell helper ─────────────────────────────────────────
    # Soft 4-tier palette: bottom = warm/pink, top = cool/green. Text always black.
    TIER_BG = ["#FBE5E5", "#FFF4D6", "#E8F5D0", "#CDEBC0"]

    def _quartile_bg(val, vals, lower_better=False):
        if pd.isna(val):
            return "#FAFAFA"
        clean = pd.Series(vals).dropna()
        if len(clean) < 4:
            return COLORS["white"]
        q1, q2, q3 = clean.quantile([0.25, 0.5, 0.75])
        if lower_better:
            if val <= q1: return TIER_BG[3]
            if val <= q2: return TIER_BG[2]
            if val <= q3: return TIER_BG[1]
            return TIER_BG[0]
        if val <= q1: return TIER_BG[0]
        if val <= q2: return TIER_BG[1]
        if val <= q3: return TIER_BG[2]
        return TIER_BG[3]

    def _fmt_pct_t(v): return "—" if pd.isna(v) else f"{v*100:.1f}%"
    def _fmt_dol_t(v): return "—" if pd.isna(v) else f"${v:.2f}"
    def _fmt_int_t(v): return "—" if pd.isna(v) else f"{int(v):,}"
    def _fmt_rev_t(v):
        if pd.isna(v): return "—"
        return f"${v/1e6:.1f}M" if v >= 1_000_000 else f"${v/1e3:.1f}K"

    def _render_perf_table(df, label_col, label_header, sort_col, metric_specs):
        """metric_specs: list of (col_name, header, fmt_fn, lower_better)."""
        df = df.dropna(subset=[sort_col]).sort_values(sort_col, ascending=False).copy()

        cell_pad  = "padding:9px 14px;"
        label_pad = "padding:9px 16px;"
        header_r = (
            f"font-family:'Barlow',sans-serif;font-size:0.6rem;font-weight:600;"
            f"letter-spacing:0.08em;text-transform:uppercase;color:{COLORS['muted']};"
            f"background:{COLORS['offwhite']};border-bottom:1px solid {COLORS['border']};"
            f"text-align:right;{cell_pad}"
        )
        header_l = header_r.replace("text-align:right;", "text-align:left;")

        head = f'<th style="{header_l}">{label_header}</th>'
        for _, hdr, _, _ in metric_specs:
            head += f'<th style="{header_r}">{hdr}</th>'

        rows = []
        for i, (_, r) in enumerate(df.iterrows()):
            row_bg = COLORS["white"] if i % 2 == 0 else COLORS["offwhite"]
            cells = (f'<td style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;'
                     f'font-weight:600;color:{COLORS["black"]};background:{row_bg};'
                     f'{label_pad}border-bottom:1px solid {COLORS["border"]};">'
                     f'{r[label_col]}</td>')
            for col, _, fmt_fn, lower_better in metric_specs:
                val = r[col]
                bg = _quartile_bg(val, df[col], lower_better=lower_better)
                cells += (f'<td style="font-family:\'Barlow\',sans-serif;'
                          f'font-size:0.73rem;font-weight:600;color:{COLORS["black"]};'
                          f'background:{bg};text-align:right;{cell_pad}'
                          f'border-bottom:1px solid {COLORS["border"]};">'
                          f'{fmt_fn(val)}</td>')
            rows.append(f"<tr>{cells}</tr>")

        table = (
            f'<table style="width:100%;border-collapse:collapse;'
            f'border:1px solid {COLORS["border"]};border-radius:8px;overflow:hidden;'
            f'margin-bottom:0.4rem;">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody>'
            f'</table>'
        )
        st.markdown(table, unsafe_allow_html=True)

    def _legend(extra_note=""):
        labels = ["Bottom 25%", "25–50%", "50–75%", "Top 25%"]
        chips = "".join(
            f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'margin-right:14px;font-family:Barlow,sans-serif;font-size:0.7rem;'
            f'color:{COLORS["muted"]};">'
            f'<span style="display:inline-block;width:14px;height:14px;'
            f'background:{TIER_BG[i]};border:1px solid {COLORS["border"]};'
            f'border-radius:3px;"></span>{labels[i]}</span>'
            for i in range(4)
        )
        note = (f'<span style="font-family:Barlow,sans-serif;font-size:0.7rem;'
                f'color:{COLORS["muted"]};margin-left:auto;font-style:italic;">'
                f'{extra_note}</span>' if extra_note else "")
        st.markdown(
            f'<div style="display:flex;align-items:center;flex-wrap:wrap;'
            f'margin:0.25rem 0 0.6rem 0;">{chips}{note}</div>',
            unsafe_allow_html=True,
        )

    # ── Build aggregated dataframes ────────────────────────────────────────
    # Products: Open/Click from Campaigns by Primary Product;
    #          Sends/Conv/Rev/Returns from Product Performance sheet.
    cdf = campaigns_df.dropna(subset=["Primary Product"]).copy()
    prod_oc = (cdf.groupby("Primary Product").agg(
        _Opens=("Unique Opens", "sum"),
        _Clicks=("Unique Clicks", "sum"),
        _Delivered=("Delivered", "sum"),
    ).reset_index())
    prod_oc["Open Rate"]  = prod_oc["_Opens"]  / prod_oc["_Delivered"].replace(0, pd.NA)
    prod_oc["Click Rate"] = prod_oc["_Clicks"] / prod_oc["_Delivered"].replace(0, pd.NA)

    pdf = product_df.dropna(subset=["Product Theme"]).copy()
    prod_cr = (pdf.groupby("Product Theme").agg(
        Sends=("Emails Sent", "sum"),
        _Conv=("Conversions", "sum"),
        Revenue=("Revenue", "sum"),
        ReturnRate=("Return Rate", "mean"),
    ).reset_index().rename(columns={"Product Theme": "Primary Product"}))
    prod_cr["Conv Rate"] = prod_cr["_Conv"]    / prod_cr["Sends"].replace(0, pd.NA)
    prod_cr["RPR"]       = prod_cr["Revenue"]  / prod_cr["Sends"].replace(0, pd.NA)

    products = prod_cr.merge(
        prod_oc[["Primary Product", "Open Rate", "Click Rate"]],
        on="Primary Product", how="left",
    )

    # Studios: everything from Studio Performance sheet
    sdf = studio_df.dropna(subset=["Studio"]).copy()
    studios = (sdf.groupby("Studio").agg(
        Sends=("Email Sends", "sum"),
        _Opens=("Opens", "sum"),
        _Clicks=("Clicks", "sum"),
        _Conv=("Ecom Conversions", "sum"),
        Revenue=("Ecom Revenue", "sum"),
        Appts=("Appts Completed", "sum"),
    ).reset_index())
    studios["Open Rate"]  = studios["_Opens"]  / studios["Sends"].replace(0, pd.NA)
    studios["Click Rate"] = studios["_Clicks"] / studios["Sends"].replace(0, pd.NA)
    studios["Conv Rate"]  = studios["_Conv"]   / studios["Sends"].replace(0, pd.NA)
    studios["RPR"]        = studios["Revenue"] / studios["Sends"].replace(0, pd.NA)

    # ── Products section ────────────────────────────────────────────────────
    st.markdown("<h2>Product Performance</h2>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-family:Barlow,sans-serif;font-size:0.78rem;'
        f'color:{COLORS["muted"]};margin-bottom:0.4rem;">'
        f'Sorted by revenue. Cell shading shows quartile rank within each metric column.'
        f'</div>', unsafe_allow_html=True)
    _legend("Open & Click from campaigns by Primary Product · all other metrics from Product Performance sheet")

    _render_perf_table(
        products,
        label_col="Primary Product",
        label_header="Product",
        sort_col="Revenue",
        metric_specs=[
            ("Sends",      "Sends",       _fmt_int_t, False),
            ("Open Rate",  "Open Rate",   _fmt_pct_t, False),
            ("Click Rate", "Click Rate",  _fmt_pct_t, False),
            ("Conv Rate",  "Conv Rate",   _fmt_pct_t, False),
            ("RPR",        "RPR",         _fmt_dol_t, False),
            ("Revenue",    "Revenue",     _fmt_rev_t, False),
            ("ReturnRate", "Return Rate", _fmt_pct_t, True),
        ],
    )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Studios section ─────────────────────────────────────────────────────
    st.markdown("<h2>Studio Performance</h2>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-family:Barlow,sans-serif;font-size:0.78rem;'
        f'color:{COLORS["muted"]};margin-bottom:0.4rem;">'
        f'Sorted by revenue. Cell shading shows quartile rank within each metric column.'
        f'</div>', unsafe_allow_html=True)
    _legend("All metrics from studio-level email sends across all months")

    _render_perf_table(
        studios,
        label_col="Studio",
        label_header="Studio",
        sort_col="Revenue",
        metric_specs=[
            ("Sends",      "Sends",      _fmt_int_t, False),
            ("Open Rate",  "Open Rate",  _fmt_pct_t, False),
            ("Click Rate", "Click Rate", _fmt_pct_t, False),
            ("Conv Rate",  "Conv Rate",  _fmt_pct_t, False),
            ("RPR",        "RPR",        _fmt_dol_t, False),
            ("Revenue",    "Revenue",    _fmt_rev_t, False),
            ("Appts",      "Appts",      _fmt_int_t, False),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
# CHANNELS TAB — Email vs SMS performance + cross-channel comparison
# ══════════════════════════════════════════════════════════════════════════════
with tab_channels:
    df_ch = campaigns_df.copy()

    # ── Filters (Year + Category) ────────────────────────────────────────────
    cf1, cf2, _ = st.columns([1.5, 1.5, 6])
    years_ch = sorted(df_ch["Send Date"].dt.year.dropna().unique().astype(int).tolist(),
                      reverse=True)
    cat_opts_ch = ["All Categories"] + sorted(df_ch["Category"].dropna().unique().tolist())
    with cf1: sel_year_ch = st.selectbox("Year", ["All Years"] + [str(y) for y in years_ch], key="ch_yr")
    with cf2: sel_cat_ch  = st.selectbox("Category", cat_opts_ch, key="ch_cat")

    filt_ch = df_ch.copy()
    if sel_year_ch != "All Years":
        filt_ch = filt_ch[filt_ch["Send Date"].dt.year == int(sel_year_ch)]
    if sel_cat_ch != "All Categories":
        filt_ch = filt_ch[filt_ch["Category"] == sel_cat_ch]

    # ── Per-channel weighted aggregates ──────────────────────────────────────
    def _ch_metrics(sub):
        camps = int(len(sub))
        sent  = float(sub["Recipients"].sum())
        deliv = float(sub["Delivered"].sum())
        opens = float(sub["Unique Opens"].sum())
        clk   = float(sub["Unique Clicks"].sum())
        conv  = float(sub["Unique Conversions"].sum())
        rev   = float(sub["Revenue"].sum())
        uns   = float(sub["Unsubscribes"].sum())
        return {
            "campaigns":  camps,
            "sent":       sent,
            "delivered":  deliv,
            "revenue":    rev,
            "rpr":        (rev / deliv) if deliv else 0.0,
            "aov":        (rev / conv)  if conv else 0.0,
            "del_rate":   (deliv / sent) if sent else 0.0,
            "open_rate":  (opens / deliv) if deliv else 0.0,
            "click_rate": (clk / deliv)  if deliv else 0.0,
            "conv_rate":  (conv / deliv) if deliv else 0.0,
            "unsub_rate": (uns / deliv)  if deliv else 0.0,
        }

    em_m  = _ch_metrics(filt_ch[filt_ch["Channel"] == "email"])
    sms_m = _ch_metrics(filt_ch[filt_ch["Channel"] == "sms"])
    all_m = _ch_metrics(filt_ch)

    rfmt_ch = fmt_rev_consistent(pd.Series([em_m["revenue"], sms_m["revenue"], all_m["revenue"]]))

    def _vol(n):
        if n >= 1_000_000: return f"{n/1e6:.1f}M"
        if n >= 1_000:     return f"{n/1e3:.1f}K"
        return f"{n:,.0f}"

    def _pct_or_dash(v, tracked=True):
        if not tracked: return "—"
        return "—" if (v is None or pd.isna(v)) else f"{v*100:.2f}%"

    def _cmp_arrow(em_v, sms_v, lower_better=False):
        """Return inline winner indicator vs the other channel."""
        if em_v is None or sms_v is None:
            return ""
        if pd.isna(em_v) or pd.isna(sms_v) or (em_v == 0 and sms_v == 0):
            return ""
        higher = em_v if em_v >= sms_v else sms_v
        winner = "email" if em_v >= sms_v else "sms"
        if lower_better:
            winner = "email" if em_v <= sms_v else "sms"
            higher = em_v if em_v <= sms_v else sms_v
        return winner

    # ── Comparison Table (banner up top) ─────────────────────────────────────
    rows = [
        ("Campaigns",       f"{em_m['campaigns']:,}",         f"{sms_m['campaigns']:,}",         f"{all_m['campaigns']:,}",       "count"),
        ("Recipients",      _vol(em_m["sent"]),               _vol(sms_m["sent"]),               _vol(all_m["sent"]),             "count"),
        ("Revenue",         rfmt_ch(em_m["revenue"]),         rfmt_ch(sms_m["revenue"]),         rfmt_ch(all_m["revenue"]),       "money"),
        ("Avg RPR",         f"${em_m['rpr']:.2f}",            f"${sms_m['rpr']:.2f}",            f"${all_m['rpr']:.2f}",          "money"),
        ("AOV",             f"${em_m['aov']:,.0f}",           f"${sms_m['aov']:,.0f}",           f"${all_m['aov']:,.0f}",         "money"),
        ("Delivery Rate",   _pct_or_dash(em_m["del_rate"]),   _pct_or_dash(sms_m["del_rate"]),   _pct_or_dash(all_m["del_rate"]), "pct"),
        ("Open Rate",       _pct_or_dash(em_m["open_rate"]),  "—",                               _pct_or_dash(em_m["open_rate"]), "pct"),
        ("Click Rate",      _pct_or_dash(em_m["click_rate"]), _pct_or_dash(sms_m["click_rate"]), _pct_or_dash(all_m["click_rate"]),"pct"),
        ("Conversion Rate", _pct_or_dash(em_m["conv_rate"]),  _pct_or_dash(sms_m["conv_rate"]),  _pct_or_dash(all_m["conv_rate"]),"pct"),
        ("Unsub Rate",      _pct_or_dash(em_m["unsub_rate"]), _pct_or_dash(sms_m["unsub_rate"]), _pct_or_dash(all_m["unsub_rate"]),"pct"),
    ]

    # Winner highlight per metric (numeric, weighted) — light-green tint on winner cell
    win_keys = {
        "Click Rate":      ("click_rate", False),
        "Conversion Rate": ("conv_rate",  False),
        "Avg RPR":         ("rpr",        False),
        "Revenue":         ("revenue",    False),
        "Delivery Rate":   ("del_rate",   False),
        "Unsub Rate":      ("unsub_rate", True),
    }

    body_rows = ""
    _GREEN_TEXT = "#1e7e34"
    for label, em_s, sms_s, total_s, _kind in rows:
        em_color, sms_color = "#222", "#222"
        em_weight, sms_weight = "400", "400"
        if label in win_keys:
            mkey, lower = win_keys[label]
            em_v, sms_v = em_m[mkey], sms_m[mkey]
            if em_v and sms_v:
                if (em_v <= sms_v) if lower else (em_v >= sms_v):
                    em_color, em_weight = _GREEN_TEXT, "700"
                else:
                    sms_color, sms_weight = _GREEN_TEXT, "700"
        body_rows += (
            '<tr style="border-bottom:1px solid #eee;">'
            f'<td style="padding:6px 12px;font-family:\'Barlow\',sans-serif;'
            f'font-size:0.73rem;font-weight:500;color:#333;">{label}</td>'
            f'<td style="padding:6px 12px;text-align:right;'
            f'font-family:\'Barlow\',sans-serif;font-size:0.73rem;'
            f'font-weight:{em_weight};color:{em_color};">{em_s}</td>'
            f'<td style="padding:6px 12px;text-align:right;'
            f'font-family:\'Barlow\',sans-serif;font-size:0.73rem;'
            f'font-weight:{sms_weight};color:{sms_color};">{sms_s}</td>'
            f'<td style="padding:6px 12px;text-align:right;background:#FAFAFA;'
            f'font-family:\'Barlow\',sans-serif;font-size:0.73rem;'
            f'font-weight:400;color:#444;">{total_s}</td>'
            '</tr>'
        )

    st.markdown(
        f'<div style="border:1px solid {COLORS["border"]};border-radius:8px;'
        f'overflow:hidden;margin-top:0.5rem;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="background:#000;color:#feee35;">'
        f'<th style="padding:8px 12px;text-align:left;font-family:\'Barlow\',sans-serif;'
        f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Metric</th>'
        f'<th style="padding:8px 12px;text-align:right;font-family:\'Barlow\',sans-serif;'
        f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Email</th>'
        f'<th style="padding:8px 12px;text-align:right;font-family:\'Barlow\',sans-serif;'
        f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">SMS</th>'
        f'<th style="padding:8px 12px;text-align:right;font-family:\'Barlow\',sans-serif;'
        f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;background:#1a1a1a;">Combined</th>'
        f'</tr></thead><tbody>{body_rows}</tbody></table></div>'
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.66rem;color:#888;'
        f'margin-top:6px;">Open Rate, CTOR & Spam Rate are not tracked for SMS · '
        f'green text = winning channel on weighted-avg metrics</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Email vs SMS — historical performance by category ───────────────────
    st.markdown("<h2>Email vs. SMS — performance by category</h2>", unsafe_allow_html=True)

    ch_comp = (
        filt_ch.groupby(["Category", "Channel"])
        .agg(_Clicks=("Unique Clicks", "sum"),
             _Delivered=("Delivered", "sum"),
             _Conv=("Unique Conversions", "sum"),
             Total_Rev=("Revenue", "sum"),
             Count=("Campaign Name", "count"))
        .reset_index().dropna(subset=["Category"])
    )
    ch_comp["Avg_Click"] = ch_comp["_Clicks"] / ch_comp["_Delivered"].replace(0, pd.NA)
    ch_comp["Avg_Conv"]  = ch_comp["_Conv"]   / ch_comp["_Delivered"].replace(0, pd.NA)
    ch_comp["channel"] = ch_comp["Channel"].str.upper()
    ch_comp = ch_comp.dropna(subset=["Avg_Click"])

    cat_order_ch = (ch_comp.groupby("Category")["Avg_Click"]
                    .mean().sort_values(ascending=False).index.tolist())

    def _short_cat(s, n=18):
        return s if len(s) <= n else s[: n - 1] + "…"

    ch_comp["Cat_Short"] = ch_comp["Category"].apply(_short_cat)
    cat_order_short = [_short_cat(c) for c in cat_order_ch]

    n_cats = len(cat_order_ch)
    chart_height = max(360, 28 * n_cats + 140)

    cc1, cc2 = st.columns(2)
    with cc1:
        fig_ch_click = px.bar(
            ch_comp, x="Cat_Short", y="Avg_Click", color="channel",
            color_discrete_map=CMAP, barmode="group",
            category_orders={"Cat_Short": cat_order_short},
            title="CLICK RATE: EMAIL VS SMS", height=chart_height,
            labels={"Avg_Click": "Avg Click Rate", "channel": "", "Cat_Short": ""},
            hover_data={"Category": True, "Cat_Short": False, "Count": True, "Avg_Click": ":.2%"},
        )
        fig_ch_click.update_layout(**plot_theme(
            margin=dict(l=0, r=10, t=40, b=120),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10, family="Barlow, sans-serif"),
                       automargin=True, showgrid=False, zeroline=False),
            yaxis=dict(tickformat=".1%", tickfont=dict(size=10),
                       gridcolor=COLORS["border"], zeroline=False),
        ))
        fig_ch_click.update_traces(marker_line_width=0.5, marker_line_color="#000")
        st.plotly_chart(fig_ch_click, use_container_width=True)

    with cc2:
        fig_ch_rev = px.bar(
            ch_comp, x="Cat_Short", y="Total_Rev", color="channel",
            color_discrete_map=CMAP, barmode="group",
            category_orders={"Cat_Short": cat_order_short},
            title="TOTAL REVENUE: EMAIL VS SMS", height=chart_height,
            labels={"Total_Rev": "Revenue", "channel": "", "Cat_Short": ""},
            hover_data={"Category": True, "Cat_Short": False, "Count": True, "Total_Rev": ":$,.0f"},
        )
        fig_ch_rev.update_layout(**plot_theme(
            margin=dict(l=0, r=10, t=40, b=120),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10, family="Barlow, sans-serif"),
                       automargin=True, showgrid=False, zeroline=False),
            yaxis=dict(tickformat="$,.2s", tickfont=dict(size=10),
                       gridcolor=COLORS["border"], zeroline=False),
        ))
        fig_ch_rev.update_traces(marker_line_width=0.5, marker_line_color="#000")
        st.plotly_chart(fig_ch_rev, use_container_width=True)

    # ── Conversion Rate by category (extra context) ──────────────────────────
    ch_comp_conv = ch_comp.dropna(subset=["Avg_Conv"]).copy()
    if not ch_comp_conv.empty:
        cat_order_conv = (ch_comp_conv.groupby("Category")["Avg_Conv"]
                          .mean().sort_values(ascending=False).index.tolist())
        cat_order_conv_short = [_short_cat(c) for c in cat_order_conv]
        fig_ch_conv = px.bar(
            ch_comp_conv, x="Cat_Short", y="Avg_Conv", color="channel",
            color_discrete_map=CMAP, barmode="group",
            category_orders={"Cat_Short": cat_order_conv_short},
            title="CONVERSION RATE: EMAIL VS SMS", height=chart_height,
            labels={"Avg_Conv": "Avg Conversion Rate", "channel": "", "Cat_Short": ""},
            hover_data={"Category": True, "Cat_Short": False, "Count": True, "Avg_Conv": ":.2%"},
        )
        fig_ch_conv.update_layout(**plot_theme(
            margin=dict(l=0, r=10, t=40, b=120),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10, family="Barlow, sans-serif"),
                       automargin=True, showgrid=False, zeroline=False),
            yaxis=dict(tickformat=".2%", tickfont=dict(size=10),
                       gridcolor=COLORS["border"], zeroline=False),
        ))
        fig_ch_conv.update_traces(marker_line_width=0.5, marker_line_color="#000")
        st.plotly_chart(fig_ch_conv, use_container_width=True)

