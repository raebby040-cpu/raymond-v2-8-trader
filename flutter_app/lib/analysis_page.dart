import 'package:flutter/material.dart';

import 'api_service.dart';

class AnalysisPage extends StatefulWidget {
  const AnalysisPage({
    super.key,
    required this.api,
  });

  final ApiService api;

  @override
  State<AnalysisPage> createState() => _AnalysisPageState();
}

class _AnalysisPageState extends State<AnalysisPage> {
  static const gold = Color(0xFFF5B82E);
  static const green = Color(0xFF00E59B);
  static const red = Color(0xFFFF5C6C);
  static const background = Color(0xFF030B14);
  static const card = Color(0xFF091724);
  static const border = Color(0xFF17334D);
  static const muted = Color(0xFF8EA4B8);

  bool loading = true;
  String errorMessage = '';

  String symbol = 'XAUUSD';
  String timeframe = 'H1';

  double close = 0;
  double ema20 = 0;
  double ema50 = 0;
  double rsi14 = 0;
  double atr14 = 0;
  double macd = 0;
  double macdSignal = 0;
  double macdHistogram = 0;

  String trend = 'Neutral';
  String signal = 'WAIT';
  int score = 50;
  int candlesUsed = 0;

  @override
  void initState() {
    super.initState();
    _loadAnalysis();
  }

  Future<void> _loadAnalysis() async {
    if (!mounted) return;

    setState(() {
      loading = true;
      errorMessage = '';
    });

    try {
      final data = await widget.api.marketIndicators(
        symbol: symbol,
      );

      if (!mounted) return;

      final indicators = data['indicators'];
      final analysis = data['analysis'];

      setState(() {
        symbol = '${data['symbol'] ?? symbol}';
        timeframe = '${data['timeframe'] ?? timeframe}';

        close = _number(data['close']);
        ema20 = _number(indicators is Map ? indicators['ema20'] : null);
        ema50 = _number(indicators is Map ? indicators['ema50'] : null);
        rsi14 = _number(indicators is Map ? indicators['rsi14'] : null);
        atr14 = _number(indicators is Map ? indicators['atr14'] : null);
        macd = _number(indicators is Map ? indicators['macd'] : null);
        macdSignal =
            _number(indicators is Map ? indicators['macd_signal'] : null);
        macdHistogram =
            _number(indicators is Map ? indicators['macd_histogram'] : null);

        trend = '${analysis is Map ? analysis['trend'] : 'Neutral'}';
        signal = '${analysis is Map ? analysis['signal'] : 'WAIT'}';

        final scoreValue = analysis is Map ? analysis['score'] : null;
        score = scoreValue is num ? scoreValue.toInt() : 50;

        final candlesValue = data['candles_used'];
        candlesUsed =
            candlesValue is num ? candlesValue.toInt() : 0;

        loading = false;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        loading = false;
        errorMessage = 'Unable to load market analysis';
      });
    }
  }

  double _number(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }

