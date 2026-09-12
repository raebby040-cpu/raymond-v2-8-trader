"""Tests for risk management module"""
import pytest
from app.risk_management import (
    PositionRiskCalculator, PortfolioRiskMonitor, EmergencyStop,
    RiskParameters, RiskLevel, AlertType
)


class TestPositionRiskCalculator:
    """Test position-level risk calculations"""
    
    def test_calculate_position_risk(self):
        """Test position risk calculation"""
        risk = PositionRiskCalculator.calculate_position_risk(
            entry_price=2050.0,
            stop_loss=2045.0,
            quantity=0.5,
            account_balance=10000.0
        )
        assert risk["entry_price"] == 2050.0
        assert risk["stop_loss"] == 2045.0
        assert risk["quantity"] == 0.5
        assert risk["risk_per_unit"] == 5.0
        assert risk["total_risk_amount"] == 2.5
        assert risk["risk_percent"] == 0.025  # 0.025% of account
        assert risk["acceptable_risk"] is True
    
    def test_calculate_position_risk_excessive(self):
        """Test excessive position risk"""
        risk = PositionRiskCalculator.calculate_position_risk(
            entry_price=2050.0,
            stop_loss=2030.0,  # Large stop loss
            quantity=1.0,
            account_balance=10000.0
        )
        assert risk["acceptable_risk"] is False
        assert risk["risk_percent"] > 2.0
    
    def test_calculate_potential_profit(self):
        """Test potential profit calculation"""
        profit = PositionRiskCalculator.calculate_potential_profit(
            entry_price=2050.0,
            take_profit=2060.0,
            quantity=0.5
        )
        assert profit["take_profit"] == 2060.0
        assert profit["profit_per_unit"] == 10.0
        assert profit["total_profit"] == 5.0
    
    def test_validate_position_valid(self):
        """Test position validation (valid trade)"""
        risk_params = RiskParameters()
        validation = PositionRiskCalculator.validate_position(
            entry_price=2050.0,
            stop_loss=2045.0,
            take_profit=2065.0,
            quantity=0.5,
            account_balance=10000.0,
            risk_params=risk_params
        )
        assert validation["valid"] is True
        assert len(validation["violations"]) == 0
    
    def test_validate_position_sl_too_close(self):
        """Test position with stop loss too close"""
        risk_params = RiskParameters()
        validation = PositionRiskCalculator.validate_position(
            entry_price=2050.0,
            stop_loss=2049.0,  # Only 1 pip away
            take_profit=2065.0,
            quantity=0.5,
            account_balance=10000.0,
            risk_params=risk_params
        )
        assert validation["valid"] is False
        assert any("SL distance" in v for v in validation["violations"])
    
    def test_validate_position_bad_risk_reward(self):
        """Test position with poor risk/reward ratio"""
        risk_params = RiskParameters()
        validation = PositionRiskCalculator.validate_position(
            entry_price=2050.0,
            stop_loss=2049.0,
            take_profit=2051.0,  # Only 1 pip profit for 1 pip risk
            quantity=0.5,
            account_balance=10000.0,
            risk_params=risk_params
        )
        assert validation["valid"] is False
        assert any("Risk/Reward" in v for v in validation["violations"])


