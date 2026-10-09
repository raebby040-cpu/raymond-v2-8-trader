
import 'package:flutter/material.dart';

import 'auth_service.dart';
import 'login_page.dart';

/// Checks authentication before showing protected app screens.
/// This gate does not change trading strategy or execution settings.
class AuthGate extends StatefulWidget {
  const AuthGate({
    super.key,
    required this.child,
  });

  final Widget child;

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  bool _checking = true;
  bool _authenticated = false;

  @override
  void initState() {
    super.initState();
    _checkAuthentication();
  }

  Future<void> _checkAuthentication() async {
    final valid = await AuthService.instance.validateToken();

    if (!mounted) return;

    setState(() {
      _authenticated = valid;
      _checking = false;
    });
  }

  void _onAuthenticated() {
    if (!mounted) return;

    setState(() {
      _authenticated = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_checking) {
      return const Scaffold(
        backgroundColor: Color(0xFF030B14),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.candlestick_chart,
                color: Color(0xFFF5B82E),
                size: 56,
              ),
              SizedBox(height: 20),
              CircularProgressIndicator(
                color: Color(0xFFF5B82E),
              ),
              SizedBox(height: 16),
              Text(
                'Checking secure sign-in...',
                style: TextStyle(
                  color: Color(0xFF8EA4B8),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (!_authenticated) {
      return LoginPage(
        onAuthenticated: _onAuthenticated,
      );
    }

    return widget.child;
  }
}