    return 0;
  }

  Color _signalColor() {
    switch (signal.toUpperCase()) {
      case 'BUY':
        return green;
      case 'SELL':
        return red;
      default:
        return gold;
    }
  }

  Color _trendColor() {
    switch (trend.toLowerCase()) {
      case 'bullish':
        return green;
      case 'bearish':
        return red;
      default:
        return gold;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      appBar: AppBar(
        backgroundColor: background,
        elevation: 0,
        title: const Text(
          'MARKET ANALYSIS',
          style: TextStyle(
            fontWeight: FontWeight.w800,
            letterSpacing: 1.0,
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: loading ? null : _loadAnalysis,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadAnalysis,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (errorMessage.isNotEmpty) _errorCard(),

              _marketHeader(),

              const SizedBox(height: 14),

              _signalCard(),

              const SizedBox(height: 14),

              _indicatorCard(),

              const SizedBox(height: 14),

              _trendCard(),

              const SizedBox(height: 14),

              _safetyCard(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _marketHeader() {
    return _card(
      child: Row(
        children: [
          const Icon(
            Icons.candlestick_chart,
            color: gold,
            size: 32,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  symbol,
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                Text(
                  'Timeframe: $timeframe',
                  style: const TextStyle(
                    color: muted,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              const Text(
                'PRICE',
                style: TextStyle(
                  color: muted,
                  fontSize: 11,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                loading ? '--' : close.toStringAsFixed(2),
                style: const TextStyle(
                  fontSize: 19,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _signalCard() {
    final color = _signalColor();

    return _card(
      child: Column(
        children: [
          const Text(
            'CURRENT SIGNAL',
            style: TextStyle(
              color: muted,
              fontWeight: FontWeight.bold,
              letterSpacing: .8,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            loading ? '--' : signal,
            style: TextStyle(
              color: color,
              fontSize: 38,
              fontWeight: FontWeight.w900,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Score: $score / 100',
            style: const TextStyle(
              color: muted,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 14),
          LinearProgressIndicator(
            value: score.clamp(0, 100) / 100,
            minHeight: 7,
            backgroundColor: border,
            valueColor: AlwaysStoppedAnimation<Color>(color),
          ),
        ],
      ),
    );
  }

  Widget _indicatorCard() {
    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'TECHNICAL INDICATORS',
            style: TextStyle(
              color: gold,
              fontWeight: FontWeight.bold,
              letterSpacing: .8,
            ),
          ),
          const SizedBox(height: 14),
          _indicatorRow(
            'EMA 20',
            ema20,
            close >= ema20,
          ),
          _indicatorRow(
            'EMA 50',
            ema50,
            close >= ema50,
          ),
          _indicatorRow(
            'RSI 14',
            rsi14,
            rsi14 >= 50,
          ),
          _indicatorRow(
            'ATR 14',
            atr14,
            true,
          ),
          _indicatorRow(
            'MACD',
            macd,
            macd >= macdSignal,
          ),
          _indicatorRow(
            'MACD Signal',
            macdSignal,
            true,
          ),
          _indicatorRow(
            'MACD Histogram',
            macdHistogram,
            macdHistogram >= 0,
          ),
        ],
      ),
    );
  }

  Widget _indicatorRow(
    String name,
    double value,
    bool positive,
  ) {
    final color = positive ? green : red;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(
        horizontal: 12,
        vertical: 11,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFF06111C),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              name,
              style: const TextStyle(
                color: muted,
                fontSize: 13,
              ),
            ),
          ),
          Text(
            loading ? '--' : value.toStringAsFixed(4),
            style: TextStyle(
              color: name == 'ATR 14' || name == 'MACD Signal'
                  ? Colors.white
                  : color,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _trendCard() {
    final color = _trendColor();

    return _card(
      child: Row(
        children: [
          Icon(
            trend.toLowerCase() == 'bullish'
                ? Icons.trending_up
                : trend.toLowerCase() == 'bearish'
                    ? Icons.trending_down
                    : Icons.trending_flat,
            color: color,
            size: 34,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'MARKET TREND',
                  style: TextStyle(
                    color: muted,
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  trend,
                  style: TextStyle(
                    color: color,
                    fontSize: 21,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
          ),
          Text(
            '$candlesUsed candles',
            style: const TextStyle(
              color: muted,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Widget _safetyCard() {
    return _card(
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.shield_outlined,
            color: green,
          ),
          SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'READ-ONLY ANALYSIS',
                  style: TextStyle(
                    color: green,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                SizedBox(height: 5),
                Text(
                  'This screen only reads market data and technical indicators. '
                  'It does not place, modify, or close trades.',
                  style: TextStyle(
                    color: muted,
                    fontSize: 13,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _errorCard() {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: red.withOpacity(.10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: red.withOpacity(.30),
        ),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.warning_amber_rounded,
            color: red,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              '$errorMessage. Pull down to retry.',
              style: const TextStyle(color: red),
            ),
          ),
        ],
      ),
    );
  }

  Widget _card({
    required Widget child,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: border,
        ),
      ),
      child: child,
    );
  }
}
