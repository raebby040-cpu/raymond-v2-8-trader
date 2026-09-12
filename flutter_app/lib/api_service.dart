import 'package:dio/dio.dart';

class ApiService {
  ApiService({String? baseUrl})
      : _dio = Dio(
          BaseOptions(
            baseUrl: baseUrl ?? 'http://10.0.2.2:8000',
            connectTimeout: const Duration(seconds: 5),
            receiveTimeout: const Duration(seconds: 10),
            sendTimeout: const Duration(seconds: 10),
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

  // Step 10B-1: persistent Step 15 paper-trade journal.
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
    final response = await _dio.get(
      '/api/market/price',
      queryParameters: {
        'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> marketIndicators({
    String symbol = 'XAUUSD',
  }) async {
    final response = await _dio.get(
      '/api/market/indicators',
      queryParameters: {
        'symbol': symbol,
      },
    );

    return _asMap(response.data);
  }

  // Step 10B-2: functional XAUUSD candlestick chart.
  Future<Map<String, dynamic>> marketCandlesticks({
    String symbol = 'XAUUSD',
    String timeframe = 'H1',
    int limit = 60,
  }) async {
    final response = await _dio.get(
      '/api/market/candlesticks',
      queryParameters: {
        'symbol': symbol,
        'timeframe': timeframe,
        'limit': limit,
      },
    );

    return _asMap(response.data);
  }

  // Step 10B-3: read-only current MT5 positions.
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
