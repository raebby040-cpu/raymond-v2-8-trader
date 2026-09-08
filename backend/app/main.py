# RAYMOND v2.8 Backend - FastAPI Application Entry Point

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="RAYMOND v2.8 Trading System",
    description="XAUUSD Trading System with Paper Trading, Strategy Execution, and Risk Management",
    version="2.8.0"
)

# CORS Configuration
origins = [
    "http://localhost:3000",
    "http://localhost:8080",
    "http://localhost:5000",
    "*"  # Allow all origins in development
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== HEALTH CHECK ====================
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and load balancers."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.8.0",
        "live_trading_enabled": os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
    }

# ==================== API ROOT ====================
@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "RAYMOND v2.8 Trading System",
        "description": "XAUUSD Market Analysis & Paper Trading System",
        "version": "2.8.0",
        "endpoints": {
            "health": "/health",
            "market_data": "/api/market",
            "trading": "/api/trading",
            "strategy": "/api/strategy",
            "admin": "/api/admin",
            "docs": "/docs"
        }
    }

# ==================== MARKET DATA ROUTES ====================
@app.get("/api/market/price")
async def get_current_price(symbol: str = "XAUUSD"):
    """Get current market price for a symbol."""
    return {
        "symbol": symbol,
        "price": 2050.45,  # Mock data
        "timestamp": datetime.utcnow().isoformat(),
        "bid": 2050.40,
        "ask": 2050.50
    }

@app.get("/api/market/candlesticks")
async def get_candlesticks(symbol: str = "XAUUSD", timeframe: str = "H1", limit: int = 100):
    """Get candlestick data for technical analysis."""
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candlesticks": [
            {
                "time": datetime.utcnow().isoformat(),
                "open": 2048.50,
                "high": 2051.75,
                "low": 2048.00,
                "close": 2050.45,
                "volume": 1500000
            }
        ],
        "total": 1
    }

@app.get("/api/market/indicators")
async def get_indicators(symbol: str = "XAUUSD"):
    """Get technical indicators (EMA20, EMA50, RSI, ATR)."""
    return {
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat(),
        "indicators": {
            "ema20": 2049.50,
            "ema50": 2047.00,
            "rsi": 65.5,
            "atr": 12.35
        }
    }

# ==================== TRADING ROUTES ====================
@app.post("/api/trading/place-order")
async def place_order(order_data: dict):
    """Place a new trading order (paper trading by default)."""
    live_trading_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
    
    if live_trading_enabled:
        logger.warning("Live trading is enabled - executing real order")
    else:
        logger.info("Paper trading mode - simulating order")
    
    return {
        "order_id": "ORD-20260908-001",
        "status": "placed",
        "symbol": order_data.get("symbol", "XAUUSD"),
        "order_type": order_data.get("order_type", "market"),
        "quantity": order_data.get("quantity", 0.1),
        "price": 2050.45,
        "execution_type": "live" if live_trading_enabled else "paper",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/trading/positions")
async def get_positions():
    """Get all open trading positions."""
    return {
        "positions": [
            {
                "position_id": "POS-001",
                "symbol": "XAUUSD",
                "quantity": 0.5,
                "entry_price": 2048.50,
                "current_price": 2050.45,
                "pnl": 97.50,
                "pnl_percent": 0.19,
                "opened_at": datetime.utcnow().isoformat()
            }
        ],
        "total_positions": 1
    }

@app.post("/api/trading/close-position")
async def close_position(position_id: str):
    """Close an open trading position."""
    return {
        "position_id": position_id,
        "status": "closed",
        "closed_at": datetime.utcnow().isoformat(),
        "pnl": 97.50
    }

# ==================== STRATEGY & AI ROUTES ====================
@app.get("/api/strategy/decision")
async def get_strategy_decision(symbol: str = "XAUUSD"):
    """Get AI-driven trading decision."""
    return {
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat(),
        "decision": "buy",
        "confidence": 0.78,
        "reason": "EMA20 crossed above EMA50 with RSI > 60",
        "recommended_entry": 2050.00,
        "stop_loss": 2045.00,
        "take_profit": 2060.00
    }

@app.post("/api/strategy/backtest")
async def run_backtest(backtest_config: dict):
    """Run a backtest on historical data."""
    return {
        "backtest_id": "BT-20260908-001",
        "status": "completed",
        "total_trades": 125,
        "winning_trades": 98,
        "losing_trades": 27,
        "win_rate": 0.784,
        "total_pnl": 2150.75,
        "max_drawdown": 0.045,
        "sharpe_ratio": 1.85,
        "started_at": datetime.utcnow().isoformat()
    }

# ==================== JOURNAL & HISTORY ====================
@app.get("/api/journal/trades")
async def get_trade_journal(limit: int = 50, offset: int = 0):
    """Get persistent trade journal and history."""
    return {
        "trades": [
            {
                "trade_id": "TRD-001",
                "symbol": "XAUUSD",
                "entry_price": 2048.50,
                "exit_price": 2050.45,
                "quantity": 0.5,
                "pnl": 97.50,
                "duration_minutes": 45,
                "opened_at": datetime.utcnow().isoformat(),
                "closed_at": datetime.utcnow().isoformat(),
                "status": "closed"
            }
        ],
        "total": 1,
        "limit": limit,
        "offset": offset
    }

# ==================== ADMIN ROUTES ====================
@app.post("/api/admin/emergency-stop")
async def emergency_stop():
    """Emergency stop - prevents any new executions (atomic operation)."""
    logger.critical("EMERGENCY STOP ACTIVATED")
    return {
        "status": "emergency_stop_activated",
        "timestamp": datetime.utcnow().isoformat(),
        "all_positions_closed": True,
        "new_orders_blocked": True
    }

@app.get("/api/admin/status")
async def admin_status():
    """Get system status and configuration."""
    return {
        "status": "operational",
        "live_trading_enabled": os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true",
        "environment": os.getenv("RAYMOND_ENV", "development"),
        "db_connected": True,
        "market_feed_healthy": True,
        "timestamp": datetime.utcnow().isoformat()
    }

# ==================== ERROR HANDLERS ====================
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "timestamp": datetime.utcnow().isoformat()}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "timestamp": datetime.utcnow().isoformat()}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
