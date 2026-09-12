//+------------------------------------------------------------------+
//| RaymondEA.mq5                                                    |
//| RAYMOND v2.8 - MT5 Telemetry Bridge                             |
//| STEP 11B-3: READ-ONLY MT5 -> RAYMOND TELEMETRY                  |
//+------------------------------------------------------------------+

#property strict
#property version   "0.2.0"
#property description "RAYMOND v2.8 read-only MT5 telemetry bridge"

#include "RaymondBridge.mqh"

input string InpSymbol = "XAUUSD";
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M15;
input int InpTimerSeconds = 5;

// HARD SAFETY LOCK.
// This EA cannot trade in Step 11B-3.
bool TRADING_ENABLED = false;

RaymondBridge Raymond;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("==================================================");
   Print("RAYMOND v2.8 EA");
   Print("STEP 11B-3");
   Print("MODE: READ-ONLY TELEMETRY");
   Print("TRADING ENABLED: FALSE");
   Print("Symbol: ", InpSymbol);
   Print("Timeframe: ", EnumToString(InpTimeframe));
   Print("==================================================");

   if(!SymbolSelect(InpSymbol, true))
   {
      Print("ERROR: Could not select symbol ", InpSymbol);
      return INIT_FAILED;
   }

   // Backend URL remains blank until Raymond's backend
   // has been deployed to a reachable address.
   string backend_url = "";

   Raymond.Configure(
      backend_url,
      "/api/mt5/telemetry",
      5000
   );

   if(!Raymond.IsConfigured())
   {
      Print("RAYMOND BRIDGE: Backend URL not configured.");
      Print("EA remains READ-ONLY.");
   }

   if(InpTimerSeconds < 1)
   {
      Print("ERROR: Timer must be at least 1 second.");
      return INIT_PARAMETERS_INCORRECT;
   }

   EventSetTimer(InpTimerSeconds);

   Print("RAYMOND EA initialized successfully.");

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();

   Print("RAYMOND v2.8 EA stopped.");
   Print("Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Tick handler                                                     |
//+------------------------------------------------------------------+
void OnTick()
{
   // Intentionally empty.
   // Telemetry is handled by the timer.
}

//+------------------------------------------------------------------+
//| Timer                                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   MonitorMarket();
   MonitorAccount();
   MonitorPositions();
   SendTelemetry();
}

//+------------------------------------------------------------------+
//| Get market data                                                  |
//+------------------------------------------------------------------+
bool GetMarketData(
   double &bid,
   double &ask
)
{
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
}

//+------------------------------------------------------------------+
//| Account monitoring                                               |
//+------------------------------------------------------------------+
void MonitorAccount()
{
   double balance =
      AccountInfoDouble(ACCOUNT_BALANCE);

   double equity =
      AccountInfoDouble(ACCOUNT_EQUITY);

   double margin =
      AccountInfoDouble(ACCOUNT_MARGIN);

   double free_margin =
      AccountInfoDouble(ACCOUNT_MARGIN_FREE);

   PrintFormat(
      "RAYMOND ACCOUNT | Balance=%.2f | Equity=%.2f | Margin=%.2f | FreeMargin=%.2f",
      balance,
      equity,
      margin,
      free_margin
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
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0)
         continue;

      string symbol =
         PositionGetString(POSITION_SYMBOL);

      long type =
         PositionGetInteger(POSITION_TYPE);

      double volume =
         PositionGetDouble(POSITION_VOLUME);

      double openPrice =
         PositionGetDouble(POSITION_PRICE_OPEN);

      double sl =
         PositionGetDouble(POSITION_SL);

      double tp =
         PositionGetDouble(POSITION_TP);

      double profit =
         PositionGetDouble(POSITION_PROFIT);

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
   double bid = 0.0;
   double ask = 0.0;

   if(!GetMarketData(bid, ask))
      return;

   double balance =
      AccountInfoDouble(ACCOUNT_BALANCE);

   double equity =
      AccountInfoDouble(ACCOUNT_EQUITY);

   double margin =
      AccountInfoDouble(ACCOUNT_MARGIN);

   double freeMargin =
      AccountInfoDouble(ACCOUNT_MARGIN_FREE);

   int openPositions =
      PositionsTotal();

   // HARD SAFETY CHECK
   if(TRADING_ENABLED)
   {
      Print(
         "RAYMOND SAFETY ERROR: Trading flag must remain FALSE."
      );

      return;
   }

   if(!Raymond.IsConfigured())
      return;

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
}

//+------------------------------------------------------------------+
//| Safety guard                                                     |
//+------------------------------------------------------------------+
bool IsTradingAllowed()
{
   // Permanently false for Step 11B-3.
   return false;
}

//+------------------------------------------------------------------+
//| End of Step 11B-3                                                |
//+------------------------------------------------------------------+
