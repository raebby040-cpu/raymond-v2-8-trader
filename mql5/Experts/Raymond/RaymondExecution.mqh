//+------------------------------------------------------------------+
//| RaymondExecution.mqh                                             |
//| Raymond v2.8 Trader - Step 11B-6                                |
//| Broker-agnostic MT5 DEMO execution layer                         |
//+------------------------------------------------------------------+
#property strict

#ifndef RAYMOND_EXECUTION_MQH
#define RAYMOND_EXECUTION_MQH

#include <Trade/Trade.mqh>

// -------------------------------------------------------------------
// IMPORTANT SAFETY POLICY
//
// Step 11B-6 supports DEMO execution only.
//
// This layer:
//   - works through the MT5 terminal
//   - does not contain broker credentials
//   - does not depend on Exness
//   - supports BUY / SELL demo orders
//   - validates volume, price and stops
//   - verifies the resulting position
//
// LIVE TRADING IS HARD-LOCKED OFF.
//
// Do NOT remove the DEMO_ONLY guard until a separate live-trading
// readiness stage has been completed and explicitly approved.
// -------------------------------------------------------------------

class RaymondExecution
{
private:

   CTrade m_trade;

   bool m_demo_only;
   bool m_live_trading_enabled;

   double m_max_spread;
   int m_deviation_points;

   string m_last_error;
   ulong m_last_ticket;

public:

   RaymondExecution()
   {
      m_demo_only = true;
      m_live_trading_enabled = false;

      // Conservative default.
      // Broker-specific testing can adjust this later.
      m_max_spread = 1.00;

      m_deviation_points = 50;

      m_last_error = "";
      m_last_ticket = 0;
   }

   // ---------------------------------------------------------------
   // CONFIGURATION
   // ---------------------------------------------------------------

   void Configure(
      double max_spread,
      int deviation_points
   )
   {
      if(max_spread > 0.0)
         m_max_spread = max_spread;

      if(deviation_points > 0)
         m_deviation_points = deviation_points;

      m_trade.SetDeviationInPoints(
         m_deviation_points
      );
   }

   // ---------------------------------------------------------------
   // ABSOLUTE LIVE-TRADING LOCK
   // ---------------------------------------------------------------

   void SetLiveTradingEnabled(bool enabled)
   {
      // Step 11B-6 NEVER enables live trading.
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
   // ERROR / RESULT INFORMATION
   // ---------------------------------------------------------------

   string LastError()
   {
      return m_last_error;
   }

   ulong LastTicket()
   {
      return m_last_ticket;
   }

   void ClearResult()
   {
      m_last_error = "";
      m_last_ticket = 0;
   }

   // ---------------------------------------------------------------
   // ACCOUNT SAFETY
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

      // Only demo accounts are accepted.
      if(mode != ACCOUNT_TRADE_MODE_DEMO)
      {
         reason =
            "Execution blocked: MT5 account is not DEMO.";

         return false;
      }

      reason =
         "MT5 DEMO account validated.";

      return true;
   }

   // ---------------------------------------------------------------
   // SYMBOL VALIDATION
   // ---------------------------------------------------------------

   bool ValidateSymbol(
      string symbol,
      string &reason
   )
   {
      if(symbol == "")
      {
         reason = "Symbol is empty.";
         return false;
      }

      if(!SymbolSelect(symbol, true))
      {
         reason =
            "Unable to select requested symbol.";

         return false;
      }

      bool exists =
         (bool)SymbolInfoInteger(
            symbol,
            SYMBOL_EXIST
         );

      if(!exists)
      {
         reason =
            "Requested symbol does not exist.";

         return false;
      }

      reason =
         "Symbol validated.";

      return true;
   }

   // ---------------------------------------------------------------
   // QUOTE VALIDATION
   // ---------------------------------------------------------------

