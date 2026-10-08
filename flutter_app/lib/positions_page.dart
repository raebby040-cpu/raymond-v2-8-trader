import 'dart:async';

import 'package:flutter/material.dart';

import 'canonical_api_service.dart';
import 'api_service.dart';

class PositionsPage extends StatefulWidget {
  const PositionsPage({
    super.key,
    required this.api,
  });

  final ApiService api;

  @override
  State<PositionsPage> createState() =>
      _PositionsPageState();
}

class _PositionsPageState
    extends State<PositionsPage> {
  static const gold =
      Color(0xFFF5B82E);

  static const green =
      Color(0xFF00E59B);

  static const red =
      Color(0xFFFF5C6C);

  static const blue =
      Color(0xFF4DA3FF);

  static const background =
      Color(0xFF030B14);

  static const card =
      Color(0xFF091724);

  static const border =
      Color(0xFF17334D);

  static const muted =
      Color(0xFF8EA4B8);

  late final CanonicalApiService
      canonicalApi;

  Timer? _refreshTimer;

  bool loading = true;
  bool requestInFlight = false;

  String error = '';

  String selectedMode = 'paper';

  List<Map<String, dynamic>>
      positions = [];

  Map<String, dynamic>?
      account;

  @override
  void initState() {
    super.initState();

    canonicalApi =
        CanonicalApiService();

    _loadState();

    _refreshTimer =
        Timer.periodic(
      const Duration(seconds: 15),
      (_) {
        if (!mounted ||
            requestInFlight) {
          return;
        }

        _loadState();
      },
    );
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _refreshTimer = null;

    super.dispose();
  }

  Future<void> _loadState() async {
    if (requestInFlight) {
      return;
    }

    requestInFlight = true;

    if (mounted) {
      setState(() {
        loading =
            positions.isEmpty;
        error = '';
      });
    }

    try {
      final positionResponse =
          await canonicalApi.openPositions(
        mode: selectedMode,
        symbol: 'XAUUSD',
        limit: 100,
      );

      Map<String, dynamic>?
          accountResponse;

      try {
        final rawAccount =
            await canonicalApi.account(
          mode: selectedMode,
        );

        final raw =
            rawAccount['account'];

        if (raw is Map) {
          accountResponse =
              Map<String, dynamic>.from(
            raw,
          );
        }
      } catch (_) {
        accountResponse = null;
      }

      if (!mounted) {
        return;
      }

      setState(() {
        positions =
            positionResponse;

        account =
            accountResponse;

        loading = false;
        error = '';
      });
    } catch (_) {
      /*
       * PAPER compatibility fallback.
       *
       * The canonical endpoint is the preferred source.
       * If the canonical API is temporarily unavailable,
       * retain the existing persistent paper endpoint so
       * the screen does not become unusable.
       */
      if (selectedMode == 'paper') {
        try {
          final fallback =
              await widget.api.paperPositions(
            status: 'open',
            limit: 100,
          );

          final raw =
              fallback['positions'];

          final parsed =
              <Map<String, dynamic>>[];

          if (raw is List) {
            for (final item in raw) {
              if (item is Map) {
                parsed.add(
                  Map<String, dynamic>.from(
                    item,
                  ),
                );
              }
            }
          }

          if (!mounted) {
            return;
          }

          setState(() {
            positions = parsed;
            account = null;
            loading = false;
            error =
                'Canonical state temporarily unavailable. '
                'Showing PAPER state.';
          });

          return;
        } catch (_) {}
      }

      if (!mounted) {
        return;
      }

      setState(() {
        loading = false;
        error =
            'Unable to load canonical '
            '${selectedMode.toUpperCase()} positions.';
      });
    } finally {
      requestInFlight = false;
    }
  }

  void _selectMode(
    String mode,
  ) {
    if (mode == selectedMode) {
      return;
    }

    setState(() {
      selectedMode = mode;
      positions = [];
      account = null;
      loading = true;
      error = '';
    });

    _loadState();
  }

  double? _numberOrNull(
    dynamic value,
  ) {
    if (value == null) {
      return null;
    }

    if (value is num) {
      return value.toDouble();
    }

    return double.tryParse(
      '$value',
    );
  }

  double _number(
    dynamic value,
  ) {
    return _numberOrNull(value) ?? 0.0;
  }

  bool _bool(
    dynamic value,
  ) {
    if (value is bool) {
      return value;
    }

    final text =
        '$value'.toLowerCase().trim();

    return text == 'true' ||
        text == '1' ||
        text == 'yes';
  }

  String _text(
    dynamic value, [
    String fallback = '--',
  ]) {
    if (value == null) {
      return fallback;
    }

    final text =
        '$value'.trim();

    if (text.isEmpty) {
      return fallback;
    }

    return text;
  }

  String _money(
    dynamic value,
  ) {
    final number =
        _numberOrNull(value);

    if (number == null) {
      return '--';
    }

    return '${number >= 0 ? '+' : '-'}'
        '\$${number.abs().toStringAsFixed(2)}';
  }

  String _price(
    dynamic value,
  ) {
    final number =
        _numberOrNull(value);

    if (number == null) {
      return '--';
    }

    return number.toStringAsFixed(2);
  }

  String _volume(
    dynamic value,
  ) {
    final number =
        _numberOrNull(value);

    if (number == null) {
      return '--';
    }

    return number.toStringAsFixed(2);
  }

  String _percent(
    dynamic value,
  ) {
    final number =
        _numberOrNull(value);

    if (number == null) {
      return '--';
    }

    return '${number >= 0 ? '+' : ''}'
        '${number.toStringAsFixed(2)}%';
  }

  String _r(
    dynamic value,
  ) {
    final number =
        _numberOrNull(value);

    if (number == null) {
      return '--';
    }

    return '${number >= 0 ? '+' : ''}'
        '${number.toStringAsFixed(2)}R';
  }

  String _date(
    dynamic value,
  ) {
    if (value == null) {
      return '--';
    }

    final parsed =
        DateTime.tryParse(
      '$value',
    );

    if (parsed == null) {
      return _text(value);
    }

    final local =
        parsed.toLocal();

    final year =
        local.year.toString();

    final month =
        local.month
            .toString()
            .padLeft(2, '0');

    final day =
        local.day
            .toString()
            .padLeft(2, '0');

    final hour =
        local.hour
            .toString()
            .padLeft(2, '0');

    final minute =
        local.minute
            .toString()
            .padLeft(2, '0');

    return '$year-$month-$day '
        '$hour:$minute';
  }

  @override
  Widget build(
    BuildContext context,
  ) {
    return Container(
      color: background,
      child: RefreshIndicator(
        onRefresh: _loadState,
        child: ListView(
          padding:
              const EdgeInsets.fromLTRB(
            16,
            12,
            16,
            28,
          ),
          children: [
            _header(),

            const SizedBox(
              height: 14,
            ),

            _modeSelector(),

            const SizedBox(
              height: 14,
            ),

            _accountCard(),

            const SizedBox(
              height: 14,
            ),

            if (error.isNotEmpty)
              _errorCard(),

            if (loading)
              const Padding(
                padding:
                    EdgeInsets.only(
                  top: 60,
                ),
                child: Center(
                  child:
                      CircularProgressIndicator(),
                ),
              )
            else if (positions.isEmpty)
              _emptyCard()
            else
              ...positions.map(
                _positionCard,
              ),
          ],
        ),
      ),
    );
  }

  Widget _header() {
    final mode =
        selectedMode.toUpperCase();

    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment:
                CrossAxisAlignment.start,
            children: [
              const Text(
                'TRADING POSITIONS',
                style: TextStyle(
                  fontSize: 25,
                  fontWeight:
                      FontWeight.w800,
                ),
              ),
              const SizedBox(
                height: 4,
              ),
              Text(
                'Canonical $mode state',
                style:
                    const TextStyle(
                  color: muted,
                ),
              ),
              const SizedBox(
                height: 3,
              ),
              Text(
                requestInFlight
                    ? 'Synchronizing...'
                    : 'Auto-refresh: 15 seconds',
                style:
                    const TextStyle(
                  color: muted,
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ),
        IconButton(
          onPressed:
              requestInFlight
                  ? null
                  : _loadState,
          icon: const Icon(
            Icons.refresh,
          ),
          tooltip:
              'Refresh canonical state',
        ),
      ],
    );
  }

  Widget _modeSelector() {
    return Container(
      padding:
          const EdgeInsets.all(5),
      decoration:
          BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(
          14,
        ),
        border:
            Border.all(
          color: border,
        ),
      ),
      child: Row(
        children: [
          _modeButton(
            label: 'PAPER',
            mode: 'paper',
            icon:
                Icons.science_outlined,
          ),
          _modeButton(
            label: 'DEMO',
            mode: 'demo',
            icon:
                Icons.account_balance_outlined,
          ),
          _modeButton(
            label: 'LIVE',
            mode: 'live',
            icon:
                Icons.bolt_outlined,
          ),
        ],
      ),
    );
  }

  Widget _modeButton({
    required String label,
    required String mode,
    required IconData icon,
  }) {
    final active =
        selectedMode == mode;

    final live =
        mode == 'live';

    final color = live
        ? red
        : gold;

    return Expanded(
      child: GestureDetector(
        onTap: () {
          _selectMode(mode);
        },
        child: AnimatedContainer(
          duration:
              const Duration(
            milliseconds: 180,
          ),
          padding:
              const EdgeInsets.symmetric(
            vertical: 11,
          ),
          decoration:
              BoxDecoration(
            color: active
                ? color.withValues(
                    alpha: .14,
                  )
                : Colors.transparent,
            borderRadius:
                BorderRadius.circular(
              10,
            ),
            border: Border.all(
              color: active
                  ? color.withValues(
                      alpha: .45,
                    )
                  : Colors.transparent,
            ),
          ),
          child: Column(
            children: [
              Icon(
                icon,
                size: 18,
                color: active
                    ? color
                    : muted,
              ),
              const SizedBox(
                height: 4,
              ),
              Text(
                label,
                style:
                    TextStyle(
                  color: active
                      ? color
                      : muted,
                  fontSize: 11,
                  fontWeight:
                      FontWeight.w800,
                ),
              ),
              if (live)
                const Text(
                  'LOCKED',
                  style: TextStyle(
                    color: red,
                    fontSize: 8,
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _accountCard() {
    final currentAccount =
        account;

    final balance =
        currentAccount?['balance'];

    final equity =
        currentAccount?['equity'];

    final floating =
        currentAccount?['floating_pnl'];

    final freeMargin =
        currentAccount?['free_margin'];

    final open =
        currentAccount?[
            'open_positions'];

    final isLive =
        selectedMode == 'live';

    return Container(
      padding:
          const EdgeInsets.all(16),
      decoration:
          BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(
          16,
        ),
        border:
            Border.all(
          color: isLive
              ? red.withValues(
                  alpha: .30,
                )
              : border,
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${selectedMode.toUpperCase()} ACCOUNT',
                  style:
                      const TextStyle(
                    color: gold,
                    fontWeight:
                        FontWeight.w800,
                    letterSpacing: .8,
                  ),
                ),
              ),
              if (isLive)
                const Icon(
                  Icons.lock_outline,
                  color: red,
                  size: 18,
                )
              else
                const Icon(
                  Icons.verified_outlined,
                  color: green,
                  size: 18,
                ),
            ],
          ),

          const SizedBox(
            height: 14,
          ),

          Row(
            children: [
              Expanded(
                child: _accountMetric(
                  'BALANCE',
                  _money(
                    balance,
                  ),
                ),
              ),
              Expanded(
                child: _accountMetric(
                  'EQUITY',
                  _money(
                    equity,
                  ),
                ),
              ),
              Expanded(
                child: _accountMetric(
                  'FLOATING',
                  _money(
                    floating,
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(
            height: 12,
          ),

          Row(
            children: [
              Expanded(
                child: _accountMetric(
                  'OPEN',
                  _text(
                    open,
                    '0',
                  ),
                ),
              ),
              Expanded(
                child: _accountMetric(
                  'FREE MARGIN',
                  _money(
                    freeMargin,
                  ),
                ),
              ),
              Expanded(
                child: _accountMetric(
                  'CURRENCY',
                  _text(
                    currentAccount?[
                        'currency'],
                    'USD',
                  ),
                ),
              ),
            ],
          ),

          if (isLive) ...[
            const SizedBox(
              height: 12,
            ),
            Container(
              width: double.infinity,
              padding:
                  const EdgeInsets.all(
                10,
              ),
              decoration:
                  BoxDecoration(
                color: red.withValues(
                  alpha: .08,
                ),
                borderRadius:
                    BorderRadius.circular(
                  10,
                ),
                border:
                    Border.all(
                  color: red.withValues(
                    alpha: .25,
                  ),
                ),
              ),
              child: const Text(
                'LIVE execution remains locked. '
                'This screen is read-only.',
                style: TextStyle(
                  color: red,
                  fontSize: 11,
                  fontWeight:
                      FontWeight.w700,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _accountMetric(
    String label,
    String value,
  ) {
    return Column(
      crossAxisAlignment:
          CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style:
              const TextStyle(
            color: muted,
            fontSize: 9,
            fontWeight:
                FontWeight.bold,
          ),
        ),
        const SizedBox(
          height: 5,
        ),
        Text(
          value,
          style:
              const TextStyle(
            fontSize: 14,
            fontWeight:
                FontWeight.w800,
          ),
        ),
      ],
    );
  }

  Widget _positionCard(
    Map<String, dynamic> position,
  ) {
    final side =
        _text(
      position['side'],
      'unknown',
    ).toUpperCase();

    final isBuy =
        side == 'BUY';

    final sideColor =
        isBuy ? green : red;

    final symbol =
        _text(
      position['symbol'],
      'XAUUSD',
    );

    final pnl =
        _number(
      position['total_pnl'],
    );

    final currentR =
        position['current_r'];

    final entry =
        position['entry_price'];

    final current =
        position['current_price'];

    final stop =
        position['stop_loss'];

    final tp =
        position['take_profit'];

    final volume =
        position['volume'];

    final breakEven =
        _bool(
      position[
          'break_even_applied'],
    );

    final trailing =
        _bool(
      position[
          'trailing_active'],
    );

    final partial =
        _bool(
      position[
          'partial_close_applied'],
    );

    final pnlColor =
        pnl >= 0
            ? green
            : red;

    return Container(
      margin:
          const EdgeInsets.only(
        bottom: 14,
      ),
      padding:
          const EdgeInsets.all(16),
      decoration:
          BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(
          18,
        ),
        border:
            Border.all(
          color: sideColor.withValues(
            alpha: .38,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration:
                    BoxDecoration(
                  color:
                      sideColor.withValues(
                    alpha: .12,
                  ),
                  borderRadius:
                      BorderRadius.circular(
                    8,
                  ),
                ),
                child: Text(
                  side,
                  style:
                      TextStyle(
                    color: sideColor,
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),
              ),

              const SizedBox(
                width: 10,
              ),

              Expanded(
                child: Text(
                  symbol,
                  style:
                      const TextStyle(
                    fontSize: 18,
                    fontWeight:
                        FontWeight.w800,
                  ),
                ),
              ),

              Text(
                _money(pnl),
                style:
                    TextStyle(
                  color: pnlColor,
                  fontSize: 16,
                  fontWeight:
                      FontWeight.w800,
                ),
              ),
            ],
          ),

          const SizedBox(
            height: 6,
          ),

          Text(
            '${_text(position['status'], 'OPEN').toUpperCase()}  •  '
            '${_r(currentR)}  •  '
            '${_percent(position['pnl_percent'])}',
            style:
                const TextStyle(
              color: muted,
              fontSize: 11,
            ),
          ),

          const SizedBox(
            height: 16,
          ),

          _priceMap(
            direction: side,
            entry:
                _numberOrNull(entry),
            current:
                _numberOrNull(current),
            stop:
                _numberOrNull(stop),
            tp:
                _numberOrNull(tp),
          ),

          const SizedBox(
            height: 16,
          ),

          _sectionTitle(
            'TRADE',
          ),

          const SizedBox(
            height: 8,
          ),

          Row(
            children: [
              Expanded(
                child: _detail(
                  'ENTRY',
                  _price(entry),
                ),
              ),
              Expanded(
                child: _detail(
                  'CURRENT',
                  _price(current),
                ),
              ),
              Expanded(
                child: _detail(
                  'VOLUME',
                  _volume(volume),
                ),
              ),
            ],
          ),

          const SizedBox(
            height: 14,
          ),

          Row(
            children: [
              Expanded(
                child: _detail(
                  'STOP LOSS',
                  _price(stop),
                ),
              ),
              Expanded(
                child: _detail(
                  'TAKE PROFIT',
                  _price(tp),
                ),
              ),
              Expanded(
                child: _detail(
                  'CURRENT R',
                  _r(currentR),
                ),
              ),
            ],
          ),

          const SizedBox(
            height: 16,
          ),

          _sectionTitle(
            'MANAGEMENT',
          ),

          const SizedBox(
            height: 8,
          ),

          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _stateChip(
                'BREAK EVEN',
                breakEven,
                green,
              ),
              _stateChip(
                'TRAILING',
                trailing,
                blue,
              ),
              _stateChip(
                'PARTIAL CLOSE',
                partial,
                gold,
              ),
            ],
          ),

          const SizedBox(
            height: 12,
          ),

          Row(
            children: [
              Expanded(
                child: _detail(
                  'PROTECTION',
                  _text(
                    position[
                        'protection_status'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'RECONCILIATION',
                  _text(
                    position[
                        'reconciliation_status'],
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(
            height: 12,
          ),

          Row(
            children: [
              Expanded(
                child: _detail(
                  'BROKER',
                  _text(
                    position['broker'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'SERVER',
                  _text(
                    position['server'],
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(
            height: 12,
          ),

          Row(
            children: [
              Expanded(
                child: _detail(
                  'BROKER TICKET',
                  _text(
                    position[
                        'broker_position_ticket'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'OPENED',
                  _date(
                    position['opened_at'],
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(
            height: 14,
          ),

          _safetyStrip(),
        ],
      ),
    );
  }

  Widget _priceMap({
    required String direction,
    required double? entry,
    required double? current,
    required double? stop,
    required double? tp,
  }) {
    final values =
        <double?>[
      entry,
      current,
      stop,
      tp,
    ].whereType<double>().toList();

    if (values.length < 2) {
      return Container(
        width: double.infinity,
        padding:
            const EdgeInsets.all(
          12,
        ),
        decoration:
            BoxDecoration(
          color: background,
          borderRadius:
              BorderRadius.circular(
            12,
          ),
          border:
              Border.all(
            color: border,
          ),
        ),
        child: const Text(
          'Price map unavailable.',
          style: TextStyle(
            color: muted,
            fontSize: 12,
          ),
        ),
      );
    }

    final minValue =
        values.reduce(
      (a, b) =>
          a < b ? a : b,
    );

    final maxValue =
        values.reduce(
      (a, b) =>
          a > b ? a : b,
    );

    final span =
        (maxValue - minValue)
                    .abs() <
                0.000001
            ? 1.0
            : maxValue - minValue;

    double location(
      double? value,
    ) {
      if (value == null) {
        return 0.0;
      }

      return (
        (value - minValue) /
            span
      ).clamp(
        0.0,
        1.0,
      );
    }

    Widget marker(
      String label,
      double? value,
      Color color,
    ) {
      if (value == null) {
        return const SizedBox
            .shrink();
      }

      return Positioned(
        left:
            location(value) * 100,
        top: 0,
        child:
            Transform.translate(
          offset:
              const Offset(
            -12,
            0,
          ),
          child: Column(
            children: [
              Container(
                width: 22,
                height: 22,
                decoration:
                    BoxDecoration(
                  color: color,
                  shape:
                      BoxShape.circle,
                ),
              ),
              const SizedBox(
                height: 3,
              ),
              Text(
                label,
                style:
                    TextStyle(
                  color: color,
                  fontSize: 8,
                  fontWeight:
                      FontWeight.bold,
                ),
              ),
            ],
          ),
        ),
      );
    }

    return Container(
      height: 65,
      padding:
          const EdgeInsets.symmetric(
        horizontal: 8,
      ),
      decoration:
          BoxDecoration(
        color: background,
        borderRadius:
            BorderRadius.circular(
          12,
        ),
        border:
            Border.all(
          color: border,
        ),
      ),
      child: LayoutBuilder(
        builder:
            (
          context,
          constraints,
        ) {
          return Stack(
            clipBehavior:
                Clip.none,
            children: [
              Positioned(
                left: 0,
                right: 0,
                top: 18,
                child: Container(
                  height: 4,
                  decoration:
                      BoxDecoration(
                    color: border,
                    borderRadius:
                        BorderRadius
                            .circular(
                      4,
                    ),
                  ),
                ),
              ),
              marker(
                'SL',
                stop,
                red,
              ),
              marker(
                'ENTRY',
                entry,
                gold,
              ),
              marker(
                'NOW',
                current,
                Colors.white,
              ),
              marker(
                'TP',
                tp,
                green,
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _sectionTitle(
    String title,
  ) {
    return Text(
      title,
      style:
          const TextStyle(
        color: gold,
        fontSize: 11,
        fontWeight:
            FontWeight.w800,
        letterSpacing: 1.1,
      ),
    );
  }

  Widget _detail(
    String label,
    String value, {
    Color? valueColor,
  }) {
    return Column(
      crossAxisAlignment:
          CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style:
              const TextStyle(
            color: muted,
            fontSize: 9,
            fontWeight:
                FontWeight.bold,
          ),
        ),
        const SizedBox(
          height: 5,
        ),
        Text(
          value,
          style:
              TextStyle(
            color: valueColor,
            fontSize: 12,
            fontWeight:
                FontWeight.w700,
          ),
        ),
      ],
    );
  }

  Widget _stateChip(
    String label,
    bool active,
    Color color,
  ) {
    return Container(
      padding:
          const EdgeInsets.symmetric(
        horizontal: 10,
        vertical: 7,
      ),
      decoration:
          BoxDecoration(
        color: active
            ? color.withValues(
                alpha: .12,
              )
            : background,
        borderRadius:
            BorderRadius.circular(
          9,
        ),
        border:
            Border.all(
          color: active
              ? color.withValues(
                  alpha: .45,
                )
              : border,
        ),
      ),
      child: Row(
        mainAxisSize:
            MainAxisSize.min,
        children: [
          Icon(
            active
                ? Icons.check_circle
                : Icons
                    .radio_button_unchecked,
            size: 14,
            color: active
                ? color
                : muted,
          ),
          const SizedBox(
            width: 6,
          ),
          Text(
            '$label: '
            '${active ? 'ON' : 'OFF'}',
            style:
                TextStyle(
              color: active
                  ? color
                  : muted,
              fontSize: 10,
              fontWeight:
                  FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _safetyStrip() {
    if (selectedMode == 'live') {
      return Container(
        width: double.infinity,
        padding:
            const EdgeInsets.all(
          11,
        ),
        decoration:
            BoxDecoration(
          color: red.withValues(
            alpha: .08,
          ),
          borderRadius:
              BorderRadius.circular(
            11,
          ),
          border:
              Border.all(
            color: red.withValues(
              alpha: .25,
            ),
          ),
        ),
        child: const Text(
          'LIVE • READ ONLY • EXECUTION LOCKED',
          style: TextStyle(
            color: red,
            fontSize: 10,
            fontWeight:
                FontWeight.bold,
          ),
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding:
          const EdgeInsets.all(
        11,
      ),
      decoration:
          BoxDecoration(
        color: gold.withValues(
          alpha: .07,
        ),
        borderRadius:
            BorderRadius.circular(
          11,
        ),
        border:
            Border.all(
          color: gold.withValues(
            alpha: .20,
          ),
        ),
      ),
      child: Text(
        '${selectedMode.toUpperCase()} • '
        'CANONICAL STATE • READ ONLY',
        style:
            const TextStyle(
          color: gold,
          fontSize: 10,
          fontWeight:
              FontWeight.bold,
        ),
      ),
    );
  }

  Widget _emptyCard() {
    final isLive =
        selectedMode == 'live';

    return Container(
      padding:
          const EdgeInsets.all(
        26,
      ),
      decoration:
          BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(
          16,
        ),
        border:
            Border.all(
          color: isLive
              ? red.withValues(
                  alpha: .25,
                )
              : border,
        ),
      ),
      child: Column(
        children: [
          Icon(
            isLive
                ? Icons.lock_outline
                : Icons
                    .swap_vert_circle_outlined,
            size: 48,
            color:
                isLive ? red : muted,
          ),
          const SizedBox(
            height: 12,
          ),
          Text(
            isLive
                ? 'No LIVE canonical positions'
                : 'No open $selectedMode positions',
            style:
                const TextStyle(
              fontSize: 18,
              fontWeight:
                  FontWeight.bold,
            ),
            textAlign:
                TextAlign.center,
          ),
          const SizedBox(
            height: 7,
          ),
          Text(
            isLive
                ? 'LIVE execution remains locked. '
                  'The screen is read-only.'
                : 'Positions will appear here '
                  'when they exist in canonical state.',
            textAlign:
                TextAlign.center,
            style:
                const TextStyle(
              color: muted,
              height: 1.4,
            ),
          ),
        ],
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
          const EdgeInsets.all(
        12,
      ),
      decoration:
          BoxDecoration(
        color: red.withValues(
          alpha: .10,
        ),
        borderRadius:
            BorderRadius.circular(
          12,
        ),
        border:
            Border.all(
          color: red.withValues(
            alpha: .30,
          ),
        ),
      ),
      child: Text(
        error,
        style:
            const TextStyle(
          color: red,
        ),
      ),
    );
  }
}
