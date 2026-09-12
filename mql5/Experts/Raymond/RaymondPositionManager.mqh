//+------------------------------------------------------------------+
//| RaymondPositionManager.mqh                                      |
//| Raymond v2.8 Trader - Step 11B-7                                |
//| DEMO position monitoring and protection                          |
//+------------------------------------------------------------------+
#property strict

#ifndef RAYMOND_POSITION_MANAGER_MQH
#define RAYMOND_POSITION_MANAGER_MQH

#include <Trade/Trade.mqh>

// -------------------------------------------------------------------
// STEP 11B-7
//
// Purpose:
//   - Monitor open MT5 positions.
//   - Protect profitable DEMO positions.
//   - Move SL toward break-even.
//   - Lock part of accumulated profit.
//   - Close DEMO positions when explicitly requested.
//
// HARD SAFETY:
//   - DEMO ONLY.
//   - No live trading.
//   - No broker credentials.
//   - Emergency stop blocks management actions.
// -------------------------------------------------------------------

class RaymondPositionManager
{
private:

   CTrade m_trade;

   bool m_demo_only;
   bool m_live_trading_enabled;
   bool m_emergency_stop;

   double m_break_even_trigger;
   double m_break_even_offset;

   double m_profit_lock_trigger;
   double m_profit_lock_distance;

   int m_deviation_points;

   string m_last_error;

public:

   RaymondPositionManager()
   {
      m_demo_only = true;
      m_live_trading_enabled = false;
      m_emergency_stop = true;

      // These values are deliberately conservative defaults.
      // They should be tuned after broker/demo testing.
      m_break_even_trigger = 2.00;
      m_break_even_offset = 0.20;

      m_profit_lock_trigger = 4.00;
      m_profit_lock_distance = 1.00;

      m_deviation_points = 50;

      m_last_error = "";

      m_trade.SetDeviationInPoints(
         m_deviation_points
      );
   }

   // ---------------------------------------------------------------
   // CONFIGURATION
   // ---------------------------------------------------------------

   void Configure(
      double break_even_trigger,
      double break_even_offset,
      double profit_lock_trigger,
      double profit_lock_distance,
      int deviation_points
   )
   {
      if(break_even_trigger > 0.0)
         m_break_even_trigger =
            break_even_trigger;

      if(break_even_offset >= 0.0)
         m_break_even_offset =
            break_even_offset;

      if(profit_lock_trigger > 0.0)
         m_profit_lock_trigger =
            profit_lock_trigger;

      if(profit_lock_distance >= 0.0)
         m_profit_lock_distance =
            profit_lock_distance;

      if(deviation_points > 0)
         m_deviation_points =
            deviation_points;

      m_trade.SetDeviationInPoints(
         m_deviation_points
      );
   }

   // ---------------------------------------------------------------
   // HARD LIVE LOCK
   // ---------------------------------------------------------------

   void SetLiveTradingEnabled(bool enabled)
   {
      // Never allow live mode in Step 11B-7.
      m_live_trading_enabled = false;
   }

   bool LiveTradingEnabled()
   {
      return false;
   }

   bool DemoOnly()
   {
      return true;
   }

   // ---------------------------------------------------------------
   // EMERGENCY STOP
   // ---------------------------------------------------------------

   void SetEmergencyStop(bool enabled)
   {
      m_emergency_stop = enabled;
   }

   bool EmergencyStopActive()
   {
      return m_emergency_stop;
   }

   // ---------------------------------------------------------------
   // ERROR
   // ---------------------------------------------------------------

   string LastError()
   {
      return m_last_error;
   }

   void ClearError()
   {
      m_last_error = "";
   }

   // ---------------------------------------------------------------
   // ACCOUNT VALIDATION
   // ---------------------------------------------------------------

   bool ValidateDemoAccount(
      string &reason
   )
   {
      ENUM_ACCOUNT_TRADE_MODE mode =
         (ENUM_ACCOUNT_TRADE_MODE)
         AccountInfoInteger(
            ACCOUNT_TRADE_MODE
         );

      if(mode != ACCOUNT_TRADE_MODE_DEMO)
      {
         reason =
            "Position management blocked: account is not DEMO.";

         return false;
      }

      reason =
         "DEMO account validated.";

      return true;
   }

   // ---------------------------------------------------------------
   // POSITION SELECTION
   // ---------------------------------------------------------------

