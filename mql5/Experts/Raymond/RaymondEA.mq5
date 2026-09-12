//+------------------------------------------------------------------+
//| RaymondEA.mq5                                                    |
//| RAYMOND v2.8 - MT5 Trading Bridge                                |
//| STEP 11B-7: SAFETY + DEMO EXECUTION + POSITION MANAGEMENT        |
//+------------------------------------------------------------------+
#property strict
#property version   "0.7.1"
#property description "RAYMOND v2.8 broker-agnostic MT5 bridge"
#property description "Telemetry, safety, DEMO execution and position protection"
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

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("==================================================");
   Print("RAYMOND v2.8 MT5 EA");
   Print("STEP 11B-7");
   Print("MODE: DEMO / SAFETY / POSITION MANAGEMENT");
   Print("LIVE TRADING: HARD LOCKED OFF");
   Print("Symbol: ", InpSymbol);
   Print("Timeframe: ", EnumToString(InpTimeframe));
   Print("==================================================");

   // ---------------------------------------------------------------
   // ABSOLUTE LIVE-TRADING SAFETY CHECK
   // ---------------------------------------------------------------

   if(TRADING_ENABLED)
   {
      Print("FATAL SAFETY ERROR: TRADING_ENABLED must remain FALSE.");
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
      Print("ERROR: Backend timeout must be at least 100 ms.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpMaxSpread <= 0.0)
   {
      Print("ERROR: Maximum spread must be greater than zero.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpMaxDecisionAgeSeconds < 1)
   {
      Print("ERROR: Maximum decision age must be greater than zero.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpDeviationPoints < 1)
   {
      Print("ERROR: Deviation must be greater than zero.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpBreakEvenTrigger < 0.0)
   {
      Print("ERROR: Break-even trigger cannot be negative.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpProfitLockTrigger < 0.0)
   {
      Print("ERROR: Profit-lock trigger cannot be negative.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpProfitLockDistance <= 0.0)
   {
      Print("ERROR: Profit-lock distance must be greater than zero.");
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
   // TELEMETRY BRIDGE
   // ---------------------------------------------------------------

   Raymond.Configure(
      InpBackendUrl,
      InpTelemetryPath,
      InpBackendTimeoutMs
   );

   Raymond.SetEnabled(true);

   if(Raymond.IsConfigured())
   {
      Print("RAYMOND BRIDGE: Backend URL configured.");
   }
   else
   {
      Print("RAYMOND BRIDGE: Backend URL not configured.");
      Print("Telemetry will remain inactive until a backend URL is supplied.");
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

   // Emergency stop remains ON at this stage.
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

   Print("--------------------------------------------------");
   Print("RAYMOND EA initialized successfully.");
   Print("LIVE TRADING IS HARD-LOCKED OFF.");
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

   // Absolute safety lock.
   if(TRADING_ENABLED)
   {
      Print(
         "RAYMOND SAFETY ERROR: TRADING_ENABLED became TRUE."
      );

      return;
   }

   // Market monitoring.
   MonitorMarket();

   // Account monitoring.
   MonitorAccount();

   // Position monitoring.
   MonitorPositions();

   // Position protection.
   //
   // The position manager has its emergency stop ON by default.
   // Therefore this cannot modify positions at this stage.
   RaymondPositionManagerEngine.MonitorAllPositions();

   // Backend telemetry.
   SendTelemetry();

   // Periodic status.
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
      "Open Positions: ",
      PositionsTotal()
   );

   Print("--------------------------------------------------");
}

//+------------------------------------------------------------------+
