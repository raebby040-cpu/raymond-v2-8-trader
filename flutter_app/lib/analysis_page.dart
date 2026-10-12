
import 'package:flutter/material.dart';
import 'api_service.dart';

/// RAYMOND market-analysis terminal.
///
/// Market analysis loads independently from paper positions.
/// If the positions endpoint fails, successful market analysis remains visible.
class AnalysisPage extends StatefulWidget {
  final ApiService api;

  const AnalysisPage({
    super.key,
    required this.api,
  });

  @override
  State<AnalysisPage> createState() => _AnalysisPageState();
}

class _AnalysisPageState extends State<AnalysisPage> {
  bool loading = true;
  String? error;
  String? positionsWarning;

  String symbol = 'XAUUSD';
  String timeframe = 'H1';

  Map<String, dynamic> analysis = <String, dynamic>{};
  List<Map<String, dynamic>> openPositions = <Map<String, dynamic>>[];

  @override
  void initState() {
    super.initState();
    _loadEverything();
  }

  Future<void> _loadEverything() async {
    if (!mounted) return;

    setState(() {
      loading = true;
      error = null;
      positionsWarning = null;
    });

    // Load market analysis first. Positions errors must not hide it.
    late final Map<String, dynamic> advisoryData;

    try {
      final raw = await widget.api.advisoryAnalysis(
        symbol: symbol,
        timeframe: timeframe,
        limit: 100,
      );

      advisoryData = _map(raw);

      if (advisoryData.isEmpty) {
        throw const FormatException(
          'The analysis response was empty or invalid.',
        );
      }
    } catch (e) {
      if (!mounted) return;

      setState(() {
        loading = false;
        error = 'Unable to load market analysis.\n\n${_errorText(e)}';
      });
      return;
    }

    // Load paper positions separately. Failure here is only a warning.
    final positions = <Map<String, dynamic>>[];
    String? warning;

    try {
      final raw = await widget.api.paperPositions(
        symbol: symbol,
        status: 'open',
        limit: 100,
      );

      final data = _map(raw);
      final rawPositions =
          data['positions'] ?? data['items'] ?? data['results'];

      if (rawPositions is List) {
        for (final item in rawPositions) {
          if (item is Map) {
            positions.add(_map(item));
          }
        }
      } else if (rawPositions != null) {
        warning =
            'Analysis loaded, but the positions response had an unexpected format.';
      }
    } catch (e) {
      warning =
          'Market analysis is available, but open paper positions could not '
          'be loaded. Check that you are signed in, then retry. '
          'Details: ${_errorText(e)}';
    }

    final market = _map(advisoryData['market']);
    final nextSymbol = _string(market['symbol'], fallback: symbol);
    final nextTimeframe =
        _string(market['timeframe'], fallback: timeframe);

    if (!mounted) return;

    setState(() {
      analysis = advisoryData;
      openPositions = positions;
      positionsWarning = warning;
      symbol = nextSymbol;
      timeframe = nextTimeframe;
      loading = false;
      error = null;
    });
  }

  Map<String, dynamic> _map(dynamic value) {
    if (value is Map) {
      return <String, dynamic>{
        for (final entry in value.entries)
          entry.key.toString(): entry.value,
      };
    }
    return <String, dynamic>{};
  }

  String _string(dynamic value, {String fallback = '--'}) {
    if (value == null) return fallback;
    final result = value.toString().trim();
    return result.isEmpty ? fallback : result;
  }

