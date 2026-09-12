//+------------------------------------------------------------------+
//| RaymondEA.mq5                                                    |
//| RAYMOND v2.8 - MT5 Bridge                                        |
//|                                                                  |
//| STEP 11B-1: READ-ONLY FOUNDATION                                 |
//|                                                                  |
//| This EA does NOT place, modify, or close trades.                 |
//| It only monitors MT5/XAUUSD state and prepares the bridge        |
//| architecture for Raymond's AI/risk system.                      |
//+------------------------------------------------------------------+

#property strict
#property version   "0.1.0"
#property description "RAYMOND v2.8 read-only MT5 bridge"

input string InpSymbol = "XAUUSD";
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M15;
input int InpTimerSeconds = 5;

// Safety: this version is permanently read-only.
bool TRADING_ENABLED = false;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("==================================================");
   Print("RAYMOND v2.8 EA starting");
   Print("MODE: READ-ONLY");
   Print("TRADING ENABLED: FALSE");
   Print("Symbol: ", InpSymbol);
   Print("Timeframe: ", EnumToString(InpTimeframe));
   Print("==================================================");

   if(!SymbolSelect(InpSymbol, true))
   {
      Print("ERROR: Could not select symbol ", InpSymbol);
      return INIT_FAILED;
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
   // Intentionally empty in Step 11B-1.
   // Market monitoring is performed on the timer.
}

//+------------------------------------------------------------------+
//| Timer                                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   MonitorMarket();
   MonitorAccount();
   MonitorPositions();
}

//+------------------------------------------------------------------+
//| Market monitoring                                                |
//+------------------------------------------------------------------+
void MonitorMarket()
{
   MqlTick tick;

   if(!SymbolInfoTick(InpSymbol, tick))
   {
      Print("WARNING: Unable to read tick for ", InpSymbol);
      return;
   }

   double spread = tick.ask - tick.bid;

   PrintFormat(
      "RAYMOND MARKET | %s | Bid=%.2f | Ask=%.2f | Spread=%.2f",
      InpSymbol,
      tick.bid,
      tick.ask,
      spread
   );
}

//+------------------------------------------------------------------+
//| Account monitoring                                               |
//+------------------------------------------------------------------+
void MonitorAccount()
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin  = AccountInfoDouble(ACCOUNT_MARGIN);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);

   PrintFormat(
      "RAYMOND ACCOUNT | Balance=%.2f | Equity=%.2f | Margin=%.2f | FreeMargin=%.2f",
      balance,
      equity,
      margin,
      freeMargin
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

      string symbol = PositionGetString(POSITION_SYMBOL);
      long type = PositionGetInteger(POSITION_TYPE);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double profit = PositionGetDouble(POSITION_PROFIT);

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
//| Safety guard                                                      |
//+------------------------------------------------------------------+
bool IsTradingAllowed()
{
   // This must remain false until the complete Raymond
   // strategy/risk/execution architecture has been tested.
   return TRADING_ENABLED;
}

//+------------------------------------------------------------------+
//| End of Step 11B-1                                                |
//+------------------------------------------------------------------+
