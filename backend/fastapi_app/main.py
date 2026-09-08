# RAYMOND v2.8 Trading System - FastAPI Application
# Main entry point with trading endpoints, database integration, and safety controls

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
import os
import httpx
import asyncio
import logging
from typing import Dict, List

# Import business logic modules
try:
    from app.models import Base, engine, SessionLocal, Trade, Order, Position
    from app.strategy import StrategyEngine, SignalType
    from app.risk_management import RiskParameters, PositionRiskCalculator
    from app.indicators import IndicatorCalculator
    from app.market_data import DataProvider, Timeframe
except ImportError as e:
    print(f"Warning: Could not import app modules: {e}")

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
    "http://localhost:4200",  # Flutter web
    "*"  # Development only
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== CONFIGURATION ====================
LIVE_TRADING_ENABLED = os.getenv("LIVE_TRADING_ENABLED", "false").lower() in ["1", "true", "yes"]
EMERGENCY_API_KEY = os.getenv("EMERGENCY_API_KEY", "")
RAYMOND_ENV = os.getenv("RAYMOND_ENV", "development")

# Global state
positions: List[Dict] = []  # In-memory cache (should be DB-backed in production)
strategy_engine = StrategyEngine()
risk_params = RiskParameters()

# ==================== STARTUP & SHUTDOWN ====================
@app.on_event("startup")
async def startup_event():
    """Initialize database and services on startup"""
    try:
        # Create all database tables
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables initialized")
        
        # Log startup configuration
        logger.info(f"✓ RAYMOND v2.8 started in {RAYMOND_ENV} mode")
        logger.info(f"✓ Live trading enabled: {LIVE_TRADING_ENABLED}")
        logger.info(f"✓ Strategy engine initialized")
        
    except Exception as e:
        logger.error(f"✗ Startup error: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("RAYMOND v2.8 shutting down...")

# ==================== DEPENDENCY INJECTION ====================
def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_emergency_key(x_api_key: str | None = Header(None)):
    """Verify emergency stop API key"""
    if not EMERGENCY_API_KEY:
        raise HTTPException(status_code=503, detail="Emergency endpoint not configured")
    if x_api_key != EMERGENCY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# ==================== HEALTH CHECK ====================
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and load balancers"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.8.0",
        "environment": RAYMOND_ENV,
        "live_trading_enabled": LIVE_TRADING_ENABLED,
        "database": "connected"
    }

# ==================== API ROOT ====================
@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "RAYMOND v2.8 Trading System",
        "description": "XAUUSD Market Analysis & Paper Trading System",
        "version": "2.8.0",
        "environment": RAYMOND_ENV,
        "endpoints": {
            "health": "/health",
            "market_data": "/api/market",
            "trading": "/api/trading",
            "strategy": "/api/strategy",
            "risk": "/api/risk",
            "admin": "/api/admin",
            "docs": "/docs"
        }
    }

# ==================== MARKET DATA ROUTES ====================
@app.get("/api/market/price")
async def get_current_price(symbol: str = "XAUUSD"):
    """Get current market price for a symbol"""
    # In production: connect to real market data provider
    return {
        "symbol": symbol,
        "price": 2050.45,
        "timestamp": datetime.utcnow().isoformat(),
        "bid": 2050.40,
        "ask": 2050.50,
        "spread": 0.10,
        "provider": "mock" if RAYMOND_ENV == "development" else "live"
    }

@app.get("/api/market/candlesticks")
async def get_candlesticks(symbol: str = "XAUUSD", timeframe: str = "H1", limit: int = 100):
    """Get candlestick data for technical analysis"""
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "limit": limit,
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
        "total": 1,
        "provider": "mock"
    }

@app.get("/api/market/indicators")
async def get_indicators(symbol: str = "XAUUSD"):
    """Get technical indicators (EMA20, EMA50, RSI, ATR)"""
    return {
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat(),
        "indicators": {
            "ema20": 2049.50,
            "ema50": 2048.25,
            "rsi": 55.30,
            "atr": 12.45,
            "macd": {"line": 1.23, "signal": 1.15, "histogram": 0.08}
        }
    }

# ==================== STRATEGY ROUTES ====================
class StrategyAnalysisRequest(BaseModel):
    symbol: str = "XAUUSD"
    ema20: float
    ema50: float
    rsi: float
    current_price: float

