//+------------------------------------------------------------------+
//| RaymondEA.mq5                                                    |
//| RAYMOND v2.8 - MT5 Trading Bridge                                |
//| STEP 11B-7: SAFETY + DEMO EXECUTION + POSITION MANAGEMENT        |
//+------------------------------------------------------------------+
#property strict
#property version   "0.7.0"
#property description "RAYMOND v2.8 broker-agnostic MT5 bridge"
#property description "Telemetry, safety, DEMO execution and position protection"
#property description "LIVE TRADING HARD-LOCKED OFF"

// -------------------------------------------------------------------
// RAYMOND MODULES
// -------------------------------------------------------------------

#include "RaymondBridge.mqh"
#include "RaymondSafety.mqh"
#include "RaymondExecution.mqh"
#include "RaymondPositionManager.mqh"

// -------------------------------------------------------------------
// INPUTS
// -------------------------------------------------------------------

// Main market symbol.
// Broker-specific symbols can be entered here, for example:
// XAUUSD, XAUUSDm, GOLD, etc.
input string InpSymbol = "XAUUSD";

// Analysis / monitoring timeframe.
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M15;

// Main monitoring interval.
input int InpTimerSeconds = 5;

// Raymond backend URL.
// Example:
// http://YOUR_SERVER:8000
//
// Leave blank until the backend is deployed and reachable.
input string InpBackendUrl = "";

// Backend telemetry endpoint.
input string InpTelemetryPath = "/api/mt5/telemetry";

// Backend request timeout.
input int InpBackendTimeoutMs = 5000;

// -------------------------------------------------------------------
// SAFETY SETTINGS
// -------------------------------------------------------------------

// Maximum accepted spread in PRICE units.
//
// Example:
// XAUUSD with bid 3500.00 and ask 3500.50
// spread = 0.50
//
// This should be tuned after testing the selected broker.
input double InpMaxSpread = 1.00;

// Maximum age of an AI decision in seconds.
input int InpMaxDecisionAgeSeconds = 30;

// -------------------------------------------------------------------
// DEMO EXECUTION SETTINGS
// -------------------------------------------------------------------

// Slippage/deviation in MT5 points.
input int InpDeviationPoints = 50;

// -------------------------------------------------------------------
// POSITION PROTECTION SETTINGS
// -------------------------------------------------------------------

// Profit amount at which break-even protection can be attempted.
//
// IMPORTANT:
// These are currently account-profit values because the position
// manager evaluates POSITION_PROFIT.
input double InpBreakEvenTrigger = 2.00;

// Amount added above/below entry when moving to break-even.
input double InpBreakEvenOffset = 0.20;

// Profit amount at which profit locking can be attempted.
input double InpProfitLockTrigger = 4.00;

// Distance from current market price used for profit locking.
input double InpProfitLockDistance = 1.00;

// -------------------------------------------------------------------
// ABSOLUTE GLOBAL SAFETY LOCK
// -------------------------------------------------------------------
//
// This variable MUST remain false in this stage.
//
// It is deliberately hard-coded rather than exposed as an input.
// No external parameter can turn live trading on.
//
bool TRADING_ENABLED = false;

// -------------------------------------------------------------------
// RAYMOND MODULE INSTANCES
// -------------------------------------------------------------------

RaymondBridge Raymond;

RaymondSafety RaymondSafetyEngine;

RaymondExecution RaymondExecutionEngine;

RaymondPositionManager RaymondPositionManagerEngine;

// -------------------------------------------------------------------
// RUNTIME STATE
// -------------------------------------------------------------------

datetime g_last_status_log = 0;

