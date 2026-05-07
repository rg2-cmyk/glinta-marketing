"""
Google Sheets sync for Glinta campaign data.

Auth priority:
  1. Streamlit Secrets — key "gcp_service_account" (dict of service-account JSON).
     Set this on Streamlit Cloud via the app's Secrets settings.
  2. gcloud Application Default Credentials — automatic on local dev after
     `gcloud auth application-default login`.

Both paths use the same service account so no sheet-sharing changes are needed.
"""

import datetime
import json
import gspread
from google.auth import default, impersonated_credentials
from google.oauth2 import service_account

# ── Config ────────────────────────────────────────────────────────────────────
SERVICE_ACCOUNT_EMAIL = "glinta-sheets-bot@glinta-marketing-studs-495303.iam.gserviceaccount.com"
SHEET_ID = "1UOz9J-V-F1grQ86_KPypI7yizx6dyQWyuKdJdU-8YNQ"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

COLUMNS = [
    # ── Planning ──────────────────────────────────────────────────
    "id", "name", "category", "channel", "send_date", "phase",
    "subject_line_draft", "goal", "product", "studio", "owner",
    "priority", "tags", "created_by",
    # ── Decisioning ───────────────────────────────────────────────
    "segments", "send_time",
    "freq_cap", "freq_cap_custom",
    "suppressions", "suppressions_custom",
    "flow_target", "flow_priority", "flow_priority_custom",
    "flow_msg_overrides",
    "refinements",
    "last_saved",
    "last_modified_by",
]

# ── Auth ──────────────────────────────────────────────────────────────────────
def _get_client():
    """
    Return an authenticated gspread client.

    Path 1 — Streamlit Secrets (Streamlit Cloud):
        Add a [gcp_service_account] section to your app's Secrets with the full
        contents of the service-account JSON file. Example structure:
            [gcp_service_account]
            type = "service_account"
            project_id = "..."
            private_key_id = "..."
            private_key = "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"
            client_email = "..."
            ...

    Path 2 — gcloud ADC (local dev):
        Run `gcloud auth application-default login` once; no further config needed.
    """
    # ── Path 1: Streamlit Secrets ─────────────────────────────────────────────
    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            creds = service_account.Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]),
                scopes=SCOPES,
            )
            return gspread.authorize(creds)
    except Exception:
        pass  # no Streamlit context or secrets not set — fall through to ADC

    # ── Path 2: gcloud Application Default Credentials ────────────────────────
    source_creds, _ = default()
    target_creds = impersonated_credentials.Credentials(
        source_credentials=source_creds,
        target_principal=SERVICE_ACCOUNT_EMAIL,
        target_scopes=SCOPES,
        lifetime=3600,
    )
    return gspread.authorize(target_creds)


REMOVED_SHEET_NAME = "Removed Campaigns"
REMOVED_COLUMNS = COLUMNS + ["removed_at"]


def _get_workbook():
    """Return the open workbook (single auth call)."""
    return _get_client().open_by_key(SHEET_ID)


def _get_sheet():
    return _get_workbook().sheet1


def _get_or_create_removed_sheet(wb):
    """Return 'Removed Campaigns' worksheet from an already-open workbook."""
    try:
        ws = wb.worksheet(REMOVED_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = wb.add_worksheet(title=REMOVED_SHEET_NAME, rows=500, cols=len(REMOVED_COLUMNS))
        ws.update("A1", [REMOVED_COLUMNS])
    # Ensure header row is current
    if ws.row_values(1) != REMOVED_COLUMNS:
        ws.update("A1", [REMOVED_COLUMNS])
    return ws


# ── Helpers ───────────────────────────────────────────────────────────────────
def _join(val):
    """Flatten a list to a comma-separated string."""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v)
    return val or ""


