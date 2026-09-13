//+------------------------------------------------------------------+
//| RaymondBridge.mqh                                                |
//| RAYMOND v2.8 - MT5 ↔ FastAPI Bridge                              |
//|                                                                  |
//| STEP 11B-8: READ-ONLY TELEMETRY + AI DECISION BRIDGE             |
//|                                                                  |
//| This bridge ONLY communicates READ-ONLY information with         |
//| Raymond's backend.                                                |
//|                                                                  |
//| It does NOT:                                                       |
//| - place trades                                                     |
//| - modify trades                                                    |
//| - close trades                                                     |
//| - authorize live trading                                          |
//| - bypass Risk Engine                                               |
//| - bypass Emergency Stop                                            |
//+------------------------------------------------------------------+

#ifndef __RAYMOND_BRIDGE_MQH__
#define __RAYMOND_BRIDGE_MQH__

// -------------------------------------------------------------------
// Safety constants
// -------------------------------------------------------------------

#define RAYMOND_BRIDGE_VERSION "0.2.0"
#define RAYMOND_BRIDGE_MODE    "READ_ONLY"

// -------------------------------------------------------------------
// Bridge class
// -------------------------------------------------------------------

class RaymondBridge
{
private:

   string m_base_url;
   string m_telemetry_path;
   string m_decision_path;
   int    m_timeout_ms;

   bool   m_enabled;

   bool   m_last_success;
   int    m_last_http_code;
   string m_last_error;

   string m_last_ai_action;
   double m_last_ai_confidence;
   string m_last_ai_response;

   // ---------------------------------------------------------------
   // Escape JSON string characters
   // ---------------------------------------------------------------
   string JsonEscape(string value)
   {
      StringReplace(value, "\\", "\\\\");
      StringReplace(value, "\"", "\\\"");
      StringReplace(value, "\r", "\\r");
      StringReplace(value, "\n", "\\n");
      StringReplace(value, "\t", "\\t");

      return value;
   }

   // ---------------------------------------------------------------
   // Build telemetry URL
   // ---------------------------------------------------------------
   string BuildTelemetryUrl()
   {
      string base = m_base_url;

      while(StringLen(base) > 0 &&
            StringSubstr(base, StringLen(base) - 1, 1) == "/")
      {
         base = StringSubstr(base, 0, StringLen(base) - 1);
      }

      string path = m_telemetry_path;

      if(StringLen(path) == 0)
         path = "/api/mt5/telemetry";

      if(StringSubstr(path, 0, 1) != "/")
         path = "/" + path;

      return base + path;
   }

   // ---------------------------------------------------------------
   // Build AI decision URL
   // ---------------------------------------------------------------
   string BuildDecisionUrl(
      string symbol,
      string timeframe,
      int limit
   )
   {
      string base = m_base_url;

      while(StringLen(base) > 0 &&
            StringSubstr(base, StringLen(base) - 1, 1) == "/")
      {
         base = StringSubstr(base, 0, StringLen(base) - 1);
      }

      string path = m_decision_path;

      if(StringLen(path) == 0)
         path = "/api/mt5/decision";

      if(StringSubstr(path, 0, 1) != "/")
         path = "/" + path;

      string encoded_symbol = symbol;

      StringReplace(encoded_symbol, " ", "%20");

      string url =
         base +
         path +
         "?symbol=" +
         encoded_symbol +
         "&timeframe=" +
         timeframe +
         "&limit=" +
         IntegerToString(limit);

      return url;
   }

   // ---------------------------------------------------------------
   // Convert UTF-8 string to byte array
   // ---------------------------------------------------------------
   void StringToUtf8Bytes(
      string text,
      uchar &data[]
   )
   {
      ArrayResize(data, 0);

      if(StringLen(text) == 0)
         return;

      StringToCharArray(
         text,
         data,
         0,
         WHOLE_ARRAY,
         CP_UTF8
      );

      int size = ArraySize(data);

      if(size > 0 && data[size - 1] == 0)
         ArrayResize(data, size - 1);
   }

   // ---------------------------------------------------------------
   // Convert response bytes to string
   // ---------------------------------------------------------------
   string BytesToString(
      uchar &data[]
   )
   {
      int size = ArraySize(data);

      if(size <= 0)
         return "";

      return CharArrayToString(
         data,
         0,
         size,
         CP_UTF8
      );
   }