   bool ValidateQuote(
      string symbol,
      double &bid,
      double &ask,
      string &reason
   )
   {
      bid = SymbolInfoDouble(
         symbol,
         SYMBOL_BID
      );

      ask = SymbolInfoDouble(
         symbol,
         SYMBOL_ASK
      );

      if(bid <= 0.0)
      {
         reason = "Invalid bid.";
         return false;
      }

      if(ask <= 0.0)
      {
         reason = "Invalid ask.";
         return false;
      }

      if(ask < bid)
      {
         reason =
            "Ask is below bid.";

         return false;
      }

      double spread =
         ask - bid;

      if(spread > m_max_spread)
      {
         reason =
            "Spread exceeds configured safety limit.";

         return false;
      }

      reason =
         "Quote validated.";

      return true;
   }

   // ---------------------------------------------------------------
   // VOLUME VALIDATION
   // ---------------------------------------------------------------

   bool ValidateVolume(
      string symbol,
      double volume,
      string &reason
   )
   {
      if(volume <= 0.0)
      {
         reason =
            "Volume must be greater than zero.";

         return false;
      }

      double minimum =
         SymbolInfoDouble(
            symbol,
            SYMBOL_VOLUME_MIN
         );

      double maximum =
         SymbolInfoDouble(
            symbol,
            SYMBOL_VOLUME_MAX
         );

      double step =
         SymbolInfoDouble(
            symbol,
            SYMBOL_VOLUME_STEP
         );

      if(minimum <= 0.0)
      {
         reason =
            "Broker returned invalid minimum volume.";

         return false;
      }

      if(maximum <= 0.0)
      {
         reason =
            "Broker returned invalid maximum volume.";

         return false;
      }

      if(step <= 0.0)
      {
         reason =
            "Broker returned invalid volume step.";

         return false;
      }

      if(volume < minimum)
      {
         reason =
            "Requested volume is below broker minimum.";

         return false;
      }

      if(volume > maximum)
      {
         reason =
            "Requested volume exceeds broker maximum.";

         return false;
      }

      double normalized =
         MathRound(
            volume / step
         ) * step;

      double tolerance =
         step * 0.0001;

      if(
         MathAbs(
            normalized - volume
         ) > tolerance
      )
      {
         reason =
            "Volume does not match broker volume step.";

         return false;
      }

      reason =
         "Volume validated.";

      return true;
   }

   // ---------------------------------------------------------------
   // STOP VALIDATION
   // ---------------------------------------------------------------

   bool ValidateStops(
      string symbol,
      ENUM_ORDER_TYPE order_type,
      double entry_price,
      double stop_loss,
      double take_profit,
      string &reason
   )
   {
      int digits =
         (int)SymbolInfoInteger(
            symbol,
            SYMBOL_DIGITS
         );

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

      if(stop_loss <= 0.0)
      {
         reason =
            "Stop loss must be provided.";

         return false;
      }

      if(take_profit <= 0.0)
      {
         reason =
            "Take profit must be provided.";

         return false;
      }

      if(order_type == ORDER_TYPE_BUY)
      {
         if(stop_loss >= entry_price)
         {
            reason =
               "BUY stop loss must be below entry.";

            return false;
         }

         if(take_profit <= entry_price)
         {
            reason =
               "BUY take profit must be above entry.";

            return false;
         }

         if(
            minimum_distance > 0.0 &&
            entry_price - stop_loss <
            minimum_distance
         )
         {
            reason =
               "BUY stop loss is too close to entry.";

            return false;
         }

         if(
            minimum_distance > 0.0 &&
            take_profit - entry_price <
            minimum_distance
         )
         {
            reason =
               "BUY take profit is too close to entry.";

            return false;
         }
      }
      else if(order_type == ORDER_TYPE_SELL)
      {
         if(stop_loss <= entry_price)
         {
            reason =
               "SELL stop loss must be above entry.";

            return false;
         }

         if(take_profit >= entry_price)
         {
            reason =
               "SELL take profit must be below entry.";

            return false;
         }

         if(
            minimum_distance > 0.0 &&
            stop_loss - entry_price <
            minimum_distance
         )
         {
            reason =
               "SELL stop loss is too close to entry.";

            return false;
         }

         if(
            minimum_distance > 0.0 &&
            entry_price - take_profit <
            minimum_distance
         )
         {
            reason =
               "SELL take profit is too close to entry.";

            return false;
         }
      }
      else
      {
         reason =
            "Unsupported order type.";

         return false;
      }

      // Normalize prices to broker precision.
      entry_price =
         NormalizeDouble(
            entry_price,
            digits
         );

      stop_loss =
         NormalizeDouble(
            stop_loss,
            digits
         );

      take_profit =
         NormalizeDouble(
            take_profit,
            digits
         );

      reason =
         "Stops validated.";

      return true;
   }

