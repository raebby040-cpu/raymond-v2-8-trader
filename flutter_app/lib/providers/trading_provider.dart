import 'package:flutter/foundation.dart';
import '../models/trading_model.dart';
import '../services/api_client.dart';

class TradingProvider extends ChangeNotifier {
  final ApiClient _apiClient = ApiClient();

  List<Position> _positions = [];
  List<Trade> _tradeHistory = [];
  StrategyDecision? _strategyDecision;
  bool _isLoading = false;
  String? _error;

  List<Position> get positions => _positions;
  List<Trade> get tradeHistory => _tradeHistory;
  StrategyDecision? get strategyDecision => _strategyDecision;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> fetchPositions() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _positions = await _apiClient.getPositions();
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> fetchTradeHistory() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _tradeHistory = await _apiClient.getTradeJournal();
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> fetchStrategyDecision() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _strategyDecision = await _apiClient.getStrategyDecision();
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> placeOrder({
    required String symbol,
    required String orderType,
    required String direction,
    required double quantity,
  }) async {
    try {
      await _apiClient.placeOrder(
        symbol: symbol,
        orderType: orderType,
        direction: direction,
        quantity: quantity,
      );
      await fetchPositions();
      _error = null;
    } catch (e) {
      _error = e.toString();
    }
    notifyListeners();
  }

  Future<void> closePosition(String positionId) async {
    try {
      await _apiClient.closePosition(positionId);
      await fetchPositions();
      _error = null;
    } catch (e) {
      _error = e.toString();
    }
    notifyListeners();
  }
}