def _campaign_to_row(c: dict) -> list:
    """Convert a campaign dict to a flat row matching COLUMNS order."""
    send_date = c.get("send_date", "")
    if isinstance(send_date, datetime.date):
        send_date = send_date.strftime("%Y-%m-%d")

    tags = _join(c.get("tags", []))

    # Decisioning fields — live in c["decisioning"] sub-dict or top-level
    dec = c.get("decisioning") or {}
    audiences = c.get("audiences", [])
    segments = _join(audiences) if audiences else _join(dec.get("segments", []))
    send_time = c.get("send_time", dec.get("send_time", ""))

    freq_cap        = dec.get("freq_cap", c.get("freq_cap", ""))
    freq_cap_custom = dec.get("freq_cap_custom", "")

    suppressions_std    = list(dec.get("suppressions", []))
    suppressions_custom = list(dec.get("suppressions_custom", []))
    suppressions_all    = _join(suppressions_std)
    suppressions_extra  = _join(suppressions_custom)

    flow_target            = dec.get("flow_target", "")
    flow_priority          = dec.get("flow_priority", "")
    flow_priority_custom   = dec.get("flow_priority_custom", "")

    # flow_msg_overrides: {flow_name: {step_num: choice}} — serialise as JSON
    raw_overrides = dec.get("flow_msg_overrides", {})
    flow_msg_overrides = json.dumps(raw_overrides) if raw_overrides else ""

    refinements = _join(dec.get("refinements", []))

    last_saved = dec.get("last_saved", c.get("last_saved", ""))
    if isinstance(last_saved, datetime.datetime):
        last_saved = last_saved.strftime("%Y-%m-%d %H:%M:%S")

    return [
        # Planning
        c.get("id", ""),
        c.get("name", ""),
        c.get("category", ""),
        c.get("channel", ""),
        send_date,
        c.get("phase", c.get("status", "")),
        c.get("subject", c.get("subject_line_draft", "")),
        c.get("goal", ""),
        c.get("product", ""),
        c.get("studio", ""),
        c.get("owner", ""),
        c.get("priority", ""),
        tags,
        c.get("created_by", ""),
        # Decisioning
        segments,
        send_time,
        freq_cap,
        freq_cap_custom,
        suppressions_all,
        suppressions_extra,
        flow_target,
        flow_priority,
        flow_priority_custom,
        flow_msg_overrides,
        refinements,
        last_saved,
        c.get("last_modified_by", ""),
    ]


# ── Date parsing ─────────────────────────────────────────────────────────────
_GS_EPOCH = datetime.date(1899, 12, 30)  # Google Sheets serial-number epoch

def _parse_date(s: str):
    """
    Parse a date string tolerantly.
    Handles:
      - ISO:                  2026-05-15
      - US short:             5/15/2026 or 05/15/2026
      - EU short:             15/5/2026 or 15/05/2026
      - US 2-digit year:      5/15/26
      - Long month:           May 15, 2026
      - Short month:          May 15, 2026
      - Alt ISO:              2026/05/15
      - Day-Month-Year:       15-May-2026 or 15 May 2026
      - Google Sheets serial: integer string like "46161"
    Returns a datetime.date or None.
    """
    if not s or not s.strip():
        return None
    s = s.strip()

    # Google Sheets serial number (integer days since Dec 30 1899)
    try:
        serial = int(s)
        if 30000 < serial < 60000:   # sanity range ≈ 1982–2064
            return _GS_EPOCH + datetime.timedelta(days=serial)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d",    # ISO              2026-05-15
        "%m/%d/%Y",    # US               5/15/2026
        "%d/%m/%Y",    # EU               15/5/2026
        "%m/%d/%y",    # US 2-digit       5/15/26
        "%B %d, %Y",   # Long month       May 15, 2026
        "%b %d, %Y",   # Short month      May 15, 2026
        "%Y/%m/%d",    # Alt ISO          2026/05/15
        "%d-%b-%Y",    # Day-Mon-Year     15-May-2026
        "%d %b %Y",    # Day Mon Year     15 May 2026
        "%d %B %Y",    # Day Month Year   15 May 2026
        "%B %d %Y",    # Month Day Year   May 15 2026
        "%m-%d-%Y",    # US dashes        5-15-2026
        "%Y.%m.%d",    # Dots             2026.05.15
    ):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── Public API ────────────────────────────────────────────────────────────────