class TestPortfolioRiskMonitor:
    """Test portfolio-level risk monitoring"""
    
    def test_add_position(self, portfolio_risk_monitor):
        """Test adding a position to portfolio"""
        position = {
            "entry_price": 2050.0,
            "stop_loss": 2045.0,
            "quantity": 0.5,
            "direction": "buy"
        }
        validation = portfolio_risk_monitor.add_position("POS-001", position)
        assert "POS-001" in portfolio_risk_monitor.positions
        assert validation["valid"] is True
    
    def test_close_position_profit(self, portfolio_risk_monitor):
        """Test closing position at profit"""
        position = {
            "entry_price": 2050.0,
            "stop_loss": 2045.0,
            "quantity": 0.5,
            "direction": "buy"
        }
        portfolio_risk_monitor.add_position("POS-001", position)
        result = portfolio_risk_monitor.close_position("POS-001", exit_price=2055.0)
        
        assert result["status"] == "closed"
        assert result["pnl"] == 2.5  # 0.5 * (2055 - 2050)
        assert portfolio_risk_monitor.daily_pnl > 0
    
    def test_close_position_loss(self, portfolio_risk_monitor):
        """Test closing position at loss"""
        position = {
            "entry_price": 2050.0,
            "stop_loss": 2045.0,
            "quantity": 0.5,
            "direction": "buy"
        }
        portfolio_risk_monitor.add_position("POS-001", position)
        result = portfolio_risk_monitor.close_position("POS-001", exit_price=2045.0)
        
        assert result["status"] == "closed"
        assert result["pnl"] == -2.5
        assert portfolio_risk_monitor.daily_pnl < 0
    
    def test_update_position_price(self, portfolio_risk_monitor):
        """Test updating position with current market price"""
        position = {
            "entry_price": 2050.0,
            "stop_loss": 2045.0,
            "take_profit": 2060.0,
            "quantity": 0.5,
            "direction": "buy"
        }
        portfolio_risk_monitor.add_position("POS-001", position)
        result = portfolio_risk_monitor.update_position_price("POS-001", current_price=2053.0)
        
        assert result["status"] is None or result["status"] != "closed"
        assert result["unrealized_pnl"] == 1.5  # 0.5 * (2053 - 2050)
    
    def test_update_position_stop_loss_triggered(self, portfolio_risk_monitor):
        """Test position stop loss trigger"""
        position = {
            "entry_price": 2050.0,
            "stop_loss": 2045.0,
            "take_profit": 2060.0,
            "quantity": 0.5,
            "direction": "buy"
        }
        portfolio_risk_monitor.add_position("POS-001", position)
        result = portfolio_risk_monitor.update_position_price("POS-001", current_price=2044.0)
        
        assert result["status"] == "closed"
        assert "POS-001" not in portfolio_risk_monitor.positions
    
    def test_update_position_take_profit_triggered(self, portfolio_risk_monitor):
        """Test position take profit trigger"""
        position = {
            "entry_price": 2050.0,
            "stop_loss": 2045.0,
            "take_profit": 2060.0,
            "quantity": 0.5,
            "direction": "buy"
        }
        portfolio_risk_monitor.add_position("POS-001", position)
        result = portfolio_risk_monitor.update_position_price("POS-001", current_price=2061.0)
        
        assert result["status"] == "closed"
        assert "POS-001" not in portfolio_risk_monitor.positions
    
    def test_get_risk_report(self, portfolio_risk_monitor):
        """Test risk report generation"""
        position = {
            "entry_price": 2050.0,
            "stop_loss": 2045.0,
            "quantity": 0.5,
            "direction": "buy"
        }
        portfolio_risk_monitor.add_position("POS-001", position)
        report = portfolio_risk_monitor.get_risk_report()
        
        assert report["open_positions"] == 1
        assert report["total_risk_amount"] > 0
        assert report["total_risk_percent"] >= 0
        assert report["risk_level"] in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


class TestEmergencyStop:
    """Test emergency stop mechanism"""
    
    def test_activate_emergency_stop(self):
        """Test activating emergency stop"""
        emergency = EmergencyStop()
        result = emergency.activate(reason="Manual activation")
        
        assert result["status"] == "activated"
        assert emergency.is_active is True
        assert emergency.reason == "Manual activation"
    
    def test_deactivate_emergency_stop(self):
        """Test deactivating emergency stop"""
        emergency = EmergencyStop()
        emergency.activate()
        result = emergency.deactivate()
        
        assert result["status"] == "deactivated"
        assert emergency.is_active is False
    
    def test_get_emergency_stop_status(self):
        """Test getting emergency stop status"""
        emergency = EmergencyStop()
        emergency.activate(reason="Test reason")
        status = emergency.get_status()
        
        assert status["is_active"] is True
        assert status["reason"] == "Test reason"
        assert status["activated_at"] is not None
    
    def test_emergency_stop_cannot_activate_twice(self):
        """Test that emergency stop cannot be activated twice"""
        emergency = EmergencyStop()
        emergency.activate()
        result = emergency.activate()  # Try to activate again
        
        assert result["status"] == "already_active"
