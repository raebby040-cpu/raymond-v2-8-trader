//+------------------------------------------------------------------+
//| RaymondExecution.mqh                                             |
//| RAYMOND v2.8 - MT5 Trading Bridge                                |
//| STEP 11B-9: SAFE EXECUTION GATE / DEMO ONLY                     |
//+------------------------------------------------------------------+
//
// PURPOSE
// -------
// This module is the execution boundary for the Raymond MT5 EA.
//
// IMPORTANT SAFETY DESIGN
// -----------------------
// 1. LIVE TRADING IS HARD-LOCKED OFF.
// 2. This module is DEMO-ONLY.
// 3. This module does NOT send broker orders.
// 4. This module does NOT call OrderSend().
// 5. This module does NOT call CTrade::Buy(), Sell(), PositionOpen(),
//    or any other order-placement method.
// 6. AI decisions are NOT automatically executable.
// 7. Risk Engine and RaymondSafety remain mandatory authorities.
// 8. Any future real execution implementation must be a separate,
//    explicitly reviewed change.
//
// The current RAYMOND architecture is:
// MT5 market data
//      -> telemetry / AI read-only decision
//      -> safety
//      -> risk
//      -> paper/demo execution architecture
//
// This file deliberately stops at the execution boundary.
//
//+------------------------------------------------------------------+
#property strict

//+------------------------------------------------------------------+
//| RaymondExecution                                                |
//+------------------------------------------------------------------+
class RaymondExecution
{
private:

   // ---------------------------------------------------------------
   // Configuration
   // ---------------------------------------------------------------

   double m_max_spread;
   int    m_deviation_points;

   // ---------------------------------------------------------------
   // Absolute safety state
   // ---------------------------------------------------------------

   bool m_live_trading_enabled;
   bool m_demo_only;
   bool m_execution_authorized;
   bool m_emergency_stop;

   // ---------------------------------------------------------------
   // Diagnostic state
   // ---------------------------------------------------------------

   string m_last_rejection_reason;

   // ---------------------------------------------------------------
   // Internal fail-closed helper
   // ---------------------------------------------------------------

   bool Reject(
      string reason
   )
   {
      m_last_rejection_reason = reason;

      Print(
         "RAYMOND EXECUTION | REJECTED | ",
         reason
      );

      return false;
   }

public:

   //+------------------------------------------------------------------+
   //| Constructor                                                      |
   //+------------------------------------------------------------------+
   RaymondExecution()
   {
      m_max_spread        = 1.00;
      m_deviation_points  = 50;

      // Absolute defaults.
      m_live_trading_enabled = false;
      m_demo_only             = true;
      m_execution_authorized  = false;
      m_emergency_stop        = true;

      m_last_rejection_reason = "Execution not authorized.";
   }

   //+------------------------------------------------------------------+
   //| Configure                                                        |
   //+------------------------------------------------------------------+
   void Configure(
      double max_spread,
      int deviation_points
   )
   {
      // ---------------------------------------------------------------
      // Validate spread configuration.
      // ---------------------------------------------------------------

      if(max_spread > 0.0)
      {
         m_max_spread = max_spread;
      }
      else
      {
         m_max_spread = 1.00;

         Print(
            "RAYMOND EXECUTION | Invalid spread configuration. ",
            "Using safe default."
         );
      }

      // ---------------------------------------------------------------
      // Validate deviation configuration.
      // ---------------------------------------------------------------

      if(deviation_points > 0)
      {
         m_deviation_points = deviation_points;
      }
      else
      {
         m_deviation_points = 50;

         Print(
            "RAYMOND EXECUTION | Invalid deviation configuration. ",
            "Using safe default."
         );
      }

      // ---------------------------------------------------------------
      // Re-assert absolute safety state after configuration.
      // ---------------------------------------------------------------

      m_live_trading_enabled = false;
      m_demo_only             = true;
      m_execution_authorized  = false;
      m_emergency_stop        = true;

      m_last_rejection_reason =
         "Execution is configured but not authorized.";

      Print(
         "RAYMOND EXECUTION | Configured | ",
         "MaxSpread=",
         DoubleToString(m_max_spread, 2),
         " | DeviationPoints=",
         IntegerToString(m_deviation_points),
         " | DEMO_ONLY=YES",
         " | LIVE=OFF",
         " | AUTHORIZED=NO"
      );
   }

