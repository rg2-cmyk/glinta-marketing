"""
Audit trail for all editable fields across the prototype.

Usage — log an edit when a value is saved:
    from shared.audit import log_edit, last_edited_html, show_history

    log_edit("camp_MC001_subject_line", new_value)
    st.markdown(last_edited_html("camp_MC001_subject_line"), unsafe_allow_html=True)

Usage — show full history in an expander:
    show_history("camp_MC001_subject_line")
"""

import os
import streamlit as st
from datetime import datetime
from shared.styles import COLORS

# ── Identity ──────────────────────────────────────────────────────────────────
# Pull from session (user can override in settings), fall back to OS username.
_OS_USER = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

DISPLAY_NAMES = {
    "riddhimagoel": "Riddhi Goel",
}


def current_user() -> str:
    """Returns the display name of whoever is running the app."""
    override = st.session_state.get("_identity_override")
    if override:
        return override
    return DISPLAY_NAMES.get(_OS_USER, _OS_USER)


def set_identity(name: str):
    """Let a user override their display name for this session."""
    st.session_state["_identity_override"] = name


# ── Log ───────────────────────────────────────────────────────────────────────
_LOG_KEY = "_audit_log"


def _log() -> dict:
    if _LOG_KEY not in st.session_state:
        st.session_state[_LOG_KEY] = {}
    return st.session_state[_LOG_KEY]


def log_edit(field_key: str, new_value, label: str = ""):
    """
    Record an edit to a named field.

    Args:
        field_key:  Unique string identifying the field (e.g. 'camp_MC001_subject').
        new_value:  The new value after the edit.
        label:      Human-readable field name for display (optional).
    """
    entry = {
        "user":      current_user(),
        "timestamp": datetime.now(),
        "value":     str(new_value)[:500],   # cap stored length
        "label":     label or field_key,
    }
    log = _log()
    if field_key not in log:
        log[field_key] = []
    log[field_key].append(entry)
    st.session_state[_LOG_KEY] = log


def get_history(field_key: str) -> list[dict]:
    """Returns the full edit history for a field, newest first."""
    return list(reversed(_log().get(field_key, [])))


def last_edit(field_key: str) -> dict | None:
    """Returns the most recent edit entry, or None."""
    history = _log().get(field_key, [])
    return history[-1] if history else None


# ── Display helpers ───────────────────────────────────────────────────────────
def _fmt_ts(ts: datetime) -> str:
    now = datetime.now()
    diff = now - ts
    if diff.seconds < 60 and diff.days == 0:
        return "just now"
    if diff.seconds < 3600 and diff.days == 0:
        return f"{diff.seconds // 60}m ago"
    if diff.days == 0:
        return f"{diff.seconds // 3600}h ago"
    if diff.days == 1:
        return f"yesterday at {ts.strftime('%-I:%M %p')}"
    return ts.strftime("%-d %b at %-I:%M %p")


def last_edited_html(field_key: str) -> str:
    """
    Returns a one-line 'Last edited by X · 3m ago' HTML string.
    Returns empty string if the field has never been edited.
    """
    entry = last_edit(field_key)
    if not entry:
        return ""
    ts_str = _fmt_ts(entry["timestamp"])
    return (
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.65rem;'
        f'color:{COLORS["muted"]};margin-top:3px;line-height:1.4;">'
        f'Last edited by <strong>{entry["user"]}</strong> · {ts_str}'
        f'</div>'
    )


def show_history(field_key: str, label: str = ""):
    """Renders the full edit history for a field inside a Streamlit expander."""
    history = get_history(field_key)
    if not history:
        return
    title = label or field_key
    with st.expander(f"Edit history — {title} ({len(history)} change{'s' if len(history) != 1 else ''})",
                     expanded=False):
        for i, entry in enumerate(history):
            ts_str = entry["timestamp"].strftime("%-d %b %Y · %-I:%M %p")
            is_latest = (i == 0)
            st.markdown(
                f'<div style="display:flex;gap:12px;align-items:flex-start;'
                f'padding:8px 0;border-bottom:1px solid {COLORS["border"]};">'
                f'<div style="font-size:0.72rem;color:{COLORS["muted"]};white-space:nowrap;'
                f'min-width:140px;">{ts_str}</div>'
                f'<div style="flex:1;">'
                f'<span style="font-size:0.72rem;font-weight:600;">{entry["user"]}</span>'
                + ('&nbsp;<span style="background:' + COLORS["yellow"] + ';font-size:0.6rem;padding:1px 6px;border-radius:3px;font-weight:600;">current</span>' if is_latest else '')
                + f'<div style="font-size:0.78rem;color:{COLORS["black"]};margin-top:3px;">'
                + (entry["value"] or '<em style="color:' + COLORS["muted"] + '">(cleared)</em>')
                + f'</div></div></div>',
                unsafe_allow_html=True,
            )


def audited_text_input(
    label: str,
    field_key: str,
    value: str = "",
    height: int | None = None,
    placeholder: str = "",
    help: str = "",
    widget_key: str = "",
) -> str:
    """
    Drop-in replacement for st.text_input / st.text_area that auto-logs edits.
    Uses a Save button pattern so edits are only logged when the user confirms.

    Returns the current saved value.
    """
    saved_key = f"_saved_{field_key}"
    if saved_key not in st.session_state:
        st.session_state[saved_key] = value

    saved_val = st.session_state[saved_key]
    wkey = widget_key or f"_widget_{field_key}"

    if height:
        draft = st.text_area(label, value=saved_val, height=height,
                             placeholder=placeholder, help=help, key=wkey)
    else:
        draft = st.text_input(label, value=saved_val,
                              placeholder=placeholder, help=help, key=wkey)

    changed = draft != saved_val
    col_save, col_meta = st.columns([1, 5])
    with col_save:
        if st.button("Save", key=f"_save_{field_key}", type="primary",
                     disabled=not changed):
            st.session_state[saved_key] = draft
            log_edit(field_key, draft, label=label)
            st.rerun()

    with col_meta:
        st.markdown(last_edited_html(field_key), unsafe_allow_html=True)

    return st.session_state[saved_key]


def audit_stamp(field_key: str):
    """
    Renders just the 'Last edited by X · Ym ago' line inline.
    Call this after any widget whose edits you've manually logged.
    """
    html = last_edited_html(field_key)
    if html:
        st.markdown(html, unsafe_allow_html=True)