   // ---------------------------------------------------------------
   // Extract a JSON string field
   //
   // This is intentionally lightweight. We only consume the
   // read-only fields needed by the EA.
   // ---------------------------------------------------------------
   string ExtractJsonString(
      string json,
      string key,
      string default_value = ""
   )
   {
      string pattern = "\"" + key + "\"";

      int key_pos = StringFind(
         json,
         pattern
      );

      if(key_pos < 0)
         return default_value;

      int colon_pos = StringFind(
         json,
         ":",
         key_pos + StringLen(pattern)
      );

      if(colon_pos < 0)
         return default_value;

      int quote_start = StringFind(
         json,
         "\"",
         colon_pos + 1
      );

      if(quote_start < 0)
         return default_value;

      int quote_end = StringFind(
         json,
         "\"",
         quote_start + 1
      );

      if(quote_end < 0)
         return default_value;

      return StringSubstr(
         json,
         quote_start + 1,
         quote_end - quote_start - 1
      );
   }

   // ---------------------------------------------------------------
   // Extract a JSON numeric field
   // ---------------------------------------------------------------
   double ExtractJsonDouble(
      string json,
      string key,
      double default_value = 0.0
   )
   {
      string pattern = "\"" + key + "\"";

      int key_pos = StringFind(
         json,
         pattern
      );

      if(key_pos < 0)
         return default_value;

      int colon_pos = StringFind(
         json,
         ":",
         key_pos + StringLen(pattern)
      );

      if(colon_pos < 0)
         return default_value;

      int start = colon_pos + 1;

      while(
         start < StringLen(json) &&
         (
            StringSubstr(json, start, 1) == " " ||
            StringSubstr(json, start, 1) == "\t" ||
            StringSubstr(json, start, 1) == "\r" ||
            StringSubstr(json, start, 1) == "\n"
         )
      )
      {
         start++;
      }

      int end = start;

      while(end < StringLen(json))
      {
         string character =
            StringSubstr(json, end, 1);

         if(
            character == "," ||
            character == "}" ||
            character == "]" ||
            character == " "
         )
         {
            break;
         }

         end++;
      }

      string number_text =
         StringSubstr(
            json,
            start,
            end - start
         );

      if(StringLen(number_text) == 0)
         return default_value;

      return StringToDouble(
         number_text
      );
   }

public:

   // ---------------------------------------------------------------
   // Constructor
   // ---------------------------------------------------------------
   RaymondBridge()
   {
      m_base_url       = "";
      m_telemetry_path = "/api/mt5/telemetry";
      m_decision_path  = "/api/mt5/decision";
      m_timeout_ms     = 5000;

      m_enabled        = false;

      m_last_success   = false;
      m_last_http_code = 0;
      m_last_error     = "";

      m_last_ai_action      = "HOLD/WAIT";
      m_last_ai_confidence  = 0.0;
      m_last_ai_response    = "";
   }

   // ---------------------------------------------------------------
   // Configure bridge
   // ---------------------------------------------------------------
   void Configure(
      string base_url,
      string telemetry_path = "/api/mt5/telemetry",
      int timeout_ms = 5000
   )
   {
      m_base_url       = base_url;
      m_telemetry_path = telemetry_path;
      m_decision_path  = "/api/mt5/decision";
      m_timeout_ms     = timeout_ms;

      m_last_success   = false;
      m_last_http_code = 0;
      m_last_error     = "";

      m_last_ai_action     = "HOLD/WAIT";
      m_last_ai_confidence = 0.0;
      m_last_ai_response   = "";

      if(StringLen(m_base_url) > 0)
         m_enabled = true;
      else
         m_enabled = false;
   }

   // ---------------------------------------------------------------
   // Enable / disable bridge
   // ---------------------------------------------------------------
   void SetEnabled(bool enabled)
   {
      m_enabled = enabled;
   }

   // ---------------------------------------------------------------
   // Check whether bridge is configured
   // ---------------------------------------------------------------
   bool IsConfigured()
   {
      return (
         m_enabled &&
         StringLen(m_base_url) > 0
      );
   }

   // ---------------------------------------------------------------
   // Last request successful?
   // ---------------------------------------------------------------
   bool LastRequestSucceeded()
   {
      return m_last_success;
   }

   // ---------------------------------------------------------------
   // Last HTTP response code
   // ---------------------------------------------------------------
   int LastHttpCode()
   {
      return m_last_http_code;
   }

   // ---------------------------------------------------------------
   // Last error message
   // ---------------------------------------------------------------
   string LastError()
   {
      return m_last_error;
   }

   // ---------------------------------------------------------------
   // Last AI action
   // ---------------------------------------------------------------
   string LastAIAction()
   {
      return m_last_ai_action;
   }

