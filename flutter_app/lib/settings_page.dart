import 'package:flutter/material.dart';

import 'api_service.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({
    super.key,
    required this.api,
  });

  final ApiService api;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  static const gold = Color(0xFFF5B82E);
  static const green = Color(0xFF00E59B);
  static const red = Color(0xFFFF5C6C);
  static const orange = Color(0xFFFFA726);
  static const background = Color(0xFF030B14);
  static const card = Color(0xFF091724);
  static const border = Color(0xFF17334D);
  static const muted = Color(0xFF8EA4B8);

  bool loading = true;
  bool actionLoading = false;

  String error = '';

  bool backendOnline = false;
  bool liveTradingEnabled = false;
  bool mt5Connected = false;
  bool marketFeedHealthy = false;
  bool dbConnected = false;
  bool tradingAllowed = false;
  bool emergencyStopActive = false;
  bool safetyConnectionHealthy = false;

  String environment = '--';
  String safetyReason = '--';

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  Future<void> _loadStatus() async {
    if (mounted) {
      setState(() {
        loading = true;
        error = '';
      });
    }

    try {
      final health = await widget.api.health();

      Map<String, dynamic> status = {};

      try {
        status = await widget.api.adminStatus();
      } catch (_) {
        // Keep the page usable even if the admin endpoint is unavailable.
      }

      final safetyRaw = status['safety'];

      final safety = safetyRaw is Map
          ? Map<String, dynamic>.from(safetyRaw)
          : <String, dynamic>{};

      if (!mounted) return;

      setState(() {
        backendOnline = health['status'] == 'healthy' ||
            status['status'] == 'operational';

        liveTradingEnabled =
            status['live_trading_enabled'] == true;

        mt5Connected =
            status['mt5_connected'] == true;

        marketFeedHealthy =
            status['market_feed_healthy'] == true;

        dbConnected =
            status['db_connected'] == true;

        tradingAllowed =
            safety['trading_allowed'] == true;

        emergencyStopActive =
            safety['emergency_stop_active'] == true;

        safetyConnectionHealthy =
            safety['connection_healthy'] == true;

        environment =
            '${status['environment'] ?? '--'}';

        safetyReason =
            '${safety['reason'] ?? '--}';

        loading = false;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        loading = false;
        backendOnline = false;
        error = 'Unable to load system safety status.';
      });
    }
  }

  Future<void> _activateEmergencyStop() async {
    final confirmed = await _confirmEmergencyStop();

    if (!confirmed) {
      return;
    }

    setState(() {
      actionLoading = true;
      error = '';
    });

    try {
      await widget.api.activateEmergencyStop();

      if (!mounted) return;

      setState(() {
        emergencyStopActive = true;
        tradingAllowed = false;
        actionLoading = false;
      });

      await _loadStatus();

      if (!mounted) return;

      _showMessage(
        'Emergency stop activated. New trading is blocked.',
        isError: false,
      );
    } catch (_) {
      if (!mounted) return;

      setState(() {
        actionLoading = false;
        error = 'Unable to activate emergency stop.';
      });

      _showMessage(
        'Emergency stop request failed.',
        isError: true,
      );
    }
  }

  Future<void> _resetEmergencyStop() async {
    final confirmed = await _confirmReset();

    if (!confirmed) {
      return;
    }

    setState(() {
      actionLoading = true;
      error = '';
    });

    try {
      await widget.api.resetEmergencyStop();

      if (!mounted) return;

      setState(() {
        actionLoading = false;
      });

      await _loadStatus();

      if (!mounted) return;

      _showMessage(
        'Emergency stop reset request sent.',
        isError: false,
      );
    } catch (_) {
      if (!mounted) return;

      setState(() {
        actionLoading = false;
        error = 'Unable to reset emergency stop.';
      });

      _showMessage(
        'Emergency stop reset failed.',
        isError: true,
      );
    }
  }

  Future<bool> _confirmEmergencyStop() async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: card,
          title: const Text(
            'Activate Emergency Stop?',
            style: TextStyle(
              color: red,
              fontWeight: FontWeight.w800,
            ),
          ),
          content: const Text(
            'This will block new trading activity through the '
            'RAYMOND safety manager.\n\n'
            'It does not automatically close existing broker '
            'positions.',
            style: TextStyle(
              color: muted,
              height: 1.5,
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop(false);
              },
              child: const Text('CANCEL'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: red,
                foregroundColor: Colors.white,
              ),
              onPressed: () {
                Navigator.of(context).pop(true);
              },
              child: const Text(
                'EMERGENCY STOP',
              ),
            ),
          ],
        );
      },
    );

    return result == true;
  }

  Future<bool> _confirmReset() async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: card,
          title: const Text(
            'Reset Emergency Stop?',
            style: TextStyle(
              color: gold,
              fontWeight: FontWeight.w800,
            ),
          ),
          content: const Text(
            'Resetting the emergency stop does not force '
            'trading to become active. The backend still requires '
            'a healthy connection and safe conditions.',
            style: TextStyle(
              color: muted,
              height: 1.5,
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop(false);
              },
              child: const Text('CANCEL'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: gold,
                foregroundColor: Colors.black,
              ),
              onPressed: () {
                Navigator.of(context).pop(true);
              },
              child: const Text(
                'RESET STOP',
              ),
            ),
          ],
        );
      },
    );

    return result == true;
  }

  void _showMessage(
    String message, {
    required bool isError,
  }) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: isError ? red : green,
        content: Text(
          message,
          style: TextStyle(
            color: isError ? Colors.white : Colors.black,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: background,
      child: RefreshIndicator(
        onRefresh: _loadStatus,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            16,
            12,
            16,
            28,
          ),
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'SETTINGS',
                    style: TextStyle(
                      fontSize: 25,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                IconButton(
                  onPressed:
                      loading || actionLoading
                          ? null
                          : _loadStatus,
                  icon: const Icon(
                    Icons.refresh,
                  ),
                ),
              ],
            ),

            const Text(
              'System configuration and safety controls',
              style: TextStyle(
                color: muted,
              ),
            ),

            const SizedBox(height: 18),

            _modeCard(),

            const SizedBox(height: 14),

            _sectionTitle(
              'SYSTEM STATUS',
            ),

            const SizedBox(height: 8),

            if (error.isNotEmpty)
              _errorCard(),

            if (loading)
              const Padding(
                padding: EdgeInsets.only(
                  top: 45,
                  bottom: 45,
                ),
                child: Center(
                  child: CircularProgressIndicator(),
                ),
              )
            else ...[
              _statusCard(
                icon: Icons.cloud_outlined,
                title: 'Backend',
                value: backendOnline
                    ? 'ONLINE'
                    : 'OFFLINE',
                healthy: backendOnline,
              ),

              _statusCard(
                icon: Icons.cable_outlined,
                title: 'MT5 Connection',
                value: mt5Connected
                    ? 'CONNECTED'
                    : 'DISCONNECTED',
                healthy: mt5Connected,
              ),

              _statusCard(
                icon: Icons.show_chart_outlined,
                title: 'Market Feed',
                value: marketFeedHealthy
                    ? 'HEALTHY'
                    : 'UNAVAILABLE',
                healthy: marketFeedHealthy,
              ),

              _statusCard(
                icon: Icons.storage_outlined,
                title: 'Database',
                value: dbConnected
                    ? 'CONNECTED'
                    : 'UNAVAILABLE',
                healthy: dbConnected,
              ),

              const SizedBox(height: 18),

              _sectionTitle(
                'TRADING MODE',
              ),

              const SizedBox(height: 8),

              _tradingModeCard(),

              const SizedBox(height: 18),

              _sectionTitle(
                'SAFETY',
              ),

              const SizedBox(height: 8),

              _safetyStatusCard(),

              const SizedBox(height: 14),

              _emergencyControls(),

              const SizedBox(height: 18),

              _sectionTitle(
                'ENVIRONMENT',
              ),

              const SizedBox(height: 8),

              _environmentCard(),

              const SizedBox(height: 18),

              _readOnlyNotice(),
            ],
          ],
        ),
      ),
    );
  }

  Widget _modeCard() {
    final safe = !liveTradingEnabled;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: safe
              ? green.withOpacity(.35)
              : red.withOpacity(.50),
        ),
      ),
      child: Row(
        children: [
          Icon(
            safe
                ? Icons.shield_outlined
                : Icons.warning_amber_rounded,
            color: safe ? green : red,
            size: 30,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment:
                  CrossAxisAlignment.start,
              children: [
                Text(
                  safe
                      ? 'SAFE PAPER MODE'
                      : 'LIVE TRADING ENABLED',
                  style: TextStyle(
                    color: safe ? green : red,
                    fontWeight: FontWeight.w800,
                    fontSize: 16,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  safe
                      ? 'Real-money trading is disabled.'
                      : 'Real-money trading configuration is active.',
                  style: const TextStyle(
                    color: muted,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _tradingModeCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: border,
        ),
      ),
      child: Column(
        children: [
          _modeRow(
            icon: Icons.science_outlined,
            title: 'Paper Trading',
            subtitle:
                'Testing and simulation mode',
            active: !liveTradingEnabled,
            activeText: 'ACTIVE',
          ),
          const Divider(
            color: border,
            height: 24,
          ),
          _modeRow(
            icon: Icons.account_balance_outlined,
            title: 'Live Trading',
            subtitle:
                'Real broker order execution',
            active: liveTradingEnabled,
            activeText: liveTradingEnabled
                ? 'ENABLED'
                : 'DISABLED',
            dangerous: true,
          ),
        ],
      ),
    );
  }

  Widget _modeRow({
    required IconData icon,
    required String title,
    required String subtitle,
    required bool active,
    required String activeText,
    bool dangerous = false,
  }) {
    final color = dangerous && active
        ? red
        : active
            ? green
            : muted;

    return Row(
      children: [
        Icon(
          icon,
          color: color,
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment:
                CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                subtitle,
                style: const TextStyle(
                  color: muted,
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(
            horizontal: 9,
            vertical: 5,
          ),
          decoration: BoxDecoration(
            color: color.withOpacity(.12),
            borderRadius:
                BorderRadius.circular(7),
          ),
          child: Text(
            activeText,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.bold,
              fontSize: 10,
            ),
          ),
        ),
      ],
    );
  }

  Widget _statusCard({
    required IconData icon,
    required String title,
    required String value,
    required bool healthy,
  }) {
    return Container(
      margin: const EdgeInsets.only(
        bottom: 10,
      ),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(14),
        border: Border.all(
          color: border,
        ),
      ),
      child: Row(
        children: [
          Icon(
            icon,
            color: healthy ? green : red,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: healthy ? green : red,
              fontWeight: FontWeight.w800,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Widget _safetyStatusCard() {
    final safe =
        !emergencyStopActive &&
        tradingAllowed &&
        safetyConnectionHealthy;

    final color = safe ? green : red;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(16),
        border: Border.all(
          color: color.withOpacity(.35),
        ),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Icon(
                safe
                    ? Icons.verified_user_outlined
                    : Icons.gpp_bad_outlined,
                color: color,
                size: 30,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    Text(
                      safe
                          ? 'SAFETY OK'
                          : 'SAFETY BLOCKED',
                      style: TextStyle(
                        color: color,
                        fontWeight:
                            FontWeight.w800,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      emergencyStopActive
                          ? 'Emergency stop is active.'
                          : tradingAllowed
                              ? 'Trading permission is currently allowed.'
                              : 'Trading permission is currently blocked.',
                      style: const TextStyle(
                        color: muted,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 16),

          _safetyRow(
            'Trading permission',
            tradingAllowed
                ? 'ALLOWED'
                : 'BLOCKED',
            tradingAllowed,
          ),

          _safetyRow(
            'Emergency stop',
            emergencyStopActive
                ? 'ACTIVE'
                : 'INACTIVE',
            !emergencyStopActive,
          ),

          _safetyRow(
            'Safety connection',
            safetyConnectionHealthy
                ? 'HEALTHY'
                : 'UNHEALTHY',
            safetyConnectionHealthy,
          ),

          const SizedBox(height: 10),

          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Reason: $safetyReason',
              style: const TextStyle(
                color: muted,
                fontSize: 11,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _safetyRow(
    String label,
    String value,
    bool healthy,
  ) {
    return Padding(
      padding: const EdgeInsets.only(
        bottom: 10,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                color: muted,
                fontSize: 12,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: healthy ? green : red,
              fontWeight: FontWeight.w800,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  Widget _emergencyControls() {
    final active = emergencyStopActive;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(16),
        border: Border.all(
          color: active
              ? red.withOpacity(.45)
              : border,
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                Icons.warning_amber_rounded,
                color: orange,
              ),
              SizedBox(width: 10),
              Text(
                'EMERGENCY CONTROL',
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),

          const SizedBox(height: 8),

          const Text(
            'Use the emergency stop to block new '
            'trading activity. It does not automatically '
            'close existing broker positions.',
            style: TextStyle(
              color: muted,
              fontSize: 12,
              height: 1.45,
            ),
          ),

          const SizedBox(height: 16),

          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed:
                  actionLoading || active
                      ? null
                      : _activateEmergencyStop,
              style: FilledButton.styleFrom(
                backgroundColor: red,
                foregroundColor: Colors.white,
                padding:
                    const EdgeInsets.symmetric(
                  vertical: 14,
                ),
              ),
              icon: actionLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child:
                          CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(
                      Icons.stop_circle_outlined,
                    ),
              label: Text(
                active
                    ? 'EMERGENCY STOP ACTIVE'
                    : 'ACTIVATE EMERGENCY STOP',
              ),
            ),
          ),

          if (active) ...[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: actionLoading
                    ? null
                    : _resetEmergencyStop,
                style: OutlinedButton.styleFrom(
                  foregroundColor: gold,
                  side: const BorderSide(
                    color: gold,
                  ),
                  padding:
                      const EdgeInsets.symmetric(
                    vertical: 14,
                  ),
                ),
                icon: const Icon(
                  Icons.lock_open_outlined,
                ),
                label: const Text(
                  'RESET EMERGENCY STOP',
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _environmentCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(16),
        border: Border.all(
          color: border,
        ),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.developer_board_outlined,
            color: gold,
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Text(
              'Environment',
              style: TextStyle(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          Text(
            environment.toUpperCase(),
            style: const TextStyle(
              color: gold,
              fontWeight: FontWeight.w800,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Widget _readOnlyNotice() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: gold.withOpacity(.07),
        borderRadius:
            BorderRadius.circular(16),
        border: Border.all(
          color: gold.withOpacity(.25),
        ),
      ),
      child: const Row(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.info_outline,
            color: gold,
          ),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'Safety controls are displayed here for '
              'operator visibility. RAYMOND remains '
              'paper-trading only until live execution '
              'is deliberately enabled and fully validated.',
              style: TextStyle(
                color: muted,
                fontSize: 12,
                height: 1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionTitle(String text) {
    return Text(
      text,
      style: const TextStyle(
        color: gold,
        fontSize: 12,
        fontWeight: FontWeight.w800,
        letterSpacing: 1.1,
      ),
    );
  }

  Widget _errorCard() {
    return Container(
      margin: const EdgeInsets.only(
        bottom: 14,
      ),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: red.withOpacity(.10),
        borderRadius:
            BorderRadius.circular(12),
        border: Border.all(
          color: red.withOpacity(.30),
        ),
      ),
      child: Text(
        error,
        style: const TextStyle(
          color: red,
        ),
      ),
    );
  }
}