   bool SelectPosition(
      ulong ticket
   )
   {
      if(ticket == 0)
         return false;

      return PositionSelectByTicket(
         ticket
      );
   }

   // ---------------------------------------------------------------
   // POSITION PROFIT
   // ---------------------------------------------------------------

   double CurrentProfit(
      ulong ticket
   )
   {
      if(!SelectPosition(ticket))
         return 0.0;

      return PositionGetDouble(
         POSITION_PROFIT
      );
   }

   // ---------------------------------------------------------------
   // POSITION TYPE
   // ---------------------------------------------------------------

   ENUM_POSITION_TYPE PositionType(
      ulong ticket
   )
   {
      if(!SelectPosition(ticket))
         return WRONG_VALUE;

      return (ENUM_POSITION_TYPE)
         PositionGetInteger(
            POSITION_TYPE
         );
   }

   // ---------------------------------------------------------------
   // CURRENT MARKET PRICE
   // ---------------------------------------------------------------

   double CurrentPrice(
      string symbol,
      ENUM_POSITION_TYPE type
   )
   {
      if(type == POSITION_TYPE_BUY)
      {
         return SymbolInfoDouble(
            symbol,
            SYMBOL_BID
         );
      }

      if(type == POSITION_TYPE_SELL)
      {
         return SymbolInfoDouble(
            symbol,
            SYMBOL_ASK
         );
      }

      return 0.0;
   }

   // ---------------------------------------------------------------
   // BREAK-EVEN CALCULATION
   // ---------------------------------------------------------------

   double BreakEvenStop(
      string symbol,
      ENUM_POSITION_TYPE type,
      double open_price
   )
   {
      int digits =
         (int)SymbolInfoInteger(
            symbol,
            SYMBOL_DIGITS
         );

      double result;

      if(type == POSITION_TYPE_BUY)
      {
         result =
            open_price +
            m_break_even_offset;
      }
      else
      {
         result =
            open_price -
            m_break_even_offset;
      }

      return NormalizeDouble(
         result,
         digits
      );
   }

   // ---------------------------------------------------------------
   // VALIDATE PROTECTIVE STOP
   // ---------------------------------------------------------------

   bool ValidateProtectiveStop(
      string symbol,
      ENUM_POSITION_TYPE type,
      double stop_loss,
      string &reason
   )
   {
      double bid =
         SymbolInfoDouble(
            symbol,
            SYMBOL_BID
         );

      double ask =
         SymbolInfoDouble(
            symbol,
            SYMBOL_ASK
         );

      if(bid <= 0.0 || ask <= 0.0)
      {
         reason =
            "Invalid market price.";

         return false;
      }

      double point =
         SymbolInfoDouble(
            symbol,
            SYMBOL_POINT
         );

      if(point <= 0.0)
      {
         reason =
            "Invalid symbol point size.";

         return false;
      }

      double minimum_distance =
         (double)SymbolInfoInteger(
            symbol,
            SYMBOL_TRADE_STOPS_LEVEL
         ) * point;

      if(type == POSITION_TYPE_BUY)
      {
         if(stop_loss >= bid)
         {
            reason =
               "BUY protective SL must remain below current bid.";

            return false;
         }

         if(
            minimum_distance > 0.0 &&
            bid - stop_loss < minimum_distance
         )
         {
            reason =
               "BUY protective SL is too close to market.";

            return false;
         }
      }
      else if(type == POSITION_TYPE_SELL)
      {
         if(stop_loss <= ask)
         {
            reason =
               "SELL protective SL must remain above current ask.";

            return false;
         }

         if(
            minimum_distance > 0.0 &&
            stop_loss - ask < minimum_distance
         )
         {
            reason =
               "SELL protective SL is too close to market.";

            return false;
         }
      }
      else
      {
         reason =
            "Unknown position type.";

         return false;
      }

      reason =
         "Protective SL validated.";

      return true;
   }

   // ---------------------------------------------------------------
   // MOVE TO BREAK EVEN
   // ---------------------------------------------------------------

