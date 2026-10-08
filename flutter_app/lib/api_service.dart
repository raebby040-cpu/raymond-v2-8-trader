import 'package:dio/dio.dart';

class ApiService {
  ApiService({String? baseUrl})
      : _dio = Dio(
          BaseOptions(
            baseUrl: baseUrl ??
                'https://raymond-v2-8-trader.onrender.com',
            connectTimeout:
                const Duration(seconds: 15),
            receiveTimeout:
                const Duration(seconds: 20),
            sendTimeout:
                const Duration(seconds: 20),
            headers: {
              'Accept': 'application/json',
              'Content-Type':
                  'application/json',
            },
          ),
        );

  final Dio _dio;

  // ============================================================
  // HEALTH
  // ============================================================

  Future<Map<String, dynamic>> health() async {
    final response =
        await _dio.get('/health');

    return _asMap(response.data);
  }

  // ============================================================
  // DEMO
  // ============================================================

  Future<Map<String, dynamic>> demoStatus() async {
    final response =
        await _dio.get('/api/demo/status');

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      demoPerformance() async {
    final response =
        await _dio.get(
      '/api/demo/performance',
    );

    return _asMap(response.data);
  }

  Future<List<Map<String, dynamic>>>
      demoTrades() async {
    final response =
        await _dio.get(
      '/api/demo/trades',
    );

    return _asTradeList(
      response.data,
    );
  }

  Future<Map<String, dynamic>>
      openDemoTrade({
    required String symbol,
    required String direction,
    required double entryPrice,
    required double quantity,
    double? stopLoss,
    double? takeProfit,
  }) async {
    final response =
        await _dio.post(
      '/api/demo/trades',
      data: {
        'symbol': symbol,
        'direction': direction,
        'entry_price': entryPrice,
        'quantity': quantity,
        'stop_loss': stopLoss,
        'take_profit': takeProfit,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      closeDemoTrade({
    required String tradeId,
    required double exitPrice,
  }) async {
    final response =
        await _dio.post(
      '/api/demo/trades/$tradeId/close',
      data: {
        'exit_price': exitPrice,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      resetDemo() async {
    final response =
        await _dio.post(
      '/api/demo/reset',
    );

    return _asMap(response.data);
  }

  // ============================================================
  // PAPER JOURNAL
  // ============================================================

  Future<Map<String, dynamic>>
      paperJournalTrades({
    int limit = 50,
    int offset = 0,
  }) async {
    final response =
        await _dio.get(
      '/api/journal/trades',
      queryParameters: {
        'limit': limit,
        'offset': offset,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      paperPositions({
    String? symbol,
    String status = 'open',
    int limit = 100,
    int offset = 0,
  }) async {
    final response =
        await _dio.get(
      '/api/online/paper-positions',
      queryParameters: {
        if (symbol != null &&
            symbol.isNotEmpty)
          'symbol': symbol,
        'status': status,
        'limit': limit,
        'offset': offset,
      },
    );

    return _asMap(response.data);
  }

  // ============================================================
  // ONLINE MARKET
  // ============================================================

  Future<Map<String, dynamic>>
      marketPrice({
    String symbol = 'XAUUSD',
  }) async {
    final response =
        await _dio.get(
      '/api/online/price',
      queryParameters: {
        'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      marketIndicators({
    String symbol = 'XAUUSD',
    String timeframe = 'H1',
    int limit = 100,
  }) async {
    final response =
        await _dio.get(
      '/api/online/indicators',
      queryParameters: {
        'symbol': symbol,
        'timeframe': timeframe,
        'limit': limit,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      marketCandlesticks({
    String symbol = 'XAUUSD',
    String timeframe = 'H1',
    int limit = 60,
  }) async {
    final response =
        await _dio.get(
      '/api/online/candlesticks',
      queryParameters: {
        'symbol': symbol,
        'timeframe': timeframe,
        'limit': limit,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      marketOnlineStatus() async {
    final response =
        await _dio.get(
      '/api/online/status',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      marketAnalysis({
    String symbol = 'XAUUSD',
    String timeframe = 'M15',
    int limit = 100,
  }) async {
    final response =
        await _dio.get(
      '/api/online/analysis',
      queryParameters: {
        'symbol': symbol,
        'timeframe': timeframe,
        'limit': limit,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      advisoryAnalysis({
    String symbol = 'XAUUSD',
    String timeframe = 'H1',
    int limit = 100,
  }) async {
    final response =
        await _dio.get(
      '/api/online/advisory-analysis',
      queryParameters: {
        'symbol': symbol,
        'timeframe': timeframe,
        'limit': limit,
      },
    );

    final raw = response.data;

    if (raw is! Map) {
      throw const FormatException(
        'Invalid advisory analysis response.',
      );
    }

    final data =
        Map<String, dynamic>.from(raw);

    final rawComparison =
        data['advisory_comparison'];

    if (rawComparison is Map) {
      final comparison =
          Map<String, dynamic>.from(
        rawComparison,
      );

      final rawAdvisory =
          comparison['advisory'];

      if (rawAdvisory is Map) {
        final advisory =
            Map<String, dynamic>.from(
          rawAdvisory,
        );

        comparison[
                'advisory_direction'] =
            advisory['direction'];

        comparison[
                'advisory_confidence'] =
            advisory['confidence'];

        comparison['advisory_score'] =
            advisory['score'];

        comparison['buy_votes'] =
            advisory['buy_votes'];

        comparison['sell_votes'] =
            advisory['sell_votes'];

        comparison['wait_votes'] =
            advisory['wait_votes'];

        comparison[
                'agreement_percent'] =
            advisory[
                'agreement_percent'];

        comparison['entry_quality'] =
            advisory['entry_quality'];
      }

      final rawResult =
          comparison['comparison'];

      if (rawResult is Map) {
        final result =
            Map<String, dynamic>.from(
          rawResult,
        );

        comparison['status'] =
            result['status'];

        comparison['summary'] =
            result['summary'];

        comparison['warning'] =
            result['warning'];
      }

      data['advisory_comparison'] =
          comparison;
    }

    return data;
  }

  Future<Map<String, dynamic>>
      marketPositions({
    String? symbol,
  }) async {
    final response =
        await _dio.get(
      '/api/trading/positions',
      queryParameters: {
        if (symbol != null &&
            symbol.isNotEmpty)
          'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  // ============================================================
  // BROKER ACCOUNTS
  // ============================================================

  Future<Map<String, dynamic>>
      brokerAccounts() async {
    final response =
        await _dio.get(
      '/api/broker-accounts',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      brokerAccount(
    String accountId,
  ) async {
    final response =
        await _dio.get(
      '/api/broker-accounts/$accountId',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      createBrokerAccount({
    required String broker,
    required String platform,
    required String server,
    required String accountNumber,
    required String credentialRef,
  }) async {
    final response =
        await _dio.post(
      '/api/broker-accounts',
      data: {
        'broker': broker,
        'platform': platform,
        'server': server,
        'account_number':
            accountNumber,
        'credential_ref':
            credentialRef,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      updateBrokerAccount({
    required String accountId,
    String? broker,
    String? server,
    String? credentialRef,
  }) async {
    final response =
        await _dio.patch(
      '/api/broker-accounts/$accountId',
      data: {
        if (broker != null)
          'broker': broker,
        if (server != null)
          'server': server,
        if (credentialRef != null)
          'credential_ref':
              credentialRef,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      selectBrokerAccount(
    String accountId,
  ) async {
    final response =
        await _dio.post(
      '/api/broker-accounts/$accountId/select',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      disableBrokerLive(
    String accountId,
  ) async {
    final response =
        await _dio.post(
      '/api/broker-accounts/$accountId/disable-live',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      deleteBrokerAccount(
    String accountId,
  ) async {
    final response =
        await _dio.delete(
      '/api/broker-accounts/$accountId',
    );

    return _asMap(response.data);
  }

  // ============================================================
  // MT5 ACCOUNT CONNECTION — STEP 17.8
  // ============================================================

  Future<Map<String, dynamic>>
      connectBrokerAccount({
    required String accountId,
    required String password,
    String? terminalPath,
  }) async {
    final response =
        await _dio.post(
      '/api/broker-accounts/$accountId/connect',
      data: {
        'password': password,
        if (terminalPath != null &&
            terminalPath.trim().isNotEmpty)
          'terminal_path':
              terminalPath.trim(),
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      disconnectBrokerAccount(
    String accountId,
  ) async {
    final response =
        await _dio.post(
      '/api/broker-accounts/$accountId/disconnect',
    );

    return _asMap(response.data);
  }

  // ============================================================
  // MT5 BROKER ADAPTER
  // ============================================================

  Future<Map<String, dynamic>>
      brokerAdapterStatus() async {
    final response =
        await _dio.get(
      '/api/broker-adapter/status',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      brokerAdapterConnect() async {
    final response =
        await _dio.post(
      '/api/broker-adapter/connect',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      brokerAdapterDisconnect() async {
    final response =
        await _dio.post(
      '/api/broker-adapter/disconnect',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      brokerAdapterAccount() async {
    final response =
        await _dio.get(
      '/api/broker-adapter/account',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      brokerAdapterTerminal() async {
    final response =
        await _dio.get(
      '/api/broker-adapter/terminal',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      brokerAdapterSymbol({
    String symbol = 'XAUUSD',
  }) async {
    final response =
        await _dio.get(
      '/api/broker-adapter/symbol',
      queryParameters: {
        'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      brokerAdapterTick({
    String symbol = 'XAUUSD',
  }) async {
    final response =
        await _dio.get(
      '/api/broker-adapter/tick',
      queryParameters: {
        'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      brokerAdapterPositions({
    String? symbol,
  }) async {
    final response =
        await _dio.get(
      '/api/broker-adapter/positions',
      queryParameters: {
        if (symbol != null &&
            symbol.isNotEmpty)
          'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  // ============================================================
  // LIVE RECONCILIATION
  // ============================================================

  Future<Map<String, dynamic>>
      liveReconciliationStatus() async {
    final response =
        await _dio.get(
      '/api/live-reconciliation/status',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      runLiveReconciliation({
    String? symbol,
  }) async {
    final response =
        await _dio.post(
      '/api/live-reconciliation/run',
      queryParameters: {
        if (symbol != null &&
            symbol.isNotEmpty)
          'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  // ============================================================
  // LIVE POSITION MONITOR
  // ============================================================

  Future<Map<String, dynamic>>
      livePositionMonitorStatus() async {
    final response =
        await _dio.get(
      '/api/live-position-monitor/status',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      livePositionMonitorPositions({
    String? symbol,
  }) async {
    final response =
        await _dio.get(
      '/api/live-position-monitor/positions',
      queryParameters: {
        if (symbol != null &&
            symbol.isNotEmpty)
          'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      runLivePositionMonitor({
    String? symbol,
  }) async {
    final response =
        await _dio.post(
      '/api/live-position-monitor/run',
      queryParameters: {
        if (symbol != null &&
            symbol.isNotEmpty)
          'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  // ============================================================
  // LIVE PROTECTION WORKER
  // ============================================================

  Future<Map<String, dynamic>>
      liveProtectionWorkerStatus() async {
    final response =
        await _dio.get(
      '/api/live-protection-worker/status',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      liveProtectionWorkerHealth() async {
    final response =
        await _dio.get(
      '/api/live-protection-worker/health',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      liveProtectionWorkerConfiguration() async {
    final response =
        await _dio.get(
      '/api/live-protection-worker/configuration',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      liveProtectionDryRun() async {
    final response =
        await _dio.post(
      '/api/live-protection-worker/dry-run',
    );

    return _asMap(response.data);
  }

  // ============================================================
  // ADMIN / SAFETY
  // ============================================================

  Future<Map<String, dynamic>>
      adminStatus() async {
    final response =
        await _dio.get(
      '/api/admin/status',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      activateEmergencyStop() async {
    final response =
        await _dio.post(
      '/api/admin/emergency-stop',
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>>
      resetEmergencyStop() async {
    final response =
        await _dio.post(
      '/api/admin/emergency-stop/reset',
    );

    return _asMap(response.data);
  }

  // ============================================================
  // HELPERS
  // ============================================================

  List<Map<String, dynamic>>
      _asTradeList(
    dynamic data,
  ) {
    if (data is Map &&
        data['trades'] is List) {
      return (data['trades'] as List)
          .whereType<Map>()
          .map(
            (item) =>
                Map<String, dynamic>.from(
              item,
            ),
          )
          .toList();
    }

    return [];
  }

  Map<String, dynamic> _asMap(
    dynamic data,
  ) {
    if (data is Map) {
      return Map<String, dynamic>.from(
        data,
      );
    }

    throw const FormatException(
      'Expected a JSON object from the API.',
    );
  }
}
