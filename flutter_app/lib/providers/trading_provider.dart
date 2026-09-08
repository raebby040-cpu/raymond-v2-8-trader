import 'package:flutter/material.dart';

class TradingProvider extends ChangeNotifier {
  List<Map<String, dynamic>> _openPositions = [];
  List<Map<String, dynamic>> _tradeHistory = [];

  List<Map<String, dynamic>> get openPositions => _openPositions;
  List<Map<String, dynamic>> get tradeHistory => _tradeHistory;

  void addPosition(String id, String symbol, double size, double entry) {
    _openPositions.add({
      'id': id,
      'symbol': symbol,
      'size': size,
      'entry': entry,
    });
    notifyListeners();
  }

  void closePosition(String id) {
    _openPositions.removeWhere((p) => p['id'] == id);
    notifyListeners();
  }
}