   //+------------------------------------------------------------------+
   //| Set live trading state                                           |
   //+------------------------------------------------------------------+
   void SetLiveTradingEnabled(
      bool enabled
   )
   {
      // ---------------------------------------------------------------
      // Absolute live-trading hard lock.
      //
      // The supplied value is deliberately ignored.
      // ---------------------------------------------------------------

      m_live_trading_enabled = false;

      if(enabled)
      {
         Print(
            "RAYMOND EXECUTION | SAFETY BLOCK | ",
            "Attempt to enable live trading was rejected."
         );

         m_last_rejection_reason =
            "Live trading is permanently disabled in this module.";

         return;
      }

      Print(
         "RAYMOND EXECUTION | Live trading remains HARD LOCKED OFF."
      );
   }

   //+------------------------------------------------------------------+
   //| Live trading status                                              |
   //+------------------------------------------------------------------+
   bool LiveTradingEnabled()
   {
      // Never return true.
      return false;
   }

   //+------------------------------------------------------------------+
   //| Demo-only status                                                 |
   //+------------------------------------------------------------------+
   bool DemoOnly()
   {
      return true;
   }

   //+------------------------------------------------------------------+
   //| Set execution authorization                                      |
   //+------------------------------------------------------------------+
   void SetExecutionAuthorized(
      bool authorized
   )
   {
      // ---------------------------------------------------------------
      // The current EA architecture does not authorize execution.
      //
      // Even if a caller attempts to authorize execution, this module
      // remains fail-closed until a separately reviewed execution
      // implementation exists.
      // ---------------------------------------------------------------

      m_execution_authorized = false;

      if(authorized)
      {
         Print(
            "RAYMOND EXECUTION | SAFETY BLOCK | ",
            "Execution authorization request rejected."
         );

         m_last_rejection_reason =
            "Execution authorization is disabled.";
      }
      else
      {
         Print(
            "RAYMOND EXECUTION | Execution authorization remains OFF."
         );
      }
   }

   //+------------------------------------------------------------------+
   //| Execution authorization status                                   |
   //+------------------------------------------------------------------+
   bool ExecutionAuthorized()
   {
      return false;
   }

   //+------------------------------------------------------------------+
   //| Set emergency stop                                                |
   //+------------------------------------------------------------------+
   void SetEmergencyStop(
      bool active
   )
   {
      m_emergency_stop = active;

      if(active)
      {
         Print(
            "RAYMOND EXECUTION | Emergency Stop = ON."
         );

         m_last_rejection_reason =
            "Emergency Stop is active.";
      }
      else
      {
         Print(
            "RAYMOND EXECUTION | Emergency Stop = OFF."
         );
      }
   }

   //+------------------------------------------------------------------+
   //| Emergency stop status                                             |
   //+------------------------------------------------------------------+
   bool EmergencyStopActive()
   {
      return m_emergency_stop;
   }

   //+------------------------------------------------------------------+
   //| Maximum spread                                                   |
   //+------------------------------------------------------------------+
   double MaxSpread()
   {
      return m_max_spread;
   }

   //+------------------------------------------------------------------+
   //| Maximum deviation                                                |
   //+------------------------------------------------------------------+
   int DeviationPoints()
   {
      return m_deviation_points;
   }

   //+------------------------------------------------------------------+
   //| Last rejection reason                                             |
   //+------------------------------------------------------------------+
   string LastRejectionReason()
   {
      return m_last_rejection_reason;
   }