def load_planned_campaigns() -> list[dict]:
    """
    Read all campaigns from the sheet and return them as plan_added-compatible dicts.
    Each dict has the same shape as entries added via Planning → Plan a Campaign.
    Campaigns with decisioning fields also include a 'decisioning' sub-dict.
    """
    sheet = _get_sheet()
    data = sheet.get_all_values()

    if not data or len(data) < 2:
        return []

    header = data[0]

    def _col(row, name, default=""):
        try:
            idx = header.index(name)
            return row[idx] if idx < len(row) else default
        except ValueError:
            return default

    def _to_list(s):
        if not s:
            return []
        return [x.strip() for x in s.split(",") if x.strip()]

    campaigns = []
    for row in data[1:]:
        if not any(row):
            continue

        # Skip fully anonymous rows (no name AND no id)
        if not _col(row, "name") and not _col(row, "id"):
            continue

        sd_str = _col(row, "send_date")
        send_date = _parse_date(sd_str)
        if send_date is None:
            # Don't drop the campaign — use a far-future placeholder so it
            # still appears in Upcoming and can be corrected via Edit.
            send_date = datetime.date.today() + datetime.timedelta(days=365)

        camp_id = _col(row, "id") or f"P{len(campaigns)+1:03d}"
        audiences = _to_list(_col(row, "segments"))

        camp = {
            "id":             camp_id,
            "name":           _col(row, "name"),
            "category":       _col(row, "category"),
            "channel":        _col(row, "channel", "email"),
            "send_date":      send_date,
            "status":         _col(row, "phase", "planned"),
            "phase":          _col(row, "phase", "planned"),
            "subject":        _col(row, "subject_line_draft"),
            "goal":           _col(row, "goal"),
            "product":        _col(row, "product"),
            "studio":         _col(row, "studio"),
            "owner":          _col(row, "owner"),
            "priority":       _col(row, "priority", "Medium"),
            "tags":           _to_list(_col(row, "tags")),
            "audiences":      audiences,
            "created_by":     _col(row, "created_by"),
            "last_modified_by": _col(row, "last_modified_by"),
        }

        # Decisioning fields — restore as sub-dict if any are present
        freq_cap             = _col(row, "freq_cap")
        freq_cap_custom      = _col(row, "freq_cap_custom")
        suppressions         = _to_list(_col(row, "suppressions"))
        suppressions_custom  = _to_list(_col(row, "suppressions_custom"))
        flow_target          = _col(row, "flow_target")
        flow_priority        = _col(row, "flow_priority")
        flow_priority_custom = _col(row, "flow_priority_custom")
        send_time            = _col(row, "send_time")
        refinements          = _to_list(_col(row, "refinements"))
        last_saved           = _col(row, "last_saved")

        raw_overrides = _col(row, "flow_msg_overrides")
        try:
            flow_msg_overrides = json.loads(raw_overrides) if raw_overrides else {}
        except (ValueError, TypeError):
            flow_msg_overrides = {}

        last_modified_by = _col(row, "last_modified_by")

        has_decisioning = any([
            freq_cap, suppressions, flow_target, flow_priority, send_time, audiences
        ])
        if has_decisioning:
            camp["decisioning"] = {
                "segments":             audiences,
                "freq_cap":             freq_cap,
                "freq_cap_custom":      freq_cap_custom,
                "suppressions":         suppressions,
                "suppressions_custom":  suppressions_custom,
                "flow_target":          flow_target,
                "flow_priority":        flow_priority,
                "flow_priority_custom": flow_priority_custom,
                "flow_msg_overrides":   flow_msg_overrides,
                "refinements":          refinements,
                "send_time":            send_time,
                "last_saved":           last_saved,
                "saved_by":             last_modified_by,
            }

        campaigns.append(camp)

    return campaigns


