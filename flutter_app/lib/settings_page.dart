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
  static const Color gold = Color(0xFFF5B82E);
  static const Color green = Color(0xFF00E59B);
  static const Color red = Color(0xFFFF5C6C);
  static const Color orange = Color(0xFFFFA726);
  static const Color background = Color(0xFF030B14);
  static const Color card = Color(0xFF091724);
  static const Color border = Color(0xFF17334D);
  static const Color muted = Color(0xFF8EA4B8);

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
        // The page remains usable if admin status is temporarily unavailable.
      }

      final dynamic safetyRaw = status['safety'];

      final Map<String, dynamic> safety =
          safetyRaw is Map<String, dynamic>
              ? safetyRaw
              : safetyRaw is Map
                  ? Map<String, dynamic>.from(safetyRaw)
                  : <String, dynamic>{};

      if (!mounted) {
        return;
      }

      setState(() {
        backendOnline =
            health['status'] == 'healthy' ||
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
            '${safety['reason'] ?? '--'}';

        loading = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        loading = false;
        backendOnline = false;
        error = 'Unable to load system safety status.';
      });
    }
  }

  Future<void> _activateEmergencyStop() async {
    final bool confirmed =
        await _confirmEmergencyStop();

    if (!confirmed) {
      return;
    }

    if (!mounted) {
      return;
    }

    setState(() {
      actionLoading = true;
      error = '';
    });

    try {
      await widget.api.activateEmergencyStop();

      if (!mounted) {
        return;
      }

      setState(() {
        emergencyStopActive = true;
        tradingAllowed = false;
        actionLoading = false;
      });

      await _loadStatus();

      if (!mounted) {
        return;
      }

      _showMessage(
        'Emergency stop activated. New trading is blocked.',
        isError: false,
      );
    } catch (_) {
      if (!mounted) {
        return;
      }

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
    final bool confirmed =
        await _confirmReset();

    if (!confirmed) {
      return;
    }

    if (!mounted) {
      return;
    }

    setState(() {
      actionLoading = true;
      error = '';
    });

    try {
      await widget.api.resetEmergencyStop();

      if (!mounted) {
        return;
      }

      setState(() {
        actionLoading = false;
      });

      await _loadStatus();

      if (!mounted) {
        return;
      }

      _showMessage(
        'Emergency stop reset request sent.',
        isError: false,
      );
    } catch (_) {
      if (!mounted) {
        return;
      }

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
    final bool? result = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
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
            'This will block new trading activity '
            'through the RAYMOND safety manager.\n\n'
            'It does not automatically close existing '
            'broker positions.',
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
    final bool? result = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
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
            'trading to become active. The backend still '
            'requires a healthy connection and safe conditions.',
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
        backgroundColor:
            isError ? red : green,
        content: Text(
          message,
          style: TextStyle(
            color:
                isError ? Colors.white : Colors.black,
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
                value:
                    backendOnline
                        ? 'ONLINE'
                        : 'OFFLINE',
                healthy: backendOnline,
              ),

              _statusCard(
                icon: Icons.cable_outlined,
                title: 'MT5 Connection',
                value:
                    mt5Connected
                        ? 'CONNECTED'
                        : 'DISCONNECTED',
                healthy: mt5Connected,
              ),

              _statusCard(
                icon: Icons.show_chart_outlined,
                title: 'Market Feed',
                value:
                    marketFeedHealthy
                        ? 'HEALTHY'
                        : 'UNAVAILABLE',
                healthy: marketFeedHealthy,
              ),

              _statusCard(
                icon: Icons.storage_outlined,
                title: 'Database',
                value:
                    dbConnected
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
    final bool safe = !liveTradingEnabled;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(16),
        border: Border.all(
          color:
              safe
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
                    color:
                        safe ? green : red,
                    fontWeight:
                        FontWeight.w800,
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
        borderRadius:
            BorderRadius.circular(16),
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
            icon:
                Icons.account_balance_outlined,
            title: 'Live Trading',
            subtitle:
                'Real broker order execution',
            active: liveTradingEnabled,
            activeText:
                liveTradingEnabled
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
    final Color color =
        dangerous && active
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
                  fontWeight:
                      FontWeight.w700,
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
          padding:
              const EdgeInsets.symmetric(
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
              fontWeight:
                  FontWeight.bold,
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
      margin:
          const EdgeInsets.only(
        bottom: 10,
      ),
      padding:
          const EdgeInsets.all(14),
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
            color:
                healthy ? green : red,
          ),

          const SizedBox(width: 12),

          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                fontWeight:
                    FontWeight.w700,
              ),
            ),
          ),

          Text(
            value,
            style: TextStyle(
              color:
                  healthy ? green : red,
              fontWeight:
                  FontWeight.w800,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Widget _safetyStatusCard() {
    final bool safe =
        safetyConnectionHealthy &&
        tradingAllowed &&
        !emergencyStopActive;

    final Color statusColor =
        safe ? green : red;

    final String statusText =
        emergencyStopActive
            ? 'EMERGENCY STOP ACTIVE'
            : tradingAllowed
                ? 'TRADING ALLOWED'
                : 'TRADING BLOCKED';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(16),
        border: Border.all(
          color:
              statusColor.withOpacity(.35),
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                safe
                    ? Icons.verified_user_outlined
                    : Icons.gpp_maybe_outlined,
                color: statusColor,
                size: 28,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  statusText,
                  style: TextStyle(
                    color: statusColor,
                    fontWeight:
                        FontWeight.w800,
                    fontSize: 15,
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 14),

          _safetyRow(
            'Safety Connection',
            safetyConnectionHealthy
                ? 'HEALTHY'
                : 'UNAVAILABLE',
            safetyConnectionHealthy,
          ),

          _safetyRow(
            'Trading Permission',
            tradingAllowed
                ? 'ALLOWED'
                : 'BLOCKED',
            tradingAllowed,
          ),

          _safetyRow(
            'Emergency Stop',
            emergencyStopActive
                ? 'ACTIVE'
                : 'INACTIVE',
            !emergencyStopActive,
          ),

          const SizedBox(height: 8),

          Text(
            'Reason: $safetyReason',
            style: const TextStyle(
              color: muted,
              fontSize: 11,
              height: 1.4,
            ),
          ),
        ],
      ),
    );
  }

  Widget _safetyRow(
    String title,
    String value,
    bool healthy,
  ) {
    return Padding(
      padding:
          const EdgeInsets.symmetric(
        vertical: 5,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                color: muted,
                fontSize: 12,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color:
                  healthy ? green : red,
              fontWeight:
                  FontWeight.w700,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  Widget _emergencyControls() {
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
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.stretch,
        children: [
          const Text(
            'EMERGENCY CONTROLS',
            style: TextStyle(
              fontWeight:
                  FontWeight.w800,
              fontSize: 14,
            ),
          ),

          const SizedBox(height: 6),

          const Text(
            'Use these controls only when necessary.',
            style: TextStyle(
              color: muted,
              fontSize: 11,
            ),
          ),

          const SizedBox(height: 14),

          SizedBox(
            height: 48,
            child: FilledButton.icon(
              onPressed:
                  actionLoading
                      ? null
                      : _activateEmergencyStop,
              style:
                  FilledButton.styleFrom(
                backgroundColor: red,
                foregroundColor:
                    Colors.white,
              ),
              icon: actionLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child:
                          CircularProgressIndicator(
                        strokeWidth: 2,
                      ),
                    )
                  : const Icon(
                      Icons.stop_circle_outlined,
                    ),
              label: const Text(
                'ACTIVATE EMERGENCY STOP',
                style: TextStyle(
                  fontWeight:
                      FontWeight.w800,
                ),
              ),
            ),
          ),

          const SizedBox(height: 10),

          SizedBox(
            height: 46,
            child: OutlinedButton.icon(
              onPressed:
                  actionLoading ||
                          !emergencyStopActive
                      ? null
                      : _resetEmergencyStop,
              icon: const Icon(
                Icons.restart_alt,
              ),
              label: const Text(
                'RESET EMERGENCY STOP',
              ),
            ),
          ),
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
            Icons.settings_suggest_outlined,
            color: orange,
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Text(
              'Environment',
              style: TextStyle(
                fontWeight:
                    FontWeight.w700,
              ),
            ),
          ),
          Text(
            environment,
            style: const TextStyle(
              color: muted,
              fontWeight:
                  FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  Widget _readOnlyNotice() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: gold.withOpacity(.08),
        borderRadius:
            BorderRadius.circular(14),
        border: Border.all(
          color: gold.withOpacity(.25),
        ),
      ),
      child: const Row(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.lock_outline,
            color: gold,
            size: 20,
          ),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              'Live broker execution remains disabled. '
              'This dashboard is intended for safe monitoring, '
              'paper trading and system controls.',
              style: TextStyle(
                color: muted,
                fontSize: 11,
                height: 1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionTitle(String title) {
    return Text(
      title,
      style: const TextStyle(
        color: muted,
        fontSize: 11,
        fontWeight: FontWeight.w800,
        letterSpacing: 1.2,
      ),
    );
  }

  Widget _errorCard() {
    return Container(
      margin:
          const EdgeInsets.only(
        bottom: 14,
      ),
      padding:
          const EdgeInsets.all(12),
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
