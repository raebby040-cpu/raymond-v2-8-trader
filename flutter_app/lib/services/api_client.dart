import 'package:dio/dio.dart';
import '../models/market_model.dart';
import '../models/trading_model.dart';

class ApiClient {
  late Dio _dio;
  static const String baseUrl = 'http://localhost:8000';

  ApiClient() {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 5),
      contentType: Headers.jsonContentType,
    ));
  }

  Future<MarketPrice> getCurrentPrice() async {
    try {
      final response = await _dio.get('/api/market/price');
      return MarketPrice.fromJson(response.data);
    } catch (e) {
      throw Exception('Failed to fetch current price: $e');
    }
  }

  Future<Indicators> getIndicators() async {
    try {
      final response = await _dio.get('/api/market/indicators');
      return Indicators.fromJson(response.data);
    } catch (e) {
      throw Exception('Failed to fetch indicators: $e');
    }
  }

  Future<List<Candlestick>> getCandlesticks() async {
    try {
      final response = await _dio.get('/api/market/candlesticks?timeframe=H1&limit=100');
      final candlesticks = response.data['candlesticks'] as List;
      return candlesticks.map((c) => Candlestick.fromJson(c)).toList();
    } catch (e) {
      throw Exception('Failed to fetch candlesticks: $e');
    }
  }

  Future<List<Position>> getPositions() async {
    try {
      final response = await _dio.get('/api/trading/positions');
      final positions = response.data['positions'] as List;
      return positions.map((p) => Position.fromJson(p)).toList();
    } catch (e) {
      throw Exception('Failed to fetch positions: $e');
    }
  }

  Future<List<Trade>> getTradeJournal() async {
    try {
      final response = await _dio.get('/api/journal/trades');
      final trades = response.data['trades'] as List;
      return trades.map((t) => Trade.fromJson(t)).toList();
    } catch (e) {
      throw Exception('Failed to fetch trade journal: $e');
    }
  }

  Future<StrategyDecision> getStrategyDecision() async {
    try {
      final response = await _dio.get('/api/strategy/decision');
      return StrategyDecision.fromJson(response.data);
    } catch (e) {
      throw Exception('Failed to fetch strategy decision: $e');
    }
  }

  Future<void> placeOrder({
    required String symbol,
    required String orderType,
    required String direction,
    required double quantity,
  }) async {
    try {
      await _dio.post('/api/trading/place-order', data: {
        'symbol': symbol,
        'order_type': orderType,
        'direction': direction,
        'quantity': quantity,
      });
    } catch (e) {
      throw Exception('Failed to place order: $e');
    }
  }

  Future<void> closePosition(String positionId) async {
    try {
      await _dio.post('/api/trading/close-position', data: {
        'position_id': positionId,
      });
    } catch (e) {
      throw Exception('Failed to close position: $e');
    }
  }
}