bool g_initialized = false;

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
   // HARD SAFETY CHECK
   // ---------------------------------------------------------------

   if(TRADING_ENABLED)
   {
      Print("FATAL SAFETY ERROR: TRADING_ENABLED must be FALSE.");
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
      Print("ERROR: Backend timeout is too small.");
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
      Print("ERROR: Deviation points must be greater than zero.");
      return INIT_PARAMETERS_INCORRECT;
   }

   // ---------------------------------------------------------------
   // SYMBOL
   // ---------------------------------------------------------------

   if(!SymbolSelect(InpSymbol, true))
   {
      Print(
         "ERROR: Could not select symbol ",
         InpSymbol
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

   if(!Raymond.IsConfigured())
   {
      Print(
         "RAYMOND BRIDGE: Backend URL is not configured."
      );

      Print(
         "Telemetry will remain disabled until a valid backend URL is supplied."
      );
   }
   else
   {
      Print(
         "RAYMOND BRIDGE: Backend URL configured."
      );
   }

   // ---------------------------------------------------------------
   // SAFETY ENGINE
   // ---------------------------------------------------------------

   RaymondSafetyEngine.Configure(
      InpMaxSpread,
      InpMaxDecisionAgeSeconds
   );

   // Emergency stop is deliberately ON at startup.
   RaymondSafetyEngine.SetEmergencyStop(true);

   // These methods are hard-locked OFF internally by the safety module.
   RaymondSafetyEngine.SetLiveTradingEnabled(false);
   RaymondSafetyEngine.SetExecutionAuthorized(false);

   // ---------------------------------------------------------------
   // DEMO EXECUTION ENGINE
   // ---------------------------------------------------------------

   RaymondExecutionEngine.Configure(
      InpMaxSpread,
      InpDeviationPoints
   );

   // The execution module itself hard-locks live trading OFF.
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

   // Emergency stop remains ON until a later deliberate control stage.
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

   Print("--------------------------------------------------");
   Print("RAYMOND SAFETY STATUS");
   Print(
      "Safety Emergency Stop: ",
      RaymondSafetyEngine.EmergencyStopActive()
      ? "ON"
      : "OFF"
   );

   Print(
      "Safety Live Trading: ",
      RaymondSafetyEngine.LiveTradingEnabled()
      ? "ON"
      : "OFF"
   );

   Print(
      "Safety Execution: ",
      RaymondSafetyEngine.ExecutionAuthorized()
      ? "AUTHORIZED"
      : "OFF"
   );

   Print(
      "Execution Demo Only: ",
      RaymondExecutionEngine.DemoOnly()
      ? "YES"
      : "NO"
   );

   Print(
      "Position Manager Demo Only: ",
      RaymondPositionManagerEngine.DemoOnly()
      ? "YES"
      : "NO"
   );

   Print("--------------------------------------------------");

   Print(
      "RAYMOND EA initialized successfully."
   );

   Print(
      "NO LIVE TRADING IS AVAILABLE IN THIS BUILD."
   );

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
   Print("Live trading remained disabled.");
   Print("==================================================");
}

//+------------------------------------------------------------------+
//| Tick handler                                                     |
//+------------------------------------------------------------------+
void OnTick()
{
   // Deliberately empty.
   //
   // Raymond uses the timer so that monitoring is controlled
   // and does not execute repeatedly on every incoming tick.
}

//+------------------------------------------------------------------+
//| Timer                                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(!g_initialized)
      return;

   // ---------------------------------------------------------------
   // ABSOLUTE SAFETY CHECK
   // ---------------------------------------------------------------

   if(TRADING_ENABLED)
   {
      Print(
         "RAYMOND SAFETY ERROR: Trading flag became TRUE."
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
   // OPEN POSITIONS
   // ---------------------------------------------------------------

   MonitorPositions();

   // ---------------------------------------------------------------
   // POSITION PROTECTION
   // ---------------------------------------------------------------
   //
   // The manager itself checks:
   // - DEMO account
   // - emergency stop
   // - DEMO_ONLY
   // - live trading lock
   //
   // Since emergency stop is ON at this stage, no modification
   // will occur.
   //
   RaymondPositionManagerEngine.MonitorAllPositions();

   // ---------------------------------------------------------------
   // TELEMETRY
   // ---------------------------------------------------------------

   SendTelemetry();

   // ---------------------------------------------------------------
   // PERIODIC STATUS
   // ---------------------------------------------------------------

   PrintStatusPeriodically();
}

//+------------------------------------------------------------------+
//| Get market data                                                  |
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
         "RAYMOND MARKET | Unable to read tick for ",
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

   // Run the same quote through Raymond's safety layer.
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

      double openPrice =
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
         openPrice,
         sl,
         tp,
         profit
      );
   }
}

//+------------------------------------------------------------------+
//| Send telemetry                                                   |
//+------------------------------------------------------------------+
void SendTelemetry()
{
   // ---------------------------------------------------------------
   // ABSOLUTE SAFETY CHECK
   // ---------------------------------------------------------------

   if(TRADING_ENABLED)
   {
      Print(
         "RAYMOND SAFETY ERROR: Telemetry blocked because trading flag is TRUE."
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

   double freeMargin =
      AccountInfoDouble(
         ACCOUNT_MARGIN_FREE
      );

   int openPositions =
      PositionsTotal();

   bool success =
      Raymond.SendTelemetry(
         InpSymbol,
         bid,
         ask,
         balance,
         equity,
         margin,
         freeMargin,
         openPositions
      );

   if(!success)
   {
      Print(
         "RAYMOND TELEMETRY | Send failed | HTTP=",
         Raymond.LastHttpCode(),
         " | Error=",
         Raymond.LastError()
      );
   }
   else
   {
      Print(
         "RAYMOND TELEMETRY | Successfully sent."
      );
   }
}

//+------------------------------------------------------------------+
//| Periodic status logging                                          |
//+------------------------------------------------------------------+
void PrintStatusPeriodically()
{
   datetime now_time =
      TimeCurrent();

   // Log detailed safety state approximately every 60 seconds.
   if(
      g_last_status_log != 0 &&
      (now_time - g_last_status_log) < 60
   )
   {
      return;
   }

   g_last_status_log =
      now_time;

   Print("==================================================");
   Print("RAYMOND STATUS");

   Print(
      "Symbol: ",
      InpSymbol
   );

   Print(
      "Timeframe: ",
      EnumToString(InpTimeframe)
   );

   Print(
      "Backend configured: ",
      Raymond.IsConfigured()
      ? "YES"
      : "NO"
   );

   Print(
      "Telemetry mode: READ_ONLY"
   );

   Print(
      "Live trading: OFF"
   );

   Print(
      "Execution authorized: OFF"
   );

   Print(
      "Demo execution only: ",
      RaymondExecutionEngine.DemoOnly()
      ? "YES"
      : "NO"
   );

   Print(
      "Emergency stop: ",
      RaymondSafetyEngine.EmergencyStopActive()
      ? "ON"
      : "OFF"
   );

   Print(
      "Position manager emergency stop: ",
      RaymondPositionManagerEngine.EmergencyStopActive()
      ? "ON"
      : "OFF"
   );

   Print(
      "==================================================");
}

//+------------------------------------------------------------------+
//| Trading permission guard                                         |
//+------------------------------------------------------------------+
bool IsTradingAllowed()
{
   // ---------------------------------------------------------------
   // ABSOLUTE LOCK
   // ---------------------------------------------------------------
   //
   // This remains FALSE during the current development stage.
   //
   // Even if another module is accidentally changed, this EA
   // cannot use this function to authorize live trading.
   //

   return false;
}

//+------------------------------------------------------------------+
//| End of RaymondEA.mq5                                             |
//+------------------------------------------------------------------+