   // ---------------------------------------------------------------
   // Last AI confidence
   // ---------------------------------------------------------------
   double LastAIConfidence()
   {
      return m_last_ai_confidence;
   }

   // ---------------------------------------------------------------
   // Last AI response
   // ---------------------------------------------------------------
   string LastAIResponse()
   {
      return m_last_ai_response;
   }

   // ---------------------------------------------------------------
   // Send telemetry to Raymond backend
   // ---------------------------------------------------------------
   bool SendTelemetry(
      string symbol,
      double bid,
      double ask,
      double balance,
      double equity,
      double margin,
      double free_margin,
      int open_positions
   )
   {
      m_last_success   = false;
      m_last_http_code = 0;
      m_last_error     = "";

      // -------------------------------------------------------------
      // HARD SAFETY CHECK
      // -------------------------------------------------------------
      // Telemetry remains read-only.
      // -------------------------------------------------------------

      if(!IsConfigured())
      {
         m_last_error =
            "Raymond bridge is not configured.";

         Print(
            "RAYMOND BRIDGE | ",
            m_last_error
         );

         return false;
      }

      // -------------------------------------------------------------
      // Build JSON payload
      // -------------------------------------------------------------

      string json = "{";

      json += "\"bridge_version\":\"";
      json += RAYMOND_BRIDGE_VERSION;
      json += "\",";

      json += "\"mode\":\"";
      json += RAYMOND_BRIDGE_MODE;
      json += "\",";

      json += "\"trading_enabled\":false,";

      json += "\"symbol\":\"";
      json += JsonEscape(symbol);
      json += "\",";

      json += "\"bid\":";
      json += DoubleToString(bid, 8);
      json += ",";

      json += "\"ask\":";
      json += DoubleToString(ask, 8);
      json += ",";

      json += "\"spread\":";
      json += DoubleToString(ask - bid, 8);
      json += ",";

      json += "\"balance\":";
      json += DoubleToString(balance, 2);
      json += ",";

      json += "\"equity\":";
      json += DoubleToString(equity, 2);
      json += ",";

      json += "\"margin\":";
      json += DoubleToString(margin, 2);
      json += ",";

      json += "\"free_margin\":";
      json += DoubleToString(free_margin, 2);
      json += ",";

      json += "\"open_positions\":";
      json += IntegerToString(open_positions);
      json += ",";

      json += "\"timestamp\":";
      json += IntegerToString(
         (int)TimeCurrent()
      );

      json += "}";

      uchar request_data[];

      StringToUtf8Bytes(
         json,
         request_data
      );

      uchar response_data[];
      string response_headers;

      string headers =
         "Content-Type: application/json\r\n"
         "Accept: application/json\r\n"
         "X-Raymond-Bridge: " +
         RAYMOND_BRIDGE_VERSION +
         "\r\n"
         "X-Raymond-Mode: READ_ONLY\r\n";

      string url =
         BuildTelemetryUrl();

      ResetLastError();

      int http_code = WebRequest(
         "POST",
         url,
         headers,
         m_timeout_ms,
         request_data,
         response_data,
         response_headers
      );

      m_last_http_code = http_code;

      if(http_code == -1)
      {
         int error_code = GetLastError();

         m_last_error =
            "WebRequest failed. MQL5 error=" +
            IntegerToString(error_code);

         Print(
            "RAYMOND BRIDGE | ",
            m_last_error
         );

         return false;
      }

      string response_text =
         BytesToString(response_data);

      if(http_code >= 200 && http_code < 300)
      {
         m_last_success = true;

         PrintFormat(
            "RAYMOND BRIDGE | Telemetry sent | HTTP=%d | Symbol=%s",
            http_code,
            symbol
         );

         if(StringLen(response_text) > 0)
         {
            Print(
               "RAYMOND BRIDGE | Response: ",
               response_text
            );
         }

         return true;
      }

      m_last_error =
         "Backend returned HTTP " +
         IntegerToString(http_code);

      Print(
         "RAYMOND BRIDGE | ",
         m_last_error
      );

      if(StringLen(response_text) > 0)
      {
         Print(
            "RAYMOND BRIDGE | Error response: ",
            response_text
         );
      }

      return false;
   }

   // ---------------------------------------------------------------
   // Request AI decision from Raymond backend
   // ---------------------------------------------------------------
   //
   // IMPORTANT:
   //
   // This method is READ ONLY.
   //
   // It asks the backend:
   //
   // MT5 market data
   //      ↓
   // indicators
   //      ↓
   // Raymond AI
   //      ↓
   // BUY / SELL / HOLD-WAIT
   //
   // It does NOT:
   //
   // - execute an order
   // - authorize execution
   // - modify a position
   // - close a position
   // - enable live trading
   //
   // ---------------------------------------------------------------

