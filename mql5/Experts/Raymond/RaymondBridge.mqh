//+------------------------------------------------------------------+
//| RaymondBridge.mqh                                                |
//| RAYMOND v2.8 - MT5 <-> FastAPI Bridge                            |
//| STEP 11B-8: READ-ONLY TELEMETRY + AI DECISION BRIDGE             |
//+------------------------------------------------------------------+
//
// SAFETY CONTRACT
// ---------------
// This bridge is READ-ONLY.
//
// It may:
//   - send MT5 telemetry;
//   - request an AI decision;
//   - receive a BUY / SELL / HOLD-WAIT recommendation.
//
// It may NOT:
//   - place orders;
//   - modify orders;
//   - close positions;
//   - authorize trading;
//   - enable live trading;
//   - bypass the Risk Engine;
//   - bypass RaymondSafety;
//   - contact a broker for trade execution.
//
// AI output is informational only.
//
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

   int m_timeout_ms;

   bool m_enabled;

   bool m_last_success;
   int  m_last_http_code;
   string m_last_error;

   string m_last_ai_action;
   double m_last_ai_confidence;
   string m_last_ai_response;

   //+------------------------------------------------------------------+
   //| Escape JSON string                                               |
   //+------------------------------------------------------------------+
   string JsonEscape(string value)
   {
      StringReplace(value, "\\", "\\\\");
      StringReplace(value, "\"", "\\\"");
      StringReplace(value, "\r", "\\r");
      StringReplace(value, "\n", "\\n");
      StringReplace(value, "\t", "\\t");

      return value;
   }

   //+------------------------------------------------------------------+
   //| Remove trailing slash                                            |
   //+------------------------------------------------------------------+
   string NormalizeBaseUrl(string base)
   {
      while(
         StringLen(base) > 0 &&
         StringSubstr(
            base,
            StringLen(base) - 1,
            1
         ) == "/"
      )
      {
         base =
            StringSubstr(
               base,
               0,
               StringLen(base) - 1
            );
      }

      return base;
   }

   //+------------------------------------------------------------------+
   //| Normalize API path                                               |
   //+------------------------------------------------------------------+
   string NormalizePath(string path)
   {
      if(StringLen(path) == 0)
         return "/";

      if(StringSubstr(path, 0, 1) != "/")
         path = "/" + path;

      return path;
   }

   //+------------------------------------------------------------------+
   //| Build telemetry URL                                              |
   //+------------------------------------------------------------------+
   string BuildTelemetryUrl()
   {
      return
         NormalizeBaseUrl(m_base_url) +
         NormalizePath(m_telemetry_path);
   }

   //+------------------------------------------------------------------+
   //| Build AI decision URL                                            |
   //+------------------------------------------------------------------+
   string BuildDecisionUrl(
      string symbol,
      string timeframe,
      int limit
   )
   {
      string base =
         NormalizeBaseUrl(m_base_url);

      string path =
         NormalizePath(m_decision_path);

      string url =
         base +
         path +
         "?symbol=" +
         symbol +
         "&timeframe=" +
         timeframe +
         "&limit=" +
         IntegerToString(limit);

      return url;
   }

   //+------------------------------------------------------------------+
   //| Convert string to UTF-8 bytes                                    |
   //+------------------------------------------------------------------+
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

      int size =
         ArraySize(data);

      if(
         size > 0 &&
         data[size - 1] == 0
      )
      {
         ArrayResize(
            data,
            size - 1
         );
      }
   }

   //+------------------------------------------------------------------+
   //| Convert bytes to UTF-8 string                                    |
   //+------------------------------------------------------------------+
   string BytesToString(
      uchar &data[]
   )
   {
      int size =
         ArraySize(data);

      if(size <= 0)
         return "";

      return CharArrayToString(
         data,
         0,
         size,
         CP_UTF8
      );
   }

   //+------------------------------------------------------------------+
   //| Extract JSON string value                                        |
   //+------------------------------------------------------------------+
   bool ExtractJsonString(
      string json,
      string key,
      string &value
   )
   {
      value = "";

      string marker =
         "\"" +
         key +
         "\":";

      int position =
         StringFind(
            json,
            marker
         );

      if(position < 0)
         return false;

      position +=
         StringLen(marker);

      while(
         position < StringLen(json) &&
         (
            StringSubstr(
               json,
               position,
               1
            ) == " " ||
            StringSubstr(
               json,
               position,
               1
            ) == "\t"
         )
      )
      {
         position++;
      }

      if(
         position >= StringLen(json) ||
         StringSubstr(
            json,
            position,
            1
         ) != "\""
      )
      {
         return false;
      }

      position++;

      string result = "";

      bool escaped = false;

      for(
         int i = position;
         i < StringLen(json);
         i++
      )
      {
         string character =
            StringSubstr(
               json,
               i,
               1
            );

         if(escaped)
         {
            if(character == "n")
               result += "\n";
            else if(character == "r")
               result += "\r";
            else if(character == "t")
               result += "\t";
            else
               result += character;

            escaped = false;
            continue;
         }

         if(character == "\\")
         {
            escaped = true;
            continue;
         }

         if(character == "\"")
         {
            value = result;
            return true;
         }

         result += character;
      }

      return false;
   }

   //+------------------------------------------------------------------+
   //| Extract JSON numeric value                                       |
   //+------------------------------------------------------------------+
   bool ExtractJsonNumber(
      string json,
      string key,
      double &value
   )
   {
      value = 0.0;

      string marker =
         "\"" +
         key +
         "\":";

      int position =
         StringFind(
            json,
            marker
         );

      if(position < 0)
         return false;

      position +=
         StringLen(marker);

      while(
         position < StringLen(json) &&
         (
            StringSubstr(
               json,
               position,
               1
            ) == " " ||
            StringSubstr(
               json,
               position,
               1
            ) == "\t"
         )
      )
      {
         position++;
      }

      int end =
         position;

      while(end < StringLen(json))
      {
         string character =
            StringSubstr(
               json,
               end,
               1
            );

         if(
            character == "," ||
            character == "}" ||
            character == "\r" ||
            character == "\n" ||
            character == " "
         )
         {
            break;
         }

         end++;
      }

      if(end <= position)
         return false;

      string number_text =
         StringSubstr(
            json,
            position,
            end - position
         );

      value =
         StringToDouble(
            number_text
         );

      return true;
   }

   //+------------------------------------------------------------------+
   //| Store validated AI response                                     |
   //+------------------------------------------------------------------+
   bool ParseAIDecision(
      string response
   )
   {
      string action = "";

      double confidence = 0.0;

      bool action_found =
         ExtractJsonString(
            response,
            "action",
            action
         );

      if(!action_found)
      {
         ExtractJsonString(
            response,
            "direction",
            action
         );
      }

      bool confidence_found =
         ExtractJsonNumber(
            response,
            "confidence",
            confidence
         );

      if(!action_found)
      {
         m_last_ai_action =
            "HOLD/WAIT";

         m_last_ai_confidence =
            0.0;

         m_last_error =
            "AI response did not contain a valid action.";

         return false;
      }

      // ---------------------------------------------------------------
      // Normalize accepted actions.
      // ---------------------------------------------------------------

      if(
         action == "BUY" ||
         action == "buy"
      )
      {
         action = "BUY";
      }
      else if(
         action == "SELL" ||
         action == "sell"
      )
      {
         action = "SELL";
      }
      else if(
         action == "WAIT" ||
         action == "HOLD" ||
         action == "HOLD/WAIT" ||
         action == "wait" ||
         action == "hold"
      )
      {
         action = "HOLD/WAIT";
      }
      else
      {
         // ------------------------------------------------------------
         // Unknown action fails closed.
         // ------------------------------------------------------------

         m_last_ai_action =
            "HOLD/WAIT";

         m_last_ai_confidence =
            0.0;

         m_last_error =
            "Unknown AI action. Failed closed to HOLD/WAIT.";

         return false;
      }

      // ---------------------------------------------------------------
      // Confidence is optional, but if present it must be sane.
      // ---------------------------------------------------------------

      if(!confidence_found)
      {
         confidence = 0.0;
      }

      if(
         confidence < 0.0 ||
         confidence > 100.0
      )
      {
         m_last_ai_action =
            "HOLD/WAIT";

         m_last_ai_confidence =
            0.0;

         m_last_error =
            "Invalid AI confidence. Failed closed.";

         return false;
      }

      m_last_ai_action =
         action;

      m_last_ai_confidence =
         confidence;

      return true;
   }

