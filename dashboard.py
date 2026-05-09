import json
from datetime import date, timedelta

import requests
import streamlit as st


st.set_page_config(page_title="Pakistan Risk Dashboard", page_icon="📊", layout="wide")


DEFAULT_API_BASE = "https://pakistan-risk-engine.onrender.com"
REQUEST_TIMEOUT = 30


def post_json(api_base: str, endpoint: str, payload: dict) -> tuple[bool, dict]:
    url = f"{api_base.rstrip('/')}{endpoint}"
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        body = resp.json() if resp.text else {}
        if resp.ok:
            return True, body
        return False, {"status_code": resp.status_code, "error": body}
    except requests.RequestException as exc:
        return False, {"error": str(exc)}


def get_json(api_base: str, endpoint: str) -> tuple[bool, dict]:
    url = f"{api_base.rstrip('/')}{endpoint}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        body = resp.json() if resp.text else {}
        if resp.ok:
            return True, body
        return False, {"status_code": resp.status_code, "error": body}
    except requests.RequestException as exc:
        return False, {"error": str(exc)}


def sample_positions(portfolio_id: str) -> dict:
    return {
        "positions": [
            {
                "portfolio_id": portfolio_id,
                "symbol": "OGDC",
                "asset_class": "equity",
                "quantity": 1000,
                "avg_cost": 95,
                "currency": "PKR",
            },
            {
                "portfolio_id": portfolio_id,
                "symbol": "HBL",
                "asset_class": "equity",
                "quantity": 500,
                "avg_cost": 140,
                "currency": "PKR",
            },
            {
                "portfolio_id": portfolio_id,
                "symbol": "PIB_3Y",
                "asset_class": "bond",
                "quantity": 200,
                "avg_cost": 98,
                "currency": "PKR",
            },
        ]
    }


def sample_prices() -> dict:
    d = date.today()
    return {
        "prices": [
            {"symbol": "OGDC", "as_of": str(d - timedelta(days=4)), "price": 100},
            {"symbol": "OGDC", "as_of": str(d - timedelta(days=3)), "price": 102},
            {"symbol": "OGDC", "as_of": str(d - timedelta(days=2)), "price": 101},
            {"symbol": "OGDC", "as_of": str(d - timedelta(days=1)), "price": 103},
            {"symbol": "OGDC", "as_of": str(d), "price": 104},
            {"symbol": "HBL", "as_of": str(d - timedelta(days=4)), "price": 145},
            {"symbol": "HBL", "as_of": str(d - timedelta(days=3)), "price": 146},
            {"symbol": "HBL", "as_of": str(d - timedelta(days=2)), "price": 144},
            {"symbol": "HBL", "as_of": str(d - timedelta(days=1)), "price": 147},
            {"symbol": "HBL", "as_of": str(d), "price": 149},
            {"symbol": "PIB_3Y", "as_of": str(d - timedelta(days=4)), "price": 99},
            {"symbol": "PIB_3Y", "as_of": str(d - timedelta(days=3)), "price": 99.2},
            {"symbol": "PIB_3Y", "as_of": str(d - timedelta(days=2)), "price": 99.1},
            {"symbol": "PIB_3Y", "as_of": str(d - timedelta(days=1)), "price": 99.3},
            {"symbol": "PIB_3Y", "as_of": str(d), "price": 99.4},
        ]
    }


st.title("Pakistan Risk Dashboard")
st.caption("User-friendly dashboard for your Render FastAPI risk engine")

with st.sidebar:
    st.header("Configuration")
    api_base = st.text_input("API Base URL", value=DEFAULT_API_BASE)
    portfolio_id = st.text_input("Portfolio ID", value="P1")
    st.markdown("---")
    if st.button("Check API Health"):
        ok, result = get_json(api_base, "/health")
        if ok:
            st.success(f"API is up: {result}")
        else:
            st.error(result)