def sync_all_campaigns(campaigns: list[dict]) -> None:
    """Full sync: overwrites the sheet with header + all campaigns."""
    sheet = _get_sheet()
    rows = [COLUMNS] + [_campaign_to_row(c) for c in campaigns]
    sheet.clear()
    sheet.update("A1", rows, value_input_option="RAW")
    print(f"[sheets] Synced {len(campaigns)} campaigns to sheet.")


def remove_campaign(campaign: dict) -> None:
    """
    Move a campaign from sheet1 to the 'Removed Campaigns' worksheet.
    Uses a single workbook connection so both operations share one auth session.
    Raises on any error so the caller can surface it to the user.
    """
    campaign_id = campaign.get("id", "")
    removed_at  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    removed_row = _campaign_to_row(campaign) + [removed_at]

    wb         = _get_workbook()
    ws_main    = wb.sheet1
    ws_removed = _get_or_create_removed_sheet(wb)

    # 1. Append to Removed Campaigns
    ws_removed.append_row(removed_row, value_input_option="RAW")
    print(f"[sheets] Archived campaign '{campaign_id}' to '{REMOVED_SHEET_NAME}'.")

    # 2. Find and delete from main sheet
    if not campaign_id:
        return  # nothing to delete if no id

    data   = ws_main.get_all_values()
    id_col = COLUMNS.index("id")

    for i, row in enumerate(data[1:], start=2):
        if len(row) > id_col and row[id_col].strip() == campaign_id.strip():
            ws_main.delete_rows(i)
            print(f"[sheets] Deleted campaign '{campaign_id}' from main sheet (row {i}).")
            return

    print(f"[sheets] Campaign '{campaign_id}' not found in main sheet — nothing deleted.")