   bool MoveToBreakEven(
      ulong ticket
   )
   {
      ClearError();

      // Absolute emergency stop.
      if(m_emergency_stop)
      {
         m_last_error =
            "Break-even blocked: Emergency Stop active.";

         return false;
      }

      // Absolute live lock.
      if(!m_demo_only || m_live_trading_enabled)
      {
         m_last_error =
            "Break-even blocked: DEMO_ONLY safety violation.";

         return false;
      }

      // Account must be DEMO.
      string account_reason = "";

      if(
         !ValidateDemoAccount(
            account_reason
         )
      )
      {
         m_last_error =
            account_reason;

         return false;
      }

      if(!SelectPosition(ticket))
      {
         m_last_error =
            "Position not found.";

         return false;
      }

      string symbol =
         PositionGetString(
            POSITION_SYMBOL
         );

      ENUM_POSITION_TYPE type =
         (ENUM_POSITION_TYPE)
         PositionGetInteger(
            POSITION_TYPE
         );

      double open_price =
         PositionGetDouble(
            POSITION_PRICE_OPEN
         );

      double current_sl =
         PositionGetDouble(
            POSITION_SL
         );

      double current_tp =
         PositionGetDouble(
            POSITION_TP
         );

      double profit =
         PositionGetDouble(
            POSITION_PROFIT
         );

      if(profit < m_break_even_trigger)
      {
         m_last_error =
            "Break-even trigger not reached.";

         return false;
      }

      double new_sl =
         BreakEvenStop(
            symbol,
            type,
            open_price
         );

      string reason = "";

      if(
         !ValidateProtectiveStop(
            symbol,
            type,
            new_sl,
            reason
         )
      )
      {
         m_last_error =
            reason;

         return false;
      }

      // Never worsen an existing protective SL.
      if(type == POSITION_TYPE_BUY)
      {
         if(
            current_sl > 0.0 &&
            new_sl <= current_sl
         )
         {
            m_last_error =
               "Existing BUY SL is already more protective.";

            return false;
         }
      }
      else if(type == POSITION_TYPE_SELL)
      {
         if(
            current_sl > 0.0 &&
            new_sl >= current_sl
         )
         {
            m_last_error =
               "Existing SELL SL is already more protective.";

            return false;
         }
      }

      // DEMO position modification.
      bool result =
         m_trade.PositionModify(
            ticket,
            new_sl,
            current_tp
         );

      if(!result)
      {
         m_last_error =
            m_trade.ResultRetcodeDescription();

         return false;
      }

      return true;
   }

   // ---------------------------------------------------------------
   // LOCK PROFIT
   // ---------------------------------------------------------------

   bool LockProfit(
      ulong ticket
   )
   {
      ClearError();

      if(m_emergency_stop)
      {
         m_last_error =
            "Profit lock blocked: Emergency Stop active.";

         return false;
      }

      if(!m_demo_only || m_live_trading_enabled)
      {
         m_last_error =
            "Profit lock blocked: DEMO_ONLY safety violation.";

         return false;
      }

      string account_reason = "";

      if(
         !ValidateDemoAccount(
            account_reason
         )
      )
      {
         m_last_error =
            account_reason;

         return false;
      }

      if(!SelectPosition(ticket))
      {
         m_last_error =
            "Position not found.";

         return false;
      }

      string symbol =
         PositionGetString(
            POSITION_SYMBOL
         );

      ENUM_POSITION_TYPE type =
         (ENUM_POSITION_TYPE)
         PositionGetInteger(
            POSITION_TYPE
         );

      double current_sl =
         PositionGetDouble(
            POSITION_SL
         );

      double current_tp =
         PositionGetDouble(
            POSITION_TP
         );

      double profit =
         PositionGetDouble(
            POSITION_PROFIT
         );

      if(profit < m_profit_lock_trigger)
      {
         m_last_error =
            "Profit-lock trigger not reached.";

         return false;
      }

      double bid =
         SymbolInfoDouble(
            symbol,
            SYMBOL_BID
         );

      double ask =
         SymbolInfoDouble(
            symbol,
            SYMBOL_ASK
         );

      double new_sl;

      if(type == POSITION_TYPE_BUY)
      {
         new_sl =
            bid -
            m_profit_lock_distance;
      }
      else
      {
         new_sl =
            ask +
            m_profit_lock_distance;
      }

      int digits =
         (int)SymbolInfoInteger(
            symbol,
            SYMBOL_DIGITS
         );

      new_sl =
         NormalizeDouble(
            new_sl,
            digits
         );

      string reason = "";

      if(
         !ValidateProtectiveStop(
            symbol,
            type,
            new_sl,
            reason
         )
      )
      {
         m_last_error =
            reason;

         return false;
      }

      // Never move a protective stop backwards.
      if(type == POSITION_TYPE_BUY)
      {
         if(
            current_sl > 0.0 &&
            new_sl <= current_sl
         )
         {
            m_last_error =
               "Existing BUY SL already protects more profit.";

            return false;
         }
      }
      else
      {
         if(
            current_sl > 0.0 &&
            new_sl >= current_sl
         )
         {
            m_last_error =
               "Existing SELL SL already protects more profit.";

            return false;
         }
      }

      bool result =
         m_trade.PositionModify(
            ticket,
            new_sl,
            current_tp
         );

      if(!result)
      {
         m_last_error =
            m_trade.ResultRetcodeDescription();

         return false;
      }

      return true;
   }

