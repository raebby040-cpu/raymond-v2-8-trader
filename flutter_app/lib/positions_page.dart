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
      final response = await widget.api.marketPositions();

      final raw = response['positions'];

      final parsed = <Map<String, dynamic>>[];

      if (raw is List) {
        for (final item in raw) {
          if (item is Map) {
            parsed.add(
              Map<String, dynamic>.from(item),
            );
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
        error = 'Unable to load current positions.';
      });
    }
  }

  double _number(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }

    return double.tryParse('$value') ?? 0;
  }

  String _price(dynamic value) {
    final number = _number(value);

    if (number == 0) {
      return '--';
    }

    return number.toStringAsFixed(2);
  }

  String _volume(dynamic value) {
    final number = _number(value);

    if (number == 0) {
      return '--';
    }

    return number.toStringAsFixed(2);
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
            24,
          ),
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'POSITIONS',
                    style: TextStyle(
                      fontSize: 25,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: loading ? null : _loadPositions,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),

            const Text(
              'Current market positions',
              style: TextStyle(
                color: muted,
              ),
            ),

            const SizedBox(height: 16),

            _modeCard(),

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
                  'READ-ONLY',
                  style: TextStyle(
                    color: gold,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  'Live order execution is disabled.',
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

  Widget _positionCard(
    Map<String, dynamic> position,
  ) {
    final typeName =
        '${position['type_name'] ?? position['type'] ?? ''}'
            .toUpperCase();

    final isBuy = typeName == 'BUY';

    final profit = _number(
      position['profit'],
    );

    final profitPositive = profit >= 0;

    final symbol =
        '${position['symbol'] ?? 'XAUUSD'}';

    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isBuy
              ? green.withOpacity(.35)
              : red.withOpacity(.35),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: (isBuy ? green : red)
                      .withOpacity(.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  isBuy ? 'BUY' : 'SELL',
                  style: TextStyle(
                    color: isBuy ? green : red,
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
                '${profitPositive ? '+' : ''}'
                '\$${profit.toStringAsFixed(2)}',
                style: TextStyle(
                  color: profitPositive ? green : red,
                  fontWeight: FontWeight.bold,
                  fontSize: 17,
                ),
              ),
            ],
          ),

          const SizedBox(height: 18),

          Row(
            children: [
              Expanded(
                child: _detail(
                  'ENTRY',
                  _price(
                    position['price_open'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'CURRENT',
                  _price(
                    position['price_current'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'VOLUME',
                  _volume(
                    position['volume'],
                  ),
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
                  _price(
                    position['price_stop_loss'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'TAKE PROFIT',
                  _price(
                    position['price_take_profit'],
                  ),
                ),
              ),
              Expanded(
                child: _detail(
                  'TICKET',
                  '${position['ticket'] ?? '--'}',
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _detail(
    String label,
    String value,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: muted,
            fontSize: 10,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          value,
          style: const TextStyle(
            fontSize: 14,
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
        border: Border.all(color: border),
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
            'No open positions',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: 6),
          Text(
            'There are currently no open market positions.',
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
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: red.withOpacity(.10),
        borderRadius: BorderRadius.circular(12),
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
