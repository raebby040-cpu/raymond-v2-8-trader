import 'package:flutter/material.dart';

import 'api_service.dart';

class PositionsPage extends StatefulWidget {
  const PositionsPage({
    super.key,
    required this.api,
  });

  final ApiService api;

  @override
  State<PositionsPage> createState() => _PositionsPageState();
}

class _PositionsPageState extends State<PositionsPage> {
  static const gold = Color(0xFFF5B82E);
  static const green = Color(0xFF00E59B);
  static const red = Color(0xFFFF5C6C);
  static const blue = Color(0xFF4DA3FF);
  static const background = Color(0xFF030B14);
  static const card = Color(0xFF091724);
  static const border = Color(0xFF17334D);
  static const muted = Color(0xFF8EA4B8);

  bool loading = true;
  String error = '';
  List<Map<String, dynamic>> positions = [];

  @override
  void initState() {
    super.initState();
    _loadPositions();
  }

  Future<void> _loadPositions() async {
    setState(() {
      loading = true;
      error = '';
    });

    try {
      final response = await widget.api.paperPositions(
        status: 'open',
        limit: 100,
      );

      final raw = response['positions'];
      final parsed = <Map<String, dynamic>>[];

      if (raw is List) {
        for (final item in raw) {
          if (item is Map) {
            parsed.add(Map<String, dynamic>.from(item));
          }
        }
      }

      if (!mounted) return;

      setState(() {
        positions = parsed;
        loading = false;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        loading = false;
        error = 'Unable to load RAYMOND paper positions.';
      });
    }
  }

  double? _optionalNumber(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    return double.tryParse('$value');
  }

  double _number(dynamic value) {
    return _optionalNumber(value) ?? 0.0;
  }

  bool _bool(dynamic value) {
    if (value is bool) return value;

    final text = '$value'.toLowerCase().trim();

    return text == 'true' ||
        text == '1' ||
        text == 'yes';
  }

  String _text(
    dynamic value, [
    String fallback = '--',
  ]) {
    if (value == null) return fallback;

    final text = '$value'.trim();

    return text.isEmpty ? fallback : text;
  }

  String _price(dynamic value) {
    final number = _optionalNumber(value);

    if (number == null) return '--';

    return number.toStringAsFixed(2);
  }

  String _quantity(dynamic value) {
    final number = _optionalNumber(value);

    if (number == null) return '--';

    return number.toStringAsFixed(2);
  }

  String _percent(dynamic value) {
    final number = _optionalNumber(value);

    if (number == null) return '--';

    return '${number >= 0 ? '+' : ''}'
        '${number.toStringAsFixed(2)}%';
  }

  String _money(dynamic value) {
    final number = _optionalNumber(value);

    if (number == null) return '--';

    return '${number >= 0 ? '+' : '-'}'
        '\$${number.abs().toStringAsFixed(2)}';
  }

  String _r(dynamic value) {
    final number = _optionalNumber(value);

    if (number == null) return '--';

    return '${number >= 0 ? '+' : ''}'
        '${number.toStringAsFixed(2)}R';
  }