   //+------------------------------------------------------------------+
   //| Validate execution environment                                    |
   //+------------------------------------------------------------------+
   bool CanExecute()
   {
      // ---------------------------------------------------------------
      // This function intentionally always fails closed.
      //
      // There is currently no broker-order implementation in this
      // module. Therefore no execution request can pass this gate.
      // ---------------------------------------------------------------

      if(m_live_trading_enabled)
      {
         return Reject(
            "Live trading flag detected."
         );
      }

      if(!m_demo_only)
      {
         return Reject(
            "DEMO_ONLY invariant was violated."
         );
      }

      if(m_execution_authorized)
      {
         return Reject(
            "Execution authorization invariant was violated."
         );
      }

      if(m_emergency_stop)
      {
         return Reject(
            "Emergency Stop is active."
         );
      }

      return Reject(
         "No broker execution implementation is enabled."
      );
   }

   //+------------------------------------------------------------------+
   //| Validate quote                                                   |
   //+------------------------------------------------------------------+
   bool ValidateQuote(
      double bid,
      double ask,
      string &reason
   )
   {
      reason = "";

      // ---------------------------------------------------------------
      // Basic quote validation.
      // ---------------------------------------------------------------

      if(bid <= 0.0)
      {
         reason = "Bid must be greater than zero.";
         return false;
      }

      if(ask <= 0.0)
      {
         reason = "Ask must be greater than zero.";
         return false;
      }

      if(ask < bid)
      {
         reason = "Ask cannot be below bid.";
         return false;
      }

      double spread = ask - bid;

      if(spread <= 0.0)
      {
         reason = "Spread must be greater than zero.";
         return false;
      }

      if(spread > m_max_spread)
      {
         reason =
            "Spread exceeds execution safety limit.";

         return false;
      }

      return true;
   }

   //+------------------------------------------------------------------+
   //| Validate symbol                                                  |
   //+------------------------------------------------------------------+
   bool ValidateSymbol(
      string symbol,
      string expected_symbol,
      string &reason
   )
   {
      reason = "";

      if(symbol == "")
      {
         reason = "Execution symbol cannot be empty.";
         return false;
      }

      if(expected_symbol == "")
      {
         reason = "Expected symbol cannot be empty.";
         return false;
      }

      if(symbol != expected_symbol)
      {
         reason =
            "Execution symbol does not match expected symbol.";

         return false;
      }

      return true;
   }

   //+------------------------------------------------------------------+
   //| Validate volume                                                  |
   //+------------------------------------------------------------------+
   bool ValidateVolume(
      double volume,
      string &reason
   )
   {
      reason = "";

      if(volume <= 0.0)
      {
         reason =
            "Execution volume must be greater than zero.";

         return false;
      }

      return true;
   }

   //+------------------------------------------------------------------+
   //| Explicitly reject order placement                                 |
   //+------------------------------------------------------------------+
   bool RejectOrderPlacement(
      string reason
   )
   {
      if(reason == "")
      {
         reason =
            "Broker order placement is disabled.";
      }

      return Reject(
         reason
      );
   }

   //+------------------------------------------------------------------+
   //| Explicitly reject AI execution                                   |
   //+------------------------------------------------------------------+
   bool RejectAIDecisionExecution(
      string action
   )
   {
      if(action == "")
      {
         action = "UNKNOWN";
      }

      return Reject(
         "AI action '" +
         action +
         "' is READ_ONLY and cannot be executed."
      );
   }

   //+------------------------------------------------------------------+
   //| Safety status                                                     |
   //+------------------------------------------------------------------+
   string Status()
   {
      return StringFormat(
         "DEMO_ONLY=%s | LIVE=%s | AUTHORIZED=%s | EMERGENCY_STOP=%s | MAX_SPREAD=%.2f | DEVIATION=%d",
         m_demo_only ? "YES" : "NO",
         m_live_trading_enabled ? "ON" : "OFF",
         m_execution_authorized ? "YES" : "NO",
         m_emergency_stop ? "ON" : "OFF",
         m_max_spread,
         m_deviation_points
      );
   }
};

//+------------------------------------------------------------------+
//| END RaymondExecution.mqh                                         |
//+------------------------------------------------------------------+
