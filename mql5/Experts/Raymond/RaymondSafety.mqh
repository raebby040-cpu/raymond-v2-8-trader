//+------------------------------------------------------------------+
//| RaymondSafety.mqh                                                |
//| Raymond v2.8 Trader - Step 11B-5                                |
//| EA-side hard safety validation                                   |
//+------------------------------------------------------------------+
#property strict

#ifndef RAYMOND_SAFETY_MQH
#define RAYMOND_SAFETY_MQH

// -------------------------------------------------------------------
// STEP 11B-5 SAFETY POLICY
//
// This module validates AI decisions before execution.
//
// IMPORTANT:
// This stage is still READ ONLY.
//
// No OrderSend()
// No PositionClose()
// No SL modification
// No TP modification
// No live execution
// -------------------------------------------------------------------

class RaymondSafety
{
private:

   bool m_emergency_stop;

   bool m_live_trading_enabled;

   bool m_execution_authorized;

   double m_max_spread;

   int m_max_decision_age_seconds;

public:

   RaymondSafety()
   {
      m_emergency_stop = true;

      m_live_trading_enabled = false;

      m_execution_authorized = false;

      // Conservative XAUUSD default.
      // Can be changed later after broker-specific testing.
      m_max_spread = 1.00;

      // AI decisions older than this are rejected.
      m_max_decision_age_seconds = 30;
   }

   // ---------------------------------------------------------------
   // CONFIGURATION
   // ---------------------------------------------------------------

   void Configure(
      double max_spread,
      int max_decision_age_seconds
   )
   {
      if(max_spread > 0.0)
         m_max_spread = max_spread;

      if(max_decision_age_seconds > 0)
         m_max_decision_age_seconds =
            max_decision_age_seconds;
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
   // EXECUTION FLAGS
   // ---------------------------------------------------------------

   void SetLiveTradingEnabled(bool enabled)
   {
      // Step 11B-5 deliberately refuses live enablement.
      m_live_trading_enabled = false;
   }

   void SetExecutionAuthorized(bool authorized)
   {
      // Step 11B-5 deliberately refuses execution authorization.
      m_execution_authorized = false;
   }

   bool LiveTradingEnabled()
   {
      return m_live_trading_enabled;
   }

   bool ExecutionAuthorized()
   {
      return m_execution_authorized;
   }

   // ---------------------------------------------------------------
   // MARKET DATA VALIDATION
   // ---------------------------------------------------------------

   bool ValidateQuote(
      double bid,
      double ask,
      string &reason
   )
   {
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
         reason = "Ask is below bid.";
         return false;
      }

      double spread = ask - bid;

      if(spread > m_max_spread)
      {
         reason = "Spread exceeds safety limit.";
         return false;
      }

      reason = "Quote passed safety validation.";

      return true;
   }

   // ---------------------------------------------------------------
   // SYMBOL VALIDATION
   // ---------------------------------------------------------------

   bool ValidateSymbol(
      string expected_symbol,
      string received_symbol,
      string &reason
   )
   {
      if(expected_symbol == "")
      {
         reason = "Expected symbol is empty.";
         return false;
      }

      if(received_symbol == "")
      {
         reason = "Received symbol is empty.";
         return false;
      }

      if(expected_symbol != received_symbol)
      {
         reason = "Symbol mismatch.";
         return false;
      }

      reason = "Symbol passed safety validation.";

      return true;
   }

   // ---------------------------------------------------------------
   // AI DECISION VALIDATION
   //
   // Step 11B-5 intentionally rejects execution.
   //
   // This function proves that a decision can be validated
   // without allowing it to become a broker order.
   // ---------------------------------------------------------------

   bool ValidateAIDecision(
      string action,
      bool trading_enabled,
      bool live_trading_enabled,
      bool execution_authorized,
      bool risk_engine_required,
      bool read_only,
      string &reason
   )
   {
      // Emergency stop always wins.
      if(m_emergency_stop)
      {
         reason = "Emergency stop is active.";
         return false;
      }

      // Global safety lock.
      if(m_live_trading_enabled)
      {
         reason = "EA live trading flag must remain disabled.";
         return false;
      }

      if(m_execution_authorized)
      {
         reason = "EA execution authorization must remain disabled.";
         return false;
      }

      // Decision supplied by Raymond must also remain locked.
      if(trading_enabled)
      {
         reason = "Raymond decision reports trading enabled.";
         return false;
      }

      if(live_trading_enabled)
      {
         reason = "Raymond reports live trading enabled.";
         return false;
      }

      if(execution_authorized)
      {
         reason = "Raymond reports execution authorized.";
         return false;
      }

      // Risk Engine must remain part of the architecture.
      if(!risk_engine_required)
      {
         reason = "Risk Engine requirement is missing.";
         return false;
      }

      // This stage must remain read-only.
      if(!read_only)
      {
         reason = "Decision is not marked READ_ONLY.";
         return false;
      }

      // Only known decision actions are accepted.
      if(
         action != "BUY" &&
         action != "SELL" &&
         action != "HOLD/WAIT"
      )
      {
         reason = "Unknown AI action.";
         return false;
      }

      // No action is executable in Step 11B-5.
      reason =
         "Decision validated but execution remains disabled.";

      return false;
   }

   // ---------------------------------------------------------------
   // DECISION AGE VALIDATION
   // ---------------------------------------------------------------

   bool ValidateDecisionAge(
      datetime decision_time,
      string &reason
   )
   {
      if(decision_time <= 0)
      {
         reason = "Invalid decision timestamp.";
         return false;
      }

      datetime now_time = TimeCurrent();

      if(now_time < decision_time)
      {
         reason = "Decision timestamp is in the future.";
         return false;
      }

      int age =
         (int)(now_time - decision_time);

      if(age > m_max_decision_age_seconds)
      {
         reason = "AI decision is stale.";
         return false;
      }

      reason = "Decision age passed safety validation.";

      return true;
   }

   // ---------------------------------------------------------------
   // ABSOLUTE EXECUTION LOCK
   // ---------------------------------------------------------------

   bool CanExecute()
   {
      // This MUST remain false during Step 11B-5.
      return false;
   }

   // ---------------------------------------------------------------
   // SAFETY STATUS
   // ---------------------------------------------------------------

   string Status()
   {
      string result =
         "Raymond Safety: ";

      result +=
         "READ_ONLY";

      result +=
         " | EmergencyStop=" +
         (m_emergency_stop ? "ON" : "OFF");

      result +=
         " | LiveTrading=OFF";

      result +=
         " | Execution=OFF";

      return result;
   }
};

#endif