   // ---------------------------------------------------------------
   // FINAL EXECUTION GATE
   //
   // This function requires every safety condition.
   // ---------------------------------------------------------------

   bool CanExecuteDemo(
      string symbol,
      ENUM_ORDER_TYPE order_type,
      double volume,
      double stop_loss,
      double take_profit,
      bool raymond_approved,
      bool risk_approved,
      bool emergency_stop,
      bool execution_authorized,
      bool live_trading_enabled,
      string &reason
   )
   {
      // Emergency stop has absolute priority.
      if(emergency_stop)
      {
         reason =
            "Execution blocked: Emergency Stop active.";

         return false;
      }

      // Live trading must remain disabled.
      if(live_trading_enabled)
      {
         reason =
            "Execution blocked: live trading flag detected.";

         return false;
      }

      // Internal live flag also remains disabled.
      if(m_live_trading_enabled)
      {
         reason =
            "Execution blocked: internal live trading flag.";

         return false;
      }

      // Execution authorization must be false in this stage.
      if(execution_authorized)
      {
         reason =
            "Execution blocked: live execution authorization detected.";

         return false;
      }

      // Raymond decision approval is required.
      if(!raymond_approved)
      {
         reason =
            "Execution blocked: Raymond approval missing.";

         return false;
      }

      // Risk approval is mandatory.
      if(!risk_approved)
      {
         reason =
            "Execution blocked: Risk Engine approval missing.";

         return false;
      }

      // Only DEMO accounts are permitted.
      if(
         !ValidateDemoAccount(
            reason
         )
      )
      {
         return false;
      }

      // Validate symbol.
      if(
         !ValidateSymbol(
            symbol,
            reason
         )
      )
      {
         return false;
      }

      // Validate volume.
      if(
         !ValidateVolume(
            symbol,
            volume,
            reason
         )
      )
      {
         return false;
      }

      // Validate quote.
      double bid = 0.0;
      double ask = 0.0;

      if(
         !ValidateQuote(
            symbol,
            bid,
            ask,
            reason
         )
      )
      {
         return false;
      }

      double entry_price;

      if(order_type == ORDER_TYPE_BUY)
         entry_price = ask;
      else if(order_type == ORDER_TYPE_SELL)
         entry_price = bid;
      else
      {
         reason =
            "Unsupported order type.";

         return false;
      }

      // Validate SL / TP.
      if(
         !ValidateStops(
            symbol,
            order_type,
            entry_price,
            stop_loss,
            take_profit,
            reason
         )
      )
      {
         return false;
      }

      // ------------------------------------------------------------
      // ABSOLUTE STEP 11B-6 DEMO GUARD
      // ------------------------------------------------------------

      if(!m_demo_only)
      {
         reason =
            "Execution blocked: DEMO_ONLY guard failed.";

         return false;
      }

      // This stage never permits live execution.
      if(m_live_trading_enabled)
      {
         reason =
            "Execution blocked: live trading is disabled.";

         return false;
      }

      reason =
         "All DEMO execution safety checks passed.";

      return true;
   }

   // ---------------------------------------------------------------
   // DEMO BUY
   // ---------------------------------------------------------------

