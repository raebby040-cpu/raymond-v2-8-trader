import 'package:flutter/foundation.dart';
import '../models/market_model.dart';
import '../services/api_client.dart';

class MarketProvider extends ChangeNotifier {
  final ApiClient _apiClient = ApiClient();

  MarketPrice? _currentPrice;
  Indicators? _indicators;
  List<Candlestick> _candlesticks = [];
  bool _isLoading = false;
  String? _error;

  MarketPrice? get currentPrice => _currentPrice;
  Indicators? get indicators => _indicators;
  List<Candlestick> get candlesticks => _candlesticks;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> fetchCurrentPrice() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _currentPrice = await _apiClient.getCurrentPrice();
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> fetchIndicators() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _indicators = await _apiClient.getIndicators();
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> fetchCandlesticks() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _candlesticks = await _apiClient.getCandlesticks();
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> refreshAll() async {
    await Future.wait([
      fetchCurrentPrice(),
      fetchIndicators(),
      fetchCandlesticks(),
    ]);
  }
}
