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
  double macdHistogram = 0.0;
  double ema20 = 0.0;
  double ema50 = 0.0;
  double atr = 0.0;

  String trend = 'Neutral';
  String signal = 'WAIT';
  double score = 50.0;
  int candlesUsed = 0;

  String reasoning = '';
  String source = '';
  double confidence = 0.0;

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

      /*
       * API response structure:
       *
       * {
       *   "market": {
       *     "symbol": "XAUUSD",
       *     "timeframe": "M15",
       *     "price": 4339.834
       *   },
       *
       *   "indicators": {
       *     "status": "ok",
       *     "symbol": "XAUUSD",
       *     "timeframe": "M15",
       *     "close": 4339.834,
       *
       *     "indicators": {
       *       "ema20": 4345.42,
       *       "ema50": 4348.89,
       *       "rsi14": 41.66,
       *       "atr14": 7.29,
       *       "macd": -5.36,
       *       "macd_signal": -5.00,
       *       "macd_histogram": -0.35
       *     },
       *
       *     "analysis": {
       *       "trend": "Bearish",
       *       "score": 14,
       *       "signal": "SELL"
       *     },
       *
       *     "candles_used": 100
       *   },
       *
       *   "decision": {
       *     "direction": "sell",
       *     "confidence": 77.8,
       *     "technical_score": 14,
       *     "trend": "Bearish",
       *     "signal": "SELL",
       *     "reasoning": "..."
       *   }
       * }
       */

      final market = _asMap(data['market']);
      final indicatorsResponse = _asMap(data['indicators']);

      // The actual technical indicators are nested inside:
      // data['indicators']['indicators']
      final technicalIndicators =
          _asMap(indicatorsResponse['indicators']);

      // Backend technical analysis is nested inside:
      // data['indicators']['analysis']
      final technicalAnalysis =
          _asMap(indicatorsResponse['analysis']);

      // AI decision is also available at the top level.
      final decision = _asMap(data['decision']);

      final returnedSymbol =
          _stringValue(market['symbol'], fallback: symbol);

      final returnedTimeframe =
          _stringValue(market['timeframe'], fallback: timeframe);

      final returnedPrice = _number(
        market['price'],
        fallback: _number(indicatorsResponse['close']),
      );

      final returnedRsi = _number(
        technicalIndicators['rsi14'],
        fallback: _number(technicalIndicators['rsi']),
      );

      final returnedMacd =
          _number(technicalIndicators['macd']);

      final returnedMacdSignal = _number(
        technicalIndicators['macd_signal'],
      );

      final returnedMacdHistogram = _number(
        technicalIndicators['macd_histogram'],
      );

      final returnedEma20 = _number(
        technicalIndicators['ema20'],
      );

      final returnedEma50 = _number(
        technicalIndicators['ema50'],
      );

      final returnedAtr = _number(
        technicalIndicators['atr14'],
        fallback: _number(technicalIndicators['atr']),
      );

      /*
       * Prefer the AI decision values when available because that is
       * the final analysis decision returned by the backend.
       *
       * Fall back to the technical analysis section if needed.
       */
      final returnedTrend = _stringValue(
        decision['trend'],
        fallback: _stringValue(
          technicalAnalysis['trend'],
          fallback: 'Neutral',
        ),
      );

      final returnedSignal = _stringValue(
        decision['signal'],
        fallback: _stringValue(
          technicalAnalysis['signal'],
          fallback: 'WAIT',
        ),
      );

      final returnedScore = _number(
        decision['technical_score'],
        fallback: _number(
          technicalAnalysis['score'],
          fallback: 50.0,
        ),
      );

      final returnedCandles = _intValue(
        indicatorsResponse['candles_used'],
      );

      final returnedReasoning = _stringValue(
        decision['reasoning'],
        fallback: _stringValue(
          data['reasoning'],
          fallback: '',
        ),
      );

      final returnedSource = _stringValue(
        data['source'],
        fallback: '',
      );

      final returnedConfidence = _number(
        decision['confidence'],
      );

      setState(() {
        symbol = returnedSymbol;
        timeframe = returnedTimeframe;

        close = returnedPrice;

        rsi = returnedRsi;
        macd = returnedMacd;
        macdSignal = returnedMacdSignal;
        macdHistogram = returnedMacdHistogram;
        ema20 = returnedEma20;
        ema50 = returnedEma50;
        atr = returnedAtr;

        trend = returnedTrend;
        signal = returnedSignal;
        score = returnedScore;
        candlesUsed = returnedCandles;

        reasoning = returnedReasoning;
        source = returnedSource;
        confidence = returnedConfidence;

        loading = false;
        error = null;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        loading = false;
        error =
            'Unable to load market analysis. Pull down to retry.';
      });
    }
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }

    return <String, dynamic>{};
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

  int _intValue(dynamic value) {
    if (value is num) {
      return value.toInt();
    }

    if (value is String) {
      return int.tryParse(value) ?? 0;
    }

    return 0;
  }

  String _stringValue(
    dynamic value, {
    String fallback = '',
  }) {
    if (value == null) {
      return fallback;
    }

    final result = value.toString().trim();

    if (result.isEmpty) {
      return fallback;
    }

    return result;
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

  String _formatNumber(
    double value,
    int decimals,
  ) {
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
                child: Text(
                  'Loading market analysis...',
                ),
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
          crossAxisAlignment:
              CrossAxisAlignment.start,
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
          crossAxisAlignment:
              CrossAxisAlignment.start,
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
                    value: (score / 100)
                        .clamp(0.0, 1.0),
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

            if (confidence > 0) ...[
              const SizedBox(height: 16),

              _indicatorRow(
                'AI Confidence',
                '${confidence.toStringAsFixed(1)}%',
              ),
            ],
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
          crossAxisAlignment:
              CrossAxisAlignment.start,
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
              'RSI 14',
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
              'MACD Histogram',
              _formatNumber(macdHistogram, 4),
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
              'ATR 14',
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
          crossAxisAlignment:
              CrossAxisAlignment.start,
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
          crossAxisAlignment:
              CrossAxisAlignment.start,
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
          crossAxisAlignment:
              CrossAxisAlignment.start,
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
      crossAxisAlignment:
          CrossAxisAlignment.start,
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
      crossAxisAlignment:
          CrossAxisAlignment.start,
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
      padding: const EdgeInsets.symmetric(
        vertical: 7,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(label),
          ),

          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: const TextStyle(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