   bool RequestAIDecision(
      string symbol,
      string timeframe,
      int limit = 100
   )
   {
      m_last_success   = false;
      m_last_http_code = 0;
      m_last_error     = "";

      m_last_ai_action     = "HOLD/WAIT";
      m_last_ai_confidence = 0.0;
      m_last_ai_response   = "";

      // -------------------------------------------------------------
      // HARD SAFETY CHECK
      // -------------------------------------------------------------

      if(!IsConfigured())
      {
         m_last_error =
            "Raymond bridge is not configured.";

         Print(
            "RAYMOND AI | ",
            m_last_error
         );

         return false;
      }

      // Never permit an invalid candle request.
      if(limit < 60)
         limit = 60;

      if(limit > 500)
         limit = 500;

      string url =
         BuildDecisionUrl(
            symbol,
            timeframe,
            limit
         );

      uchar request_data[];
      uchar response_data[];
      string response_headers;

      // -------------------------------------------------------------
      // READ-ONLY HTTP GET
      // -------------------------------------------------------------
      //
      // Empty request body.
      // No broker command is sent.
      // -------------------------------------------------------------

      ArrayResize(
         request_data,
         0
      );

      string headers =
         "Accept: application/json\r\n"
         "X-Raymond-Bridge: " +
         RAYMOND_BRIDGE_VERSION +
         "\r\n"
         "X-Raymond-Mode: READ_ONLY\r\n";

      ResetLastError();

      int http_code = WebRequest(
         "GET",
         url,
         headers,
         m_timeout_ms,
         request_data,
         response_data,
         response_headers
      );

      m_last_http_code = http_code;

      if(http_code == -1)
      {
         int error_code = GetLastError();

         m_last_error =
            "AI decision WebRequest failed. MQL5 error=" +
            IntegerToString(error_code);

         Print(
            "RAYMOND AI | ",
            m_last_error
         );

         return false;
      }

      string response_text =
         BytesToString(response_data);

      m_last_ai_response =
         response_text;

      // -------------------------------------------------------------
      // HTTP failure
      // -------------------------------------------------------------

      if(http_code < 200 || http_code >= 300)
      {
         m_last_error =
            "AI decision backend returned HTTP " +
            IntegerToString(http_code);

         Print(
            "RAYMOND AI | ",
            m_last_error
         );

         if(StringLen(response_text) > 0)
         {
            Print(
               "RAYMOND AI | Response: ",
               response_text
            );
         }

         // Fail closed.
         m_last_ai_action =
            "HOLD/WAIT";

         m_last_ai_confidence =
            0.0;

         return false;
      }

      // -------------------------------------------------------------
      // Parse only the read-only decision fields.
      // -------------------------------------------------------------

      string direction =
         ExtractJsonString(
            response_text,
            "direction",
            ""
         );

      string action =
         ExtractJsonString(
            response_text,
            "action",
            ""
         );

      double confidence =
         ExtractJsonDouble(
            response_text,
            "confidence",
            0.0
         );

      // -------------------------------------------------------------
      // Normalize action.
      // -------------------------------------------------------------

      if(
         action != "BUY" &&
         action != "SELL" &&
         action != "HOLD/WAIT"
      )
      {
         if(
            direction == "BUY" ||
            direction == "SELL"
         )
         {
            action = direction;
         }
         else
         {
            action = "HOLD/WAIT";
         }
      }

      // -------------------------------------------------------------
      // SAFETY: only accept known AI actions.
      // -------------------------------------------------------------

      if(
         action != "BUY" &&
         action != "SELL" &&
         action != "HOLD/WAIT"
      )
      {
         action = "HOLD/WAIT";
         confidence = 0.0;
      }

      // -------------------------------------------------------------
      // SAFETY: confidence must be sane.
      // -------------------------------------------------------------

      if(
         confidence < 0.0 ||
         confidence > 100.0
      )
      {
         confidence = 0.0;
      }

      m_last_ai_action =
         action;

      m_last_ai_confidence =
         confidence;

      m_last_success = true;

      PrintFormat(
         "RAYMOND AI | READ_ONLY | Symbol=%s | TF=%s | Action=%s | Confidence=%.2f",
         symbol,
         timeframe,
         action,
         confidence
      );

      return true;
   }
};

#endif

//+------------------------------------------------------------------+
//| End of RaymondBridge.mqh                                         |
//+------------------------------------------------------------------+