tab_data, tab_overview, tab_var, tab_stress = st.tabs(
    ["1) Upload Data", "2) Portfolio Overview", "3) VaR", "4) Stress Test"]
)

with tab_data:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Upload Positions")
        pos_json = st.text_area(
            "Positions JSON",
            value=json.dumps(sample_positions(portfolio_id), indent=2),
            height=320,
        )
        if st.button("Upload Positions", use_container_width=True):
            try:
                payload = json.loads(pos_json)
                ok, result = post_json(api_base, "/positions/upload", payload)
                if ok:
                    st.success("Positions uploaded successfully")
                    st.json(result)
                else:
                    st.error("Failed to upload positions")
                    st.json(result)
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")

    with col_b:
        st.subheader("Upload Prices")
        prices_json = st.text_area(
            "Prices JSON", value=json.dumps(sample_prices(), indent=2), height=320
        )
        if st.button("Upload Prices", use_container_width=True):
            try:
                payload = json.loads(prices_json)
                ok, result = post_json(api_base, "/prices/upload", payload)
                if ok:
                    st.success("Prices uploaded successfully")
                    st.json(result)
                else:
                    st.error("Failed to upload prices")
                    st.json(result)
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")

with tab_overview:
    st.subheader("Portfolio Overview")
    if st.button("Get Overview", use_container_width=True):
        ok, result = get_json(api_base, f"/portfolio/{portfolio_id}/overview")
        if ok:
            st.success("Overview fetched")
            st.metric("Total Market Value (PKR)", f"{result.get('total_market_value', 0):,.2f}")
            st.json(result)
        else:
            st.error("Failed to fetch overview")
            st.json(result)

with tab_var:
    st.subheader("Value at Risk (VaR)")
    c1, c2 = st.columns(2)
    with c1:
        confidence = st.slider("Confidence", min_value=0.80, max_value=0.99, value=0.95, step=0.01)
    with c2:
        lookback_days = st.number_input("Lookback Days", min_value=2, max_value=365, value=60)

    if st.button("Calculate VaR", use_container_width=True):
        payload = {
            "portfolio_id": portfolio_id,
            "confidence": float(confidence),
            "lookback_days": int(lookback_days),
        }
        ok, result = post_json(api_base, "/risk/var", payload)
        if ok:
            st.success("VaR calculated")
            st.metric("Historical VaR %", f"{result.get('historical_var_pct', 0) * 100:.2f}%")
            st.metric(
                "Historical VaR Amount (PKR)",
                f"{result.get('historical_var_amount_pkr', 0):,.2f}",
            )
            st.json(result)
        else:
            st.error("Failed to calculate VaR")
            st.json(result)

with tab_stress:
    st.subheader("Stress Test")
    st.caption("Enter shocks as decimal values (e.g. -0.10 = -10%).")
    shock_ogdc = st.number_input("OGDC Shock", value=-0.10, step=0.01, format="%.2f")
    shock_hbl = st.number_input("HBL Shock", value=-0.08, step=0.01, format="%.2f")
    shock_pib = st.number_input("PIB_3Y Shock", value=-0.02, step=0.01, format="%.2f")

    if st.button("Run Stress Test", use_container_width=True):
        payload = {
            "portfolio_id": portfolio_id,
            "shocks": {"OGDC": shock_ogdc, "HBL": shock_hbl, "PIB_3Y": shock_pib},
        }
        ok, result = post_json(api_base, "/risk/stress", payload)
        if ok:
            st.success("Stress test completed")
            st.metric("Base Market Value", f"{result.get('base_market_value', 0):,.2f}")
            st.metric("Stressed Market Value", f"{result.get('stressed_market_value', 0):,.2f}")
            st.metric("Portfolio PnL Impact", f"{result.get('portfolio_pnl_impact', 0):,.2f}")
            st.json(result)
        else:
            st.error("Failed to run stress test")
            st.json(result)
