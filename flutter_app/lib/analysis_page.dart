import 'package:flutter/material.dart';
import 'api_service.dart';

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

  String symbol = 'XAUUSD';
  String timeframe = 'M15';

  double close = 0.0;
  double rsi = 0.0;
  double macd = 0.0;
  double macdSignal = 0.0;
  double ema20 = 0.0;
  double ema50 = 0.0;
  double atr = 0.0;

  String trend = 'Neutral';
  String signal = 'WAIT';
  double score = 50.0;
  int candlesUsed = 0;

  String reasoning = '';
  String source = '';

  @override
  void initState() {
    super.initState();
    _loadAnalysis();
  }

  Future<void> _loadAnalysis() async {
    if (!mounted) return;

    setState(() {
      loading = true;
      error = null;
    });

    try {
      final data = await widget.api.marketAnalysis(
        symbol: symbol,
        timeframe: timeframe,
        limit: 100,
      );

      if (!mounted) return;

      final market = data['market'];
      final indicators = data['indicators'];

      final marketMap = market is Map
          ? Map<String, dynamic>.from(market)
          : <String, dynamic>{};

      final indicatorsMap = indicators is Map
          ? Map<String, dynamic>.from(indicators)
          : <String, dynamic>{};

      setState(() {
        symbol = '${marketMap['symbol'] ?? symbol}';
        timeframe = '${marketMap['timeframe'] ?? timeframe}';

        close = _number(marketMap['price']);

        rsi = _number(indicatorsMap['rsi']);
        macd = _number(indicatorsMap['macd']);
        macdSignal = _number(indicatorsMap['macd_signal']);
        ema20 = _number(indicatorsMap['ema20']);
        ema50 = _number(indicatorsMap['ema50']);
        atr = _number(indicatorsMap['atr']);

        trend = '${data['trend'] ?? 'Neutral'}';
        signal = '${data['signal'] ?? 'WAIT'}';

        final scoreValue = data['technical_score'];
        if (scoreValue is num) {
          score = scoreValue.toDouble();
        } else {
          score = _number(indicatorsMap['score'], fallback: 50.0);
        }

        final candlesValue = indicatorsMap['candles_used'];
        if (candlesValue is num) {
          candlesUsed = candlesValue.toInt();
        } else {
          candlesUsed = 0;
        }

        reasoning = '${data['reasoning'] ?? ''}';
        source = '${data['source'] ?? ''}';

        loading = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        loading = false;
        error = 'Unable to load market analysis. Pull down to retry.';
      });
    }
  }

  double _number(
    dynamic value, {
    double fallback = 0.0,
  }) {
    if (value is num) {
      return value.toDouble();
    }

    if (value is String) {
      return double.tryParse(value) ?? fallback;
    }

    return fallback;
  }

  Color _signalColor() {
    switch (signal.toUpperCase()) {
      case 'BUY':
        return Colors.green;
      case 'SELL':
        return Colors.red;
      default:
        return Colors.orange;
    }
  }

  Color _trendColor() {
    switch (trend.toLowerCase()) {
      case 'bullish':
        return Colors.green;
      case 'bearish':
        return Colors.red;
      default:
        return Colors.orange;
    }
  }

  String _formatNumber(double value, int decimals) {
    return value.toStringAsFixed(decimals);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Market Analysis'),
        actions: [
          IconButton(
            onPressed: loading ? null : _loadAnalysis,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh analysis',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadAnalysis,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            _onlineBanner(),

            const SizedBox(height: 16),

            if (loading) ...[
              const SizedBox(height: 40),
              const Center(
                child: CircularProgressIndicator(),
              ),
              const SizedBox(height: 20),
              const Center(
                child: Text('Loading market analysis...'),
              ),
            ] else if (error != null) ...[
              _errorCard(),
            ] else ...[
              _marketCard(),
              const SizedBox(height: 12),
              _signalCard(),
              const SizedBox(height: 12),
              _indicatorsCard(),
              const SizedBox(height: 12),
              _reasoningCard(),
              const SizedBox(height: 12),
              _dataCard(),
              const SizedBox(height: 12),
              _safetyCard(),
            ],
          ],
        ),
      ),
    );
  }

  Widget _onlineBanner() {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: 14,
        vertical: 10,
      ),
      decoration: BoxDecoration(
        color: Colors.green.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.green.withValues(alpha: 0.35),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: const BoxDecoration(
              color: Colors.green,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'ONLINE',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: Colors.green,
              ),
            ),
          ),
          Text(
            '$symbol • $timeframe',
            style: const TextStyle(
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _marketCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Market',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: _valueTile(
                    'Symbol',
                    symbol,
                  ),
                ),
                Expanded(
                  child: _valueTile(
                    'Timeframe',
                    timeframe,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _valueTile(
              'Current Price',
              _formatNumber(close, 2),
              large: true,
            ),
          ],
        ),
      ),
    );
  }

  Widget _signalCard() {
    final signalColor = _signalColor();
    final trendColor = _trendColor();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Trading Analysis',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: _analysisValue(
                    'Trend',
                    trend,
                    trendColor,
                  ),
                ),
                Expanded(
                  child: _analysisValue(
                    'Signal',
                    signal,
                    signalColor,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            Text(
              'Technical Score',
              style: TextStyle(
                color: Theme.of(context)
                    .textTheme
                    .bodyMedium
                    ?.color
                    ?.withValues(alpha: 0.7),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: LinearProgressIndicator(
                    value: (score / 100).clamp(0.0, 1.0),
                    minHeight: 10,
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  '${score.toStringAsFixed(0)}/100',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _indicatorsCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Technical Indicators',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 14),
            _indicatorRow(
              'RSI',
              _formatNumber(rsi, 2),
            ),
            _indicatorRow(
              'MACD',
              _formatNumber(macd, 4),
            ),
            _indicatorRow(
              'MACD Signal',
              _formatNumber(macdSignal, 4),
            ),
            _indicatorRow(
              'EMA 20',
              _formatNumber(ema20, 2),
            ),
            _indicatorRow(
              'EMA 50',
              _formatNumber(ema50, 2),
            ),
            _indicatorRow(
              'ATR',
              _formatNumber(atr, 4),
            ),
          ],
        ),
      ),
    );
  }

  Widget _reasoningCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Analysis Reasoning',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              reasoning.isEmpty
                  ? 'No additional reasoning was returned by the analysis engine.'
                  : reasoning,
              style: const TextStyle(
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _dataCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Data',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            _indicatorRow(
              'Candles Used',
              '$candlesUsed',
            ),
            if (source.isNotEmpty)
              _indicatorRow(
                'Market Source',
                source,
              ),
          ],
        ),
      ),
    );
  }

  Widget _safetyCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.lock,
                  color: Colors.green,
                ),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'SAFE PAPER MODE',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: Colors.green,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Text(
              'This analysis is read-only. Live broker order execution remains disabled.',
              style: TextStyle(
                height: 1.4,
              ),
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
              size: 42,
              color: Colors.red,
            ),
            const SizedBox(height: 12),
            Text(
              error!,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 14),
            ElevatedButton.icon(
              onPressed: _loadAnalysis,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _valueTile(
    String label,
    String value, {
    bool large = false,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 13,
            color: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.color
                ?.withValues(alpha: 0.65),
          ),
        ),
        const SizedBox(height: 5),
        Text(
          value,
          style: TextStyle(
            fontSize: large ? 28 : 17,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }

  Widget _analysisValue(
    String label,
    String value,
    Color color,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.color
                ?.withValues(alpha: 0.65),
          ),
        ),
        const SizedBox(height: 5),
        Text(
          value,
          style: TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.bold,
            color: color,
          ),
        ),
      ],
    );
  }

  Widget _indicatorRow(
    String label,
    String value,
  ) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        children: [
          Expanded(
            child: Text(label),
          ),
          Text(
            value,
            style: const TextStyle(
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
