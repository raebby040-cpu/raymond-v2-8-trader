import 'package:dio/dio.dart';

class ApiService {
  ApiService({String? baseUrl})
      : _dio = Dio(
          BaseOptions(
            // Render backend
            baseUrl: baseUrl ?? 'https://raymond-v2-8-trader.onrender.com',
            connectTimeout: const Duration(seconds: 15),
            receiveTimeout: const Duration(seconds: 20),
            sendTimeout: const Duration(seconds: 20),
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json',
            },
          ),
        );

  final Dio _dio;

  Future<Map<String, dynamic>> health() async {
    final response = await _dio.get('/health');
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> demoStatus() async {
    final response = await _dio.get('/api/demo/status');
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> demoPerformance() async {
    final response = await _dio.get('/api/demo/performance');
    return _asMap(response.data);
  }

  Future<List<Map<String, dynamic>>> demoTrades() async {
    final response = await _dio.get('/api/demo/trades');
    return _asTradeList(response.data);
  }

  Future<Map<String, dynamic>> paperJournalTrades({
    int limit = 50,
    int offset = 0,
  }) async {
    final response = await _dio.get(
      '/api/journal/trades',
      queryParameters: {
        'limit': limit,
        'offset': offset,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> marketPrice({
    String symbol = 'XAUUSD',
  }) async {
    // Read-only online market feed.
    // This keeps the Android dashboard independent
    // from the optional MT5 connection.
    final response = await _dio.get(
      '/api/online/price',
      queryParameters: {
        'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> marketIndicators({
    String symbol = 'XAUUSD',
    String timeframe = 'H1',
    int limit = 100,
  }) async {
    final response = await _dio.get(
      '/api/online/indicators',
      queryParameters: {
        'symbol': symbol,
        'timeframe': timeframe,
        'limit': limit,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> marketCandlesticks({
    String symbol = 'XAUUSD',
    String timeframe = 'H1',
    int limit = 60,
  }) async {
    final response = await _dio.get(
      '/api/online/candlesticks',
      queryParameters: {
        'symbol': symbol,
        'timeframe': timeframe,
        'limit': limit,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> marketOnlineStatus() async {
    final response = await _dio.get('/api/online/status');
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> marketAnalysis({
    String symbol = 'XAUUSD',
    String timeframe = 'M15',
    int limit = 100,
  }) async {
    final response = await _dio.get(
      '/api/online/analysis',
      queryParameters: {
        'symbol': symbol,
        'timeframe': timeframe,
        'limit': limit,
      },
    );

    return _asMap(response.data);
  }

  /// RAYMOND Step 13 + independent 8-brain advisory analysis.
  ///
  /// READ-ONLY.
  ///
  /// This does not place, modify, or close any trade.
  Future<Map<String, dynamic>> advisoryAnalysis({
    String symbol = 'XAUUSD',
    String timeframe = 'H1',
    int limit = 100,
  }) async {
    final response = await _dio.get(
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

    final data = Map<String, dynamic>.from(raw);

    /*
     * The backend returns advisory_comparison in this structure:
     *
     * advisory_comparison:
     *   raymond: {...}
     *   advisory:
     *     direction
     *     confidence
     *     score
     *     buy_votes
     *     sell_votes
     *     wait_votes
     *     agreement_percent
     *     entry_quality
     *   comparison:
     *     status
     *     summary
     *     warning
     *   brains:
     *     [...]
     *
     * The Flutter terminal historically reads the master advisory
     * fields from the comparison object itself.
     *
     * Normalize the response here so the rest of the terminal can
     * use one consistent contract.
     */

    final rawComparison = data['advisory_comparison'];

    if (rawComparison is Map) {
      final comparison =
          Map<String, dynamic>.from(rawComparison);

      final rawAdvisory = comparison['advisory'];

      if (rawAdvisory is Map) {
        final advisory =
            Map<String, dynamic>.from(rawAdvisory);

        comparison['advisory_direction'] =
            advisory['direction'];

        comparison['advisory_confidence'] =
            advisory['confidence'];

        comparison['advisory_score'] =
            advisory['score'];

        comparison['buy_votes'] =
            advisory['buy_votes'];

        comparison['sell_votes'] =
            advisory['sell_votes'];

        comparison['wait_votes'] =
            advisory['wait_votes'];

        comparison['agreement_percent'] =
            advisory['agreement_percent'];

        comparison['entry_quality'] =
            advisory['entry_quality'];
      }

      final rawResult = comparison['comparison'];

      if (rawResult is Map) {
        final result =
            Map<String, dynamic>.from(rawResult);

        comparison['status'] =
            result['status'];

        comparison['summary'] =
            result['summary'];

        comparison['warning'] =
            result['warning'];
      }

      data['advisory_comparison'] = comparison;
    }

    return data;
  }

  /// Persistent PAPER positions maintained by RAYMOND.
  ///
  /// READ-ONLY.
  ///
  /// This is intentionally separate from the MT5 positions endpoint.
  /// The Android terminal should use this endpoint for RAYMOND paper
  /// trades because the Render deployment does not require MT5.
  Future<Map<String, dynamic>> paperPositions({
    String? symbol,
    String status = 'open',
    int limit = 100,
    int offset = 0,
  }) async {
    final response = await _dio.get(
      '/api/online/paper-positions',
      queryParameters: {
        if (symbol != null && symbol.isNotEmpty) 'symbol': symbol,
        'status': status,
        'limit': limit,
        'offset': offset,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> marketPositions({
    String? symbol,
  }) async {
    final response = await _dio.get(
      '/api/trading/positions',
      queryParameters: {
        if (symbol != null && symbol.isNotEmpty) 'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> adminStatus() async {
    final response = await _dio.get('/api/admin/status');
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> activateEmergencyStop() async {
    final response = await _dio.post('/api/admin/emergency-stop');
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> resetEmergencyStop() async {
    final response = await _dio.post('/api/admin/emergency-stop/reset');
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> openDemoTrade({
    required String symbol,
    required String direction,
    required double entryPrice,
    required double quantity,
    double? stopLoss,
    double? takeProfit,
  }) async {
    final payload = {
      'symbol': symbol,
      'direction': direction,
      'entry_price': entryPrice,
      'quantity': quantity,
      'stop_loss': stopLoss,
      'take_profit': takeProfit,
    };

    final response = await _dio.post(
      '/api/demo/trades',
      data: payload,
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> closeDemoTrade({
    required String tradeId,
    required double exitPrice,
  }) async {
    final response = await _dio.post(
      '/api/demo/trades/$tradeId/close',
      data: {
        'exit_price': exitPrice,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> resetDemo() async {
    final response = await _dio.post('/api/demo/reset');
    return _asMap(response.data);
  }

  List<Map<String, dynamic>> _asTradeList(dynamic data) {
    if (data is Map && data['trades'] is List) {
      return (data['trades'] as List)
          .whereType<Map>()
          .map(
            (item) => Map<String, dynamic>.from(item),
          )
          .toList();
    }

    return [];
  }

  Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map) {
      return Map<String, dynamic>.from(data);
    }

    throw const FormatException(
      'Expected a JSON object from the API.',
    );
  }
}
