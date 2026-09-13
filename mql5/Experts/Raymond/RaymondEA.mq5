//+------------------------------------------------------------------+
//| RaymondEA.mq5                                                    |
//| RAYMOND v2.8 - MT5 Trading Bridge                                |
//| STEP 11B-8: AI READ-ONLY DECISION + SAFETY + DEMO                |
//+------------------------------------------------------------------+
#property strict
#property version   "0.8.0"
#property description "RAYMOND v2.8 broker-agnostic MT5 bridge"
#property description "Telemetry, READ-ONLY AI decisions, safety and DEMO protection"
#property description "LIVE TRADING HARD-LOCKED OFF"

#include "RaymondBridge.mqh"
#include "RaymondSafety.mqh"
#include "RaymondExecution.mqh"
#include "RaymondPositionManager.mqh"

// -------------------------------------------------------------------
// INPUTS
// -------------------------------------------------------------------

input string InpSymbol = "XAUUSD";
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M15;
input int InpTimerSeconds = 5;

input string InpBackendUrl = "";
input string InpTelemetryPath = "/api/mt5/telemetry";
input int InpBackendTimeoutMs = 5000;

// -------------------------------------------------------------------
// AI READ-ONLY SETTINGS
// -------------------------------------------------------------------

input int InpAIDecisionIntervalSeconds = 15;
input int InpAICandleLimit = 100;

// -------------------------------------------------------------------
// SAFETY
// -------------------------------------------------------------------

input double InpMaxSpread = 1.00;
input int InpMaxDecisionAgeSeconds = 30;

// -------------------------------------------------------------------
// DEMO EXECUTION
// -------------------------------------------------------------------

input int InpDeviationPoints = 50;

// -------------------------------------------------------------------
// POSITION PROTECTION
// -------------------------------------------------------------------

input double InpBreakEvenTrigger = 2.00;
input double InpBreakEvenOffset = 0.20;

input double InpProfitLockTrigger = 4.00;
input double InpProfitLockDistance = 1.00;

// -------------------------------------------------------------------
// ABSOLUTE LIVE-TRADING LOCK
// -------------------------------------------------------------------

bool TRADING_ENABLED = false;

// -------------------------------------------------------------------
// MODULES
// -------------------------------------------------------------------

RaymondBridge Raymond;
RaymondSafety RaymondSafetyEngine;
RaymondExecution RaymondExecutionEngine;
RaymondPositionManager RaymondPositionManagerEngine;

// -------------------------------------------------------------------
// RUNTIME STATE
// -------------------------------------------------------------------

bool g_initialized = false;

datetime g_last_status_log = 0;
datetime g_last_ai_request = 0;

string g_ai_action = "HOLD/WAIT";
double g_ai_confidence = 0.0;