def load_removed_campaign_ids() -> set:
    """Returns set of campaign IDs in the 'Removed Campaigns' sheet."""
    try:
        wb = _get_workbook()
        try:
            ws = wb.worksheet(REMOVED_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            return set()
        data = ws.get_all_values()
        if not data or len(data) < 2:
            return set()
        header = data[0]
        id_col = header.index("id") if "id" in header else 0
        return {
            row[id_col].strip()
            for row in data[1:]
            if row and len(row) > id_col and row[id_col].strip()
        }
    except Exception:
        return set()


def load_all_campaigns() -> tuple:
    """
    Loads all campaigns from sheet1, splits into (planned, drafts),
    and excludes any IDs found in 'Removed Campaigns'.
    Returns (planned_list, drafts_list) — both are plan_added-compatible dicts.
    """
    removed_ids = load_removed_campaign_ids()
    all_camps = load_planned_campaigns()
    active  = [c for c in all_camps if c.get("id", "") not in removed_ids]
    planned = [c for c in active if c.get("status", "planned") != "draft"]
    drafts  = [c for c in active if c.get("status", "planned") == "draft"]
    return planned, drafts


def upsert_campaign(campaign: dict) -> None:
    """
    Insert or update a single campaign row, matched by id.
    Updates in-place if id exists, appends if new.
    Also re-writes the header if columns have changed.
    """
    sheet = _get_sheet()
    data = sheet.get_all_values()

    if not data:
        sheet.update("A1", [COLUMNS, _campaign_to_row(campaign)], value_input_option="RAW")
        print(f"[sheets] Created sheet with header + campaign {campaign['id']}.")
        return

    # Always keep header in sync with COLUMNS definition
    if data[0] != COLUMNS:
        sheet.update("A1", [COLUMNS], value_input_option="RAW")
        data[0] = COLUMNS
        print("[sheets] Header updated.")

    # Find existing row by id
    id_col = COLUMNS.index("id")
    campaign_id = campaign["id"]
    for i, row in enumerate(data[1:], start=2):
        if len(row) > id_col and row[id_col] == campaign_id:
            sheet.update(f"A{i}", [_campaign_to_row(campaign)], value_input_option="RAW")
            print(f"[sheets] Updated campaign {campaign_id} at row {i}.")
            return

    # Not found — append
    sheet.append_row(_campaign_to_row(campaign), value_input_option="RAW")
    print(f"[sheets] Appended new campaign {campaign_id}.")


# ── Calendar Comments ─────────────────────────────────────────────────────────
COMMENTS_SHEET_NAME = "Calendar Comments"
COMMENT_COLUMNS = ["id", "author", "text", "timestamp", "reply_to", "resolved"]


def _get_or_create_comments_sheet(wb):
    """Return 'Calendar Comments' worksheet, creating it if needed."""
    try:
        ws = wb.worksheet(COMMENTS_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = wb.add_worksheet(title=COMMENTS_SHEET_NAME, rows=2000, cols=len(COMMENT_COLUMNS))
        ws.update("A1", [COMMENT_COLUMNS])
        return ws
    # Migrate header if resolved column is missing
    existing_header = ws.row_values(1)
    if "resolved" not in existing_header:
        ws.resize(rows=2000, cols=len(COMMENT_COLUMNS))
        col_letter = chr(ord("A") + len(COMMENT_COLUMNS) - 1)
        ws.update(f"{col_letter}1", [["resolved"]])
    return ws


def load_comments() -> list[dict]:
    """
    Load all comments from the Calendar Comments sheet.
    Returns a list of dicts ordered oldest-first.
    """
    try:
        wb = _get_workbook()
        ws = _get_or_create_comments_sheet(wb)
        data = ws.get_all_values()
    except Exception as e:
        print(f"[sheets] load_comments error: {e}")
        return []

    if not data or len(data) < 2:
        return []

    header = data[0]

    def _col(row, name, default=""):
        try:
            idx = header.index(name)
            return row[idx] if idx < len(row) else default
        except ValueError:
            return default

    comments = []
    for row in data[1:]:
        if not any(row):
            continue
        comments.append({
            "id":        _col(row, "id"),
            "author":    _col(row, "author"),
            "text":      _col(row, "text"),
            "timestamp": _col(row, "timestamp"),
            "reply_to":  _col(row, "reply_to"),
            "resolved":  _col(row, "resolved", ""),
        })
    return comments


def post_comment(comment: dict) -> None:
    """
    Append a comment to the Calendar Comments sheet.
    Expected keys: id, author, text, timestamp, reply_to (optional).
    """
    row = [
        comment.get("id", ""),
        comment.get("author", ""),
        comment.get("text", ""),
        comment.get("timestamp", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        comment.get("reply_to", ""),
        "",  # resolved — empty on creation
    ]
    wb = _get_workbook()
    ws = _get_or_create_comments_sheet(wb)
    ws.append_row(row, value_input_option="USER_ENTERED")
    print(f"[sheets] Posted comment {comment.get('id')} by {comment.get('author')}.")


def resolve_comment(comment_id: str) -> None:
    """
    Mark a comment as resolved by setting the 'resolved' column to '1'.
    """
    wb = _get_workbook()
    ws = _get_or_create_comments_sheet(wb)
    data = ws.get_all_values()
    if not data or len(data) < 2:
        return
    header = data[0]
    try:
        id_col       = header.index("id")
        resolved_col = header.index("resolved")
    except ValueError:
        return
    for i, row in enumerate(data[1:], start=2):
        if len(row) > id_col and row[id_col].strip() == comment_id.strip():
            col_letter = chr(ord("A") + resolved_col)
            ws.update(f"{col_letter}{i}", [["1"]])
            print(f"[sheets] Resolved comment {comment_id} at row {i}.")
            return
    print(f"[sheets] Comment {comment_id} not found — nothing resolved.")
