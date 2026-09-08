"""Database migration utilities"""
import logging
from sqlalchemy import text
from app.database import engine, SessionLocal, Base
from app.models import Trade, Position, StrategyDecision, RiskEvent, Journal, Account, Backtest

logger = logging.getLogger(__name__)

def create_all_tables():
    """Create all database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("All tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        return False

def drop_all_tables():
    """Drop all database tables (CAREFUL!)"""
    try:
        Base.metadata.drop_all(bind=engine)
        logger.warning("All tables dropped")
        return True
    except Exception as e:
        logger.error(f"Failed to drop tables: {e}")
        return False

def seed_demo_data():
    """Seed database with demo data for testing"""
    db = SessionLocal()
    try:
        # Check if data already exists
        if db.query(Account).count() > 0:
            logger.info("Demo data already exists")
            return True
        
        # Create demo account
        demo_account = Account(
            account_id="DEMO-001",
            broker="demo",
            account_type="demo",
            currency="USD",
            initial_balance=10000.0,
            current_balance=10000.0,
            equity=10000.0,
            margin_available=10000.0,
            is_active=True
        )
        db.add(demo_account)
        
        # Create demo trades
        from datetime import datetime, timedelta
        from app.models import TradeStatus, OrderType, OrderDirection
        
        demo_trades = [
            Trade(
                trade_id="DEMO-TRD-001",
                symbol="XAUUSD",
                direction=OrderDirection.BUY,
                order_type=OrderType.MARKET,
                entry_price=2048.50,
                exit_price=2050.45,
                quantity=0.5,
                stop_loss=2045.00,
                take_profit=2055.00,
                status=TradeStatus.CLOSED,
                pnl=97.50,
                pnl_percent=0.19,
                opened_at=datetime.utcnow() - timedelta(days=1),
                closed_at=datetime.utcnow(),
                broker="demo",
                strategy_decision="strong_buy",
                confidence=0.85
            ),
            Trade(
                trade_id="DEMO-TRD-002",
                symbol="XAUUSD",
                direction=OrderDirection.SELL,
                order_type=OrderType.MARKET,
                entry_price=2052.00,
                quantity=0.3,
                stop_loss=2055.00,
                take_profit=2048.00,
                status=TradeStatus.OPEN,
                opened_at=datetime.utcnow(),
                broker="demo",
                strategy_decision="buy",
                confidence=0.72
            )
        ]
        
        for trade in demo_trades:
            db.add(trade)
        
        # Create demo strategy decisions
        demo_decisions = [
            StrategyDecision(
                symbol="XAUUSD",
                decision="strong_buy",
                confidence=0.85,
                current_price=2050.45,
                bid=2050.40,
                ask=2050.50,
                ema20=2049.50,
                ema50=2047.00,
                rsi=65.5,
                atr=12.35,
                risk_level="medium",
                executed=False
            )
        ]
        
        for decision in demo_decisions:
            db.add(decision)
        
        db.commit()
        logger.info("Demo data seeded successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to seed demo data: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def get_database_info():
    """Get database connection info and stats"""
    db = SessionLocal()
    try:
        info = {
            "trades_count": db.query(Trade).count(),
            "positions_count": db.query(Position).count(),
            "strategy_decisions_count": db.query(StrategyDecision).count(),
            "risk_events_count": db.query(RiskEvent).count(),
            "journal_entries_count": db.query(Journal).count(),
            "accounts_count": db.query(Account).count(),
            "backtests_count": db.query(Backtest).count()
        }
        return info
    except Exception as e:
        logger.error(f"Failed to get database info: {e}")
        return {}
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python migrations.py [create|drop|seed|info]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "create":
        create_all_tables()
    elif command == "drop":
        response = input("Are you sure you want to drop all tables? (yes/no): ")
        if response.lower() == "yes":
            drop_all_tables()
    elif command == "seed":
        create_all_tables()
        seed_demo_data()
    elif command == "info":
        info = get_database_info()
        print("Database Info:")
        for key, value in info.items():
            print(f"  {key}: {value}")
    else:
        print(f"Unknown command: {command}")