  double? _num(dynamic value) {
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value.trim());
    return null;
  }

  String _number(
    dynamic value, {
    int decimals = 2,
    String fallback = '--',
  }) {
    final n = _num(value);
    return n == null ? fallback : n.toStringAsFixed(decimals);
  }

  String _errorText(Object e) {
    final text = e.toString();
    return text.length > 450 ? '${text.substring(0, 450)}…' : text;
  }

  Color _signalColor(String signal) {
    switch (signal.toUpperCase()) {
      case 'BUY':
      case 'STRONG BUY':
        return Colors.green;
      case 'SELL':
      case 'STRONG SELL':
        return Colors.red;
      default:
        return Colors.orange;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('RAYMOND Market Analysis'),
        actions: [
          IconButton(
            tooltip: 'Refresh analysis',
            onPressed: loading ? null : _loadEverything,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadEverything,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(14),
          children: [
            _header(),
            const SizedBox(height: 12),
            if (loading)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(28),
                  child: Column(
                    children: [
                      CircularProgressIndicator(),
                      SizedBox(height: 14),
                      Text('RAYMOND is analysing the market…'),
                    ],
                  ),
                ),
              )
            else if (error != null)
              _errorCard()
            else ...[
              if (positionsWarning != null) ...[
                _warningCard(positionsWarning!),
                const SizedBox(height: 12),
              ],
              _marketCard(),
              const SizedBox(height: 12),
              _decisionCard(),
              const SizedBox(height: 12),
              _indicatorsCard(),
              const SizedBox(height: 12),
              _brainsCard(),
              const SizedBox(height: 12),
              _tradePlanCard(),
              const SizedBox(height: 12),
              _positionsCard(),
              const SizedBox(height: 12),
              _safetyCard(),
            ],
            const SizedBox(height: 28),
          ],
        ),
      ),
    );
  }

  Widget _header() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            const Icon(Icons.insights, size: 30),
            const SizedBox(width: 12),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'RAYMOND TRADING TERMINAL',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 3),
                  Text(
                    'Market analysis • paper mode',
                    style: TextStyle(fontSize: 12),
                  ),
                ],
              ),
            ),
            Text(
              '$symbol\n$timeframe',
              textAlign: TextAlign.right,
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
          ],
        ),
      ),
    );
  }

  Widget _errorCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          children: [
            const Icon(
              Icons.error_outline,
              size: 40,
              color: Colors.orange,
            ),
            const SizedBox(height: 10),
            Text(error ?? 'Analysis unavailable',
                textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: loading ? null : _loadEverything,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry analysis'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _warningCard(String message) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.info_outline, color: Colors.orange),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(fontSize: 12),
              ),
            ),
            IconButton(
              tooltip: 'Retry',
              onPressed: loading ? null : _loadEverything,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
      ),
    );
  }

  Widget _card(String title, IconData icon, List<Widget> children) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: ExpansionTile(
        initiallyExpanded: true,
        leading: Icon(icon),
        title: Text(
          title,
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 16),
        children: children,
      ),
    );
  }

  Widget _row(String label, dynamic value, {Color? color}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(label, style: const TextStyle(fontSize: 13)),
          ),
          const SizedBox(width: 12),
          Flexible(
            child: Text(
              _string(value),
              textAlign: TextAlign.right,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: color,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _metric(String label, String value) {
    return Expanded(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
            const SizedBox(height: 4),
            Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }

  Widget _marketCard() {
    final market = _map(analysis['market']);

    return _card('MARKET DATA', Icons.show_chart, [
      Row(
        children: [
          _metric('Symbol', _string(market['symbol'], fallback: symbol)),
          _metric(
            'Timeframe',
            _string(market['timeframe'], fallback: timeframe),
          ),
        ],
      ),
      Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 14),
          child: Column(
            children: [
              const Text('CURRENT PRICE',
                  style: TextStyle(fontSize: 12)),
              const SizedBox(height: 4),
              Text(
                _number(market['price'], decimals: 2),
                style: const TextStyle(
                  fontSize: 32,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ],
          ),
        ),
      ),
      _row('Data source', analysis['source'] ?? analysis['source_type']),
      _row('Market timestamp', market['timestamp'] ?? market['time']),
    ]);
  }

  Widget _decisionCard() {
    final raymond = _map(analysis['raymond']);
    final signal =
        _string(raymond['signal'], fallback: 'WAIT').toUpperCase();
    final color = _signalColor(signal);

    return _card('RAYMOND DECISION', Icons.psychology, [
      Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Column(
            children: [
              Text(
                signal,
                style: TextStyle(
                  fontSize: 34,
                  fontWeight: FontWeight.w900,
                  color: color,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                _string(
                  raymond['direction'],
                  fallback: 'No direction supplied',
                ),
              ),
            ],
          ),
        ),
      ),
      Row(
        children: [
          _metric(
            'Confidence',
            _num(raymond['confidence']) == null
                ? '--'
                : '${_number(raymond['confidence'], decimals: 1)}%',
          ),
          _metric(
            'Technical score',
            _number(raymond['technical_score'], decimals: 0),
          ),
          _metric(
            'Confluence',
            _number(raymond['confluence_score'], decimals: 0),
          ),
        ],
      ),
      _row('Trend', raymond['trend']),
      _row('Market regime', raymond['market_regime']),
      _row('Setup', raymond['setup']),
      _row('Reasoning', raymond['reasoning']),
    ]);
  }

  Widget _indicatorsCard() {
    final outer = _map(analysis['indicators']);
    final values = _map(outer['indicators']);
    final technical = _map(outer['analysis']);

    return _card('TECHNICAL INDICATORS', Icons.analytics, [
      _row('EMA 20', _number(values['ema20'], decimals: 3)),
      _row('EMA 50', _number(values['ema50'], decimals: 3)),
      _row('RSI 14', _number(values['rsi14'])),
      _row('ATR 14', _number(values['atr14'])),
      _row('MACD', _number(values['macd'])),
      _row('MACD signal', _number(values['macd_signal'])),
      _row('MACD histogram', _number(values['macd_histogram'])),
      _row('Trend', technical['trend'] ?? outer['trend']),
      _row('Signal', technical['signal'] ?? outer['signal']),
      _row('Score', technical['score'] ?? outer['score']),
      _row('Candles used', outer['candles_used']),
    ]);
  }

  Widget _brainsCard() {
    final comparison = _map(analysis['advisory_comparison']);
    final rawBrains = comparison['brains'];
    final brains =
        rawBrains is List ? rawBrains.whereType<Map>().toList() : <Map>[];

    return _card('AI BRAIN COMPARISON', Icons.hub, [
      _row('Advisory direction', comparison['advisory_direction']),
      _row('Advisory confidence', comparison['advisory_confidence']),
      _row('Agreement', comparison['agreement_percent']),
      _row('Buy votes', comparison['buy_votes']),
      _row('Sell votes', comparison['sell_votes']),
      _row('Wait votes', comparison['wait_votes']),
      _row('Comparison status', comparison['status']),
      _row('Summary', comparison['summary']),
      if (comparison['warning'] != null)
        _row('Warning', comparison['warning']),
      if (brains.isNotEmpty) ...[
        const Divider(),
        for (final brain in brains)
          _row(
            _string(
              brain['name'] ?? brain['brain'],
              fallback: 'AI brain',
            ),
            '${_string(brain['signal'] ?? brain['direction'])} • '
            'confidence ${_string(brain['confidence'])}',
          ),
      ] else
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 8),
          child: Text(
            'Detailed brain votes were not included in this API response.',
            style: TextStyle(fontSize: 12),
          ),
        ),
    ]);
  }

  Widget _tradePlanCard() {
    final plan = _map(analysis['trade_plan']);
    final raymond = _map(analysis['raymond']);
    final nested = _map(raymond['trade_plan']);
    final data = plan.isNotEmpty ? plan : nested;

    return _card('TRADE PLAN', Icons.rule, [
      _row('Status', data['status'] ?? raymond['signal']),
      _row('Direction', data['direction'] ?? raymond['direction']),
      _row(
        'Entry',
        _number(
          data['entry'] ?? data['entry_price'] ?? raymond['entry'],
        ),
      ),
      _row(
        'Stop Loss',
        _number(
          data['stop_loss'] ?? data['sl'] ?? raymond['stop_loss'],
        ),
      ),
      _row(
        'Take Profit 1',
        _number(
          data['take_profit_1'] ??
              data['tp1'] ??
              raymond['take_profit_1'],
        ),
      ),
      _row(
        'Take Profit 2',
        _number(
          data['take_profit_2'] ??
              data['tp2'] ??
              raymond['take_profit_2'],
        ),
      ),
      _row('Risk/reward', data['risk_reward'] ?? data['rr']),
      _row('Entry quality', data['entry_quality'] ?? raymond['entry_quality']),
      const Padding(
        padding: EdgeInsets.only(top: 8),
        child: Text(
          'This is analysis/advisory information, not a broker order. '
          'Verify current prices and risk before any trade.',
          style: TextStyle(fontSize: 12),
        ),
      ),
    ]);
  }

  Widget _positionsCard() {
    if (openPositions.isEmpty) {
      return _card('OPEN PAPER POSITIONS', Icons.candlestick_chart, const [
        Padding(
          padding: EdgeInsets.symmetric(vertical: 10),
          child: Text(
            'No open paper positions were returned. '
            'This does not prevent market analysis from working.',
          ),
        ),
      ]);
    }

    return _card(
      'OPEN PAPER POSITIONS (${openPositions.length})',
      Icons.candlestick_chart,
      [
        for (var i = 0; i < openPositions.length; i++) ...[
          if (i > 0) const Divider(),
          _row(
            'Position ${i + 1}',
            openPositions[i]['trade_id'] ??
                openPositions[i]['position_id'] ??
                openPositions[i]['id'],
          ),
          _row('Symbol', openPositions[i]['symbol']),
          _row(
            'Direction',
            openPositions[i]['direction'] ?? openPositions[i]['side'],
          ),
          _row(
            'Entry',
            _number(
              openPositions[i]['entry_price'] ??
                  openPositions[i]['entry'],
            ),
          ),
          _row(
            'Current price',
            _number(
              openPositions[i]['current_price'] ??
                  openPositions[i]['mark_price'],
            ),
          ),
          _row(
            'Quantity / lots',
            openPositions[i]['quantity'] ?? openPositions[i]['lots'],
          ),
          _row(
            'Stop Loss',
            _number(
              openPositions[i]['stop_loss'] ?? openPositions[i]['sl'],
            ),
          ),
          _row(
            'Take Profit',
            _number(
              openPositions[i]['take_profit'] ?? openPositions[i]['tp'],
            ),
          ),
          _row(
            'Unrealized P&L',
            _number(
              openPositions[i]['unrealized_pnl'] ??
                  openPositions[i]['pnl'],
            ),
          ),
        ],
      ],
    );
  }

  Widget _safetyCard() {
    final safety = _map(analysis['safety']);

    return _card('SAFETY STATUS', Icons.security, [
      _row(
        'Execution mode',
        safety['execution_mode'] ??
            analysis['execution_mode'] ??
            'Advisory / paper',
      ),
      _row(
        'Paper trading',
        safety['paper_trading_enabled'] ?? true,
      ),
      _row(
        'Live trading enabled',
        safety['live_trading_enabled'] ?? false,
      ),
      _row(
        'Broker orders allowed',
        safety['broker_orders_allowed'] ?? false,
      ),
      _row(
        'Execution authorized',
        safety['execution_authorized'] ?? false,
      ),
      const Padding(
        padding: EdgeInsets.only(top: 8),
        child: Text(
          'This screen displays analysis and paper-trading state. '
          'It does not send broker orders. Live execution should remain '
          'disabled until the broker bridge and safety checks are verified.',
          style: TextStyle(fontSize: 12),
        ),
      ),
    ]);
  }
}
