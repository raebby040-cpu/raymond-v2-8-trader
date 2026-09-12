"""Tests for risk management"""
import pytest
from app.risk_management import (
    RiskParameters, PositionRiskCalculator, RiskLevel
)

class TestRiskParameters:
    """Test risk parameters"""
    
    def test_default_parameters(self):
        """Test default risk parameters"""
        params = RiskParameters()
        
        assert params.max_daily_loss_percent == 2.0
        assert params.max_single_trade_loss == 1.0
        assert params.max_open_positions == 3
        assert params.max_leverage == 20
        assert params.emergency_stop_threshold == 5.0

class TestPositionRiskCalculator:
    """Test position risk calculator"""
    
    def test_calculate_position_risk(self):
        """Test position risk calculation"""
        risk = PositionRiskCalculator.calculate_position_risk(
            entry_price=2050.00,
            stop_loss=2045.00,
            quantity=0.5,
            account_balance=10000.0
        )
        
        assert risk["risk_per_unit"] == 5.0
        assert risk["total_risk_amount"] == 2.5
        assert risk["risk_percent"] == 0.025
        assert risk["acceptable_risk"] is True
    
    def test_unacceptable_risk(self):
        """Test unacceptable risk threshold"""
        risk = PositionRiskCalculator.calculate_position_risk(
            entry_price=2050.00,
            stop_loss=2000.00,  # 50 pips
            quantity=5.0,  # 5 lots (large)
            account_balance=10000.0
        )
        
        # Risk: 50 * 5 = 250, 250/10000 = 2.5% > 2% threshold
        assert risk["risk_percent"] > 2.0
        assert risk["acceptable_risk"] is False
    
    def test_calculate_potential_profit(self):
        """Test potential profit calculation"""
        profit = PositionRiskCalculator.calculate_potential_profit(
            entry_price=2050.00,
            take_profit=2070.00,
            quantity=0.5
        )
        
        assert profit["take_profit"] == 2070.00
        assert profit["profit_per_unit"] == 20.0
        assert profit["total_profit"] == 10.0
    
    def test_risk_reward_ratio(self):
        """Test risk/reward ratio calculation"""
        risk = PositionRiskCalculator.calculate_position_risk(
            entry_price=2050.00,
            stop_loss=2045.00,
            quantity=0.5,
            account_balance=10000.0
        )
        
        profit = PositionRiskCalculator.calculate_potential_profit(
            entry_price=2050.00,
            take_profit=2060.00,
            quantity=0.5
        )
        
        # Risk = 5 pips, Profit = 10 pips, RRR = 2.0
        rr_ratio = profit["profit_per_unit"] / risk["risk_per_unit"]
        assert rr_ratio == 2.0
    
    def test_validate_position_sl_too_close(self):
        """Test position validation with stop loss too close"""
        params = RiskParameters()
        
        validation = PositionRiskCalculator.validate_position(
            entry_price=2050.00,
            stop_loss=2049.00,  # Only 1 pip away
            take_profit=2060.00,
            quantity=0.5,
            account_balance=10000.0,
            risk_params=params
        )
        
        assert len(validation["violations"]) > 0
        assert "stop loss" in validation["violations"][0].lower()
    
    def test_validate_position_valid(self):
        """Test position validation with valid parameters"""
        params = RiskParameters()
        
        validation = PositionRiskCalculator.validate_position(
            entry_price=2050.00,
            stop_loss=2045.00,
            take_profit=2060.00,
            quantity=0.5,
            account_balance=10000.0,
            risk_params=params
        )
        
        assert validation["is_valid"] is True
        assert len(validation["violations"]) == 0