  String _date(dynamic value) {
    if (value == null) return '--';

    final parsed = DateTime.tryParse('$value');

    if (parsed == null) {
      return _text(value);
    }

    final local = parsed.toLocal();

    final hh = local.hour.toString().padLeft(2, '0');
    final mm = local.minute.toString().padLeft(2, '0');

    return '${local.year}-'
        '${local.month.toString().padLeft(2, '0')}-'
        '${local.day.toString().padLeft(2, '0')} '
        '$hh:$mm';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: background,
      child: RefreshIndicator(
        onRefresh: _loadPositions,
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
                    'PAPER POSITIONS',
                    style: TextStyle(
                      fontSize: 25,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: loading ? null : _loadPositions,
                  icon: const Icon(Icons.refresh),
                  tooltip: 'Refresh positions',
                ),
              ],
            ),
            const Text(
              'Authoritative RAYMOND persistent trade state',
              style: TextStyle(
                color: muted,
              ),
            ),
            const SizedBox(height: 16),
            _modeCard(),
            const SizedBox(height: 14),
            _summaryCard(),
            const SizedBox(height: 14),
            if (error.isNotEmpty) _errorCard(),
            if (loading)
              const Padding(
                padding: EdgeInsets.only(top: 60),
                child: Center(
                  child: CircularProgressIndicator(),
                ),
              )
            else if (positions.isEmpty)
              _emptyCard()
            else
              ...positions.map(_positionCard),
          ],
        ),
      ),
    );
  }

  Widget _modeCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: border),
      ),
      child: const Row(
        children: [
          Icon(
            Icons.shield_outlined,
            color: gold,
          ),
          SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'PAPER MODE • READ ONLY',
                  style: TextStyle(
                    color: gold,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  'These are RAYMOND paper positions. '
                  'No MT5 or broker orders are used here.',
                  style: TextStyle(
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

  Widget _summaryCard() {
    final openCount = positions.length;

    var pnl = 0.0;
    var positive = 0;
    var negative = 0;

    for (final position in positions) {
      final value = _number(position['pnl']);

      pnl += value;

      if (value > 0) positive++;
      if (value < 0) negative++;
    }

    final pnlColor = pnl >= 0 ? green : red;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: border),
      ),
      child: Row(
        children: [
          Expanded(
            child: _summaryValue(
              'OPEN',
              '$openCount',
              blue,
            ),
          ),
          Expanded(
            child: _summaryValue(
              'P/L',
              _money(pnl),
              pnlColor,
            ),
          ),
          Expanded(
            child: _summaryValue(
              'WINNING',
              '$positive',
              green,
            ),
          ),
          Expanded(
            child: _summaryValue(
              'LOSING',
              '$negative',
              red,
            ),
          ),
        ],
      ),
    );
  }

  Widget _summaryValue(
    String label,
    String value,
    Color color,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: muted,
            fontSize: 9,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 15,
            fontWeight: FontWeight.w800,
          ),
        ),
      ],
    );
  }

  Widget _positionCard(
    Map<String, dynamic> position,
  ) {
    final direction = _text(
      position['direction'] ??
          position['type_name'] ??
          position['type'],
      'WAIT',
    ).toUpperCase();

    final isBuy = direction == 'BUY';

    final directionColor = isBuy ? green : red;

    final symbol = _text(
      position['symbol'],
      'XAUUSD',
    );

    final status = _text(
      position['status'],
      'open',
    ).toUpperCase();

    final pnl = _number(position['pnl']);

    final pnlColor = pnl >= 0 ? green : red;

    final breakEven = _bool(
      position['break_even_applied'],
    );

    final partial = _bool(
      position['partial_close_applied'],
    );

    final trailing = _bool(
      position['trailing_active'],
    );

    final entry = _optionalNumber(
      position['entry_price'],
    );

    final current = _optionalNumber(
      position['current_price'],
    );

    final stop = _optionalNumber(
      position['current_stop_loss'] ??
          position['stop_loss'],
    );

    final tp1 = _optionalNumber(
      position['take_profit_1'] ??
          position['take_profit'],
    );

    final tp2 = _optionalNumber(
      position['take_profit_2'],
    );

    final currentR = position['current_r'];

    final quantity =
        position['remaining_quantity'] ??
            position['quantity'];

    return Container(
      margin: const EdgeInsets.only(
        bottom: 14,
      ),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: directionColor.withValues(
            alpha: .38,
          ),
        ),
      ),
      child: ExpansionTile(
        initiallyExpanded: true,
        tilePadding: const EdgeInsets.fromLTRB(
          16,
          8,
          16,
          8,
        ),
        childrenPadding: const EdgeInsets.fromLTRB(
          16,
          0,
          16,
          16,
        ),
        iconColor: muted,
        collapsedIconColor: muted,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: 10,
                vertical: 6,
              ),
              decoration: BoxDecoration(
                color: directionColor.withValues(
                  alpha: .12,
                ),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                direction,
                style: TextStyle(
                  color: directionColor,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                symbol,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            Text(
              _money(pnl),
              style: TextStyle(
                color: pnlColor,
                fontWeight: FontWeight.w800,
                fontSize: 16,
              ),
            ),
          ],
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 5),
          child: Text(
            '$status  •  '
            '${_r(currentR)}  •  '
            '${_percent(position['pnl_percent'])}',
            style: const TextStyle(
              color: muted,
              fontSize: 11,
            ),
          ),
        ),
        children: [
          _priceMap(
            direction: direction,
            entry: entry,
            current: current,
            stop: stop,
            tp1: tp1,
            tp2: tp2,
          ),
          const SizedBox(height: 16),
          _sectionTitle('TRADE LEVELS'),
          const SizedBox(height: 8),
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
                  _quantity(quantity),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
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
                  'TP1',
                  _price(tp1),
                ),
              ),
              Expanded(
                child: _detail(
                  'TP2',
                  _price(tp2),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _sectionTitle('PERFORMANCE'),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: _detail(
                  'P/L',
                  _money(pnl),
                  valueColor: pnlColor,
                ),
              ),
              Expanded(
                child: _detail(
                  'P/L %',
                  _percent(
                    position['pnl_percent'],
                  ),
                  valueColor: pnlColor,
                ),
              ),
              Expanded(
                child: _detail(
                  'CURRENT R',
                  _r(currentR),
                  valueColor: pnlColor,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _sectionTitle('MANAGEMENT'),
          const SizedBox(height: 8),
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
                'PARTIAL CLOSE',
                partial,
                gold,
              ),
              _stateChip(
                'TRAILING',
                trailing,
                blue,
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _detail(
                  'MANAGEMENT',
                  _text(
                    position['management_status'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'LAST ACTION',
                  _text(
                    position[
                        'last_management_action'],
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _detail(
                  'OPENED',
                  _date(
                    position['opened_at'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'TRADE ID',
                  _text(
                    position['trade_id'] ??
                        position['position_id'],
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _sectionTitle('RAYMOND CONTEXT'),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: _detail(
                  'REGIME',
                  _text(
                    position['regime'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'SETUP',
                  _text(
                    position['setup'],
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _detail(
                  'TECH SCORE',
                  _text(
                    position['technical_score'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'CONFLUENCE',
                  _text(
                    position['confluence'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'CONFIDENCE',
                  _text(
                    position['confidence'],
                  ),
                ),
              ),
            ],
          ),
          if (_text(
                position['trade_thesis'],
                '',
              ).isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: background,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: border,
                ),
              ),
              child: Text(
                _text(
                  position['trade_thesis'],
                ),
                style: const TextStyle(
                  color: muted,
                  fontSize: 12,
                  height: 1.4,
                ),
              ),
            ),
          ],
          const SizedBox(height: 14),
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
    required double? tp1,
    required double? tp2,
  }) {
    final values = <double?>[
      entry,
      current,
      stop,
      tp1,
      tp2,
    ].whereType<double>().toList();

    if (values.length < 2) {
      return Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: border,
          ),
        ),
        child: const Text(
          'Price map unavailable for this position.',
          style: TextStyle(
            color: muted,
            fontSize: 12,
          ),
        ),
      );
    }

    final minValue = values.reduce(
      (a, b) => a < b ? a : b,
    );

    final maxValue = values.reduce(
      (a, b) => a > b ? a : b,
    );

    final span =
        (maxValue - minValue).abs() < 0.000001
            ? 1.0
            : maxValue - minValue;

    double location(double? value) {
      if (value == null) return 0.0;

      return ((value - minValue) / span)
          .clamp(0.0, 1.0);
    }

    Widget marker(
      String label,
      double? value,
      Color color,
    ) {
      if (value == null) {
        return const SizedBox.shrink();
      }

      return Positioned(
        left: location(value) * 100,
        top: 0,
        child: Transform.translate(
          offset: const Offset(-12, 0),
          child: Column(
            children: [
              Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  color: color,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  color: color,
                  fontSize: 9,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Text(
                value.toStringAsFixed(2),
                style: const TextStyle(
                  color: muted,
                  fontSize: 8,
                ),
              ),
            ],
          ),
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        return Container(
          height: 82,
          padding: const EdgeInsets.symmetric(
            horizontal: 8,
            vertical: 8,
          ),
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: border,
            ),
          ),
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              Positioned(
                left: 0,
                right: 0,
                top: 12,
                child: Container(
                  height: 4,
                  decoration: BoxDecoration(
                    color: border,
                    borderRadius:
                        BorderRadius.circular(4),
                  ),
                ),
              ),
              Positioned(
                left: 0,
                right: 0,
                top: 12,
                child: FractionallySizedBox(
                  alignment:
                      direction == 'BUY'
                          ? Alignment.centerLeft
                          : Alignment.centerRight,
                  widthFactor: .5,
                  child: Container(
                    height: 4,
                    decoration: BoxDecoration(
                      color:
                          direction == 'BUY'
                              ? green
                              : red,
                      borderRadius:
                          BorderRadius.circular(4),
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
                'TP1',
                tp1,
                green,
              ),
              marker(
                'TP2',
                tp2,
                blue,
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
            ],
          ),
        );
      },
    );
  }

  Widget _sectionTitle(String title) {
    return Text(
      title,
      style: const TextStyle(
        color: gold,
        fontSize: 11,
        fontWeight: FontWeight.w800,
        letterSpacing: 1.1,
      ),
    );
  }

  Widget _stateChip(
    String label,
    bool active,
    Color color,
  ) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: 10,
        vertical: 7,
      ),
      decoration: BoxDecoration(
        color: active
            ? color.withValues(alpha: .12)
            : background,
        borderRadius: BorderRadius.circular(9),
        border: Border.all(
          color: active
              ? color.withValues(alpha: .45)
              : border,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            active
                ? Icons.check_circle
                : Icons.radio_button_unchecked,
            size: 14,
            color: active ? color : muted,
          ),
          const SizedBox(width: 6),
          Text(
            '$label: ${active ? 'ON' : 'OFF'}',
            style: TextStyle(
              color: active ? color : muted,
              fontSize: 10,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _safetyStrip() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: gold.withValues(alpha: .07),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: gold.withValues(alpha: .22),
        ),
      ),
      child: const Wrap(
        spacing: 10,
        runSpacing: 6,
        children: [
          Text(
            'PAPER ONLY',
            style: TextStyle(
              color: gold,
              fontSize: 10,
              fontWeight: FontWeight.bold,
            ),
          ),
          Text(
            'READ ONLY',
            style: TextStyle(
              color: gold,
              fontSize: 10,
              fontWeight: FontWeight.bold,
            ),
          ),
          Text(
            'LIVE OFF',
            style: TextStyle(
              color: green,
              fontSize: 10,
              fontWeight: FontWeight.bold,
            ),
          ),
          Text(
            'BROKER OFF',
            style: TextStyle(
              color: green,
              fontSize: 10,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _detail(
    String label,
    String value, {
    Color? valueColor,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: muted,
            fontSize: 9,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          value,
          style: TextStyle(
            color: valueColor,
            fontSize: 13,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }

  Widget _emptyCard() {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: border,
        ),
      ),
      child: const Column(
        children: [
          Icon(
            Icons.swap_vert_circle_outlined,
            size: 48,
            color: muted,
          ),
          SizedBox(height: 12),
          Text(
            'No open paper positions',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: 6),
          Text(
            'When RAYMOND accepts a paper trade, '
            'the persistent position will appear here.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: muted,
            ),
          ),
        ],
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
        color: red.withValues(alpha: .10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: red.withValues(alpha: .30),
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
