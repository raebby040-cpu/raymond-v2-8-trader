"""
RAYMOND v2.8 - Risk Management
Position protection, emergency stop, and risk controls
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)

# ==================== RISK ENUMS ====================
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertType(str, Enum):
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

# ==================== RISK PARAMETERS ====================
class RiskParameters:
    """Risk management parameters"""
    
    def __init__(self):
        self.max_daily_loss_percent = 2.0  # Max daily loss in % of balance
        self.max_single_trade_loss = 1.0  # Max loss per trade in %
        self.max_open_positions = 3  # Maximum concurrent positions
        self.max_leverage = 20  # Maximum leverage allowed
        self.min_stop_loss_distance = 5.0  # Minimum SL distance in pips (XAUUSD)
        self.max_position_size = 10.0  # Max position size in lots
        self.correlation_limit = 0.8  # Position correlation limit
        self.emergency_stop_threshold = 5.0  # Trigger emergency stop at % loss

# ==================== POSITION RISK CALCULATOR ====================
class PositionRiskCalculator:
    """Calculate risk metrics for individual positions"""
    
    @staticmethod
    def calculate_position_risk(
        entry_price: float,
        stop_loss: float,
        quantity: float,
        account_balance: float
    ) -> Dict:
        """Calculate risk metrics for a position"""
        
        # Risk per unit
        risk_per_unit = abs(entry_price - stop_loss)
        total_risk = risk_per_unit * quantity
        risk_percent = (total_risk / account_balance) * 100
        
        return {
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "quantity": quantity,
            "risk_per_unit": round(risk_per_unit, 2),
            "total_risk_amount": round(total_risk, 2),
            "risk_percent": round(risk_percent, 2),
            "acceptable_risk": risk_percent <= 2.0  # Max 2% per trade
        }
    
    @staticmethod
    def calculate_potential_profit(
        entry_price: float,
        take_profit: float,
        quantity: float
    ) -> Dict:
        """Calculate potential profit"""
        
        profit_per_unit = abs(take_profit - entry_price)
        total_profit = profit_per_unit * quantity
        
        return {
            "take_profit": take_profit,
            "profit_per_unit": round(profit_per_unit, 2),
            "total_profit": round(total_profit, 2),
            "risk_reward_ratio": round(profit_per_unit / abs(take_profit - entry_price), 2) if (take_profit - entry_price) != 0 else 0
        }
    
    @staticmethod
    def validate_position(
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
        account_balance: float,
        risk_params: RiskParameters
    ) -> Dict:
        """Validate position against risk parameters"""
        
        violations = []
        
        # Check stop loss distance
        sl_distance = abs(entry_price - stop_loss)
        if sl_distance < risk_params.min_stop_loss_distance:
            violations.append(f"SL distance {sl_distance:.2f} < minimum {risk_params.min_stop_loss_distance}")
        
        # Check position size
        if quantity > risk_params.max_position_size:
            violations.append(f"Position size {quantity} > max {risk_params.max_position_size}")
        
        # Check risk per trade
        risk_calc = PositionRiskCalculator.calculate_position_risk(
            entry_price, stop_loss, quantity, account_balance
        )
        if risk_calc["risk_percent"] > risk_params.max_single_trade_loss:
            violations.append(f"Risk {risk_calc['risk_percent']:.2f}% > max {risk_params.max_single_trade_loss}%")
        
        # Check risk/reward ratio
        profit_calc = PositionRiskCalculator.calculate_potential_profit(
            entry_price, take_profit, quantity
        )
        if profit_calc["risk_reward_ratio"] < 1.5:
            violations.append(f"Risk/Reward {profit_calc['risk_reward_ratio']:.2f} < 1.5")
        
        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "risk_metrics": risk_calc,
            "profit_metrics": profit_calc
        }

# ==================== PORTFOLIO RISK MONITOR ====================
class PortfolioRiskMonitor:
    """Monitor portfolio-level risk"""
    
    def __init__(self, risk_params: RiskParameters):
        self.risk_params = risk_params
        self.positions: Dict = {}
        self.daily_pnl = 0.0
        self.account_balance = 10000.0
        self.alerts: List[Dict] = []
    
    def add_position(self, position_id: str, position_data: Dict) -> Dict:
        """Add position to portfolio"""
        self.positions[position_id] = position_data
        
        # Check portfolio constraints
        validation = self._validate_portfolio()
        
        if not validation["valid"]:
            logger.warning(f"Portfolio risk violation: {validation['violations']}")
            self._create_alert(AlertType.ALERT, validation["violations"])
        
        return validation
    
    def close_position(self, position_id: str, exit_price: float) -> Dict:
        """Close position and update P&L"""
        if position_id not in self.positions:
            return {"status": "error", "message": "Position not found"}
        
        position = self.positions.pop(position_id)
        entry_price = position.get("entry_price", 0)
        quantity = position.get("quantity", 0)
        direction = position.get("direction", "buy")
        
        # Calculate P&L
        if direction == "buy":
            pnl = (exit_price - entry_price) * quantity
        else:
            pnl = (entry_price - exit_price) * quantity
        
        self.daily_pnl += pnl
        
        # Check daily loss limit
        if self.daily_pnl < 0:
            loss_percent = abs(self.daily_pnl) / self.account_balance * 100
            if loss_percent >= self.risk_params.daily_loss_percent:
                self._create_alert(
                    AlertType.CRITICAL,
                    f"Daily loss {loss_percent:.2f}% exceeds limit {self.risk_params.max_daily_loss_percent}%"
                )
        
        return {
            "position_id": position_id,
            "status": "closed",
            "pnl": round(pnl, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "closed_at": datetime.utcnow().isoformat()
        }
    
    def update_position_price(self, position_id: str, current_price: float) -> Dict:
        """Update position with current market price"""
        if position_id not in self.positions:
            return {"status": "error", "message": "Position not found"}
        
        position = self.positions[position_id]
        entry_price = position.get("entry_price", 0)
        quantity = position.get("quantity", 0)
        direction = position.get("direction", "buy")
        stop_loss = position.get("stop_loss", 0)
        take_profit = position.get("take_profit", 0)
        
        # Calculate unrealized P&L
        if direction == "buy":
            unrealized_pnl = (current_price - entry_price) * quantity
            hit_stop_loss = current_price <= stop_loss
            hit_take_profit = current_price >= take_profit
        else:
            unrealized_pnl = (entry_price - current_price) * quantity
            hit_stop_loss = current_price >= stop_loss
            hit_take_profit = current_price <= take_profit
        
        position["current_price"] = current_price
        position["unrealized_pnl"] = unrealized_pnl
        
        # Check stop loss
        if hit_stop_loss:
            self._create_alert(
                AlertType.CRITICAL,
                f"Position {position_id} hit stop loss at {current_price}"
            )
            return self.close_position(position_id, stop_loss)
        
        # Check take profit
        if hit_take_profit:
            self._create_alert(
                AlertType.WARNING,
                f"Position {position_id} hit take profit at {current_price}"
            )
            return self.close_position(position_id, take_profit)
        
        return {
            "position_id": position_id,
            "current_price": current_price,
            "unrealized_pnl": round(unrealized_pnl, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _validate_portfolio(self) -> Dict:
        """Validate portfolio against risk limits"""
        violations = []
        
        # Check number of open positions
        if len(self.positions) > self.risk_params.max_open_positions:
            violations.append(
                f"Open positions {len(self.positions)} > max {self.risk_params.max_open_positions}"
            )
        
        # Check total portfolio risk
        total_risk = sum(
            abs(p.get("stop_loss", 0) - p.get("entry_price", 0)) * p.get("quantity", 0)
            for p in self.positions.values()
        )
        total_risk_percent = (total_risk / self.account_balance) * 100
        
        if total_risk_percent > self.risk_params.max_daily_loss_percent * 2:
            violations.append(
                f"Total portfolio risk {total_risk_percent:.2f}% > threshold"
            )
        
        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "open_positions": len(self.positions),
            "total_risk_percent": round(total_risk_percent, 2)
        }
    
    def _create_alert(self, alert_type: AlertType, message: str) -> Dict:
        """Create risk alert"""
        alert = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": alert_type.value,
            "message": message
        }
        self.alerts.append(alert)
        logger.warning(f"[{alert_type.value.upper()}] {message}")
        return alert
    
    def get_risk_report(self) -> Dict:
        """Generate portfolio risk report"""
        total_risk = sum(
            abs(p.get("stop_loss", 0) - p.get("entry_price", 0)) * p.get("quantity", 0)
            for p in self.positions.values()
        )
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "account_balance": round(self.account_balance, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "open_positions": len(self.positions),
            "total_risk_amount": round(total_risk, 2),
            "total_risk_percent": round((total_risk / self.account_balance) * 100, 2),
            "max_allowed_risk": self.risk_params.max_daily_loss_percent,
            "risk_level": self._assess_risk_level(total_risk),
            "recent_alerts": self.alerts[-5:]
        }
    
    def _assess_risk_level(self, total_risk: float) -> RiskLevel:
        """Assess overall portfolio risk level"""
        risk_percent = (total_risk / self.account_balance) * 100
        
        if risk_percent >= self.risk_params.emergency_stop_threshold:
            return RiskLevel.CRITICAL
        elif risk_percent >= self.risk_params.max_daily_loss_percent * 1.5:
            return RiskLevel.HIGH
        elif risk_percent >= self.risk_params.max_daily_loss_percent:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

# ==================== EMERGENCY STOP ====================
class EmergencyStop:
    """Emergency stop mechanism for risk control"""
    
    def __init__(self):
        self.is_active = False
        self.activated_at: Optional[datetime] = None
        self.reason: Optional[str] = None
        self.positions_closed_count = 0
    
    def activate(self, reason: str = "Manual activation") -> Dict:
        """Activate emergency stop"""
        if self.is_active:
            return {"status": "already_active", "message": "Emergency stop already active"}
        
        self.is_active = True
        self.activated_at = datetime.utcnow()
        self.reason = reason
        
        logger.critical(f"EMERGENCY STOP ACTIVATED: {reason}")
        
        return {
            "status": "activated",
            "activated_at": self.activated_at.isoformat(),
            "reason": reason,
            "action": "All new orders blocked, closing all positions",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def deactivate(self) -> Dict:
        """Deactivate emergency stop"""
        if not self.is_active:
            return {"status": "not_active", "message": "Emergency stop not active"}
        
        self.is_active = False
        duration = (datetime.utcnow() - self.activated_at).total_seconds()
        
        logger.info(f"Emergency stop deactivated after {duration} seconds")
        
        return {
            "status": "deactivated",
            "duration_seconds": round(duration, 2),
            "positions_closed": self.positions_closed_count,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def get_status(self) -> Dict:
        """Get emergency stop status"""
        return {
            "is_active": self.is_active,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "reason": self.reason,
            "timestamp": datetime.utcnow().isoformat()
        }

# ==================== POSITION PROTECTION ====================
class PositionProtection:
    """Automatic position protection and trailing stop logic"""
    
    @staticmethod
    def apply_trailing_stop(
        current_price: float,
        entry_price: float,
        current_stop_loss: float,
        trailing_percent: float = 1.0
    ) -> Dict:
        """Apply trailing stop to a position"""
        
        profit = current_price - entry_price
        trailing_distance = (trailing_percent / 100) * current_price
        
        # Calculate new stop loss
        new_stop_loss = current_price - trailing_distance
        
        # Only update if new SL is higher than current
        if new_stop_loss > current_stop_loss:
            return {
                "updated": True,
                "new_stop_loss": round(new_stop_loss, 2),
                "old_stop_loss": round(current_stop_loss, 2),
                "protected_profit": round(new_stop_loss - entry_price, 2)
            }
        else:
            return {
                "updated": False,
                "current_stop_loss": round(current_stop_loss, 2),
                "reason": "New SL would be below current SL"
            }
    
    @staticmethod
    def calculate_breakeven_stop(
        entry_price: float,
        quantity: float,
        commission: float = 0.0
    ) -> float:
        """Calculate breakeven stop loss"""
        breakeven = entry_price + (commission / quantity)
        return round(breakeven, 2)
