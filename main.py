from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import date
import numpy as np

app = FastAPI(title="Pakistan Risk Engine MVP", version="0.1.0")

# -------------------------
# In-memory stores (MVP)
# -------------------------
positions_store: Dict[str, List[dict]] = {}
prices_store: Dict[str, List[dict]] = {}

# -------------------------
# Models
# -------------------------
class Position(BaseModel):
    portfolio_id: str
    symbol: str = Field(..., description="e.g., OGDC, HBL, PIB_3Y")
    asset_class: str = Field(..., description="equity | bond | fx | cash")
    quantity: float
    avg_cost: float
    currency: str = "PKR"

class PricePoint(BaseModel):
    symbol: str
    as_of: date
    price: float

class UploadPositionsRequest(BaseModel):
    positions: List[Position]

class UploadPricesRequest(BaseModel):
    prices: List[PricePoint]

class RiskRequest(BaseModel):
    portfolio_id: str
    confidence: float = 0.95
    lookback_days: int = 60

class StressRequest(BaseModel):
    portfolio_id: str
    shocks: Dict[str, float]  # symbol -> pct shock (e.g. -0.1 = -10%)

# -------------------------
# Helper functions
# -------------------------
def latest_price_for_symbol(symbol: str) -> Optional[float]:
    series = prices_store.get(symbol, [])
    if not series:
        return None
    # sorted by date, pick latest
    series_sorted = sorted(series, key=lambda x: x["as_of"])
    return series_sorted[-1]["price"]

def get_returns(symbol: str, lookback_days: int) -> np.ndarray:
    series = prices_store.get(symbol, [])
    if len(series) < 2:
        return np.array([])
    series_sorted = sorted(series, key=lambda x: x["as_of"])
    prices = np.array([p["price"] for p in series_sorted[-(lookback_days+1):]], dtype=float)
    if len(prices) < 2:
        return np.array([])
    rets = prices[1:] / prices[:-1] - 1.0
    return rets

def portfolio_market_value(positions: List[dict]) -> float:
    total = 0.0
    for p in positions:
        px = latest_price_for_symbol(p["symbol"])
        if px is None:
            continue
        total += p["quantity"] * px
    return total

# -------------------------
# Endpoints
# -------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/positions/upload")
def upload_positions(req: UploadPositionsRequest):
    grouped: Dict[str, List[dict]] = {}
    for p in req.positions:
        grouped.setdefault(p.portfolio_id, []).append(p.model_dump())

    for pid, plist in grouped.items():
        positions_store[pid] = plist

    return {"message": "positions uploaded", "portfolios": list(grouped.keys())}

@app.post("/prices/upload")
def upload_prices(req: UploadPricesRequest):
    for pr in req.prices:
        prices_store.setdefault(pr.symbol, []).append(pr.model_dump())
    return {"message": "prices uploaded", "symbols": list({p.symbol for p in req.prices})}

@app.get("/portfolio/{portfolio_id}/overview")
def portfolio_overview(portfolio_id: str):
    positions = positions_store.get(portfolio_id)
    if not positions:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    rows = []
    total_mv = 0.0
    for p in positions:
        px = latest_price_for_symbol(p["symbol"])
        if px is None:
            continue

        mv = p["quantity"] * px
        cost_value = p["quantity"] * p["avg_cost"]
        pnl = mv - cost_value
        total_mv += mv

        rows.append({
            "symbol": p["symbol"],
            "asset_class": p["asset_class"],
            "quantity": p["quantity"],
            "price": px,
            "market_value": mv,
            "pnl": pnl
        })

    # concentration
    for r in rows:
        r["weight"] = (r["market_value"] / total_mv) if total_mv > 0 else 0.0

    top_5 = sorted(rows, key=lambda x: x["weight"], reverse=True)[:5]
    return {
        "portfolio_id": portfolio_id,
        "total_market_value": total_mv,
        "holdings": rows,
        "top_5_concentration": top_5
    }

@app.post("/risk/var")
def calculate_var(req: RiskRequest):
    positions = positions_store.get(req.portfolio_id)
    if not positions:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Build position values and return matrix
    symbols = [p["symbol"] for p in positions]
    values = []
    returns_list = []

    for p in positions:
        px = latest_price_for_symbol(p["symbol"])
        if px is None:
            continue

        mv = p["quantity"] * px
        rets = get_returns(p["symbol"], req.lookback_days)
        if len(rets) == 0:
            continue

        values.append(mv)
        returns_list.append(rets)

    if not returns_list:
        raise HTTPException(status_code=400, detail="Not enough price history to compute VaR")

    # Align length by truncating to minimum
    min_len = min(len(r) for r in returns_list)
    mat = np.vstack([r[-min_len:] for r in returns_list])  # shape: n_assets x T
    w = np.array(values, dtype=float)
    w = w / w.sum()

    # Portfolio returns time series
    port_rets = np.dot(w, mat)  # shape: T

    # Historical VaR (positive number = potential loss)
    alpha = 1.0 - req.confidence
    var_ret = np.quantile(port_rets, alpha)  # typically negative
    total_mv = portfolio_market_value(positions)
    var_amount = abs(var_ret) * total_mv

    return {
        "portfolio_id": req.portfolio_id,
        "confidence": req.confidence,
        "lookback_days": req.lookback_days,
        "historical_var_pct": abs(float(var_ret)),
        "historical_var_amount_pkr": float(var_amount)
    }

@app.post("/risk/stress")
def stress_test(req: StressRequest):
    positions = positions_store.get(req.portfolio_id)
    if not positions:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    base_mv = 0.0
    stressed_mv = 0.0

    details = []
    for p in positions:
        px = latest_price_for_symbol(p["symbol"])
        if px is None:
            continue

        shock = req.shocks.get(p["symbol"], 0.0)
        new_px = px * (1.0 + shock)

        base = p["quantity"] * px
        stressed = p["quantity"] * new_px

        base_mv += base
        stressed_mv += stressed

        details.append({
            "symbol": p["symbol"],
            "base_price": px,
            "shock_pct": shock,
            "stressed_price": new_px,
            "base_value": base,
            "stressed_value": stressed,
            "pnl_impact": stressed - base
        })

    return {
        "portfolio_id": req.portfolio_id,
        "base_market_value": base_mv,
        "stressed_market_value": stressed_mv,
        "portfolio_pnl_impact": stressed_mv - base_mv,
        "details": details
    }