//+------------------------------------------------------------------+
//| Convert MT5 timeframe enum to Raymond API timeframe              |
//+------------------------------------------------------------------+
string RaymondTimeframe()
{
   switch(InpTimeframe)
   {
      case PERIOD_M1:
         return "M1";

      case PERIOD_M5:
         return "M5";

      case PERIOD_M15:
         return "M15";

      case PERIOD_M30:
         return "M30";

      case PERIOD_H1:
         return "H1";

      case PERIOD_H4:
         return "H4";

      case PERIOD_D1:
         return "D1";

      default:
         return "M15";
   }
}

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("==================================================");
   Print("RAYMOND v2.8 MT5 EA");
   Print("STEP 11B-8");
   Print("MODE: READ-ONLY AI / DEMO / SAFETY");
   Print("LIVE TRADING: HARD LOCKED OFF");
   Print("Symbol: ", InpSymbol);
   Print("Timeframe: ", EnumToString(InpTimeframe));
   Print("==================================================");

   // ---------------------------------------------------------------
   // ABSOLUTE LIVE-TRADING SAFETY CHECK
   // ---------------------------------------------------------------

   if(TRADING_ENABLED)
   {
      Print(
         "FATAL SAFETY ERROR: TRADING_ENABLED must remain FALSE."
      );

      return INIT_FAILED;
   }

   // ---------------------------------------------------------------
   // INPUT VALIDATION
   // ---------------------------------------------------------------

   if(InpSymbol == "")
   {
      Print("ERROR: Symbol cannot be empty.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpTimerSeconds < 1)
   {
      Print("ERROR: Timer must be at least 1 second.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpBackendTimeoutMs < 100)
   {
      Print(
         "ERROR: Backend timeout must be at least 100 ms."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpAIDecisionIntervalSeconds < 1)
   {
      Print(
         "ERROR: AI decision interval must be at least 1 second."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpAICandleLimit < 60)
   {
      Print(
         "ERROR: AI candle limit must be at least 60."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpAICandleLimit > 500)
   {
      Print(
         "ERROR: AI candle limit cannot exceed 500."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpMaxSpread <= 0.0)
   {
      Print(
         "ERROR: Maximum spread must be greater than zero."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpMaxDecisionAgeSeconds < 1)
   {
      Print(
         "ERROR: Maximum decision age must be greater than zero."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpDeviationPoints < 1)
   {
      Print(
         "ERROR: Deviation must be greater than zero."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpBreakEvenTrigger < 0.0)
   {
      Print(
         "ERROR: Break-even trigger cannot be negative."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpProfitLockTrigger < 0.0)
   {
      Print(
         "ERROR: Profit-lock trigger cannot be negative."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpProfitLockDistance <= 0.0)
   {
      Print(
         "ERROR: Profit-lock distance must be greater than zero."
      );

      return INIT_PARAMETERS_INCORRECT;
   }

   // ---------------------------------------------------------------
   // SYMBOL
   // ---------------------------------------------------------------

   ResetLastError();

   if(!SymbolSelect(InpSymbol, true))
   {
      Print(
         "ERROR: Could not select symbol ",
         InpSymbol,
         ". Error=",
         GetLastError()
      );

      return INIT_FAILED;
   }

   // ---------------------------------------------------------------
   // TELEMETRY + AI BRIDGE
   // ---------------------------------------------------------------

   Raymond.Configure(
      InpBackendUrl,
      InpTelemetryPath,
      InpBackendTimeoutMs
   );

   Raymond.SetEnabled(true);

   if(Raymond.IsConfigured())
   {
      Print(
         "RAYMOND BRIDGE: Backend URL configured."
      );
   }
   else
   {
      Print(
         "RAYMOND BRIDGE: Backend URL not configured."
      );

      Print(
         "Telemetry and AI decision requests will remain inactive."
      );
   }

   // ---------------------------------------------------------------
   // SAFETY ENGINE
   // ---------------------------------------------------------------

   RaymondSafetyEngine.Configure(
      InpMaxSpread,
      InpMaxDecisionAgeSeconds
   );

   // Emergency stop deliberately starts ON.
   RaymondSafetyEngine.SetEmergencyStop(true);

   // Hard-disabled.
   RaymondSafetyEngine.SetLiveTradingEnabled(false);
   RaymondSafetyEngine.SetExecutionAuthorized(false);

   // ---------------------------------------------------------------
   // DEMO EXECUTION ENGINE
   // ---------------------------------------------------------------

   RaymondExecutionEngine.Configure(
      InpMaxSpread,
      InpDeviationPoints
   );

   RaymondExecutionEngine.SetLiveTradingEnabled(false);

   // ---------------------------------------------------------------
   // POSITION MANAGER
   // ---------------------------------------------------------------

   RaymondPositionManagerEngine.Configure(
      InpBreakEvenTrigger,
      InpBreakEvenOffset,
      InpProfitLockTrigger,
      InpProfitLockDistance,
      InpDeviationPoints
   );

   // Emergency stop remains ON.
   RaymondPositionManagerEngine.SetEmergencyStop(true);

   // Live trading remains disabled.
   RaymondPositionManagerEngine.SetLiveTradingEnabled(false);

   // ---------------------------------------------------------------
   // TIMER
   // ---------------------------------------------------------------

   ResetLastError();

   if(!EventSetTimer(InpTimerSeconds))
   {
      Print(
         "ERROR: EventSetTimer failed. Error=",
         GetLastError()
      );

      return INIT_FAILED;
   }

   g_initialized = true;
   g_last_status_log = TimeCurrent();
   g_last_ai_request = 0;

   g_ai_action = "HOLD/WAIT";
   g_ai_confidence = 0.0;

   // ---------------------------------------------------------------
   // STARTUP STATUS
   // ---------------------------------------------------------------

   Print("--------------------------------------------------");
   Print("RAYMOND SAFETY STATUS");

   Print(
      "Emergency Stop: ",
      RaymondSafetyEngine.EmergencyStopActive()
      ? "ON"
      : "OFF"
   );

   Print(
      "Live Trading: ",
      RaymondSafetyEngine.LiveTradingEnabled()
      ? "ON"
      : "OFF"
   );

   Print(
      "Execution Authorized: ",
      RaymondSafetyEngine.ExecutionAuthorized()
      ? "YES"
      : "NO"
   );

   Print(
      "Execution DEMO Only: ",
      RaymondExecutionEngine.DemoOnly()
      ? "YES"
      : "NO"
   );

   Print(
      "Position Manager DEMO Only: ",
      RaymondPositionManagerEngine.DemoOnly()
      ? "YES"
      : "NO"
   );

   Print(
      "AI Decision Mode: READ_ONLY"
   );

   Print(
      "AI Decision Execution: DISABLED"
   );

   Print("--------------------------------------------------");
   Print("RAYMOND EA initialized successfully.");
   Print("LIVE TRADING IS HARD-LOCKED OFF.");
   Print("AI MAY RECOMMEND, BUT THIS EA WILL NOT EXECUTE THE AI SIGNAL.");
   Print("==================================================");

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();

   g_initialized = false;

   Print("==================================================");
   Print("RAYMOND v2.8 EA stopped.");
   Print("Reason: ", reason);
   Print("LIVE TRADING REMAINED DISABLED.");
   Print("==================================================");
}

//+------------------------------------------------------------------+
//| Tick                                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   // Deliberately empty.
   //
   // Raymond performs controlled monitoring through OnTimer().
}

//+------------------------------------------------------------------+
//| Timer                                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(!g_initialized)
      return;

   // ---------------------------------------------------------------
   // ABSOLUTE SAFETY LOCK
   // ---------------------------------------------------------------

   if(TRADING_ENABLED)
   {
      Print(
         "RAYMOND SAFETY ERROR: TRADING_ENABLED became TRUE."
      );

      return;
   }

   // ---------------------------------------------------------------
   // MARKET
   // ---------------------------------------------------------------

   MonitorMarket();

   // ---------------------------------------------------------------
   // ACCOUNT
   // ---------------------------------------------------------------

   MonitorAccount();

   // ---------------------------------------------------------------
   // POSITIONS
   // ---------------------------------------------------------------

   MonitorPositions();

   // ---------------------------------------------------------------
   // POSITION PROTECTION
   // ---------------------------------------------------------------
   //
   // Emergency stop remains ON, so the existing position manager
   // remains blocked from modifying positions.
   // ---------------------------------------------------------------

   RaymondPositionManagerEngine.MonitorAllPositions();

   // ---------------------------------------------------------------
   // READ-ONLY AI DECISION
   // ---------------------------------------------------------------

   RequestAIDecisionIfDue();

   // ---------------------------------------------------------------
   // BACKEND TELEMETRY
   // ---------------------------------------------------------------

   SendTelemetry();

   // ---------------------------------------------------------------
   // PERIODIC STATUS
   // ---------------------------------------------------------------

   PrintStatusPeriodically();
}

//+------------------------------------------------------------------+
//| Read current market quote                                        |
//+------------------------------------------------------------------+
bool GetMarketData(
   double &bid,
   double &ask
)
{
   bid = 0.0;
   ask = 0.0;

   MqlTick tick;

   if(!SymbolInfoTick(InpSymbol, tick))
   {
      Print(
         "RAYMOND MARKET | Failed to read tick for ",
         InpSymbol
      );

      return false;
   }

   bid = tick.bid;
   ask = tick.ask;

   if(bid <= 0.0 || ask <= 0.0)
   {
      Print(
         "RAYMOND MARKET | Invalid quote."
      );

      return false;
   }

   if(ask < bid)
   {
      Print(
         "RAYMOND MARKET | Invalid quote: ask below bid."
      );

      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Market monitoring                                                |
//+------------------------------------------------------------------+
void MonitorMarket()
{
   double bid = 0.0;
   double ask = 0.0;

   if(!GetMarketData(bid, ask))
      return;

   double spread = ask - bid;

   PrintFormat(
      "RAYMOND MARKET | %s | Bid=%.2f | Ask=%.2f | Spread=%.2f",
      InpSymbol,
      bid,
      ask,
      spread
   );

   string reason = "";

   bool quote_ok =
      RaymondSafetyEngine.ValidateQuote(
         bid,
         ask,
         reason
      );

   if(!quote_ok)
   {
      Print(
         "RAYMOND SAFETY | Quote rejected | ",
         reason
      );
   }
}

//+------------------------------------------------------------------+
//| Account monitoring                                               |
//+------------------------------------------------------------------+
void MonitorAccount()
{
   double balance =
      AccountInfoDouble(
         ACCOUNT_BALANCE
      );

   double equity =
      AccountInfoDouble(
         ACCOUNT_EQUITY
      );

   double margin =
      AccountInfoDouble(
         ACCOUNT_MARGIN
      );

   double free_margin =
      AccountInfoDouble(
         ACCOUNT_MARGIN_FREE
      );

   long trade_mode =
      AccountInfoInteger(
         ACCOUNT_TRADE_MODE
      );

   PrintFormat(
      "RAYMOND ACCOUNT | Balance=%.2f | Equity=%.2f | Margin=%.2f | FreeMargin=%.2f | TradeMode=%d",
      balance,
      equity,
      margin,
      free_margin,
      trade_mode
   );
}

//+------------------------------------------------------------------+
//| Position monitoring                                              |
//+------------------------------------------------------------------+
void MonitorPositions()
{
   int total = PositionsTotal();

   PrintFormat(
      "RAYMOND POSITIONS | Open positions=%d",
      total
   );

   for(int i = 0; i < total; i++)
   {
      ulong ticket =
         PositionGetTicket(i);

      if(ticket == 0)
         continue;

      string symbol =
         PositionGetString(
            POSITION_SYMBOL
         );

      long type =
         PositionGetInteger(
            POSITION_TYPE
         );

      double volume =
         PositionGetDouble(
            POSITION_VOLUME
         );

      double open_price =
         PositionGetDouble(
            POSITION_PRICE_OPEN
         );

      double sl =
         PositionGetDouble(
            POSITION_SL
         );

      double tp =
         PositionGetDouble(
            POSITION_TP
         );

      double profit =
         PositionGetDouble(
            POSITION_PROFIT
         );

      PrintFormat(
         "RAYMOND POSITION | Ticket=%I64u | Symbol=%s | Type=%d | Volume=%.2f | Open=%.2f | SL=%.2f | TP=%.2f | Profit=%.2f",
         ticket,
         symbol,
         type,
         volume,
         open_price,
         sl,
         tp,
         profit
      );
   }
}

//+------------------------------------------------------------------+
//| Request AI decision when interval has elapsed                     |
//+------------------------------------------------------------------+
void RequestAIDecisionIfDue()
{
   // ---------------------------------------------------------------
   // ABSOLUTE SAFETY LOCK
   // ---------------------------------------------------------------

   if(TRADING_ENABLED)
   {
      Print(
         "RAYMOND AI | Request blocked because trading flag is TRUE."
      );

      return;
   }

   if(!Raymond.IsConfigured())
      return;

   datetime now = TimeCurrent();

   if(
      g_last_ai_request != 0 &&
      (now - g_last_ai_request) <
      InpAIDecisionIntervalSeconds
   )
   {
      return;
   }

   g_last_ai_request = now;

   string timeframe =
      RaymondTimeframe();

   Print(
      "RAYMOND AI | Requesting READ_ONLY decision | Symbol=",
      InpSymbol,
      " | Timeframe=",
      timeframe
   );

   bool result =
      Raymond.RequestAIDecision(
         InpSymbol,
         timeframe,
         InpAICandleLimit
      );

   if(!result)
   {
      // ------------------------------------------------------------
      // FAIL CLOSED
      // ------------------------------------------------------------

      g_ai_action = "HOLD/WAIT";
      g_ai_confidence = 0.0;

      Print(
         "RAYMOND AI | Decision request failed."
      );

      Print(
         "RAYMOND AI | HTTP=",
         Raymond.LastHttpCode(),
         " | Error=",
         Raymond.LastError()
      );

      return;
   }

   // ---------------------------------------------------------------
   // Store only the read-only AI result.
   // ---------------------------------------------------------------

   g_ai_action =
      Raymond.LastAIAction();

   g_ai_confidence =
      Raymond.LastAIConfidence();

   PrintFormat(
      "RAYMOND AI | READ_ONLY RESULT | Action=%s | Confidence=%.2f",
      g_ai_action,
      g_ai_confidence
   );

   // ---------------------------------------------------------------
   // CRITICAL:
   //
   // The result is NOT sent to RaymondExecutionEngine.
   // The result is NOT sent to CTrade.
   // The result is NOT used to open a position.
   //
   // AI recommendation ends here.
   // Risk and execution remain separate.
   // ---------------------------------------------------------------

   if(
      g_ai_action == "BUY" ||
      g_ai_action == "SELL"
   )
   {
      Print(
         "RAYMOND AI | Recommendation received."
      );

      Print(
         "RAYMOND AI | Execution remains DISABLED."
      );
   }
   else
   {
      Print(
         "RAYMOND AI | HOLD/WAIT - no trading action."
      );
   }
}

//+------------------------------------------------------------------+
//| Telemetry                                                        |
//+------------------------------------------------------------------+
void SendTelemetry()
{
   // Absolute safety lock.
   if(TRADING_ENABLED)
   {
      Print(
         "RAYMOND SAFETY | Telemetry blocked because trading flag is TRUE."
      );

      return;
   }

   if(!Raymond.IsConfigured())
      return;

   double bid = 0.0;
   double ask = 0.0;

   if(!GetMarketData(bid, ask))
      return;

   double balance =
      AccountInfoDouble(
         ACCOUNT_BALANCE
      );

   double equity =
      AccountInfoDouble(
         ACCOUNT_EQUITY
      );

   double margin =
      AccountInfoDouble(
         ACCOUNT_MARGIN
      );

   double free_margin =
      AccountInfoDouble(
         ACCOUNT_MARGIN_FREE
      );

   int open_positions =
      PositionsTotal();

   bool result =
      Raymond.SendTelemetry(
         InpSymbol,
         bid,
         ask,
         balance,
         equity,
         margin,
         free_margin,
         open_positions
      );

   if(!result)
   {
      Print(
         "RAYMOND TELEMETRY | Request failed | HTTP=",
         Raymond.LastHttpCode(),
         " | Error=",
         Raymond.LastError()
      );
   }
}

//+------------------------------------------------------------------+
//| Periodic status                                                  |
//+------------------------------------------------------------------+
void PrintStatusPeriodically()
{
   datetime now = TimeCurrent();

   // Print detailed status approximately every 60 seconds.
   if(
      g_last_status_log != 0 &&
      (now - g_last_status_log) < 60
   )
   {
      return;
   }

   g_last_status_log = now;

   Print("--------------------------------------------------");
   Print("RAYMOND PERIODIC STATUS");

   Print(
      "Symbol: ",
      InpSymbol
   );

   Print(
      "Timeframe: ",
      RaymondTimeframe()
   );

   Print(
      "Backend Configured: ",
      Raymond.IsConfigured()
      ? "YES"
      : "NO"
   );

   Print(
      "Emergency Stop: ",
      RaymondSafetyEngine.EmergencyStopActive()
      ? "ON"
      : "OFF"
   );

   Print(
      "Live Trading: HARD LOCKED OFF"
   );

   Print(
      "Execution Authorized: ",
      RaymondSafetyEngine.ExecutionAuthorized()
      ? "YES"
      : "NO"
   );

   Print(
      "Execution Mode: DEMO ONLY"
   );

   Print(
      "AI Mode: READ_ONLY"
   );

   Print(
      "AI Action: ",
      g_ai_action
   );

   PrintFormat(
      "AI Confidence: %.2f",
      g_ai_confidence
   );

   Print(
      "AI Execution: DISABLED"
   );

   Print(
      "Open Positions: ",
      PositionsTotal()
   );

   Print("--------------------------------------------------");
}

//+------------------------------------------------------------------+
