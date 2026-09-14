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
  String timeframe = 'H1';

  Map<String, dynamic> analysis = {};
  Map<String, dynamic>? openPosition;

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
    });

    try {
      final results = await Future.wait([
        widget.api.advisoryAnalysis(
          symbol: symbol,
          timeframe: timeframe,
          limit: 100,
        ),
        widget.api.paperPositions(
          symbol: symbol,
          status: 'open',
          limit: 100,
        ),
      ]);

      final advisoryData =
          Map<String, dynamic>.from(results[0]);

      final positionsData =
          Map<String, dynamic>.from(results[1]);

      Map<String, dynamic>? position;

      final positions = positionsData['positions'];

      if (positions is List && positions.isNotEmpty) {
        final first = positions.first;

        if (first is Map) {
          position = Map<String, dynamic>.from(first);
        }
      }

      if (!mounted) return;

      setState(() {
        analysis = advisoryData;
        openPosition = position;

        final market =
            _map(advisoryData['market']);

        symbol = _string(
          market['symbol'],
          fallback: symbol,
        );

        timeframe = _string(
          market['timeframe'],
          fallback: timeframe,
        );

        loading = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        loading = false;
        error =
            'Unable to load the RAYMOND trading terminal.';
      });
    }
  }

  Map<String, dynamic> _map(dynamic value) {
    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }

    return <String, dynamic>{};
  }

  List<dynamic> _list(dynamic value) {
    if (value is List) {
      return value;
    }

    return [];
  }

  String _string(
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

  int _int(
    dynamic value, {
    int fallback = 0,
  }) {
    if (value is num) {
      return value.toInt();
    }

    if (value is String) {
      return int.tryParse(value) ?? fallback;
    }

    return fallback;
  }

  bool _bool(
    dynamic value, {
    bool fallback = false,
  }) {
    if (value is bool) {
      return value;
    }

    if (value is String) {
      final normalized = value.toLowerCase();

      if (normalized == 'true' ||
          normalized == 'yes' ||
          normalized == '1') {
        return true;
      }

      if (normalized == 'false' ||
          normalized == 'no' ||
          normalized == '0') {
        return false;
      }
    }

    if (value is num) {
      return value != 0;
    }

    return fallback;
  }

  Color _signalColor(String value) {
    switch (value.toUpperCase()) {
      case 'BUY':
        return Colors.green;

      case 'SELL':
        return Colors.red;

      default:
        return Colors.orange;
    }
  }

  Color _comparisonColor(String value) {
    switch (value.toUpperCase()) {
      case 'AGREE':
      case 'STRONG':
        return Colors.green;

      case 'DISAGREE':
        return Colors.red;

      case 'WEAK_ENTRY':
      case 'WEAK':
        return Colors.orange;

      default:
        return Colors.grey;
    }
  }

  String _format(
    dynamic value, {
    int decimals = 2,
  }) {
    return _number(value).toStringAsFixed(decimals);
  }

  String _formatNullable(
    dynamic value, {
    int decimals = 2,
  }) {
    if (value == null) {
      return '--';
    }

    return _format(
      value,
      decimals: decimals,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'RAYMOND Trading Terminal',
        ),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: loading
                ? null
                : _loadEverything,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadEverything,
        child: ListView(
          physics:
              const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(14),
          children: [
            _terminalHeader(),

            const SizedBox(height: 12),

            if (loading)
              _loadingCard()
            else if (error != null)
              _errorCard()
            else ...[
              _marketSection(),

              const SizedBox(height: 12),

              _raymondSection(),

              const SizedBox(height: 12),

              _brainsSection(),

              const SizedBox(height: 12),

              _tradePlanSection(),

              const SizedBox(height: 12),

              _openTradeSection(),

              const SizedBox(height: 12),

              _managementSection(),

              const SizedBox(height: 12),

              _reasoningSection(),

              const SizedBox(height: 12),

              _technicalIndicatorsSection(),

              const SizedBox(height: 12),

              _safetySection(),
            ],

            const SizedBox(height: 30),
          ],
        ),
      ),
    );
  }

  Widget _terminalHeader() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Container(
              width: 12,
              height: 12,
              decoration: const BoxDecoration(
                color: Colors.green,
                shape: BoxShape.circle,
              ),
            ),

            const SizedBox(width: 10),

            const Expanded(
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment.start,
                children: [
                  Text(
                    'RAYMOND ONLINE',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  SizedBox(height: 2),
                  Text(
                    'Paper trading terminal',
                    style: TextStyle(
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),

            Text(
              '$symbol\n$timeframe',
              textAlign: TextAlign.right,
              style: const TextStyle(
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _loadingCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(30),
        child: Column(
          children: const [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text(
              'RAYMOND is analysing the market...',
            ),
            SizedBox(height: 6),
            Text(
              'Loading indicators, 8 brains and paper position state.',
              textAlign: TextAlign.center,
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
            ),

            const SizedBox(height: 10),

            Text(
              error ?? 'Unknown error',
              textAlign: TextAlign.center,
            ),

            const SizedBox(height: 14),

            FilledButton.icon(
              onPressed: _loadEverything,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _marketSection() {
    final market =
        _map(analysis['market']);

    final price =
        _number(market['price']);

    final source =
        _string(
      analysis['source'],
      fallback: 'Online market feed',
    );

    return _section(
      title: 'LIVE MARKET',
      icon: Icons.show_chart,
      initiallyExpanded: true,
      children: [
        Row(
          children: [
            Expanded(
              child: _metric(
                'Symbol',
                symbol,
              ),
            ),
            Expanded(
              child: _metric(
                'Timeframe',
                timeframe,
              ),
            ),
          ],
        ),

        const SizedBox(height: 12),

        _largeMetric(
          'CURRENT PRICE',
          price.toStringAsFixed(2),
        ),

        const SizedBox(height: 12),

        _infoRow(
          'Data source',
          source,
        ),

        _infoRow(
          'Feed',
          'Online',
        ),
      ],
    );
  }

  Widget _raymondSection() {
    final raymond =
        _map(analysis['raymond']);

    final signal =
        _string(
      raymond['signal'],
      fallback: 'WAIT',
    );

    final direction =
        _string(
      raymond['direction'],
      fallback: signal,
    );

    final trend =
        _string(
      raymond['trend'],
      fallback: 'Neutral',
    );

    final confidence =
        _number(
      raymond['confidence'],
    );

    final technicalScore =
        _number(
      raymond['technical_score'],
    );

    final regime =
        _string(
      raymond['market_regime'],
      fallback: 'uncertain',
    );

    final setup =
        _string(
      raymond['setup'],
      fallback: 'no_setup',
    );

    final confluence =
        _number(
      raymond['confluence_score'],
    );

    final color =
        _signalColor(signal);

    return _section(
      title: 'RAYMOND STEP 13',
      icon: Icons.psychology,
      initiallyExpanded: true,
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            borderRadius:
                BorderRadius.circular(14),
            border: Border.all(
              color:
                  color.withOpacity(0.5),
            ),
          ),
          child: Column(
            children: [
              const Text(
                'RAYMOND DECISION',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                ),
              ),

              const SizedBox(height: 6),

              Text(
                signal.toUpperCase(),
                style: TextStyle(
                  fontSize: 34,
                  fontWeight: FontWeight.w900,
                  color: color,
                ),
              ),

              const SizedBox(height: 4),

              Text(
                direction.toUpperCase(),
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 14),

        Row(
          children: [
            Expanded(
              child: _metric(
                'Confidence',
                '${confidence.toStringAsFixed(1)}%',
              ),
            ),
            Expanded(
              child: _metric(
                'Technical',
                technicalScore
                    .toStringAsFixed(0),
              ),
            ),
            Expanded(
              child: _metric(
                'Confluence',
                confluence
                    .toStringAsFixed(0),
              ),
            ),
          ],
        ),

        const SizedBox(height: 12),

        _infoRow(
          'Trend',
          trend,
        ),

        _infoRow(
          'Market regime',
          regime,
        ),

        _infoRow(
          'Setup',
          setup,
        ),
      ],
    );
  }

  Widget _brainsSection() {
    final comparison =
        _map(
      analysis['advisory_comparison'],
    );

    final brains =
        _extractBrains(
      comparison,
      analysis,
    );

    final advisoryDirection =
        _string(
      comparison['advisory_direction'],
      fallback: 'WAIT',
    );

    final advisoryConfidence =
        _number(
      comparison['advisory_confidence'],
    );

    final advisoryScore =
        _number(
      comparison['advisory_score'],
    );

    final buyVotes =
        _int(
      comparison['buy_votes'],
    );

    final sellVotes =
        _int(
      comparison['sell_votes'],
    );

    final waitVotes =
        _int(
      comparison['wait_votes'],
    );

    final agreement =
        _number(
      comparison['agreement_percent'],
    );

    final entryQuality =
        _string(
      comparison['entry_quality'],
      fallback: 'UNKNOWN',
    );

    final comparisonStatus =
        _string(
      comparison['status'],
      fallback: _string(
        comparison['comparison'],
        fallback: 'UNKNOWN',
      ),
    );

    return _section(
      title: '8 ADVISORY BRAINS',
      icon: Icons.hub,
      initiallyExpanded: true,
      children: [
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius:
                BorderRadius.circular(12),
            color: _comparisonColor(
              comparisonStatus,
            ).withOpacity(0.08),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      'MASTER CONSENSUS',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),

                  _statusChip(
                    comparisonStatus,
                    _comparisonColor(
                      comparisonStatus,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 12),

              Row(
                children: [
                  Expanded(
                    child: _metric(
                      'Direction',
                      advisoryDirection
                          .toUpperCase(),
                    ),
                  ),
                  Expanded(
                    child: _metric(
                      'Confidence',
                      '${advisoryConfidence.toStringAsFixed(1)}%',
                    ),
                  ),
                  Expanded(
                    child: _metric(
                      'Score',
                      advisoryScore
                          .toStringAsFixed(1),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 12),

              Row(
                children: [
                  Expanded(
                    child: _voteMetric(
                      'BUY',
                      buyVotes,
                      Colors.green,
                    ),
                  ),
                  Expanded(
                    child: _voteMetric(
                      'SELL',
                      sellVotes,
                      Colors.red,
                    ),
                  ),
                  Expanded(
                    child: _voteMetric(
                      'WAIT',
                      waitVotes,
                      Colors.orange,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 12),

              _infoRow(
                'Agreement',
                '${agreement.toStringAsFixed(1)}%',
              ),

              _infoRow(
                'Entry quality',
                entryQuality,
              ),
            ],
          ),
        ),

        const SizedBox(height: 14),

        if (brains.isEmpty)
          const Padding(
            padding: EdgeInsets.all(12),
            child: Text(
              'No individual brain data returned by the advisory API.',
            ),
          )
        else
          ...brains.map(
            (brain) => _brainCard(brain),
          ),
      ],
    );
  }

  List<Map<String, dynamic>> _extractBrains(
    Map<String, dynamic> comparison,
    Map<String, dynamic> root,
  ) {
    dynamic raw;

    final advisory =
        _map(
      comparison['advisory'],
    );

    if (advisory['brains'] is List) {
      raw = advisory['brains'];
    } else if (comparison['brains'] is List) {
      raw = comparison['brains'];
    } else if (root['brains'] is List) {
      raw = root['brains'];
    }

    return _list(raw)
        .whereType<Map>()
        .map(
          (item) =>
              Map<String, dynamic>.from(item),
        )
        .toList();
  }

  Widget _brainCard(
    Map<String, dynamic> brain,
  ) {
    final name =
        _string(
      brain['brain'],
      fallback: _string(
        brain['name'],
        fallback: 'Advisory Brain',
      ),
    );

    final vote =
        _string(
      brain['vote'],
      fallback: _string(
        brain['direction'],
        fallback: 'WAIT',
      ),
    );

    final confidence =
        _number(
      brain['confidence'],
    );

    final score =
        _number(
      brain['score'],
    );

    final evidence =
        _string(
      brain['evidence'],
      fallback: _string(
        brain['reasoning'],
        fallback: 'No evidence supplied.',
      ),
    );

    final color =
        _signalColor(vote);

    return Card(
      margin:
          const EdgeInsets.only(bottom: 9),
      child: ExpansionTile(
        leading: Icon(
          Icons.psychology_alt,
          color: color,
        ),
        title: Text(
          name,
          style: const TextStyle(
            fontWeight: FontWeight.bold,
          ),
        ),
        trailing: _statusChip(
          vote.toUpperCase(),
          color,
        ),
        childrenPadding:
            const EdgeInsets.fromLTRB(
          16,
          0,
          16,
          16,
        ),
        children: [
          Row(
            children: [
              Expanded(
                child: _metric(
                  'Vote',
                  vote.toUpperCase(),
                ),
              ),
              Expanded(
                child: _metric(
                  'Confidence',
                  '${confidence.toStringAsFixed(1)}%',
                ),
              ),
              Expanded(
                child: _metric(
                  'Score',
                  score.toStringAsFixed(1),
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Evidence',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: Theme.of(context)
                    .textTheme
                    .bodyMedium
                    ?.color
                    ?.withOpacity(0.7),
              ),
            ),
          ),

          const SizedBox(height: 5),

          Align(
            alignment: Alignment.centerLeft,
            child: Text(evidence),
          ),
        ],
      ),
    );
  }

  Widget _tradePlanSection() {
    final raymond =
        _map(analysis['raymond']);

    final proposal =
        _map(
      raymond['proposal'],
    );

    final entry =
        _firstNumber([
      proposal['entry_price'],
      proposal['entry'],
      raymond['entry_price'],
    ]);

    final stopLoss =
        _firstNumber([
      proposal['stop_loss'],
      proposal['sl'],
      raymond['stop_loss'],
    ]);

    final tp1 =
        _firstNumber([
      proposal['take_profit_1'],
      proposal['tp1'],
      raymond['take_profit_1'],
    ]);

    final tp2 =
        _firstNumber([
      proposal['take_profit_2'],
      proposal['tp2'],
      raymond['take_profit_2'],
    ]);

    final takeProfit =
        _firstNumber([
      proposal['take_profit'],
      raymond['take_profit'],
      tp1,
    ]);

    final rr =
        _firstNumber([
      proposal['risk_reward'],
      proposal['rr'],
      raymond['risk_reward'],
    ]);

    final quantity =
        _firstNumber([
      proposal['position_size'],
      proposal['quantity'],
      proposal['volume'],
      raymond['position_size'],
    ]);

    final riskAmount =
        _firstNumber([
      proposal['risk_amount'],
      proposal['monetary_risk'],
      raymond['risk_amount'],
    ]);

    final riskAllowed =
        _bool(
      proposal['risk_allowed'],
      fallback: _bool(
        raymond['risk_allowed'],
        fallback: false,
      ),
    );

    final executionType =
        _string(
      raymond['execution_type'],
      fallback: 'paper',
    );

    return _section(
      title: 'TRADE PLAN',
      icon: Icons.track_changes,
      initiallyExpanded: true,
      children: [
        Row(
          children: [
            Expanded(
              child: _tradePriceTile(
                'ENTRY',
                entry,
              ),
            ),
            Expanded(
              child: _tradePriceTile(
                'STOP LOSS',
                stopLoss,
              ),
            ),
          ],
        ),

        const SizedBox(height: 10),

        Row(
          children: [
            Expanded(
              child: _tradePriceTile(
                'TAKE PROFIT 1',
                takeProfit,
              ),
            ),
            Expanded(
              child: _tradePriceTile(
                'TAKE PROFIT 2',
                tp2,
              ),
            ),
          ],
        ),

        const SizedBox(height: 14),

        Row(
          children: [
            Expanded(
              child: _metric(
                'Risk / Reward',
                rr == null
                    ? '--'
                    : '${rr.toStringAsFixed(2)}R',
              ),
            ),
            Expanded(
              child: _metric(
                'Position size',
                quantity == null
                    ? '--'
                    : quantity
                        .toStringAsFixed(2),
              ),
            ),
          ],
        ),

        const SizedBox(height: 12),

        _infoRow(
          'Risk amount',
          riskAmount == null
              ? '--'
              : riskAmount
                  .toStringAsFixed(2),
        ),

        _infoRow(
          'Risk approval',
          riskAllowed
              ? 'APPROVED'
              : 'NOT APPROVED',
          valueColor:
              riskAllowed
                  ? Colors.green
                  : Colors.red,
        ),

        _infoRow(
          'Execution',
          executionType.toUpperCase(),
        ),

        _infoRow(
          'Broker order',
          'DISABLED',
          valueColor: Colors.green,
        ),
      ],
    );
  }

  double? _firstNumber(
    List<dynamic> values,
  ) {
    for (final value in values) {
      if (value == null) {
        continue;
      }

      if (value is num) {
        return value.toDouble();
      }

      if (value is String) {
        final parsed =
            double.tryParse(value);

        if (parsed != null) {
          return parsed;
        }
      }
    }

    return null;
  }

  Widget _tradePriceTile(
    String label,
    double? value,
  ) {
    return Container(
      margin:
          const EdgeInsets.all(3),
      padding:
          const EdgeInsets.all(13),
      decoration: BoxDecoration(
        borderRadius:
            BorderRadius.circular(10),
        border: Border.all(
          color: Theme.of(context)
              .dividerColor,
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
            ),
          ),

          const SizedBox(height: 5),

          Text(
            value == null
                ? '--'
                : value.toStringAsFixed(2),
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }

  Widget _openTradeSection() {
    final position = openPosition;

    if (position == null) {
      return _section(
        title: 'OPEN PAPER TRADE',
        icon: Icons.swap_horiz,
        initiallyExpanded: true,
        children: [
          Container(
            width: double.infinity,
            padding:
                const EdgeInsets.all(18),
            decoration: BoxDecoration(
              borderRadius:
                  BorderRadius.circular(12),
              border: Border.all(
                color: Colors.grey
                    .withOpacity(0.35),
              ),
            ),
            child: const Column(
              children: [
                Icon(
                  Icons.pause_circle_outline,
                  size: 38,
                ),
                SizedBox(height: 8),
                Text(
                  'NO OPEN PAPER POSITION',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  'RAYMOND currently has no persistent open paper trade.',
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ],
      );
    }

    final direction =
        _string(
      position['direction'],
      fallback: 'WAIT',
    );

    final entry =
        _number(
      position['entry_price'],
    );

    final current =
        _number(
      position['current_price'],
      fallback: entry,
    );

    final sl =
        _firstNumber([
      position['current_stop_loss'],
      position['stop_loss'],
    ]);

    final tp1 =
        _firstNumber([
      position['take_profit_1'],
      position['take_profit'],
    ]);

    final tp2 =
        _numberNullable(
      position['take_profit_2'],
    );

    final pnl =
        _number(
      position['pnl'],
    );

    final pnlPercent =
        _number(
      position['pnl_percent'],
    );

    final currentR =
        _number(
      position['current_r'],
    );

    final quantity =
        _firstNumber([
      position['remaining_quantity'],
      position['quantity'],
    ]);

    final status =
        _string(
      position['status'],
      fallback: 'open',
    );

    final color =
        _signalColor(direction);

    return _section(
      title: 'OPEN PAPER TRADE',
      icon: Icons.swap_horiz,
      initiallyExpanded: true,
      children: [
        Container(
          width: double.infinity,
          padding:
              const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius:
                BorderRadius.circular(14),
            border: Border.all(
              color: color.withOpacity(0.45),
            ),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      direction.toUpperCase(),
                      style: TextStyle(
                        fontSize: 25,
                        fontWeight: FontWeight.w900,
                        color: color,
                      ),
                    ),
                  ),
                  _statusChip(
                    status.toUpperCase(),
                    color,
                  ),
                ],
              ),

              const SizedBox(height: 16),

              Row(
                children: [
                  Expanded(
                    child: _metric(
                      'Entry',
                      entry.toStringAsFixed(2),
                    ),
                  ),
                  Expanded(
                    child: _metric(
                      'Current',
                      current.toStringAsFixed(2),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 14),

              _positionRange(
                direction: direction,
                entry: entry,
                current: current,
                stopLoss: sl,
                takeProfit: tp1,
              ),

              const SizedBox(height: 14),

              Row(
                children: [
                  Expanded(
                    child: _pnlMetric(
                      'P&L',
                      pnl,
                      pnl >= 0
                          ? Colors.green
                          : Colors.red,
                    ),
                  ),
                  Expanded(
                    child: _pnlMetric(
                      'P&L %',
                      pnlPercent,
                      pnlPercent >= 0
                          ? Colors.green
                          : Colors.red,
                      suffix: '%',
                    ),
                  ),
                  Expanded(
                    child: _pnlMetric(
                      'R',
                      currentR,
                      currentR >= 0
                          ? Colors.green
                          : Colors.red,
                      suffix: 'R',
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 14),

              _infoRow(
                'Stop loss',
                _formatNullable(
                  sl,
                ),
              ),

              _infoRow(
                'Take profit 1',
                _formatNullable(
                  tp1,
                ),
              ),

              _infoRow(
                'Take profit 2',
                _formatNullable(
                  tp2,
                ),
              ),

              _infoRow(
                'Remaining volume',
                quantity == null
                    ? '--'
                    : quantity
                        .toStringAsFixed(2),
              ),
            ],
          ),
        ),
      ],
    );
  }

  double? _numberNullable(
    dynamic value,
  ) {
    if (value == null) {
      return null;
    }

    if (value is num) {
      return value.toDouble();
    }

    if (value is String) {
      return double.tryParse(value);
    }

    return null;
  }

  Widget _positionRange({
    required String direction,
    required double entry,
    required double current,
    required double? stopLoss,
    required double? takeProfit,
  }) {
    final values = <double>[
      entry,
      current,
      if (stopLoss != null) stopLoss,
      if (takeProfit != null) takeProfit,
    ];

    double minValue = values.reduce(
      (a, b) => a < b ? a : b,
    );

    double maxValue = values.reduce(
      (a, b) => a > b ? a : b,
    );

    if ((maxValue - minValue).abs() < 0.0001) {
      minValue -= 1;
      maxValue += 1;
    }

    final range = maxValue - minValue;

    double position(double value) {
      return ((value - minValue) / range)
          .clamp(0.0, 1.0);
    }

    return Column(
      crossAxisAlignment:
          CrossAxisAlignment.start,
      children: [
        const Text(
          'PRICE MAP',
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.bold,
          ),
        ),

        const SizedBox(height: 8),

        SizedBox(
          height: 70,
          child: Stack(
            children: [
              Align(
                alignment:
                    Alignment.centerLeft,
                child: Container(
                  height: 6,
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: Colors.grey
                        .withOpacity(0.25),
                    borderRadius:
                        BorderRadius.circular(5),
                  ),
                ),
              ),

              if (stopLoss != null)
                _mapMarker(
                  position(stopLoss),
                  Colors.red,
                  'SL',
                ),

              _mapMarker(
                position(entry),
                Colors.orange,
                'ENTRY',
              ),

              _mapMarker(
                position(current),
                Colors.blue,
                'NOW',
              ),

              if (takeProfit != null)
                _mapMarker(
                  position(takeProfit),
                  Colors.green,
                  'TP',
                ),
            ],
          ),
        ),

        Row(
          mainAxisAlignment:
              MainAxisAlignment.spaceBetween,
          children: [
            Text(
              minValue.toStringAsFixed(2),
              style:
                  const TextStyle(fontSize: 10),
            ),
            Text(
              maxValue.toStringAsFixed(2),
              style:
                  const TextStyle(fontSize: 10),
            ),
          ],
        ),
      ],
    );
  }

  Widget _mapMarker(
    double position,
    Color color,
    String label,
  ) {
    return Positioned(
      left: position * 100,
      right: null,
      top: 5,
      child: Column(
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 9,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          const SizedBox(height: 3),
          Container(
            width: 10,
            height: 30,
            decoration: BoxDecoration(
              color: color,
              borderRadius:
                  BorderRadius.circular(5),
            ),
          ),
        ],
      ),
    );
  }

  Widget _managementSection() {
    final position = openPosition;

    if (position == null) {
      return _section(
        title: 'TRADE MANAGEMENT',
        icon: Icons.manage_accounts,
        children: [
          const Text(
            'No open paper position to manage.',
          ),
        ],
      );
    }

    final breakEven =
        _bool(
      position['break_even_applied'],
    );

    final partial =
        _bool(
      position['partial_close_applied'],
    );

    final trailing =
        _bool(
      position['trailing_active'],
    );

    final managementStatus =
        _string(
      position['management_status'],
      fallback: 'HOLD',
    );

    final lastAction =
        _string(
      position['last_management_action'],
      fallback: 'NONE',
    );

    final currentStop =
        _firstNumber([
      position['current_stop_loss'],
      position['stop_loss'],
    ]);

    final remaining =
        _firstNumber([
      position['remaining_quantity'],
      position['quantity'],
    ]);

    return _section(
      title: 'TRADE MANAGEMENT',
      icon: Icons.manage_accounts,
      initiallyExpanded: true,
      children: [
        _managementStatusTile(
          'BREAK EVEN',
          breakEven,
          breakEven
              ? 'ACTIVE'
              : 'NOT ACTIVE',
        ),

        const SizedBox(height: 8),

        _managementStatusTile(
          'PARTIAL CLOSE',
          partial,
          partial
              ? 'EXECUTED'
              : 'NOT EXECUTED',
        ),

        const SizedBox(height: 8),

        _managementStatusTile(
          'TRAILING STOP',
          trailing,
          trailing
              ? 'ACTIVE'
              : 'NOT ACTIVE',
        ),

        const SizedBox(height: 14),

        _infoRow(
          'Management state',
          managementStatus,
        ),

        _infoRow(
          'Last action',
          lastAction,
        ),

        _infoRow(
          'Current protected SL',
          currentStop == null
              ? '--'
              : currentStop
                  .toStringAsFixed(2),
        ),

        _infoRow(
          'Remaining volume',
          remaining == null
              ? '--'
              : remaining
                  .toStringAsFixed(2),
        ),
      ],
    );
  }

  Widget _managementStatusTile(
    String title,
    bool active,
    String value,
  ) {
    final color =
        active ? Colors.green : Colors.grey;

    return Container(
      padding:
          const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius:
            BorderRadius.circular(10),
        border: Border.all(
          color:
              color.withOpacity(0.35),
        ),
      ),
      child: Row(
        children: [
          Icon(
            active
                ? Icons.check_circle
                : Icons.radio_button_unchecked,
            color: color,
          ),

          const SizedBox(width: 10),

          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                fontWeight: FontWeight.bold,
              ),
            ),
          ),

          Text(
            value,
            style: TextStyle(
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _reasoningSection() {
    final raymond =
        _map(analysis['raymond']);

    final reasoning =
        _string(
      raymond['reasoning'],
      fallback: _string(
        analysis['reasoning'],
        fallback:
            'No reasoning returned.',
      ),
    );

    final comparison =
        _map(
      analysis['advisory_comparison'],
    );

    final summary =
        _string(
      comparison['summary'],
      fallback: '',
    );

    final warning =
        _string(
      comparison['warning'],
      fallback: '',
    );

    return _section(
      title: 'WHY RAYMOND DECIDED',
      icon: Icons.article_outlined,
      initiallyExpanded: false,
      children: [
        const Align(
          alignment: Alignment.centerLeft,
          child: Text(
            'RAYMOND REASONING',
            style: TextStyle(
              fontWeight: FontWeight.bold,
            ),
          ),
        ),

        const SizedBox(height: 7),

        Text(reasoning),

        if (summary.isNotEmpty) ...[
          const SizedBox(height: 16),

          const Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'ADVISORY SUMMARY',
              style: TextStyle(
                fontWeight: FontWeight.bold,
              ),
            ),
          ),

          const SizedBox(height: 7),

          Text(summary),
        ],

        if (warning.isNotEmpty) ...[
          const SizedBox(height: 16),

          Container(
            width: double.infinity,
            padding:
                const EdgeInsets.all(12),
            decoration: BoxDecoration(
              borderRadius:
                  BorderRadius.circular(10),
              color: Colors.orange
                  .withOpacity(0.10),
            ),
            child: Row(
              crossAxisAlignment:
                  CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.warning_amber,
                  color: Colors.orange,
                ),

                const SizedBox(width: 8),

                Expanded(
                  child: Text(warning),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _technicalIndicatorsSection() {
    final indicatorResponse =
        _map(analysis['indicators']);

    final indicators =
        _map(
      indicatorResponse['indicators'],
    );

    final rsi =
        _firstNumber([
      indicators['rsi14'],
      indicators['rsi'],
    ]);

    final macd =
        _numberNullable(
      indicators['macd'],
    );

    final macdSignal =
        _numberNullable(
      indicators['macd_signal'],
    );

    final histogram =
        _numberNullable(
      indicators['macd_histogram'],
    );

    final ema20 =
        _numberNullable(
      indicators['ema20'],
    );

    final ema50 =
        _numberNullable(
      indicators['ema50'],
    );

    final atr =
        _firstNumber([
      indicators['atr14'],
      indicators['atr'],
    ]);

    return _section(
      title: 'TECHNICAL INDICATORS',
      icon: Icons.analytics_outlined,
      initiallyExpanded: false,
      children: [
        _indicatorRow(
          'RSI 14',
          _formatNullable(
            rsi,
            decimals: 2,
          ),
        ),

        _indicatorRow(
          'MACD',
          _formatNullable(
            macd,
            decimals: 4,
          ),
        ),

        _indicatorRow(
          'MACD Signal',
          _formatNullable(
            macdSignal,
            decimals: 4,
          ),
        ),

        _indicatorRow(
          'MACD Histogram',
          _formatNullable(
            histogram,
            decimals: 4,
          ),
        ),

        _indicatorRow(
          'EMA 20',
          _formatNullable(
            ema20,
            decimals: 2,
          ),
        ),

        _indicatorRow(
          'EMA 50',
          _formatNullable(
            ema50,
            decimals: 2,
          ),
        ),

        _indicatorRow(
          'ATR 14',
          _formatNullable(
            atr,
            decimals: 4,
          ),
        ),
      ],
    );
  }

  Widget _safetySection() {
    final safety =
        _map(analysis['safety']);

    final paper =
        _bool(
      safety['paper_trading_enabled'],
      fallback: true,
    );

    final live =
        _bool(
      safety['live_trading_enabled'],
      fallback: false,
    );

    final broker =
        _bool(
      safety['broker_orders_allowed'],
      fallback: false,
    );

    final authorized =
        _bool(
      safety['execution_authorized'],
      fallback: false,
    );

    final riskBypass =
        _bool(
      safety['risk_engine_bypass'],
      fallback: false,
    );

    final step13Replaced =
        _bool(
      safety['step13_replaced'],
      fallback: false,
    );

    return _section(
      title: 'SAFETY',
      icon: Icons.shield_outlined,
      initiallyExpanded: true,
      children: [
        _safetyRow(
          'Paper trading',
          paper,
          true,
        ),

        _safetyRow(
          'Live trading',
          live,
          false,
        ),

        _safetyRow(
          'Broker orders',
          broker,
          false,
        ),

        _safetyRow(
          'Execution authorized',
          authorized,
          false,
        ),

        _safetyRow(
          'Risk engine bypass',
          riskBypass,
          false,
        ),

        _safetyRow(
          'Step 13 replaced',
          step13Replaced,
          false,
        ),

        const SizedBox(height: 12),

        Container(
          width: double.infinity,
          padding:
              const EdgeInsets.all(12),
          decoration: BoxDecoration(
            borderRadius:
                BorderRadius.circular(10),
            color: Colors.green
                .withOpacity(0.08),
          ),
          child: const Row(
            children: [
              Icon(
                Icons.lock,
                color: Colors.green,
              ),

              SizedBox(width: 8),

              Expanded(
                child: Text(
                  'This screen is READ-ONLY. It cannot place broker orders.',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _safetyRow(
    String title,
    bool value,
    bool desired,
  ) {
    final safe =
        value == desired;

    final color =
        safe ? Colors.green : Colors.red;

    return Padding(
      padding:
          const EdgeInsets.symmetric(
        vertical: 6,
      ),
      child: Row(
        children: [
          Icon(
            safe
                ? Icons.check_circle
                : Icons.warning,
            color: color,
            size: 20,
          ),

          const SizedBox(width: 10),

          Expanded(
            child: Text(title),
          ),

          Text(
            value ? 'ON' : 'OFF',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _section({
    required String title,
    required IconData icon,
    required List<Widget> children,
    bool initiallyExpanded = false,
  }) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: ExpansionTile(
        initiallyExpanded:
            initiallyExpanded,
        leading: Icon(icon),
        title: Text(
          title,
          style: const TextStyle(
            fontWeight: FontWeight.bold,
          ),
        ),
        childrenPadding:
            const EdgeInsets.fromLTRB(
          16,
          0,
          16,
          16,
        ),
        children: children,
      ),
    );
  }

  Widget _metric(
    String label,
    String value,
  ) {
    return Padding(
      padding:
          const EdgeInsets.symmetric(
        horizontal: 3,
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.color
                  ?.withOpacity(0.65),
            ),
          ),

          const SizedBox(height: 4),

          Text(
            value,
            style: const TextStyle(
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _largeMetric(
    String label,
    String value,
  ) {
    return Container(
      padding:
          const EdgeInsets.all(15),
      decoration: BoxDecoration(
        borderRadius:
            BorderRadius.circular(12),
        border: Border.all(
          color: Theme.of(context)
              .dividerColor,
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
            ),
          ),

          const SizedBox(height: 4),

          Text(
            value,
            style: const TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
      ),
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
            fontSize: 11,
            color: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.color
                ?.withOpacity(0.65),
          ),
        ),

        const SizedBox(height: 4),

        Text(
          value,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            color: color,
          ),
        ),
      ],
    );
  }

  Widget _infoRow(
    String label,
    String value, {
    Color? valueColor,
  }) {
    return Padding(
      padding:
          const EdgeInsets.symmetric(
        vertical: 5,
      ),
      child: Row(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: Theme.of(context)
                    .textTheme
                    .bodyMedium
                    ?.color
                    ?.withOpacity(0.7),
              ),
            ),
          ),

          const SizedBox(width: 12),

          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: valueColor,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _indicatorRow(
    String label,
    String value,
  ) {
    return Padding(
      padding:
          const EdgeInsets.symmetric(
        vertical: 6,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(label),
          ),
          Text(
            value,
            style: const TextStyle(
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _voteMetric(
    String label,
    int votes,
    Color color,
  ) {
    return Column(
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.bold,
            color: color,
          ),
        ),

        const SizedBox(height: 4),

        Text(
          votes.toString(),
          style: TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.w900,
            color: color,
          ),
        ),
      ],
    );
  }

  Widget _pnlMetric(
    String label,
    double value,
    Color color, {
    String suffix = '',
  }) {
    final sign =
        value > 0 ? '+' : '';

    return Column(
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.bold,
          ),
        ),

        const SizedBox(height: 4),

        Text(
          '$sign${value.toStringAsFixed(2)}$suffix',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w900,
            color: color,
          ),
        ),
      ],
    );
  }

  Widget _statusChip(
    String value,
    Color color,
  ) {
    return Container(
      padding:
          const EdgeInsets.symmetric(
        horizontal: 9,
        vertical: 5,
      ),
      decoration: BoxDecoration(
        borderRadius:
            BorderRadius.circular(20),
        color: color.withOpacity(0.10),
        border: Border.all(
          color: color.withOpacity(0.35),
        ),
      ),
      child: Text(
        value,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.bold,
          color: color,
        ),
      ),
    );
  }
}