   // ---------------------------------------------------------------
   // CLOSE DEMO POSITION
   //
   // This function requires an explicit caller decision.
   // The manager does NOT independently invent a trade signal.
   // ---------------------------------------------------------------

   bool CloseDemoPosition(
      ulong ticket,
      bool raymond_close_approved,
      bool risk_close_approved
   )
   {
      ClearError();

      if(m_emergency_stop)
      {
         m_last_error =
            "Close blocked: Emergency Stop active.";

         return false;
      }

      if(!m_demo_only || m_live_trading_enabled)
      {
         m_last_error =
            "Close blocked: DEMO_ONLY safety violation.";

         return false;
      }

      if(!raymond_close_approved)
      {
         m_last_error =
            "Close blocked: Raymond approval missing.";

         return false;
      }

      if(!risk_close_approved)
      {
         m_last_error =
            "Close blocked: Risk approval missing.";

         return false;
      }

      string account_reason = "";

      if(
         !ValidateDemoAccount(
            account_reason
         )
      )
      {
         m_last_error =
            account_reason;

         return false;
      }

      if(!SelectPosition(ticket))
      {
         m_last_error =
            "Position not found.";

         return false;
      }

      // DEMO ONLY.
      bool result =
         m_trade.PositionClose(
            ticket
         );

      if(!result)
      {
         m_last_error =
            m_trade.ResultRetcodeDescription();

         return false;
      }

      return true;
   }

   // ---------------------------------------------------------------
   // AUTOMATIC PROTECTION CHECK
   //
   // This function only protects positions that have already
   // reached configured profit thresholds.
   //
   // It does not generate new trades.
   // It does not create new signals.
   // It does not enable live trading.
   // ---------------------------------------------------------------

   void MonitorPosition(
      ulong ticket
   )
   {
      if(ticket == 0)
         return;

      if(m_emergency_stop)
         return;

      if(!m_demo_only)
         return;

      if(m_live_trading_enabled)
         return;

      if(!SelectPosition(ticket))
         return;

      double profit =
         PositionGetDouble(
            POSITION_PROFIT
         );

      if(profit <= 0.0)
         return;

      // First attempt break-even protection.
      if(
         profit >=
         m_break_even_trigger
      )
      {
         MoveToBreakEven(
            ticket
         );
      }

      // Then attempt stronger profit protection.
      if(
         profit >=
         m_profit_lock_trigger
      )
      {
         LockProfit(
            ticket
         );
      }
   }

   // ---------------------------------------------------------------
   // MONITOR ALL POSITIONS
   // ---------------------------------------------------------------

   void MonitorAllPositions()
   {
      if(m_emergency_stop)
         return;

      if(!m_demo_only)
         return;

      if(m_live_trading_enabled)
         return;

      for(
         int i = PositionsTotal() - 1;
         i >= 0;
         i--
      )
      {
         ulong ticket =
            PositionGetTicket(i);

         if(ticket == 0)
            continue;

         MonitorPosition(
            ticket
         );
      }
   }

   // ---------------------------------------------------------------
   // POSITION COUNT
   // ---------------------------------------------------------------

   int PositionCount()
   {
      return PositionsTotal();
   }

   // ---------------------------------------------------------------
   // STATUS
   // ---------------------------------------------------------------

   string Status()
   {
      string result =
         "Raymond Position Manager: ";

      result +=
         "MT5";

      result +=
         " | Broker=Agnostic";

      result +=
         " | DEMO_ONLY=ON";

      result +=
         " | LiveTrading=OFF";

      result +=
         " | EmergencyStop=";

      result +=
         (m_emergency_stop ? "ON" : "OFF");

      result +=
         " | Positions=";

      result +=
         IntegerToString(
            PositionsTotal()
         );

      return result;
   }
};

#endif
