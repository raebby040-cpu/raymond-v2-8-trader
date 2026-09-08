"""
RAYMOND v2.8 - Broker Adapters
MT5 and Exness broker connectors for order execution and verification
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from enum import Enum
import os

logger = logging.getLogger(__name__)

# ==================== BROKER ENUMS ====================
class BrokerType(str, Enum):
    MT5 = "mt5"
    EXNESS = "exness"

class OrderStatus(str, Enum):
    PENDING = "pending"
    PLACED = "placed"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

# ==================== BASE BROKER ADAPTER ====================
class BaseBrokerAdapter:
    """Base class for broker adapters"""
    
    def __init__(self, broker_type: BrokerType):
        self.broker_type = broker_type
        self.is_connected = False
        self.account_info = {}
        self.open_orders = {}
        self.closed_orders = {}
        self.execution_history = []
        
        logger.info(f"Initializing {broker_type.value} broker adapter")
    
    async def connect(self) -> bool:
        """Connect to broker"""
        raise NotImplementedError
    
    async def disconnect(self) -> bool:
        """Disconnect from broker"""
        raise NotImplementedError
    
    async def place_order(self, order_data: Dict) -> Dict:
        """Place a new order"""
        raise NotImplementedError
    
    async def cancel_order(self, order_id: str) -> Dict:
        """Cancel an open order"""
        raise NotImplementedError
    
    async def close_position(self, position_id: str) -> Dict:
        """Close an open position"""
        raise NotImplementedError
    
    async def get_account_info(self) -> Dict:
        """Get account information"""
        raise NotImplementedError
    
    async def get_open_positions(self) -> Dict:
        """Get all open positions"""
        raise NotImplementedError

# ==================== MT5 BROKER ADAPTER ====================
class MT5BrokerAdapter(BaseBrokerAdapter):
    """MetaTrader 5 broker adapter"""
    
    def __init__(self):
        super().__init__(BrokerType.MT5)
        self.login = os.getenv("MT5_LOGIN", "demo_login")
        self.password = os.getenv("MT5_PASSWORD", "demo_password")
        self.server = os.getenv("MT5_SERVER", "MT5-Demo")
        self.account_type = os.getenv("MT5_ACCOUNT_TYPE", "demo")
    
    async def connect(self) -> bool:
        """Connect to MT5 broker"""
        try:
            # In production, use actual MT5 API
            # import MetaTrader5 as mt5
            # if not mt5.initialize(login=self.login, password=self.password, server=self.server):
            #     logger.error("MT5 initialization failed")
            #     return False
            
            logger.info(f"Connected to MT5: {self.server} (Account: {self.account_type})")
            self.is_connected = True
            
            # Mock account info
            self.account_info = {
                "login": self.login,
                "server": self.server,
                "balance": 10000.0,
                "equity": 10000.0,
                "margin": 0.0,
                "free_margin": 10000.0,
                "margin_level": 0.0,
                "currency": "USD"
            }
            
            return True
        except Exception as e:
            logger.error(f"MT5 connection failed: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from MT5"""
        try:
            # mt5.shutdown()
            logger.info("Disconnected from MT5")
            self.is_connected = False
            return True
        except Exception as e:
            logger.error(f"MT5 disconnection failed: {e}")
            return False
    
    async def place_order(self, order_data: Dict) -> Dict:
        """Place order on MT5"""
        if not self.is_connected:
            return {"status": "error", "message": "Not connected to MT5"}
        
        try:
            order_id = f"MT5-{len(self.open_orders) + 1:06d}"
            symbol = order_data.get("symbol", "XAUUSD")
            order_type = order_data.get("order_type", "market")
            direction = order_data.get("direction", "buy")
            quantity = order_data.get("quantity", 0.1)
            price = order_data.get("price", 0.0)
            
            # In production: use mt5.order_send()
            order_result = {
                "order_id": order_id,
                "symbol": symbol,
                "type": order_type,
                "direction": direction,
                "quantity": quantity,
                "price": price,
                "status": OrderStatus.FILLED,
                "filled_at": datetime.utcnow().isoformat(),
                "broker": "mt5"
            }
            
            self.open_orders[order_id] = order_result
            self.execution_history.append(order_result)
            
            logger.info(f"MT5 Order placed: {order_id} ({symbol} {quantity} {direction})")
            
            return order_result
        except Exception as e:
            logger.error(f"MT5 order placement failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def cancel_order(self, order_id: str) -> Dict:
        """Cancel MT5 order"""
        if order_id not in self.open_orders:
            return {"status": "error", "message": "Order not found"}
        
        order = self.open_orders.pop(order_id)
        order["status"] = OrderStatus.CANCELLED
        order["cancelled_at"] = datetime.utcnow().isoformat()
        
        logger.info(f"MT5 Order cancelled: {order_id}")
        return order
    
    async def close_position(self, position_id: str) -> Dict:
        """Close MT5 position"""
        try:
            # In production: use mt5.order_send() with opposite direction
            result = {
                "position_id": position_id,
                "status": "closed",
                "closed_at": datetime.utcnow().isoformat(),
                "broker": "mt5"
            }
            
            logger.info(f"MT5 Position closed: {position_id}")
            return result
        except Exception as e:
            logger.error(f"MT5 position close failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def get_account_info(self) -> Dict:
        """Get MT5 account info"""
        return {
            "broker": "mt5",
            "account_info": self.account_info,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def get_open_positions(self) -> Dict:
        """Get MT5 open positions"""
        return {
            "broker": "mt5",
            "positions": list(self.open_orders.values()),
            "total": len(self.open_orders),
            "timestamp": datetime.utcnow().isoformat()
        }

# ==================== EXNESS BROKER ADAPTER ====================
class ExnessBrokerAdapter(BaseBrokerAdapter):
    """Exness broker adapter"""
    
    def __init__(self):
        super().__init__(BrokerType.EXNESS)
        self.api_token = os.getenv("EXNESS_TOKEN", "demo_token")
        self.account_id = os.getenv("EXNESS_ACCOUNT_ID", "demo_account")
        self.account_type = os.getenv("EXNESS_ACCOUNT_TYPE", "demo")
        self.api_base_url = "https://api.exness.com/v1"
    
    async def connect(self) -> bool:
        """Connect to Exness broker"""
        try:
            # In production: validate API token with Exness
            logger.info(f"Connected to Exness: Account {self.account_id} (Type: {self.account_type})")
            self.is_connected = True
            
            # Mock account info
            self.account_info = {
                "account_id": self.account_id,
                "account_type": self.account_type,
                "balance": 10000.0,
                "equity": 10000.0,
                "margin_used": 0.0,
                "margin_available": 10000.0,
                "margin_level": 0.0,
                "currency": "USD"
            }
            
            return True
        except Exception as e:
            logger.error(f"Exness connection failed: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Exness"""
        try:
            logger.info("Disconnected from Exness")
            self.is_connected = False
            return True
        except Exception as e:
            logger.error(f"Exness disconnection failed: {e}")
            return False
    
    async def place_order(self, order_data: Dict) -> Dict:
        """Place order on Exness"""
        if not self.is_connected:
            return {"status": "error", "message": "Not connected to Exness"}
        
        try:
            order_id = f"EXN-{len(self.open_orders) + 1:06d}"
            symbol = order_data.get("symbol", "XAUUSD")
            order_type = order_data.get("order_type", "market")
            direction = order_data.get("direction", "buy")
            quantity = order_data.get("quantity", 0.1)
            price = order_data.get("price", 0.0)
            
            # In production: use Exness REST API
            order_result = {
                "order_id": order_id,
                "symbol": symbol,
                "type": order_type,
                "direction": direction,
                "quantity": quantity,
                "price": price,
                "status": OrderStatus.FILLED,
                "filled_at": datetime.utcnow().isoformat(),
                "broker": "exness"
            }
            
            self.open_orders[order_id] = order_result
            self.execution_history.append(order_result)
            
            logger.info(f"Exness Order placed: {order_id} ({symbol} {quantity} {direction})")
            
            return order_result
        except Exception as e:
            logger.error(f"Exness order placement failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def cancel_order(self, order_id: str) -> Dict:
        """Cancel Exness order"""
        if order_id not in self.open_orders:
            return {"status": "error", "message": "Order not found"}
        
        order = self.open_orders.pop(order_id)
        order["status"] = OrderStatus.CANCELLED
        order["cancelled_at"] = datetime.utcnow().isoformat()
        
        logger.info(f"Exness Order cancelled: {order_id}")
        return order
    
    async def close_position(self, position_id: str) -> Dict:
        """Close Exness position"""
        try:
            # In production: use Exness REST API
            result = {
                "position_id": position_id,
                "status": "closed",
                "closed_at": datetime.utcnow().isoformat(),
                "broker": "exness"
            }
            
            logger.info(f"Exness Position closed: {position_id}")
            return result
        except Exception as e:
            logger.error(f"Exness position close failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def get_account_info(self) -> Dict:
        """Get Exness account info"""
        return {
            "broker": "exness",
            "account_info": self.account_info,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def get_open_positions(self) -> Dict:
        """Get Exness open positions"""
        return {
            "broker": "exness",
            "positions": list(self.open_orders.values()),
            "total": len(self.open_orders),
            "timestamp": datetime.utcnow().isoformat()
        }

# ==================== BROKER FACTORY ====================
class BrokerFactory:
    """Factory for creating broker adapters"""
    
    _adapters = {
        BrokerType.MT5: MT5BrokerAdapter,
        BrokerType.EXNESS: ExnessBrokerAdapter
    }
    
    @staticmethod
    def create_adapter(broker_type: BrokerType) -> BaseBrokerAdapter:
        """Create broker adapter instance"""
        adapter_class = BrokerFactory._adapters.get(broker_type)
        if not adapter_class:
            raise ValueError(f"Unknown broker type: {broker_type}")
        return adapter_class()

# ==================== EXECUTION VERIFIER ====================
class ExecutionVerifier:
    """Verify order execution across brokers"""
    
    def __init__(self):
        self.verification_history = []
    
    async def verify_order(self, order_data: Dict, broker_adapter: BaseBrokerAdapter) -> Dict:
        """Verify order execution"""
        verification = {
            "timestamp": datetime.utcnow().isoformat(),
            "order_id": order_data.get("order_id"),
            "broker": broker_adapter.broker_type.value,
            "expected_status": order_data.get("status"),
            "verified": True,
            "discrepancies": []
        }
        
        # Check if order exists in broker system
        positions = await broker_adapter.get_open_positions()
        order_found = any(
            p["order_id"] == order_data.get("order_id") 
            for p in positions.get("positions", [])
        )
        
        if not order_found:
            verification["verified"] = False
            verification["discrepancies"].append("Order not found in broker system")
        
        self.verification_history.append(verification)
        logger.info(f"Order verification: {order_data.get('order_id')} - {'PASSED' if verification['verified'] else 'FAILED'}")
        
        return verification
    
    def get_verification_report(self) -> Dict:
        """Get verification report"""
        total = len(self.verification_history)
        verified = sum(1 for v in self.verification_history if v["verified"])
        
        return {
            "total_verifications": total,
            "verified_count": verified,
            "failed_count": total - verified,
            "verification_rate": (verified / total * 100) if total > 0 else 0,
            "recent_verifications": self.verification_history[-10:]
        }
