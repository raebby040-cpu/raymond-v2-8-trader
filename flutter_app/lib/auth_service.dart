
import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// RAYMOND V2.8 authentication service.
/// Does not execute trades or modify the strategy.
class AuthService {
  AuthService._();

  static final AuthService instance = AuthService._();

  static const String _baseUrl =
      'https://raymond-v2-8-trader.onrender.com';

  static const String _tokenKey = 'raymond_access_token';
  static const String _emailKey = 'raymond_user_email';

  final Dio _dio = Dio(
    BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 20),
      receiveTimeout: const Duration(seconds: 20),
      sendTimeout: const Duration(seconds: 20),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
    ),
  );

  Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(_tokenKey);

    if (token == null || token.trim().isEmpty) {
      return null;
    }

    return token;
  }

  Future<String?> getSavedEmail() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_emailKey);
  }

  Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _dio.post(
        '/api/auth/login',
        data: {
          'email': email.trim().toLowerCase(),
          'password': password,
        },
      );

      return await _saveResponse(response.data);
    } on DioException catch (error) {
      throw Exception(_errorMessage(error));
    }
  }

  Future<Map<String, dynamic>> register({
    required String email,
    required String password,
  }) async {
    if (password.length < 12) {
      throw Exception(
        'Password must contain at least 12 characters.',
      );
    }

    try {
      final response = await _dio.post(
        '/api/auth/register',
        data: {
          'email': email.trim().toLowerCase(),
          'password': password,
        },
      );

      return await _saveResponse(response.data);
    } on DioException catch (error) {
      throw Exception(_errorMessage(error));
    }
  }

  Future<Map<String, dynamic>> _saveResponse(
    dynamic responseData,
  ) async {
    if (responseData is! Map) {
      throw Exception('Invalid authentication response from server.');
    }

    final data = Map<String, dynamic>.from(responseData);
    final token = data['access_token'];

    if (token is! String || token.isEmpty) {
      throw Exception('Server did not return an access token.');
    }

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);

    final user = data['user'];
    if (user is Map && user['email'] is String) {
      await prefs.setString(
        _emailKey,
        user['email'] as String,
      );
    }

    return data;
  }

  Future<bool> validateToken() async {
    final token = await getToken();

    if (token == null) return false;

    try {
      final response = await _dio.get(
        '/api/auth/me',
        options: Options(
          headers: {'Authorization': 'Bearer $token'},
        ),
      );

      return response.statusCode == 200 &&
          response.data is Map;
    } on DioException catch (error) {
      if (error.response?.statusCode == 401 ||
          error.response?.statusCode == 403) {
        await logout();
      }
      return false;
    }
  }

  Future<Options> authenticatedOptions() async {
    final token = await getToken();

    if (token == null) {
      throw Exception('Please sign in to RAYMOND V2.8.');
    }

    return Options(
      headers: {'Authorization': 'Bearer $token'},
    );
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    await prefs.remove(_emailKey);
  }

  String _errorMessage(DioException error) {
    final data = error.response?.data;

    if (data is Map && data['detail'] != null) {
      return data['detail'].toString();
    }

    switch (error.response?.statusCode) {
      case 401:
        return 'Invalid email or password.';
      case 403:
        return 'This account is not allowed to sign in.';
      case 409:
        return 'An account with this email already exists.';
      case 422:
        return 'Please check the email and password requirements.';
      default:
        if (error.response == null) {
          return 'Connection failed. Check your internet and try again.';
        }
        return 'Authentication failed. Please try again.';
    }
  }
}
