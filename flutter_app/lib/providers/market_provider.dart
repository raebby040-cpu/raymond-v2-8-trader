import 'package:flutter/material.dart';

class MarketProvider extends ChangeNotifier {
  double? _currentPrice;
  double? _bid;
  double? _ask;
  bool _isLoading = false;

  double? get currentPrice => _currentPrice;
  double? get bid => _bid;
  double? get ask => _ask;
  bool get isLoading => _isLoading;

  Future<void> fetchPrice() async {
    _isLoading = true;
    notifyListeners();

    try {
      // Mock data for now
      await Future.delayed(const Duration(seconds: 1));
      _currentPrice = 2050.45;
      _bid = 2050.40;
      _ask = 2050.50;
    } catch (e) {
      debugPrint('Error fetching price: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