   bool BuyDemo(
      string symbol,
      double volume,
      double stop_loss,
      double take_profit,
      bool raymond_approved,
      bool risk_approved,
      bool emergency_stop,
      bool execution_authorized,
      bool live_trading_enabled
   )
   {
      ClearResult();

      string reason = "";

      if(
         !CanExecuteDemo(
            symbol,
            ORDER_TYPE_BUY,
            volume,
            stop_loss,
            take_profit,
            raymond_approved,
            risk_approved,
            emergency_stop,
            execution_authorized,
            live_trading_enabled,
            reason
         )
      )
      {
         m_last_error = reason;
         return false;
      }

      double ask =
         SymbolInfoDouble(
            symbol,
            SYMBOL_ASK
         );

      if(ask <= 0.0)
      {
         m_last_error =
            "Invalid BUY execution price.";

         return false;
      }

      // DEMO ONLY.
      bool result =
         m_trade.Buy(
            volume,
            symbol,
            ask,
            stop_loss,
            take_profit,
            "Raymond DEMO BUY"
         );

      if(!result)
      {
         m_last_error =
            m_trade.ResultRetcodeDescription();

         return false;
      }

      m_last_ticket =
         m_trade.ResultOrder();

      // Verify resulting position.
      if(!VerifyPosition(
         symbol,
         POSITION_TYPE_BUY
      ))
      {
         m_last_error =
            "BUY order reported success but position verification failed.";

         return false;
      }

      return true;
   }

   // ---------------------------------------------------------------
   // DEMO SELL
   // ---------------------------------------------------------------

   bool SellDemo(
      string symbol,
      double volume,
      double stop_loss,
      double take_profit,
      bool raymond_approved,
      bool risk_approved,
      bool emergency_stop,
      bool execution_authorized,
      bool live_trading_enabled
   )
   {
      ClearResult();

      string reason = "";

      if(
         !CanExecuteDemo(
            symbol,
            ORDER_TYPE_SELL,
            volume,
            stop_loss,
            take_profit,
            raymond_approved,
            risk_approved,
            emergency_stop,
            execution_authorized,
            live_trading_enabled,
            reason
         )
      )
      {
         m_last_error = reason;
         return false;
      }

      double bid =
         SymbolInfoDouble(
            symbol,
            SYMBOL_BID
         );

      if(bid <= 0.0)
      {
         m_last_error =
            "Invalid SELL execution price.";

         return false;
      }

      // DEMO ONLY.
      bool result =
         m_trade.Sell(
            volume,
            symbol,
            bid,
            stop_loss,
            take_profit,
            "Raymond DEMO SELL"
         );

      if(!result)
      {
         m_last_error =
            m_trade.ResultRetcodeDescription();

         return false;
      }

      m_last_ticket =
         m_trade.ResultOrder();

      // Verify resulting position.
      if(!VerifyPosition(
         symbol,
         POSITION_TYPE_SELL
      ))
      {
         m_last_error =
            "SELL order reported success but position verification failed.";

         return false;
      }

      return true;
   }

   // ---------------------------------------------------------------
   // POSITION VERIFICATION
   // ---------------------------------------------------------------

   bool VerifyPosition(
      string symbol,
      ENUM_POSITION_TYPE expected_type
   )
   {
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

         if(!PositionSelectByTicket(ticket))
            continue;

         string position_symbol =
            PositionGetString(
               POSITION_SYMBOL
            );

         if(position_symbol != symbol)
            continue;

         ENUM_POSITION_TYPE type =
            (ENUM_POSITION_TYPE)
            PositionGetInteger(
               POSITION_TYPE
            );

         if(type == expected_type)
            return true;
      }

      return false;
   }

   // ---------------------------------------------------------------
   // EXECUTION STATUS
   // ---------------------------------------------------------------

   string Status()
   {
      string result =
         "Raymond Execution: ";

      result +=
         "MT5";

      result +=
         " | Broker=Agnostic";

      result +=
         " | DEMO_ONLY=ON";

      result +=
         " | LiveTrading=OFF";

      result +=
         " | Credentials=External";

      return result;
   }
};

#endif
