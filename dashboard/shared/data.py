import pandas as pd
import streamlit as st
from pathlib import Path

XLSX = Path(__file__).resolve().parent.parent.parent / "Glinta_Email and SMS_Data (1).xlsx"


@st.cache_data
def load_data():
    xl = pd.ExcelFile(XLSX)

    campaigns = pd.read_excel(xl, "Campaigns")
    campaigns["Send Date"] = pd.to_datetime(campaigns["Send Date"], errors="coerce")
    for c in ["Open Rate", "Click Rate", "Conversion Rate", "Delivery Rate",
              "Unsub Rate", "CTOR", "RPR", "Revenue", "Recipients", "AOV", "Unsubscribes",
              "Delivered", "Unique Opens", "Unique Clicks", "Unique Conversions",
              "Spam Complaints", "Bounces"]:
        if c in campaigns.columns:
            campaigns[c] = pd.to_numeric(campaigns[c], errors="coerce")

    flow_monthly = pd.read_excel(xl, "Flow Monthly")
    flow_monthly["Month"] = pd.to_datetime(flow_monthly["Month"], errors="coerce")
    for c in ["Open Rate", "Click Rate", "Conversion Rate", "Revenue", "RPR",
              "Unsub Rate", "Recipients", "Unsubscribes"]:
        if c in flow_monthly.columns:
            flow_monthly[c] = pd.to_numeric(flow_monthly[c], errors="coerce")

    flow_msgs = pd.read_excel(xl, "Flow Messages")
    for c in ["Open Rate", "Click Rate", "Conversion Rate", "Revenue", "RPR", "Recipients 90d"]:
        if c in flow_msgs.columns:
            flow_msgs[c] = pd.to_numeric(flow_msgs[c], errors="coerce")

    benchmarks = pd.read_excel(xl, "Benchmarks")
    return campaigns, flow_monthly, flow_msgs, benchmarks


@st.cache_data
def load_product_studio():
    xl = pd.ExcelFile(XLSX)

    product = pd.read_excel(xl, "Product Performance")
    product["Month"] = pd.to_datetime(product["Month"], errors="coerce")
    for c in ["Emails Sent", "Conversions", "AOV", "Revenue",
              "Returns Count", "Returns Value", "Net Revenue", "Return Rate"]:
        if c in product.columns:
            product[c] = pd.to_numeric(product[c], errors="coerce")

    studio = pd.read_excel(xl, "Studio Performance")
    studio["Month"] = pd.to_datetime(studio["Month"], errors="coerce")
    for c in ["Email Sends", "Opens", "Clicks", "Open Rate", "Click Rate",
              "Appts Booked", "Appts Completed", "No-Show Rate",
              "Ecom Conversions", "Ecom Revenue", "RPR"]:
        if c in studio.columns:
            studio[c] = pd.to_numeric(studio[c], errors="coerce")

    return product, studio


@st.cache_data
def load_list_growth():
    xl = pd.ExcelFile(XLSX)
    df = pd.read_excel(xl, "List Growth")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for c in ["Email Signups", "Email Unsubs", "Email Bounces", "Email Spam",
              "Email Net Change", "Email List Size",
              "SMS Signups", "SMS Unsubs", "SMS Net Change", "SMS List Size"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@st.cache_data
def load_segments():
    xl = pd.ExcelFile(XLSX)
    df = pd.read_excel(xl, "Segments")
    df["Last Send Date"] = pd.to_datetime(df["Last Send Date"], errors="coerce")
    for c in ["Current Size", "Active 30d", "Active Rate 30d",
              "Purchasers 90d", "Purchaser Rate 90d", "AOV",
              "Est. LTV", "Churn Rate 90d"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fmt_revenue(val):
    if val >= 1_000_000:
        return f"${val/1e6:.1f}M"
    if val >= 1_000:
        return f"${val/1e3:.1f}K"
    return f"${val:,.0f}"