public:

   //+------------------------------------------------------------------+
   //| Constructor                                                      |
   //+------------------------------------------------------------------+
   RaymondBridge()
   {
      m_base_url =
         "";

      m_telemetry_path =
         "/api/mt5/telemetry";

      m_decision_path =
         "/api/mt5/decision";

      m_timeout_ms =
         5000;

      m_enabled =
         false;

      m_last_success =
         false;

      m_last_http_code =
         0;

      m_last_error =
         "";

      m_last_ai_action =
         "HOLD/WAIT";

      m_last_ai_confidence =
         0.0;

      m_last_ai_response =
         "";
   }

   //+------------------------------------------------------------------+
   //| Configure bridge                                                 |
   //+------------------------------------------------------------------+
   void Configure(
      string base_url,
      string telemetry_path = "/api/mt5/telemetry",
      int timeout_ms = 5000
   )
   {
      m_base_url =
         NormalizeBaseUrl(
            base_url
         );

      m_telemetry_path =
         NormalizePath(
            telemetry_path
         );

      m_decision_path =
         "/api/mt5/decision";

      m_timeout_ms =
         timeout_ms;

      m_last_success =
         false;

      m_last_http_code =
         0;

      m_last_error =
         "";

      m_last_ai_action =
         "HOLD/WAIT";

      m_last_ai_confidence =
         0.0;

      m_last_ai_response =
         "";

      if(
         StringLen(m_base_url) > 0 &&
         m_timeout_ms >= 100
      )
      {
         m_enabled =
            true;
      }
      else
      {
         m_enabled =
            false;
      }
   }

   //+------------------------------------------------------------------+
   //| Enable / disable bridge                                          |
   //+------------------------------------------------------------------+
   void SetEnabled(
      bool enabled
   )
   {
      m_enabled =
         enabled;
   }

   //+------------------------------------------------------------------+
   //| Check configuration                                              |
   //+------------------------------------------------------------------+
   bool IsConfigured()
   {
      return(
         m_enabled &&
         StringLen(m_base_url) > 0 &&
         StringLen(m_telemetry_path) > 0 &&
         StringLen(m_decision_path) > 0
      );
   }

   //+------------------------------------------------------------------+
   //| Last request successful                                          |
   //+------------------------------------------------------------------+
   bool LastRequestSucceeded()
   {
      return m_last_success;
   }

   //+------------------------------------------------------------------+
   //| Last HTTP code                                                   |
   //+------------------------------------------------------------------+
   int LastHttpCode()
   {
      return m_last_http_code;
   }

   //+------------------------------------------------------------------+
   //| Last error                                                       |
   //+------------------------------------------------------------------+
   string LastError()
   {
      return m_last_error;
   }

   //+------------------------------------------------------------------+
   //| Last AI action                                                   |
   //+------------------------------------------------------------------+
   string LastAIAction()
   {
      return m_last_ai_action;
   }

   //+------------------------------------------------------------------+
   //| Last AI confidence                                               |
   //+------------------------------------------------------------------+
   double LastAIConfidence()
   {
      return m_last_ai_confidence;
   }

   //+------------------------------------------------------------------+
   //| Last raw AI response                                             |
   //+------------------------------------------------------------------+
   string LastAIResponse()
   {
      return m_last_ai_response;
   }

   //+------------------------------------------------------------------+
   //| Request READ-ONLY AI decision                                    |
   //+------------------------------------------------------------------+
   bool RequestAIDecision(
      string symbol,
      string timeframe,
      int limit = 100
   )
   {
      m_last_success =
         false;

      m_last_http_code =
         0;

      m_last_error =
         "";

      // ---------------------------------------------------------------
      // Always fail closed.
      // ---------------------------------------------------------------

      m_last_ai_action =
         "HOLD/WAIT";

      m_last_ai_confidence =
         0.0;

      m_last_ai_response =
         "";

      // ---------------------------------------------------------------
      // Configuration validation.
      // ---------------------------------------------------------------

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

      if(symbol == "")
      {
         m_last_error =
            "AI request symbol is empty.";

         return false;
      }

      if(timeframe == "")
      {
         m_last_error =
            "AI request timeframe is empty.";

         return false;
      }

      // ---------------------------------------------------------------
      // Clamp candle limit to backend safety range.
      // ---------------------------------------------------------------

      if(limit < 60)
         limit = 60;

      if(limit > 500)
         limit = 500;

      // ---------------------------------------------------------------
      // Build read-only URL.
      // ---------------------------------------------------------------

      string url =
         BuildDecisionUrl(
            symbol,
            timeframe,
            limit
         );

      uchar request_data[];

      ArrayResize(
         request_data,
         0
      );

      uchar response_data[];

      string response_headers =
         "";

      // ---------------------------------------------------------------
      // READ-ONLY HTTP headers.
      // ---------------------------------------------------------------

      string headers =
         "Accept: application/json\r\n"
         "X-Raymond-Bridge: " +
         RAYMOND_BRIDGE_VERSION +
         "\r\n"
         "X-Raymond-Mode: READ_ONLY\r\n"
         "X-Raymond-Execution: DISABLED\r\n";

      ResetLastError();

      // ---------------------------------------------------------------
      // GET only.
      //
      // This request asks for information.
      // It does not contain an order instruction.
      // ---------------------------------------------------------------

      int http_code =
         WebRequest(
            "GET",
            url,
            headers,
            m_timeout_ms,
            request_data,
            response_data,
            response_headers
         );

      m_last_http_code =
         http_code;

      if(http_code == -1)
      {
         int error_code =
            GetLastError();

         m_last_error =
            "AI WebRequest failed. MQL5 error=" +
            IntegerToString(
               error_code
            );

         Print(
            "RAYMOND AI | ",
            m_last_error
         );

         return false;
      }

      string response_text =
         BytesToString(
            response_data
         );

      m_last_ai_response =
         response_text;

      // ---------------------------------------------------------------
      // Require successful HTTP response.
      // ---------------------------------------------------------------

      if(
         http_code < 200 ||
         http_code >= 300
      )
      {
         m_last_error =
            "AI backend returned HTTP " +
            IntegerToString(
               http_code
            );

         Print(
            "RAYMOND AI | ",
            m_last_error
         );

         return false;
      }

      // ---------------------------------------------------------------
      // Parse and validate AI result.
      // ---------------------------------------------------------------

      if(
         !ParseAIDecision(
            response_text
         )
      )
      {
         Print(
            "RAYMOND AI | Response rejected | ",
            m_last_error
         );

         return false;
      }

      m_last_success =
         true;

      PrintFormat(
         "RAYMOND AI | READ_ONLY decision received | Action=%s | Confidence=%.2f | HTTP=%d",
         m_last_ai_action,
         m_last_ai_confidence,
         http_code
      );

      return true;
   }

   //+------------------------------------------------------------------+
   //| Send telemetry                                                   |
   //+------------------------------------------------------------------+
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
      m_last_success =
         false;

      m_last_http_code =
         0;

      m_last_error =
         "";

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

      // ---------------------------------------------------------------
      // Build read-only telemetry JSON.
      // ---------------------------------------------------------------

      string json =
         "{";

      json +=
         "\"bridge_version\":\"";

      json +=
         RAYMOND_BRIDGE_VERSION;

      json +=
         "\",";

      json +=
         "\"mode\":\"";

      json +=
         RAYMOND_BRIDGE_MODE;

      json +=
         "\",";

      json +=
         "\"trading_enabled\":false,";

      json +=
         "\"live_trading_enabled\":false,";

      json +=
         "\"execution_authorized\":false,";

      json +=
         "\"symbol\":\"";

      json +=
         JsonEscape(symbol);

      json +=
         "\",";

      json +=
         "\"bid\":";

      json +=
         DoubleToString(
            bid,
            8
         );

      json +=
         ",";

      json +=
         "\"ask\":";

      json +=
         DoubleToString(
            ask,
            8
         );

      json +=
         ",";

      json +=
         "\"spread\":";

      json +=
         DoubleToString(
            ask - bid,
            8
         );

      json +=
         ",";

      json +=
         "\"balance\":";

      json +=
         DoubleToString(
            balance,
            2
         );

      json +=
         ",";

      json +=
         "\"equity\":";

      json +=
         DoubleToString(
            equity,
            2
         );

      json +=
         ",";

      json +=
         "\"margin\":";

      json +=
         DoubleToString(
            margin,
            2
         );

      json +=
         ",";

      json +=
         "\"free_margin\":";

      json +=
         DoubleToString(
            free_margin,
            2
         );

      json +=
         ",";

      json +=
         "\"open_positions\":";

      json +=
         IntegerToString(
            open_positions
         );

      json +=
         ",";

      json +=
         "\"timestamp\":";

      json +=
         IntegerToString(
            (int)TimeCurrent()
         );

      json +=
         "}";

      uchar request_data[];

      StringToUtf8Bytes(
         json,
         request_data
      );

      uchar response_data[];

      string response_headers =
         "";

      string headers =
         "Content-Type: application/json\r\n"
         "Accept: application/json\r\n"
         "X-Raymond-Bridge: " +
         RAYMOND_BRIDGE_VERSION +
         "\r\n"
         "X-Raymond-Mode: READ_ONLY\r\n"
         "X-Raymond-Execution: DISABLED\r\n";

      string url =
         BuildTelemetryUrl();

      ResetLastError();

      int http_code =
         WebRequest(
            "POST",
            url,
            headers,
            m_timeout_ms,
            request_data,
            response_data,
            response_headers
         );

      m_last_http_code =
         http_code;

      if(http_code == -1)
      {
         int error_code =
            GetLastError();

         m_last_error =
            "Telemetry WebRequest failed. MQL5 error=" +
            IntegerToString(
               error_code
            );

         Print(
            "RAYMOND BRIDGE | ",
            m_last_error
         );

         return false;
      }

      string response_text =
         BytesToString(
            response_data
         );

      if(
         http_code >= 200 &&
         http_code < 300
      )
      {
         m_last_success =
            true;

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
         "Telemetry backend returned HTTP " +
         IntegerToString(
            http_code
         );

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
};

#endif

//+------------------------------------------------------------------+
//| END RaymondBridge.mqh                                             |
//+------------------------------------------------------------------+
