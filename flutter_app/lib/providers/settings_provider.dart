import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SettingsProvider extends ChangeNotifier {
  late SharedPreferences _prefs;

  String _apiUrl = 'http://localhost:8000';
  String _broker = 'mt5';
  bool _liveTrading = false;
  bool _darkMode = true;

  String get apiUrl => _apiUrl;
  String get broker => _broker;
  bool get liveTrading => _liveTrading;
  bool get darkMode => _darkMode;

  Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
    _apiUrl = _prefs.getString('api_url') ?? 'http://localhost:8000';
    _broker = _prefs.getString('broker') ?? 'mt5';
    _liveTrading = _prefs.getBool('live_trading') ?? false;
    _darkMode = _prefs.getBool('dark_mode') ?? true;
    notifyListeners();
  }

  Future<void> setApiUrl(String url) async {
    _apiUrl = url;
    await _prefs.setString('api_url', url);
    notifyListeners();
  }

  Future<void> setBroker(String broker) async {
    _broker = broker;
    await _prefs.setString('broker', broker);
    notifyListeners();
  }

  Future<void> setLiveTrading(bool enabled) async {
    _liveTrading = enabled;
    await _prefs.setBool('live_trading', enabled);
    notifyListeners();
  }

  Future<void> setDarkMode(bool enabled) async {
    _darkMode = enabled;
    await _prefs.setBool('dark_mode', enabled);
    notifyListeners();
  }
}
