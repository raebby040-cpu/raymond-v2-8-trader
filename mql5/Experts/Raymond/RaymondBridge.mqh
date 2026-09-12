//+------------------------------------------------------------------+
//| RaymondBridge.mqh                                                |
//| RAYMOND v2.8 - MT5 ↔ FastAPI Bridge                              |
//|                                                                  |
//| STEP 11B-2: READ-ONLY COMMUNICATION FOUNDATION                   |
//|                                                                  |
//| This bridge ONLY sends telemetry to Raymond's backend.           |
//| It does NOT place, modify, or close trades.                      |
//+------------------------------------------------------------------+

#ifndef __RAYMOND_BRIDGE_MQH__
#define __RAYMOND_BRIDGE_MQH__

// -------------------------------------------------------------------
// Safety constants
// -------------------------------------------------------------------

#define RAYMOND_BRIDGE_VERSION "0.1.0"
#define RAYMOND_BRIDGE_MODE    "READ_ONLY"

// -------------------------------------------------------------------
// Bridge class
// -------------------------------------------------------------------

class RaymondBridge
{
private:

   string m_base_url;
   string m_telemetry_path;
   int    m_timeout_ms;

   bool   m_enabled;
   bool   m_last_success;
   int    m_last_http_code;
   string m_last_error;

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
   // Build HTTP URL
   // ---------------------------------------------------------------
   string BuildUrl()
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
   // Convert UTF-8 string to byte array
   // ---------------------------------------------------------------
   void StringToUtf8Bytes(string text, uchar &data[])
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

      // Remove terminating zero byte.
      int size = ArraySize(data);

      if(size > 0 && data[size - 1] == 0)
         ArrayResize(data, size - 1);
   }

   // ---------------------------------------------------------------
   // Convert response bytes to string
   // ---------------------------------------------------------------
   string BytesToString(uchar &data[])
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

public:

   // ---------------------------------------------------------------
   // Constructor
   // ---------------------------------------------------------------
   RaymondBridge()
   {
      m_base_url       = "";
      m_telemetry_path = "/api/mt5/telemetry";
      m_timeout_ms     = 5000;

      m_enabled        = false;
      m_last_success   = false;
      m_last_http_code = 0;
      m_last_error     = "";
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
      m_timeout_ms     = timeout_ms;

      m_last_success   = false;
      m_last_http_code = 0;
      m_last_error     = "";

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
         StringLen(m_base_url) > 0 &&
         StringLen(m_telemetry_path) > 0
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
      // Step 11B-2 is telemetry only.
      // There is intentionally no trading method here.
      // -------------------------------------------------------------

      if(!IsConfigured())
      {
         m_last_error = "Raymond bridge is not configured.";
         Print("RAYMOND BRIDGE | ", m_last_error);

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
      json += IntegerToString((int)TimeCurrent());

      json += "}";

      // -------------------------------------------------------------
      // Convert payload to UTF-8
      // -------------------------------------------------------------

      uchar request_data[];

      StringToUtf8Bytes(
         json,
         request_data
      );

      uchar response_data[];
      string response_headers;

      // -------------------------------------------------------------
      // HTTP headers
      // -------------------------------------------------------------

      string headers =
         "Content-Type: application/json\r\n"
         "Accept: application/json\r\n"
         "X-Raymond-Bridge: " + RAYMOND_BRIDGE_VERSION + "\r\n"
         "X-Raymond-Mode: READ_ONLY\r\n";

      string url = BuildUrl();

      ResetLastError();

      // -------------------------------------------------------------
      // READ-ONLY HTTP POST
      // -------------------------------------------------------------

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

      // -------------------------------------------------------------
      // HTTP success
      // -------------------------------------------------------------

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

      // -------------------------------------------------------------
      // HTTP failure
      // -------------------------------------------------------------

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
};

#endif

//+------------------------------------------------------------------+
//| End of RaymondBridge.mqh                                         |
//+------------------------------------------------------------------+
