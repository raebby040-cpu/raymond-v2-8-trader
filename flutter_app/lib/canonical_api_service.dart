
import 'package:dio/dio.dart';
import 'auth_service.dart';

/// RAYMOND v2.8
///
/// Canonical trading-state API client.
///
/// The backend canonical state is the application's persistent
/// source of truth for PAPER / DEMO / LIVE positions.
///
/// Important:
/// - This client is read-only.
/// - It does not place broker orders.
/// - It does not authorize LIVE trading.
/// - It does not modify positions.
/// - LIVE data can be displayed only when the backend has
///   canonical LIVE state available.
class CanonicalApiService {
  CanonicalApiService({
    String? baseUrl,
  }) : _dio = Dio(
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
              'Content-Type': 'application/json',
            },
          ),
        ) {
    // Attach the saved login token to canonical API requests.
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token =
              await AuthService.instance.getToken();

          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] =
                'Bearer $token';
          }

          handler.next(options);
        },
      ),
    );
  }

  final Dio _dio;

  // ============================================================
  // CANONICAL POSITIONS
  // ============================================================

  Future<Map<String, dynamic>> positions({
    String? mode,
    String? status,
    String? symbol,
    int limit = 100,
  }) async {
    final response = await _dio.get(
      '/api/canonical/positions',
      queryParameters: {
        if (mode != null && mode.isNotEmpty)
          'mode': mode,
        if (status != null && status.isNotEmpty)
          'status': status,
        if (symbol != null && symbol.isNotEmpty)
          'symbol': symbol,
        'limit': limit,
      },
    );

    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> position(
    String canonicalId,
  ) async {
    final response = await _dio.get(
      '/api/canonical/positions/$canonicalId',
    );

    return _asMap(response.data);
  }

  // ============================================================
  // CANONICAL ACCOUNT
  // ============================================================

  Future<Map<String, dynamic>> account({
    required String mode,
    int? brokerAccountId,
  }) async {
    final response = await _dio.get(
      '/api/canonical/account/$mode',
      queryParameters: {
        if (brokerAccountId != null)
          'broker_account_id': brokerAccountId,
      },
    );

    return _asMap(response.data);
  }

  // ============================================================
  // CANONICAL HEALTH
  // ============================================================

  Future<Map<String, dynamic>> health() async {
    final response = await _dio.get(
      '/api/canonical/health',
    );

    return _asMap(response.data);
  }

  // ============================================================
  // CONVENIENCE METHODS
  // ============================================================

  Future<List<Map<String, dynamic>>> openPositions({
    required String mode,
    String? symbol,
    int limit = 100,
  }) async {
    final response = await positions(
      mode: mode,
      status: 'open',
      symbol: symbol,
      limit: limit,
    );

    return _positionList(response['positions']);
  }

  Future<List<Map<String, dynamic>>> allPositions({
    required String mode,
    String? symbol,
    int limit = 100,
  }) async {
    final response = await positions(
      mode: mode,
      symbol: symbol,
      limit: limit,
    );

    return _positionList(response['positions']);
  }

  // ============================================================
  // HELPERS
  // ============================================================

  Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map) {
      return Map<String, dynamic>.from(data);
    }

    throw const FormatException(
      'Expected a JSON object from the canonical API.',
    );
  }

  List<Map<String, dynamic>> _positionList(dynamic raw) {
    if (raw is! List) {
      return [];
    }

    return raw
        .whereType<Map>()
        .map(
          (item) => Map<String, dynamic>.from(item),
        )
        .toList();
  }
}
