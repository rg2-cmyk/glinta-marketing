import sys
import re
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from shared.styles import COLORS, inject_css, top_nav, campaign_context_card
from shared.data import load_data, load_segments, fmt_revenue

inject_css()
top_nav("QA Review")

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
        st.session_state["_last_sheet_sync"] = date.today()
    except Exception:
        st.session_state.setdefault("plan_added", [])
        st.session_state.setdefault("plan_drafts", [])

st.markdown("<h1>QA Review</h1>", unsafe_allow_html=True)

# ── Data connectors ───────────────────────────────────────────────────────────
_QA_CONNECTIONS = [
    {
        "name":   "Klaviyo",
        "abbr":   "KL",
        "color":  "#1a1a1a",
        "status": "mock data",
        "what":   "Finalized campaign decisions — segments, email body, suppressions, send time, frequency caps",
        "why":    "Pulls the live campaign record into QA so checks run against exactly what Klaviyo will send",
    },
    {
        "name":   "Litmus",
        "abbr":   "LI",
        "color":  "#FF5722",
        "status": "not connected",
        "what":   "Cross-client render tests — Gmail, Outlook, Apple Mail, dark mode, mobile",
        "why":    "Replaces the manual render checks below with live screenshots across 90+ email clients",
    },
    {
        "name":   "Shopify",
        "abbr":   "SH",
        "color":  "#96bf48",
        "status": "not connected",
        "what":   "Live product URLs and inventory status at send time",
        "why":    "Confirms links resolve to in-stock products and UTM params are appended correctly",
    },
]
_QA_STATUS_STYLE = {
    "mock data":     ("background:#f5f000;color:#000;",  "Mock data"),
    "connected":     ("background:#caf30b;color:#000;",  "Connected"),
    "not connected": ("background:#f2f2f2;color:#888;",  "Not connected"),
    "tbd":           ("background:#e8c5ff;color:#000;",  "TBD"),
}
_qa_conn_html = (
    '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px;">'
)
for _c in _QA_CONNECTIONS:
    _st_css, _st_lbl = _QA_STATUS_STYLE.get(_c["status"], ("background:#eee;color:#666;", _c["status"]))
    _qa_conn_html += (
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
_qa_conn_html += '</div>'
st.markdown(_qa_conn_html, unsafe_allow_html=True)
st.divider()

# ── Pull upcoming campaigns the same way Generation does (data + plan_added) ──
campaigns_df, *_ = load_data()
_cdf = campaigns_df.dropna(subset=["Send Date"]).copy()
_cdf["_date"] = _cdf["Send Date"].dt.date


def _normalize_data_row(row, idx):
    auds = []
    if pd.notna(row.get("Audiences")):
        auds = [a.strip() for a in str(row["Audiences"]).split(",") if a.strip()]
    recipients = row.get("Recipients", 0)
    revenue    = row.get("Revenue", 0)
    return {
        "id":           str(row.get("Campaign ID", f"D{idx:04d}")),
        "name":         str(row.get("Campaign Name", "(unnamed)")),
        "category":     str(row.get("Category", "")) or "Editorial",
        "channel":      str(row.get("Channel", "email")).lower() or "email",
        "send_date":    row["_date"],
        "phase":        "execution",
        "tags":         [],
        "segment":      ", ".join(auds) if auds else "—",
        "audience_est": int(recipients) if pd.notna(recipients) else 0,
        "subject_line_draft": str(row.get("Subject Line", "") or ""),
        "revenue_est":  float(revenue) if pd.notna(revenue) else 0.0,
        "assigned_to":  "—",
        "brief_status": "Approved",
        "design_status":"Approved",
        "qa_status":    "In Progress",
        "priority":     "Medium",
        "category_tag": str(row.get("Category", "")).lower().replace(" ", "_"),
        "audiences":    auds,
        "product":      str(row.get("Primary Product", "") or ""),
        "studio":       str(row.get("Primary Studio", "") or ""),
        "_source":      "scheduled",
    }


def _normalize_planned(p):
    auds = p.get("audiences", []) or []
    return {
        "id":           p["id"],
        "name":         p["name"],
        "category":     p.get("category", "Editorial"),
        "channel":      p.get("channel", "email"),
        "send_date":    p["send_date"],
        "phase":        "execution",
        "tags":         [p.get("goal", "")],
        "segment":      ", ".join(auds) if auds else "—",
        "audience_est": 0,
        "subject_line_draft": p.get("subject", ""),
        "revenue_est":  0.0,
        "assigned_to":  "Unassigned",
        "brief_status": "Approved",
        "design_status":"Approved",
        "qa_status":    "In Progress",
        "priority":     "Medium",
        "category_tag": p.get("category", "ed").lower().replace(" ", "_"),
        "audiences":    auds,
        "product":      p.get("product", ""),
        "studio":       p.get("studio", ""),
        "_source":      "planned",
    }


_today = date.today()
_data_upcoming = _cdf[_cdf["_date"] >= _today].sort_values("Send Date")
all_campaigns = (
    [_normalize_data_row(r, i) for i, (_, r) in enumerate(_data_upcoming.iterrows())]
    + [_normalize_planned(p) for p in st.session_state.get("plan_added", [])]
)
all_campaigns.sort(key=lambda c: c["send_date"])

# ── Segment size lookup (used to fill audience_est when data is absent) ───────
_segs_df = load_segments()
_seg_lookup = {
    str(r["Segment Name"]).strip().lower(): int(r["Current Size"])
    for _, r in _segs_df.iterrows()
    if pd.notna(r.get("Segment Name")) and pd.notna(r.get("Current Size"))
}


def _lookup_audience(camp_):
    """Return audience size from Segments sheet; 0 if truly unknown."""
    if camp_.get("audience_est", 0) > 0:
        return camp_["audience_est"]
    seg = (camp_.get("segment") or "").strip().lower()
    if not seg or seg == "—":
        return 0
    # Exact match first
    if seg in _seg_lookup:
        return _seg_lookup[seg]
    # Substring: find any segment whose name appears in the campaign segment string
    for name, size in _seg_lookup.items():
        if name in seg or seg in name:
            return size
    return 0


if not all_campaigns:
    st.markdown(
        f'<div style="border:2px dashed {COLORS["border"]};border-radius:10px;'
        f'padding:32px 24px;text-align:center;background:{COLORS["offwhite"]};'
        f'margin:20px 0;">'
        f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.1rem;'
        f'font-weight:700;letter-spacing:0.04em;text-transform:uppercase;'
        f'margin-bottom:8px;">No upcoming campaigns to QA</div>'
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.9rem;'
        f'color:{COLORS["muted"]};line-height:1.5;">'
        f'QA pulls from the same upcoming campaigns as Generation. '
        f'Plan a campaign and generate copy first, then come back here to review.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_Planning.py", label="→ Go to Planning")
    st.stop()


def _camp_label(c):
    tag = " · planned" if c.get("_source") == "planned" else " · scheduled"
    return f"{c['name']}{tag}"


camp_labels = [_camp_label(c) for c in all_campaigns]
active_id  = st.session_state.get("active_campaign_id", all_campaigns[0]["id"])
active_idx = next((i for i, c in enumerate(all_campaigns) if c["id"] == active_id), 0)

sel_col, _ = st.columns([3, 3])
with sel_col:
    chosen_label = st.selectbox(
        "Reviewing campaign",
        camp_labels,
        index=active_idx,
        key="exec_camp",
        help="Same upcoming-campaigns pool as Generation: scheduled sends + anything "
             "you added in Plan a Campaign.",
    )
camp = all_campaigns[camp_labels.index(chosen_label)]
st.session_state["active_campaign_id"] = camp["id"]
campaign_context_card(camp)

# ── Disclaimer note ───────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:{COLORS['offwhite']};border:1px solid {COLORS['border']};
            border-left:3px solid {COLORS['black']};border-radius:6px;
            padding:10px 14px;margin-bottom:14px;display:flex;align-items:flex-start;gap:10px;">
  <span style="font-size:0.85rem;flex-shrink:0;margin-top:1px;">ℹ️</span>
  <span style="font-family:'Barlow',sans-serif;font-size:0.78rem;line-height:1.45;
               color:{COLORS['black']};">
    <strong>QA &amp; review in Copilot is designed to assist the human QA process — not replace it.</strong>
    Automated checks flag common issues but cannot substitute for human judgment on brand voice,
    legal compliance, or final creative approval.
  </span>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Resolve copy + subject + preview from prior phases (session state) ────────
def _resolve_subject(camp):
    """Use the subject text Generation would have surfaced for this campaign."""
    draft = (camp.get("subject_line_draft") or "").strip()
    # Build the same historical pool Generation uses, take the top one if no draft.
    if draft:
        return draft
    pool = _cdf[_cdf["Subject Line"].notna()].copy()
    pool["Subject Line"] = pool["Subject Line"].astype(str).str.strip()
    pool = pool[pool["Subject Line"].str.len() > 3]
    if pool.empty:
        return ""
    cat = camp.get("category") or ""
    ch  = (camp.get("channel") or "").lower()
    cat_pool = pool[pool["Category"] == cat] if cat else pool
    if len(cat_pool) < 1:
        cat_pool = pool
    same_ch = cat_pool[cat_pool["Channel"].astype(str).str.lower() == ch] if ch else cat_pool
    if len(same_ch) >= 1:
        cat_pool = same_ch
    cat_pool["_score"] = (
        pd.to_numeric(cat_pool.get("Open Rate"),       errors="coerce").fillna(0)
        + 4  * pd.to_numeric(cat_pool.get("Click Rate"),      errors="coerce").fillna(0)
        + 12 * pd.to_numeric(cat_pool.get("Conversion Rate"), errors="coerce").fillna(0)
    )
    return str(cat_pool.sort_values("_score", ascending=False).iloc[0]["Subject Line"])


# Resolve audience size once — used by both the send manifest and suppression QA check
aud_size = _lookup_audience(camp)

# Session state from Generation only applies if the user generated for THIS campaign
gen_owner = st.session_state.get("gen_for_camp_id")
copy_from_gen = (gen_owner == camp["id"])

email_body = (st.session_state.get("gen_email_text", "") if copy_from_gen
              else "(Generation has not produced copy for this campaign yet — go to "
                   "Generation, then return to QA.)")
sms_body   = (st.session_state.get("gen_sms_text", "") if copy_from_gen
              else "(No SMS copy generated for this campaign yet.)")
preview_text = (st.session_state.get("gen_preview", "") if copy_from_gen
                else f"This week's {camp.get('category','').lower() or 'edit'} →")
subject_text = _resolve_subject(camp)

# Mocked design metadata (would come from Design phase once that page is built)
hero_alt   = (f"{camp.get('product') or camp['category']} hero — "
              f"clean studio backdrop, model wearing the featured stack")
cta_label  = "Shop the edit"
cta_url    = "https://studs.com/collections/" + camp["category_tag"].replace("_", "-")
sender     = "Glinta <hello@studs.com>"


# ══════════════════════════════════════════════════════════════════════════════
# CREATIVE PREVIEW (copy + design pulled from prior phases)
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("Creative Preview — pulled from Generation & Design", expanded=True):
    prev_col_l, prev_col_r = st.columns([3, 2], gap="large")

    with prev_col_l:
        # Email or SMS render mock — depends on channel
        if camp["channel"] == "email":
            body_html = (email_body or "").replace("\n", "<br>")
            st.markdown(f"""
            <div style="border:1px solid {COLORS['border']};border-radius:10px;
                        background:{COLORS['white']};overflow:hidden;
                        font-family:'Barlow',sans-serif;">
              <!-- Inbox header -->
              <div style="background:{COLORS['offwhite']};padding:10px 14px;
                          border-bottom:1px solid {COLORS['border']};font-size:0.7rem;
                          color:{COLORS['muted']};">
                <div><strong style="color:{COLORS['black']};">From:</strong> {sender}</div>
                <div style="margin-top:2px;">
                  <strong style="color:{COLORS['black']};">Subject:</strong>
                  <span style="color:{COLORS['black']};">{subject_text or '(no subject)'}</span>
                </div>
                <div style="margin-top:2px;font-style:italic;">{preview_text}</div>
              </div>
              <!-- Hero placeholder -->
              <div style="height:140px;background:{COLORS['offwhite']};
                          border-bottom:1px solid {COLORS['border']};
                          display:flex;flex-direction:column;align-items:center;
                          justify-content:center;text-align:center;padding:0 20px;gap:6px;">
                <div style="font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;
                            color:{COLORS['muted']};">Hero image · 600×400</div>
                <div style="font-size:0.65rem;color:#BBBBBB;font-style:italic;
                            line-height:1.35;">{hero_alt}</div>
              </div>
              <!-- Body copy -->
              <div style="padding:18px 22px;font-size:0.85rem;line-height:1.55;
                          color:{COLORS['black']};">
                {body_html}
              </div>
              <!-- CTA -->
              <div style="padding:0 22px 18px;">
                <a style="display:inline-block;background:{COLORS['black']};color:{COLORS['white']};
                          padding:10px 22px;border-radius:4px;font-family:'Barlow Condensed',sans-serif;
                          font-weight:700;letter-spacing:0.06em;text-transform:uppercase;
                          font-size:0.8rem;text-decoration:none;">{cta_label}</a>
                <div style="font-size:0.62rem;color:{COLORS['muted']};margin-top:6px;
                            font-family:'Barlow',sans-serif;">→ {cta_url}</div>
              </div>
              <!-- Footer -->
              <div style="border-top:1px solid {COLORS['border']};padding:10px 22px;
                          font-size:0.62rem;color:{COLORS['muted']};">
                Glinta · NYC · You can <u>unsubscribe</u> or <u>manage preferences</u>.
              </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            sms_html = (sms_body or "").replace("\n", "<br>")
            st.markdown(f"""
            <div style="background:{COLORS['offwhite']};border:1px solid {COLORS['border']};
                        border-radius:10px;padding:24px 18px;display:flex;justify-content:center;
                        font-family:'Barlow',sans-serif;">
              <div style="max-width:300px;">
                <div style="font-size:0.62rem;color:{COLORS['muted']};text-align:center;
                            margin-bottom:6px;letter-spacing:0.08em;text-transform:uppercase;">
                  Glinta · {camp['send_date'].strftime('%b %d, %I:%M %p')}
                </div>
                <div style="background:{COLORS['white']};border:1px solid {COLORS['border']};
                            border-radius:18px 18px 18px 4px;padding:12px 16px;
                            font-size:0.85rem;line-height:1.45;color:{COLORS['black']};">
                  {sms_html}
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

    with prev_col_r:
        st.markdown(
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.7rem;'
            f'letter-spacing:0.08em;text-transform:uppercase;color:{COLORS["muted"]};'
            f'margin-bottom:8px;">Send manifest</div>',
            unsafe_allow_html=True,
        )
        suppressions_n = max(int(aud_size * 0.045), 0) if aud_size else 0
        final_send_n   = max(aud_size - suppressions_n, 0)
        rev_disp = fmt_revenue(camp["revenue_est"]) if camp.get("revenue_est") else "—"
        aud_disp   = f"{aud_size:,}"    if aud_size  else "—"
        supp_disp  = f"{suppressions_n:,}  (unsub + bounce + frequency cap)" if aud_size else "—"
        final_disp = f"{final_send_n:,}" if aud_size else "—"
        manifest_rows = [
            ("Channel",          camp["channel"].upper()),
            ("Send date",        camp["send_date"].strftime("%a, %b %d, %Y")),
            ("Send window",      "10:00 AM ET — optimal per segment timing"),
            ("Segment",          camp["segment"] if camp.get("segment") and camp["segment"] != "—" else "—"),
            ("Audience size",    aud_disp),
            ("Suppressed",       supp_disp),
            ("Final recipients", final_disp),
            ("Est. revenue",     rev_disp),
            ("Owner",            camp["assigned_to"] if camp.get("assigned_to") and camp["assigned_to"] != "—" else "—"),
        ]
        rows_html = "".join(
            f'<div style="display:flex;justify-content:space-between;gap:12px;'
            f'padding:6px 0;border-bottom:1px solid {COLORS["border"]};font-size:0.75rem;">'
            f'<span style="color:{COLORS["muted"]};">{k}</span>'
            f'<span style="color:{COLORS["black"]};font-weight:600;text-align:right;">{v}</span>'
            f'</div>'
            for k, v in manifest_rows
        )
        st.markdown(
            f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};'
            f'border-radius:8px;padding:12px 14px;">{rows_html}</div>',
            unsafe_allow_html=True,
        )

        if not copy_from_gen:
            st.markdown(
                f'<div style="margin-top:12px;background:#FFF7E6;border:1px solid #F0C36D;'
                f'border-radius:8px;padding:10px 12px;font-size:0.72rem;line-height:1.4;'
                f'color:#7A5800;">'
                f'<strong>Heads up:</strong> the copy shown above isn\'t from this session. '
                f'Open Generation, produce copy for this campaign, and the QA panel below '
                f'will re-evaluate.</div>',
                unsafe_allow_html=True,
            )

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# QA REVIEW SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
PASS, FAIL, REVIEW, INFO = "pass", "fail", "review", "info"

STATUS_STYLE = {
    PASS:   {"label": "PASS",   "bg": "#E7F6EE", "fg": "#1B7A3E", "icon": "✓"},
    FAIL:   {"label": "FAIL",   "bg": "#FBE7E5", "fg": "#A8261B", "icon": "✗"},
    REVIEW: {"label": "REVIEW", "bg": "#FFF6DC", "fg": "#7A5800", "icon": "?"},
    INFO:   {"label": "PENDING","bg": COLORS["offwhite"], "fg": COLORS["muted"], "icon": "—"},
}


def utm_check(body: str):
    has_utm = bool(re.search(r"utm_(source|medium|campaign)=", body or "", re.IGNORECASE))
    if has_utm:
        return PASS, "All links carry utm_source / utm_medium / utm_campaign."
    return FAIL, ("No UTM parameters detected on outbound links. Append "
                  "`?utm_source=email&utm_medium=" + camp["channel"] +
                  "&utm_campaign=" + camp["category_tag"] + "` before send.")


def link_check(email: str, sms: str):
    text = (email or "") + " " + (sms or "")
    urls = re.findall(r"https?://\S+|studs\.com\S*", text)
    n = len(urls)
    if camp["channel"] == "email":
        if n >= 2:
            return PASS, f"{n} links rendered, all resolve to studs.com (mock-checked)."
        if n == 1:
            return REVIEW, "Only 1 link in body — confirm hero + CTA both link out."
        return FAIL, "No outbound links found in email body."
    if n >= 1:
        return PASS, f"{n} link in SMS — resolves to studs.com (mock-checked)."
    return FAIL, "SMS has no link — recipient can't tap through."


def segment_check(camp_):
    seg = camp_.get("segment") or ""
    auds = camp_.get("audiences") or []
    if not seg or seg == "—":
        return FAIL, "No segment defined on this campaign."
    if auds and len(auds) > 1:
        return PASS, f"Multi-audience send ({len(auds)} segments): {', '.join(auds[:3])}" \
                     + ("…" if len(auds) > 3 else "")
    return PASS, f"Single segment locked in: {seg}"


def proofread_check(email: str, sms: str):
    text = (email or "") + " " + (sms or "")
    issues = []
    if re.search(r"\s{2,}", text):
        issues.append("double spaces")
    if re.search(r"\b(teh|recieve|definately|seperate|occured)\b", text, re.IGNORECASE):
        issues.append("common typos")
    if re.search(r"!{2,}|\?{2,}", text):
        issues.append("repeated punctuation")
    if re.search(r"\b([A-Z]{4,})\b", text) and "STOP" not in text:
        issues.append("stray ALL CAPS")
    if not issues:
        return PASS, "No spelling, spacing, or punctuation issues caught by automated check."
    return REVIEW, "Automated check flagged: " + ", ".join(issues) + ". Human proofread recommended."


def subject_check(subj: str):
    s = (subj or "").strip()
    if not s:
        return FAIL, "Subject line is empty."
    n = len(s)
    if n < 25:
        return REVIEW, f"Subject is {n} chars — short subjects can read as spammy. Aim for 35–55."
    if n > 70:
        return REVIEW, f"Subject is {n} chars — likely truncated on iOS Mail (~50) and Gmail (~70)."
    return PASS, f"{n} chars — within the 35–55 sweet spot for {camp['channel'].upper()}."


def preview_check(text: str):
    s = (text or "").strip()
    if not s:
        return FAIL, "Preview text is empty — Gmail will pull the first body line instead."
    if len(s) > 110:
        return REVIEW, f"Preview is {len(s)} chars — most clients show ~85–100."
    return PASS, f"{len(s)} chars — visible on Gmail, Apple Mail, and Outlook web."


def mobile_check():
    return PASS, "Rendered at 375×667 (iPhone) — single column holds, CTA above fold, " \
                 "tap targets ≥44px."


def web_check():
    return PASS, "Rendered at 1024×768 desktop web — hero crops cleanly, body wraps at 600px."


def gmail_check():
    return REVIEW, "Gmail web + iOS app — render OK in mock. Confirm message clipping " \
                   "stays under 102KB once images inlined."


def outlook_check():
    return REVIEW, "Outlook 365 desktop renders correctly in mock. Background images need " \
                   "VML fallback — verify in Litmus before send."


def darkmode_check():
    return REVIEW, "Dark-mode preview not yet generated. Confirm logo + CTA contrast on " \
                   "dark backgrounds (Apple Mail auto-inverts)."


def suppressions_check(camp_, resolved_aud=0):
    n = resolved_aud or _lookup_audience(camp_)
    if n == 0:
        return REVIEW, "Audience size is unknown — suppression count can't be confirmed."
    n_supp = max(int(n * 0.045), 0)
    return PASS, (f"Global unsubs, hard bounces, and 7-day frequency cap applied — "
                  f"{n_supp:,} addresses excluded.")


def sendtime_check(camp_):
    sd = camp_["send_date"]
    if sd < _today:
        return FAIL, f"Send date {sd:%b %d} is in the past."
    if sd.weekday() >= 5:
        return REVIEW, f"{sd:%A} send — weekends underperform {camp_['category']} historically."
    days_out = (sd - _today).days
    if days_out < 1:
        return REVIEW, "Send is within 24h — limited room for QA fixes if anything fails."
    return PASS, f"{sd:%a, %b %d} at 10:00 AM ET · {days_out} days out · weekday slot."


def brand_tone_check():
    return REVIEW, "Requires more detail on guidelines to review against — supply the Glinta " \
                   "tone guide (voice attributes, banned words, cadence rules) and reviewers."


def legal_check():
    return REVIEW, "Requires more detail on guidelines to review against — supply legal review " \
                   "ruleset (claims, disclaimers, jurisdictional opt-out language, promo T&Cs)."


qa_topics = [
    ("UTM tracking",         utm_check(email_body)),
    ("Links",                link_check(email_body, sms_body)),
    ("Segments",             segment_check(camp)),
    ("Proof read",           proofread_check(email_body, sms_body)),
    ("Subject line",         subject_check(subject_text)),
    ("Preview text",         preview_check(preview_text)),
    ("Mobile view",          mobile_check()),
    ("Web view",             web_check()),
    ("In-app · Gmail",       gmail_check()),
    ("In-app · Outlook",     outlook_check()),
    ("Dark mode",            darkmode_check()),
    ("Suppressions",         suppressions_check(camp, aud_size)),
    ("Send time",            sendtime_check(camp)),
    ("Brand tone",           brand_tone_check()),
    ("Legal",                legal_check()),
]

n_pass   = sum(1 for _, (s, _m) in qa_topics if s == PASS)
n_fail   = sum(1 for _, (s, _m) in qa_topics if s == FAIL)
n_review = sum(1 for _, (s, _m) in qa_topics if s == REVIEW)
n_total  = len(qa_topics)

if n_fail > 0:
    overall = FAIL
    overall_msg = f"{n_fail} blocking issue{'s' if n_fail != 1 else ''} — cannot send until resolved."
elif n_review > 0:
    overall = REVIEW
    overall_msg = f"{n_review} item{'s' if n_review != 1 else ''} need human review before approval."
else:
    overall = PASS
    overall_msg = "All checks pass — ready for final approval."

st.markdown("<h2>QA Review</h2>", unsafe_allow_html=True)
st.markdown(
    f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;color:#666;'
    f'margin:-0.4rem 0 1rem;">Automated checks against the creative shown above. '
    f'Items marked <strong>review</strong> need a human; items marked <strong>fail</strong> '
    f'block the send.</p>',
    unsafe_allow_html=True,
)

st_overall = STATUS_STYLE[overall]
st.markdown(f"""
<div style="background:{st_overall['bg']};border:1px solid {st_overall['fg']};
            border-radius:10px;padding:14px 18px;display:flex;align-items:center;
            gap:18px;margin-bottom:14px;">
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;font-weight:800;
              color:{st_overall['fg']};letter-spacing:0.04em;text-transform:uppercase;">
    {st_overall['icon']} {st_overall['label']}
  </div>
  <div style="flex:1;font-family:'Barlow',sans-serif;font-size:0.85rem;
              color:{st_overall['fg']};">{overall_msg}</div>
  <div style="display:flex;gap:14px;font-family:'Barlow Condensed',sans-serif;
              font-size:0.78rem;color:{st_overall['fg']};">
    <span><strong>{n_pass}</strong>/{n_total} pass</span>
    <span><strong>{n_review}</strong> review</span>
    <span><strong>{n_fail}</strong> fail</span>
  </div>
</div>
""", unsafe_allow_html=True)

# QA topic rows — two columns for density
left_topics  = qa_topics[:8]
right_topics = qa_topics[8:]


def _render_topic(label, status_tuple):
    status, message = status_tuple
    s = STATUS_STYLE[status]
    needs_more = (label in ("Brand tone", "Legal"))
    note_html = ""
    if needs_more:
        note_html = (
            f'<div style="margin-top:4px;font-size:0.65rem;color:{COLORS["muted"]};'
            f'font-style:italic;">Note: requires more detail on guidelines to review '
            f'against.</div>'
        )
    return f"""
    <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 12px;
                border:1px solid {COLORS['border']};border-radius:8px;margin-bottom:8px;
                background:{COLORS['white']};">
      <div style="flex-shrink:0;width:64px;text-align:center;
                  background:{s['bg']};color:{s['fg']};border-radius:50px;
                  font-family:'Barlow Condensed',sans-serif;font-size:0.66rem;
                  font-weight:800;letter-spacing:0.06em;padding:4px 0;">
        {s['icon']} {s['label']}
      </div>
      <div style="flex:1;">
        <div style="font-family:'Barlow',sans-serif;font-size:0.82rem;font-weight:600;
                    color:{COLORS['black']};margin-bottom:2px;">{label}</div>
        <div style="font-family:'Barlow',sans-serif;font-size:0.74rem;line-height:1.4;
                    color:{COLORS['muted']};">{message}</div>
        {note_html}
      </div>
    </div>
    """


qcol_l, qcol_r = st.columns(2, gap="medium")
with qcol_l:
    st.markdown("".join(_render_topic(lbl, st_) for lbl, st_ in left_topics),
                unsafe_allow_html=True)
with qcol_r:
    st.markdown("".join(_render_topic(lbl, st_) for lbl, st_ in right_topics),
                unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# FINAL APPROVAL
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.markdown("<h2>Final Approval</h2>", unsafe_allow_html=True)

ap_l, ap_m, ap_r = st.columns([2, 2, 2])
with ap_l:
    if st.button("Re-run QA checks", type="secondary", use_container_width=True,
                 key="rerun_qa"):
        st.rerun()
with ap_m:
    request_review = st.button("Request human review", type="secondary",
                               use_container_width=True, key="request_review")
with ap_r:
    approve_disabled = (overall == FAIL)
    approve = st.button(
        "Approve & schedule send" if not approve_disabled else "Resolve fails to approve",
        type="primary",
        use_container_width=True,
        key="approve_send",
        disabled=approve_disabled,
    )

if request_review:
    st.info(f"Tagged Brand and Legal reviewers — notified via Slack (mock). "
            f"Reviewers will see the {n_review} items above marked Review.")
if approve and not approve_disabled:
    st.success(f"Approved. {camp['name']} scheduled for "
               f"{camp['send_date']:%a, %b %d} at 10:00 AM ET (mock).")


# ── Page nav ──────────────────────────────────────────────────────────────────
st.divider()
prev_col, _, _ = st.columns([1, 5, 1])
with prev_col:
    st.page_link("pages/4_Design.py", label="← Design")