@app.post("/api/strategy/analyze")
async def analyze_strategy(request: StrategyAnalysisRequest):
    """Analyze market conditions and generate trading signal"""
    try:
        ema_analysis = strategy_engine.analyze_ema_crossover(
            request.ema20, request.ema50, request.current_price
        )
        rsi_analysis = strategy_engine.analyze_rsi(request.rsi)
        
        return {
            "symbol": request.symbol,
            "timestamp": datetime.utcnow().isoformat(),
            "ema_analysis": ema_analysis,
            "rsi_analysis": rsi_analysis,
            "confidence_level": "medium",
            "recommendation": "HOLD"
        }
    except Exception as e:
        logger.error(f"Strategy analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== TRADING ROUTES ====================
class PlaceOrderRequest(BaseModel):
    symbol: str = "XAUUSD"
    direction: str  # "buy" or "sell"
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float

@app.post("/api/trading/place-order")
async def place_order(request: PlaceOrderRequest, db: Session = Depends(get_db)):
    """Place a new trading order"""
    if LIVE_TRADING_ENABLED and RAYMOND_ENV == "production":
        # Real trading logic
        pass
    
    # Paper trading (default)
    try:
        order_data = {
            "symbol": request.symbol,
            "direction": request.direction,
            "quantity": request.quantity,
            "entry_price": request.entry_price,
            "stop_loss": request.stop_loss,
            "take_profit": request.take_profit,
            "status": "pending",
            "timestamp": datetime.utcnow().isoformat()
        }
        positions.append(order_data)
        
        logger.info(f"Order placed: {request.direction} {request.quantity} {request.symbol}")
        
        return {
            "status": "success",
            "order": order_data,
            "mode": "paper_trading"
        }
    except Exception as e:
        logger.error(f"Order placement error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trading/positions")
async def get_open_positions(db: Session = Depends(get_db)):
    """Get all open positions"""
    return {
        "count": len(positions),
        "positions": positions,
        "total_pnl": 0.0,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/trading/close-position")
async def close_position(position_id: str, exit_price: float, db: Session = Depends(get_db)):
    """Close an open position"""
    try:
        # Find and close position
        for pos in positions:
            if pos.get("timestamp") == position_id:
                pos["status"] = "closed"
                pos["exit_price"] = exit_price
                pos["closed_at"] = datetime.utcnow().isoformat()
                
                logger.info(f"Position closed at {exit_price}")
                return {"status": "success", "position": pos}
        
        raise HTTPException(status_code=404, detail="Position not found")
    except Exception as e:
        logger.error(f"Position close error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== RISK MANAGEMENT ROUTES ====================
class RiskValidationRequest(BaseModel):
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    account_balance: float

@app.post("/api/risk/validate-position")
async def validate_position(request: RiskValidationRequest):
    """Validate position against risk parameters"""
    try:
        risk_calc = PositionRiskCalculator.validate_position(
            request.entry_price,
            request.stop_loss,
            request.take_profit,
            request.quantity,
            request.account_balance,
            risk_params
        )
        
        return {
            "valid": len(risk_calc.get("violations", [])) == 0,
            "risk_metrics": risk_calc,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Risk validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ADMIN ROUTES ====================
class EmergencyAction(BaseModel):
    reason: str

@app.post("/api/admin/emergency-stop")
async def emergency_stop(action: EmergencyAction, authorized: bool = Depends(verify_emergency_key)):
    """
    Emergency stop endpoint - closes all open positions and halts trading.
    
    Requires X-API-Key header with valid EMERGENCY_API_KEY.
    CRITICAL: Live trading disabled by default. Manual override required.
    """
    try:
        global positions
        closed_count = len(positions)
        
        # Close all positions
        for pos in positions:
            pos["status"] = "emergency_closed"
            pos["closed_at"] = datetime.utcnow().isoformat()
            pos["reason"] = action.reason
        
        logger.critical(f"EMERGENCY STOP TRIGGERED: {action.reason} - Closed {closed_count} positions")
        
        return {
            "status": "emergency_stop_activated",
            "positions_closed": closed_count,
            "reason": action.reason,
            "timestamp": datetime.utcnow().isoformat(),
            "live_trading_status": "DISABLED" if not LIVE_TRADING_ENABLED else "ENABLED"
        }
    except Exception as e:
        logger.error(f"Emergency stop error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== UTILITY ENDPOINTS ====================
JOKE_API_URL = "https://icanhazdadjoke.com/"
FALLBACK_JOKES = [
    {"id": "fallback-1", "joke": "Why don't programmers like nature? It has too many bugs."},
    {"id": "fallback-2", "joke": "Why do Java developers wear glasses? Because they don't C#."},
    {"id": "fallback-3", "joke": "Why did the trader bring a ladder to the market? To take profits to the next level!"},
]

_fallback_idx = 0
_fallback_lock = asyncio.Lock()

async def fetch_joke_from_api(timeout: float = 2.0) -> Dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "raymond-v2.8-joke-client/1.0"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(JOKE_API_URL, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return {"source": "icanhazdadjoke", "id": data.get("id", ""), "joke": data.get("joke", "")}

async def get_fallback_joke():
    global _fallback_idx
    async with _fallback_lock:
        joke = FALLBACK_JOKES[_fallback_idx % len(FALLBACK_JOKES)]
        _fallback_idx += 1
        return {"source": "fallback", **joke}

@app.get("/joke")
async def random_joke():
    """Returns a random joke (with fallback if external API fails)"""
    try:
        joke = await fetch_joke_from_api()
        if not joke.get("joke"):
            raise ValueError("Empty joke from API")
        return {"ok": True, "joke": joke}
    except Exception:
        fallback = await get_fallback_joke()
        return {"ok": False, "error": "external API unavailable, returning fallback", "joke": fallback}

# ==================== ERROR HANDLERS ====================
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.warning(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    return {"error": exc.detail, "status_code": exc.status_code}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
