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

  Map<String, dynamic> analysis = <String, dynamic>{};

  // IMPORTANT:
  // Keep ALL open positions, not only positions.first.
  List<Map<String, dynamic>> openPositions =
      <Map<String, dynamic>>[];

  @override
  void initState() {
    super.initState();
    _loadEverything();
  }

  // ===========================================================================
  // LOAD
  // ===========================================================================

  Future<void> _loadEverything() async {
    if (!mounted) return;

    setState(() {
      loading = true;
      error = null;
    });

    try {
      final results = await Future.wait<dynamic>([
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

      final advisoryRaw = results[0];

      if (advisoryRaw is! Map) {
        throw const FormatException(
          'Invalid RAYMOND advisory response.',
        );
      }

      final advisoryData =
          Map<String, dynamic>.from(advisoryRaw);

      final positionsData =
          results[1] is Map
              ? Map<String, dynamic>.from(results[1])
              : <String, dynamic>{};

      final positions =
          positionsData['positions'];

      final allPositions =
          <Map<String, dynamic>>[];

      if (positions is List) {
        for (final item in positions) {
          if (item is Map) {
            allPositions.add(
              Map<String, dynamic>.from(item),
            );
          }
        }
      }

      final market =
          _map(advisoryData['market']);

      final responseSymbol = _string(
        market['symbol'],
        fallback: symbol,
      );

      final responseTimeframe = _string(
        market['timeframe'],
        fallback: timeframe,
      );

      if (!mounted) return;

      setState(() {
        analysis = advisoryData;
        openPositions = allPositions;
        symbol = responseSymbol;
        timeframe = responseTimeframe;
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        loading = false;
        error =
            'Unable to load the RAYMOND trading terminal.\n\n'
            '${e.toString()}';
      });
    }
  }

  // ===========================================================================
  // SAFE DATA HELPERS
  // ===========================================================================

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

    return <dynamic>[];
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

  double? _numberNullable(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }

    if (value is String) {
      return double.tryParse(value);
    }

    return null;
  }

  double _number(
    dynamic value, {
    double fallback = 0.0,
  }) {
    return _numberNullable(value) ?? fallback;
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
      final normalized =
          value.toLowerCase().trim();

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

  String _display(
    dynamic value, {
    String fallback = '--',
  }) {
    if (value == null) {
      return fallback;
    }

    final text = value.toString().trim();

    if (text.isEmpty) {
      return fallback;
    }

    return text;
  }

  String _format(
    dynamic value, {
    int decimals = 2,
    String fallback = '--',
  }) {
    final number = _numberNullable(value);

    if (number == null) {
      return fallback;
    }

    return number.toStringAsFixed(decimals);
  }

  String _percent(dynamic value) {
    final number = _numberNullable(value);

    if (number == null) {
      return '--';
    }

    return '${number.toStringAsFixed(1)}%';
  }

  // ===========================================================================
  // COLORS
  // ===========================================================================

  Color _signalColor(String value) {
    switch (value.toUpperCase()) {
      case 'BUY':
        return Colors.green;

      case 'SELL':
        return Colors.red;

      case 'WAIT':
      case 'HOLD':
      case 'HOLD/WAIT':
        return Colors.orange;

      default:
        return Colors.grey;
    }
  }

  Color _statusColor(String value) {
    final normalized =
        value.toUpperCase();

    if (normalized.contains('AGREE') ||
        normalized.contains('STRONG') ||
        normalized.contains('APPROVED') ||
        normalized.contains('ACTIVE') ||
        normalized == 'OPEN') {
      return Colors.green;
    }

    if (normalized.contains('DISAGREE') ||
        normalized.contains('REJECT') ||
        normalized.contains('ERROR') ||
        normalized.contains('BLOCK')) {
      return Colors.red;
    }

    if (normalized.contains('WAIT') ||
        normalized.contains('WEAK')) {
      return Colors.orange;
    }

    return Colors.grey;
  }

  // ===========================================================================
  // BUILD
  // ===========================================================================

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
            onPressed:
                loading ? null : _loadEverything,
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

              _openTradesSection(),

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

  // ===========================================================================
  // HEADER
  // ===========================================================================

  Widget _terminalHeader() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Container(
              width: 12,
              height: 12,
              decoration:
                  const BoxDecoration(
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
                      fontWeight:
                          FontWeight.bold,
                    ),
                  ),
                  SizedBox(height: 3),
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
                fontWeight:
                    FontWeight.bold,
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
              textAlign: TextAlign.center,
            ),

            SizedBox(height: 8),

            Text(
              'Loading market data, indicators, '
              '8 brains and paper-trade state.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 12,
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
              size: 44,
            ),

            const SizedBox(height: 10),

            Text(
              error ?? 'Unknown error',
              textAlign: TextAlign.center,
            ),

            const SizedBox(height: 14),

            FilledButton.icon(
              onPressed: _loadEverything,
              icon: const Icon(
                Icons.refresh,
              ),
              label:
                  const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  // ===========================================================================
  // SECTION
  // ===========================================================================

  Widget _section({
    required String title,
    required IconData icon,
    required List<Widget> children,
    bool initiallyExpanded = true,
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
          14,
          0,
          14,
          16,
        ),
        children: children,
      ),
    );
  }

  // ===========================================================================
  // LIVE MARKET
  // ===========================================================================

  Widget _marketSection() {
    final market =
        _map(analysis['market']);

    final price =
        _numberNullable(
      market['price'],
    );

    final source = _string(
      analysis['source'],
      fallback: 'Online market feed',
    );

    final sourceType = _string(
      analysis['source_type'],
      fallback:
          'public_reference_feed',
    );

    return _section(
      title: 'LIVE MARKET',
      icon: Icons.show_chart,
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

        const SizedBox(height: 14),

        Container(
          width: double.infinity,
          padding:
              const EdgeInsets.all(18),
          decoration: BoxDecoration(
            borderRadius:
                BorderRadius.circular(14),
            border: Border.all(
              color:
                  Theme.of(context)
                      .dividerColor,
            ),
          ),
          child: Column(
            children: [
              const Text(
                'CURRENT PRICE',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight:
                      FontWeight.bold,
                ),
              ),

              const SizedBox(height: 6),

              Text(
                price == null
                    ? '--'
                    : price.toStringAsFixed(
                        2,
                      ),
                style: const TextStyle(
                  fontSize: 34,
                  fontWeight:
                      FontWeight.w900,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 12),

        _infoRow(
          'Data source',
          source,
        ),

        _infoRow(
          'Source type',
          sourceType,
        ),

        _infoRow(
          'Market status',
          'ONLINE',
          valueColor:
              Colors.green,
        ),
      ],
    );
  }

  // ===========================================================================
  // RAYMOND
  // ===========================================================================

  Widget _raymondSection() {
    final raymond =
        _map(analysis['raymond']);

    final signal = _string(
      raymond['signal'],
      fallback: 'WAIT',
    ).toUpperCase();

    final direction = _string(
      raymond['direction'],
      fallback: 'wait',
    ).toUpperCase();

    final trend = _string(
      raymond['trend'],
      fallback: 'Unavailable',
    );

    final confidence =
        _numberNullable(
      raymond['confidence'],
    );

    final technicalScore =
        _numberNullable(
      raymond['technical_score'],
    );

    final regime = _string(
      raymond['market_regime'],
      fallback: 'Unavailable',
    );

    final setup = _string(
      raymond['setup'],
      fallback: 'Unavailable',
    );

    final confluence =
        _numberNullable(
      raymond['confluence_score'],
    );

    final reasoning = _string(
      raymond['reasoning'],
      fallback:
          'No Raymond reasoning available.',
    );

    final color =
        _signalColor(signal);

    return _section(
      title: 'RAYMOND STEP 13',
      icon: Icons.psychology,
      children: [
        Container(
          width: double.infinity,
          padding:
              const EdgeInsets.all(18),
          decoration: BoxDecoration(
            borderRadius:
                BorderRadius.circular(14),
            border: Border.all(
              color: color.withValues(
                alpha: 0.55,
              ),
            ),
          ),
          child: Column(
            children: [
              const Text(
                'RAYMOND DECISION',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight:
                      FontWeight.bold,
                ),
              ),

              const SizedBox(height: 6),

              Text(
                signal,
                style: TextStyle(
                  fontSize: 34,
                  fontWeight:
                      FontWeight.w900,
                  color: color,
                ),
              ),

              const SizedBox(height: 4),

              Text(
                direction,
                style: const TextStyle(
                  fontWeight:
                      FontWeight.bold,
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
                confidence == null
                    ? '--'
                    : '${confidence.toStringAsFixed(1)}%',
              ),
            ),
            Expanded(
              child: _metric(
                'Technical',
                technicalScore == null
                    ? '--'
                    : technicalScore
                        .toStringAsFixed(0),
              ),
            ),
            Expanded(
              child: _metric(
                'Confluence',
                confluence == null
                    ? '--'
                    : confluence
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

        const SizedBox(height: 8),

        _subCard(
          title: 'Raymond reasoning',
          child: Text(reasoning),
        ),
      ],
    );
  }

  // ===========================================================================
  // 8 BRAINS
  // ===========================================================================

  List<Map<String, dynamic>>
      _extractBrains(
    Map<String, dynamic> comparison,
  ) {
    final raw =
        comparison['brains'];

    if (raw is! List) {
      return <Map<String, dynamic>>[];
    }

    final result =
        <Map<String, dynamic>>[];

    for (final item in raw) {
      if (item is Map) {
        result.add(
          Map<String, dynamic>.from(item),
        );
      }
    }

    return result;
  }

  Widget _brainsSection() {
    final comparison =
        _map(
      analysis['advisory_comparison'],
    );

    final brains =
        _extractBrains(comparison);

    final advisory =
        _map(comparison['advisory']);

    final comparisonResult =
        _map(comparison['comparison']);

    final advisoryDirection =
        _string(
      comparison['advisory_direction'],
      fallback: _string(
        advisory['direction'],
        fallback: 'WAIT',
      ),
    );

    final advisoryConfidence =
        _numberNullable(
          comparison[
              'advisory_confidence'],
        ) ??
        _numberNullable(
          advisory['confidence'],
        );

    final advisoryScore =
        _numberNullable(
          comparison[
              'advisory_score'],
        ) ??
        _numberNullable(
          advisory['score'],
        );

    final buyVotes = _int(
      comparison['buy_votes'],
      fallback:
          _int(advisory['buy_votes']),
    );

    final sellVotes = _int(
      comparison['sell_votes'],
      fallback:
          _int(advisory['sell_votes']),
    );

    final waitVotes = _int(
      comparison['wait_votes'],
      fallback:
          _int(advisory['wait_votes']),
    );

    final agreement =
        _numberNullable(
          comparison[
              'agreement_percent'],
        ) ??
        _numberNullable(
          advisory['agreement_percent'],
        );

    final entryQuality =
        _string(
      comparison['entry_quality'],
      fallback: _string(
        advisory['entry_quality'],
        fallback: 'UNKNOWN',
      ),
    );

    final status = _string(
      comparison['status'],
      fallback: _string(
        comparisonResult['status'],
        fallback: 'UNKNOWN',
      ),
    );

    final summary = _string(
      comparison['summary'],
      fallback: _string(
        comparisonResult['summary'],
        fallback:
            'No advisory comparison summary available.',
      ),
    );

    final warning = _string(
      comparison['warning'],
      fallback: _string(
        comparisonResult['warning'],
        fallback: '',
      ),
    );

    return _section(
      title: '8 BRAINS — LIVE BREAKDOWN',
      icon: Icons.hub,
      children: [
        _subCard(
          title: 'MASTER CONSENSUS',
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      advisoryDirection
                          .toUpperCase(),
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight:
                            FontWeight.w900,
                        color:
                            _signalColor(
                          advisoryDirection,
                        ),
                      ),
                    ),
                  ),
                  _statusChip(
                    status,
                    _statusColor(status),
                  ),
                ],
              ),

              const SizedBox(height: 12),

              Row(
                children: [
                  Expanded(
                    child: _metric(
                      'Confidence',
                      advisoryConfidence ==
                              null
                          ? '--'
                          : '${advisoryConfidence.toStringAsFixed(1)}%',
                    ),
                  ),
                  Expanded(
                    child: _metric(
                      'Score',
                      advisoryScore == null
                          ? '--'
                          : advisoryScore
                              .toStringAsFixed(1),
                    ),
                  ),
                  Expanded(
                    child: _metric(
                      'Agreement',
                      agreement == null
                          ? '--'
                          : '${agreement.toStringAsFixed(1)}%',
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 12),

              _infoRow(
                'BUY votes',
                buyVotes.toString(),
              ),

              _infoRow(
                'SELL votes',
                sellVotes.toString(),
              ),

              _infoRow(
                'WAIT votes',
                waitVotes.toString(),
              ),

              _infoRow(
                'Entry quality',
                entryQuality,
              ),

              const SizedBox(height: 8),

              Text(summary),

              if (warning.isNotEmpty) ...[
                const SizedBox(height: 10),
                _warningBox(warning),
              ],
            ],
          ),
        ),

        const SizedBox(height: 14),

        if (brains.isEmpty)
          _warningBox(
            '8-brain data is unavailable from the advisory API.',
          )
        else
          ...brains.asMap().entries.map(
            (entry) => Padding(
              padding:
                  const EdgeInsets.only(
                bottom: 10,
              ),
              child: _brainCard(
                entry.key + 1,
                entry.value,
              ),
            ),
          ),
      ],
    );
  }

  Widget _brainCard(
    int index,
    Map<String, dynamic> brain,
  ) {
    final name = _string(
      brain['name'],
      fallback: 'Brain $index',
    );

    final direction = _string(
      brain['direction'],
      fallback: 'WAIT',
    );

    final confidence =
        _numberNullable(
      brain['confidence'],
    );

    final score =
        _numberNullable(
      brain['score'],
    );

    final summary = _string(
      brain['summary'],
      fallback:
          'No evidence summary available.',
    );

    final evidence =
        _list(brain['evidence']);

    final color =
        _signalColor(direction);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        borderRadius:
            BorderRadius.circular(12),
        border: Border.all(
          color: color.withValues(
            alpha: 0.35,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 15,
                child: Text(
                  index.toString(),
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),
              ),

              const SizedBox(width: 10),

              Expanded(
                child: Text(
                  name,
                  style:
                      const TextStyle(
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),
              ),

              Text(
                direction.toUpperCase(),
                style: TextStyle(
                  fontWeight:
                      FontWeight.w900,
                  color: color,
                ),
              ),
            ],
          ),

          const SizedBox(height: 10),

          Row(
            children: [
              Expanded(
                child: _metric(
                  'Confidence',
                  confidence == null
                      ? '--'
                      : '${confidence.toStringAsFixed(1)}%',
                ),
              ),
              Expanded(
                child: _metric(
                  'Score',
                  score == null
                      ? '--'
                      : score.toStringAsFixed(
                          1,
                        ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 8),

          Text(
            summary,
            style:
                const TextStyle(
              fontSize: 13,
            ),
          ),

          if (evidence.isNotEmpty) ...[
            const SizedBox(height: 8),

            const Text(
              'Evidence',
              style: TextStyle(
                fontWeight:
                    FontWeight.bold,
                fontSize: 12,
              ),
            ),

            const SizedBox(height: 4),

            ...evidence.map(
              (item) => Padding(
                padding:
                    const EdgeInsets.only(
                  bottom: 3,
                ),
                child: Row(
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    const Text('• '),
                    Expanded(
                      child: Text(
                        item.toString(),
                        style:
                            const TextStyle(
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  // ===========================================================================
  // TRADE PLAN
  // ===========================================================================

  Widget _tradePlanSection() {
    final raymond =
        _map(analysis['raymond']);

    final proposal =
        _map(raymond['proposal']);

    final hasProposal =
        proposal.isNotEmpty;

    final direction = _string(
      proposal['direction'],
      fallback:
          _string(
        raymond['direction'],
        fallback: 'WAIT',
      ),
    ).toUpperCase();

    final entry =
        proposal['entry'] ??
        proposal['entry_price'] ??
        proposal['price'];

    final stopLoss =
        proposal['stop_loss'] ??
        proposal['sl'];

    final tp1 =
        proposal['tp1'] ??
        proposal['take_profit_1'] ??
        proposal['take_profit'];

    final tp2 =
        proposal['tp2'] ??
        proposal['take_profit_2'];

    final riskReward =
        proposal['risk_reward'] ??
        proposal['rr'] ??
        proposal['risk_reward_ratio'];

    final quantity =
        proposal['quantity'] ??
        proposal['qty'] ??
        proposal['position_size'];

    final riskAmount =
        proposal['risk_amount'] ??
        proposal['risk'];

    final riskApproved =
        proposal['risk_approved'];

    return _section(
      title: 'TRADE PLAN',
      icon: Icons.assignment,
      children: [
        if (!hasProposal)
          _warningBox(
            'No executable trade proposal is currently available. '
            'RAYMOND remains in ${_string(raymond['direction'], fallback: 'WAIT').toUpperCase()} state.',
          ),

        _infoRow(
          'Direction',
          direction,
          valueColor:
              _signalColor(direction),
        ),

        _infoRow(
          'Entry',
          _format(entry),
        ),

        _infoRow(
          'Stop Loss',
          _format(stopLoss),
        ),

        _infoRow(
          'TP1',
          _format(tp1),
        ),

        _infoRow(
          'TP2',
          _format(tp2),
        ),

        _infoRow(
          'Risk : Reward',
          _display(riskReward),
        ),

        _infoRow(
          'Position size',
          _display(quantity),
        ),

        _infoRow(
          'Risk amount',
          _display(riskAmount),
        ),

        _infoRow(
          'Risk approved',
          riskApproved == null
              ? '--'
              : _bool(riskApproved)
                  ? 'YES'
                  : 'NO',
          valueColor:
              riskApproved == null
                  ? null
                  : _bool(riskApproved)
                      ? Colors.green
                      : Colors.red,
        ),

        _infoRow(
          'Execution',
          'PAPER',
        ),

        _infoRow(
          'Broker order',
          'OFF',
          valueColor:
              Colors.green,
        ),
      ],
    );
  }

  // ===========================================================================
  // ALL OPEN PAPER TRADES
  // ===========================================================================

  Widget _openTradesSection() {
    if (openPositions.isEmpty) {
      return _section(
        title: 'OPEN PAPER TRADES',
        icon: Icons.candlestick_chart,
        children: [
          _emptyState(
            Icons.pause_circle_outline,
            'NO OPEN PAPER TRADES',
            'RAYMOND currently has no open paper positions.',
          ),
        ],
      );
    }

    return _section(
      title:
          'OPEN PAPER TRADES (${openPositions.length})',
      icon: Icons.candlestick_chart,
      children: [
        Container(
          width: double.infinity,
          padding:
              const EdgeInsets.all(12),
          decoration: BoxDecoration(
            borderRadius:
                BorderRadius.circular(10),
            border: Border.all(
              color: Colors.green
                  .withValues(alpha: 0.35),
            ),
          ),
          child: Text(
            '${openPositions.length} open paper '
            '${openPositions.length == 1 ? 'position' : 'positions'} '
            'currently tracked by RAYMOND.',
            style: const TextStyle(
              fontWeight:
                  FontWeight.bold,
            ),
          ),
        ),

        const SizedBox(height: 12),

        // IMPORTANT:
        // Every position is rendered independently.
        ...openPositions.asMap().entries.map(
          (entry) {
            return Padding(
              padding:
                  const EdgeInsets.only(
                bottom: 12,
              ),
              child: _openTradeCard(
                entry.key + 1,
                entry.value,
              ),
            );
          },
        ),
      ],
    );
  }

  Widget _openTradeCard(
    int index,
    Map<String, dynamic> position,
  ) {
    final direction = _string(
      position['direction'],
      fallback: 'WAIT',
    ).toUpperCase();

    final status = _string(
      position['status'],
      fallback: 'OPEN',
    ).toUpperCase();

    final tradeId = _string(
      position['trade_id'],
      fallback: _string(
        position['position_id'],
        fallback: 'Position $index',
      ),
    );

    final entry =
        position['entry_price'] ??
        position['entry'];

    final currentPrice =
        position['current_price'] ??
        position['price'];

    final pnl =
        position['pnl'] ??
        position['profit_loss'];

    final pnlPercent =
        position['pnl_percent'] ??
        position['profit_loss_percent'];

    final currentR =
        position['current_r'] ??
        position['r_multiple'];

    final stopLoss =
        position['current_stop_loss'] ??
        position['current_sl'] ??
        position['stop_loss'] ??
        position['sl'];

    final takeProfit1 =
        position['take_profit_1'] ??
        position['take_profit'] ??
        position['tp'];

    final takeProfit2 =
        position['take_profit_2'];

    final quantity =
        position['remaining_quantity'] ??
        position['remaining_qty'] ??
        position['quantity'] ??
        position['qty'];

    final originalQuantity =
        position['original_quantity'] ??
        position['quantity'] ??
        quantity;

    final regime = _string(
      position['market_regime'],
      fallback: _string(
        position['regime'],
        fallback: '--',
      ),
    );

    final setup = _string(
      position['setup'],
      fallback: '--',
    );

    final technicalScore =
        position['technical_score'];

    final confluence =
        position['confluence_score'];

    final confidence =
        position['confidence'];

    final thesis = _string(
      position['trade_thesis'],
      fallback: _string(
        position['thesis'],
        fallback: 'No thesis recorded.',
      ),
    );

    final directionColor =
        _signalColor(direction);

    final pnlNumber =
        _numberNullable(pnl);

    return Container(
      width: double.infinity,
      padding:
          const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius:
            BorderRadius.circular(14),
        border: Border.all(
          color:
              directionColor.withValues(
            alpha: 0.45,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 16,
                child: Text(
                  index.toString(),
                  style:
                      const TextStyle(
                    fontSize: 12,
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),
              ),

              const SizedBox(width: 10),

              Expanded(
                child: Column(
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    Text(
                      'PAPER POSITION $index',
                      style:
                          const TextStyle(
                        fontWeight:
                            FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      tradeId,
                      style:
                          const TextStyle(
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),

              _statusChip(
                direction,
                directionColor,
              ),
            ],
          ),

          const SizedBox(height: 12),

          Row(
            children: [
              Expanded(
                child: _metric(
                  'Status',
                  status,
                ),
              ),
              Expanded(
                child: _metric(
                  'Direction',
                  direction,
                ),
              ),
            ],
          ),

          const SizedBox(height: 10),

          _infoRow(
            'Entry',
            _format(entry),
          ),

          _infoRow(
            'Current price',
            _format(currentPrice),
          ),

          _infoRow(
            'Position size',
            _display(quantity),
          ),

          _infoRow(
            'Original size',
            _display(originalQuantity),
          ),

          _infoRow(
            'Stop Loss',
            _format(stopLoss),
          ),

          _infoRow(
            'Take Profit 1',
            _format(takeProfit1),
          ),

          _infoRow(
            'Take Profit 2',
            _format(takeProfit2),
          ),

          _infoRow(
            'P&L',
            _display(pnl),
            valueColor:
                pnlNumber == null
                    ? null
                    : pnlNumber >= 0
                        ? Colors.green
                        : Colors.red,
          ),

          _infoRow(
            'P&L %',
            _display(pnlPercent),
          ),

          _infoRow(
            'Current R',
            _display(currentR),
          ),

          _infoRow(
            'Regime',
            regime,
          ),

          _infoRow(
            'Setup',
            setup,
          ),

          _infoRow(
            'Technical score',
            _display(technicalScore),
          ),

          _infoRow(
            'Confluence',
            _display(confluence),
          ),

          _infoRow(
            'Confidence',
            _display(confidence),
          ),

          const SizedBox(height: 8),

          _subCard(
            title: 'Trade thesis',
            child: Text(thesis),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // MANAGEMENT FOR ALL POSITIONS
  // ===========================================================================

  Widget _managementSection() {
    if (openPositions.isEmpty) {
      return _section(
        title: 'TRADE MANAGEMENT',
        icon: Icons.shield,
        children: [
          _emptyState(
            Icons.check_circle_outline,
            'MANAGEMENT IDLE',
            'No open paper trade requires management.',
          ),
        ],
      );
    }

    return _section(
      title: 'TRADE MANAGEMENT',
      icon: Icons.shield,
      children: [
        ...openPositions.asMap().entries.map(
          (entry) {
            return Padding(
              padding:
                  const EdgeInsets.only(
                bottom: 12,
              ),
              child:
                  _managementCard(
                entry.key + 1,
                entry.value,
              ),
            );
          },
        ),

        const SizedBox(height: 4),

        const Text(
          'Paper-trade management is displayed from '
          'the backend position state. No broker order '
          'is sent by this terminal.',
          style: TextStyle(
            fontSize: 12,
          ),
        ),
      ],
    );
  }

  Widget _managementCard(
    int index,
    Map<String, dynamic> position,
  ) {
    final tradeId = _string(
      position['trade_id'],
      fallback: _string(
        position['position_id'],
        fallback:
            'Position $index',
      ),
    );

    final breakEven = _bool(
      position['break_even_applied'],
    );

    final partial = _bool(
      position['partial_close_applied'],
    );

    final trailing = _bool(
      position['trailing_active'],
    );

    final managementStatus =
        _string(
      position['management_status'],
      fallback: 'ACTIVE',
    );

    final lastAction = _string(
      position['last_management_action'],
      fallback: 'None',
    );

    final lastActionTime =
        _string(
      position['last_management_time'],
      fallback: '--',
    );

    return Container(
      width: double.infinity,
      padding:
          const EdgeInsets.all(13),
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
          Row(
            children: [
              Expanded(
                child: Text(
                  'POSITION $index',
                  style:
                      const TextStyle(
                    fontWeight:
                        FontWeight.w900,
                  ),
                ),
              ),
              Text(
                tradeId,
                style:
                    const TextStyle(
                  fontSize: 11,
                ),
              ),
            ],
          ),

          const SizedBox(height: 10),

          _infoRow(
            'Management state',
            managementStatus,
          ),

          _infoRow(
            'Break-even',
            breakEven
                ? 'APPLIED'
                : 'NOT APPLIED',
            valueColor:
                breakEven
                    ? Colors.green
                    : null,
          ),

          _infoRow(
            'Partial profit',
            partial
                ? 'APPLIED'
                : 'NOT APPLIED',
            valueColor:
                partial
                    ? Colors.green
                    : null,
          ),

          _infoRow(
            'Trailing protection',
            trailing
                ? 'ACTIVE'
                : 'INACTIVE',
            valueColor:
                trailing
                    ? Colors.green
                    : null,
          ),

          _infoRow(
            'Last action',
            lastAction,
          ),

          _infoRow(
            'Last action time',
            lastActionTime,
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // REASONING
  // ===========================================================================

  Widget _reasoningSection() {
    final raymond =
        _map(analysis['raymond']);

    final reasoning = _string(
      raymond['reasoning'],
      fallback:
          'No Raymond reasoning is available.',
    );

    final comparison =
        _map(
      analysis[
          'advisory_comparison'],
    );

    final comparisonMap =
        _map(
      comparison['comparison'],
    );

    final summary = _string(
      comparison['summary'],
      fallback: _string(
        comparisonMap['summary'],
        fallback:
            'No comparison summary available.',
      ),
    );

    final warning = _string(
      comparison['warning'],
      fallback: _string(
        comparisonMap['warning'],
        fallback: '',
      ),
    );

    return _section(
      title: 'DECISION REASONING',
      icon: Icons.lightbulb_outline,
      children: [
        _subCard(
          title: 'Raymond',
          child: Text(reasoning),
        ),

        const SizedBox(height: 10),

        _subCard(
          title: 'Advisory comparison',
          child: Text(summary),
        ),

        if (warning.isNotEmpty) ...[
          const SizedBox(height: 10),
          _warningBox(warning),
        ],
      ],
    );
  }

  // ===========================================================================
  // TECHNICAL INDICATORS
  // ===========================================================================

  Widget _technicalIndicatorsSection() {
    final indicators =
        _map(
      analysis['indicators'],
    );

    final values =
        _map(
      indicators['indicators'],
    );

    final technicalAnalysis =
        _map(
      indicators['analysis'],
    );

    final trend = _string(
      technicalAnalysis['trend'],
      fallback: _string(
        indicators['trend'],
        fallback: '--',
      ),
    );

    final signal = _string(
      technicalAnalysis['signal'],
      fallback: _string(
        indicators['signal'],
        fallback: '--',
      ),
    );

    final score =
        _numberNullable(
          technicalAnalysis['score'],
        ) ??
        _numberNullable(
          indicators['score'],
        );

    return _section(
      title: 'TECHNICAL INDICATORS',
      icon: Icons.analytics,
      children: [
        _infoRow(
          'EMA 20',
          _format(
            values['ema20'],
            decimals: 3,
          ),
        ),

        _infoRow(
          'EMA 50',
          _format(
            values['ema50'],
            decimals: 3,
          ),
        ),

        _infoRow(
          'RSI 14',
          _format(
            values['rsi14'],
          ),
        ),

        _infoRow(
          'ATR 14',
          _format(
            values['atr14'],
          ),
        ),

        _infoRow(
          'MACD',
          _format(
            values['macd'],
          ),
        ),

        _infoRow(
          'MACD signal',
          _format(
            values['macd_signal'],
          ),
        ),

        _infoRow(
          'MACD histogram',
          _format(
            values['macd_histogram'],
          ),
        ),

        _infoRow(
          'Technical trend',
          trend,
        ),

        _infoRow(
          'Technical signal',
          signal,
          valueColor:
              _signalColor(signal),
        ),

        _infoRow(
          'Technical score',
          score == null
              ? '--'
              : score.toStringAsFixed(0),
        ),

        _infoRow(
          'Candles used',
          _display(
            indicators[
                'candles_used'],
          ),
        ),
      ],
    );
  }

  // ===========================================================================
  // SAFETY
  // ===========================================================================

  Widget _safetySection() {
    final safety =
        _map(analysis['safety']);

    final paper = _bool(
      safety[
          'paper_trading_enabled'],
      fallback: true,
    );

    final live = _bool(
      safety[
          'live_trading_enabled'],
      fallback: false,
    );

    final execution = _bool(
      safety[
          'execution_authorized'],
      fallback: false,
    );

    final broker = _bool(
      safety[
          'broker_orders_allowed'],
      fallback: false,
    );

    final riskBypass = _bool(
      safety[
          'risk_engine_bypass'],
      fallback: false,
    );

    final step13Replaced = _bool(
      safety[
          'step13_replaced'],
      fallback: false,
    );

    return _section(
      title: 'SAFETY PANEL',
      icon: Icons.security,
      children: [
        _safetyRow(
          'Paper trading',
          paper,
          safeExpected: true,
        ),

        _safetyRow(
          'Live trading',
          live,
          safeExpected: false,
        ),

        _safetyRow(
          'Broker orders',
          broker,
          safeExpected: false,
        ),

        _safetyRow(
          'Execution authorized',
          execution,
          safeExpected: false,
        ),

        _safetyRow(
          'Risk engine bypass',
          riskBypass,
          safeExpected: false,
        ),

        _safetyRow(
          'Step 13 replaced',
          step13Replaced,
          safeExpected: false,
        ),

        const SizedBox(height: 12),

        Container(
          width: double.infinity,
          padding:
              const EdgeInsets.all(13),
          decoration: BoxDecoration(
            borderRadius:
                BorderRadius.circular(12),
            border: Border.all(
              color: Colors.green
                  .withValues(alpha: 0.5),
            ),
          ),
          child: const Column(
            crossAxisAlignment:
                CrossAxisAlignment.start,
            children: [
              Text(
                'READ-ONLY / PAPER MODE',
                style: TextStyle(
                  fontWeight:
                      FontWeight.w900,
                ),
              ),

              SizedBox(height: 5),

              Text(
                'The terminal analyses markets and '
                'displays paper-trading state. '
                'Live broker execution remains disabled.',
                style: TextStyle(
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // ===========================================================================
  // UI HELPERS
  // ===========================================================================

  Widget _metric(
    String label,
    String value,
  ) {
    return Padding(
      padding:
          const EdgeInsets.symmetric(
        horizontal: 4,
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 11,
              color: Colors.grey,
            ),
          ),

          const SizedBox(height: 3),

          Text(
            value,
            style: const TextStyle(
              fontWeight:
                  FontWeight.bold,
            ),
          ),
        ],
      ),
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
              style:
                  const TextStyle(
                fontSize: 13,
              ),
            ),
          ),

          const SizedBox(width: 12),

          Flexible(
            child: Text(
              value,
              textAlign:
                  TextAlign.right,
              style: TextStyle(
                fontSize: 13,
                fontWeight:
                    FontWeight.bold,
                color: valueColor,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _statusChip(
    String text,
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
        border: Border.all(
          color: color.withValues(
            alpha: 0.5,
          ),
        ),
      ),
      child: Text(
        text.toUpperCase(),
        style: TextStyle(
          fontSize: 10,
          fontWeight:
              FontWeight.bold,
          color: color,
        ),
      ),
    );
  }

  Widget _subCard({
    required String title,
    required Widget child,
  }) {
    return Container(
      width: double.infinity,
      padding:
          const EdgeInsets.all(13),
      decoration: BoxDecoration(
        borderRadius:
            BorderRadius.circular(12),
        border: Border.all(
          color:
              Theme.of(context)
                  .dividerColor,
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontWeight:
                  FontWeight.bold,
              fontSize: 12,
            ),
          ),

          const SizedBox(height: 7),

          child,
        ],
      ),
    );
  }

  Widget _warningBox(
    String message,
  ) {
    return Container(
      width: double.infinity,
      padding:
          const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius:
            BorderRadius.circular(10),
        border: Border.all(
          color: Colors.orange
              .withValues(alpha: 0.5),
        ),
      ),
      child: Row(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.warning_amber,
            size: 20,
            color: Colors.orange,
          ),

          const SizedBox(width: 9),

          Expanded(
            child: Text(
              message,
              style:
                  const TextStyle(
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _emptyState(
    IconData icon,
    String title,
    String message,
  ) {
    return Container(
      width: double.infinity,
      padding:
          const EdgeInsets.all(18),
      child: Column(
        children: [
          Icon(
            icon,
            size: 38,
          ),

          const SizedBox(height: 8),

          Text(
            title,
            style:
                const TextStyle(
              fontWeight:
                  FontWeight.w900,
            ),
          ),

          const SizedBox(height: 5),

          Text(
            message,
            textAlign:
                TextAlign.center,
            style:
                const TextStyle(
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Widget _safetyRow(
    String label,
    bool enabled, {
    required bool safeExpected,
  }) {
    final correct =
        enabled == safeExpected;

    return Padding(
      padding:
          const EdgeInsets.symmetric(
        vertical: 5,
      ),
      child: Row(
        children: [
          Icon(
            correct
                ? Icons.check_circle
                : Icons.warning,
            size: 20,
            color: correct
                ? Colors.green
                : Colors.red,
          ),

          const SizedBox(width: 9),

          Expanded(
            child: Text(
              label,
              style:
                  const TextStyle(
                fontSize: 13,
              ),
            ),
          ),

          Text(
            enabled ? 'ON' : 'OFF',
            style: TextStyle(
              fontWeight:
                  FontWeight.bold,
              color: correct
                  ? Colors.green
                  : Colors.red,
            ),
          ),
        ],
      ),
    );
  }
}
