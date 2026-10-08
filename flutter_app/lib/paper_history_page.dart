import 'package:flutter/material.dart';

import 'api_service.dart';

class PaperHistoryPage extends StatefulWidget {
  const PaperHistoryPage({
    super.key,
    required this.api,
  });

  final ApiService api;

  @override
  State<PaperHistoryPage> createState() =>
      _PaperHistoryPageState();
}

class _PaperHistoryPageState
    extends State<PaperHistoryPage> {
  static const gold = Color(0xFFF5B82E);
  static const green = Color(0xFF00E59B);
  static const red = Color(0xFFFF5C6C);
  static const background = Color(0xFF030B14);
  static const card = Color(0xFF091724);
  static const border = Color(0xFF17334D);
  static const muted = Color(0xFF8EA4B8);

  bool loading = true;
  bool loadingMore = false;

  String error = '';

  List<Map<String, dynamic>> trades = [];

  int totalTrades = 0;
  int offset = 0;

  static const int pageSize = 50;

  @override
  void initState() {
    super.initState();
    _loadHistory(reset: true);
  }

  Future<void> _loadHistory({
    bool reset = false,
  }) async {
    if (loadingMore) {
      return;
    }

    if (reset) {
      setState(() {
        loading = true;
        error = '';
        trades = [];
        offset = 0;
      });
    } else {
      setState(() {
        loadingMore = true;
        error = '';
      });
    }

    try {
      final response =
          await widget.api.paperJournalTrades(
        limit: pageSize,
        offset: reset ? 0 : offset,
      );

      final rawTrades = response['trades'];

      if (rawTrades is! List) {
        throw const FormatException(
          'Invalid paper history response.',
        );
      }

      final fetched = rawTrades
          .whereType<Map>()
          .map(
            (item) =>
                Map<String, dynamic>.from(item),
          )
          .where(
            (trade) =>
                '${trade['status'] ?? ''}'
                    .toLowerCase() ==
                'closed',
          )
          .toList();

      final total =
          response['total'] is num
              ? (response['total'] as num).toInt()
              : fetched.length;

      if (!mounted) {
        return;
      }

      setState(() {
        if (reset) {
          trades = fetched;
          offset = pageSize;
        } else {
          trades.addAll(fetched);
          offset += pageSize;
        }

        totalTrades = total;

        loading = false;
        loadingMore = false;
      });
    } catch (exc) {
      if (!mounted) {
        return;
      }

      setState(() {
        loading = false;
        loadingMore = false;
        error = 'Unable to load paper history';
      });
    }
  }

  bool get canLoadMore {
    return trades.length < totalTrades;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      appBar: AppBar(
        backgroundColor: background,
        elevation: 0,
        title: const Row(
          children: [
            Text(
              'PAPER',
              style: TextStyle(
                fontWeight: FontWeight.w800,
                letterSpacing: 1.1,
              ),
            ),
            SizedBox(width: 6),
            Text(
              'HISTORY',
              style: TextStyle(
                color: gold,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.1,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: loading
                ? null
                : () => _loadHistory(
                      reset: true,
                    ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _loadHistory(
          reset: true,
        ),
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (loading) {
      return const Center(
        child: CircularProgressIndicator(
          color: gold,
        ),
      );
    }

    if (error.isNotEmpty &&
        trades.isEmpty) {
      return ListView(
        physics:
            const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          _errorCard(),
        ],
      );
    }

    return ListView(
      physics:
          const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(
        16,
        8,
        16,
        30,
      ),
      children: [
        _summaryCard(),

        const SizedBox(height: 14),

        if (trades.isEmpty)
          _emptyCard()
        else
          ...trades.map(
            _historyCard,
          ),

        if (canLoadMore)
          Padding(
            padding:
                const EdgeInsets.only(
              top: 10,
            ),
            child: SizedBox(
              height: 48,
              child: OutlinedButton(
                onPressed: loadingMore
                    ? null
                    : () => _loadHistory(
                          reset: false,
                        ),
                style:
                    OutlinedButton.styleFrom(
                  side: const BorderSide(
                    color: border,
                  ),
                ),
                child: loadingMore
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child:
                            CircularProgressIndicator(
                          strokeWidth: 2,
                          color: gold,
                        ),
                      )
                    : const Text(
                        'LOAD MORE',
                        style: TextStyle(
                          color: gold,
                          fontWeight:
                              FontWeight.bold,
                        ),
                      ),
              ),
            ),
          ),
      ],
    );
  }

  Widget _summaryCard() {
    double realizedPnl = 0.0;

    for (final trade in trades) {
      final value = trade['pnl'];

      if (value is num) {
        realizedPnl += value.toDouble();
      }
    }

    final positive = realizedPnl >= 0;

    return Container(
      width: double.infinity,
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
            CrossAxisAlignment.start,
        children: [
          const Text(
            'CLOSED PAPER POSITIONS',
            style: TextStyle(
              color: gold,
              fontWeight: FontWeight.bold,
            ),
          ),

          const SizedBox(height: 16),

          Row(
            children: [
              Expanded(
                child: _summaryMetric(
                  'CLOSED',
                  '$totalTrades',
                ),
              ),
              Expanded(
                child: _summaryMetric(
                  'LOADED',
                  '${trades.length}',
                ),
              ),
              Expanded(
                child: _summaryMetric(
                  'REALIZED',
                  '${positive ? '+' : ''}'
                  '\$${realizedPnl.toStringAsFixed(2)}',
                  valueColor:
                      positive ? green : red,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _summaryMetric(
    String title,
    String value, {
    Color? valueColor,
  }) {
    return Column(
      crossAxisAlignment:
          CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            color: muted,
            fontSize: 10,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          value,
          style: TextStyle(
            color: valueColor,
            fontSize: 17,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }

  Widget _historyCard(
    Map<String, dynamic> trade,
  ) {
    final direction =
        '${trade['direction'] ?? ''}'
            .toUpperCase();

    final pnl = _number(
      trade['pnl'],
    );

    final quantity = _number(
      trade['quantity'],
    );

    final entry = _number(
      trade['entry_price'],
    );

    final exit = _number(
      trade['exit_price'],
    );

    final positive = pnl >= 0;

    return Container(
      margin:
          const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(15),
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
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color:
                      (direction == 'BUY'
                              ? green
                              : red)
                          .withOpacity(.12),
                  borderRadius:
                      BorderRadius.circular(
                    10,
                  ),
                ),
                child: Icon(
                  direction == 'BUY'
                      ? Icons.arrow_upward
                      : Icons.arrow_downward,
                  color:
                      direction == 'BUY'
                          ? green
                          : red,
                ),
              ),

              const SizedBox(width: 10),

              Expanded(
                child: Column(
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${trade['symbol'] ?? 'XAUUSD'} '
                      '$direction',
                      style:
                          const TextStyle(
                        fontWeight:
                            FontWeight.bold,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(
                      height: 3,
                    ),
                    const Text(
                      'CLOSED • PAPER',
                      style: TextStyle(
                        color: muted,
                        fontSize: 10,
                        fontWeight:
                            FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),

              Text(
                '${positive ? '+' : ''}'
                '\$${pnl.toStringAsFixed(2)}',
                style: TextStyle(
                  color:
                      positive ? green : red,
                  fontSize: 17,
                  fontWeight:
                      FontWeight.bold,
                ),
              ),
            ],
          ),

          const SizedBox(height: 14),

          _detailRow(
            'Entry',
            entry.toStringAsFixed(2),
          ),

          _detailRow(
            'Exit',
            exit > 0
                ? exit.toStringAsFixed(2)
                : '—',
          ),

          _detailRow(
            'Volume',
            quantity.toStringAsFixed(2),
          ),

          _detailRow(
            'P&L %',
            '${_number(
              trade['pnl_percent'],
            ).toStringAsFixed(2)}%',
          ),

          if (trade['stop_loss'] != null)
            _detailRow(
              'Stop Loss',
              _number(
                trade['stop_loss'],
              ).toStringAsFixed(2),
            ),

          if (trade['take_profit'] != null)
            _detailRow(
              'Take Profit',
              _number(
                trade['take_profit'],
              ).toStringAsFixed(2),
            ),

          const Divider(
            color: border,
            height: 20,
          ),

          _detailRow(
            'Opened',
            _formatDate(
              trade['opened_at'],
            ),
          ),

          _detailRow(
            'Closed',
            _formatDate(
              trade['closed_at'],
            ),
          ),
        ],
      ),
    );
  }

  Widget _detailRow(
    String label,
    String value,
  ) {
    return Padding(
      padding:
          const EdgeInsets.symmetric(
        vertical: 4,
      ),
      child: Row(
        mainAxisAlignment:
            MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: muted,
              fontSize: 12,
            ),
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

  Widget _emptyCard() {
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(16),
        border: Border.all(
          color: border,
        ),
      ),
      child: const Column(
        children: [
          Icon(
            Icons.history,
            size: 42,
            color: muted,
          ),
          SizedBox(height: 12),
          Text(
            'No closed paper positions yet.',
            style: TextStyle(
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: 6),
          Text(
            'Closed paper trades will remain '
            'here permanently.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: muted,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Widget _errorCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: red.withOpacity(.10),
        borderRadius:
            BorderRadius.circular(12),
        border: Border.all(
          color: red.withOpacity(.30),
        ),
      ),
      child: Text(
        '$error. Pull down to retry.',
        style: const TextStyle(
          color: red,
        ),
      ),
    );
  }

  double _number(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }

    return double.tryParse(
          '$value',
        ) ??
        0.0;
  }

  String _formatDate(dynamic value) {
    if (value == null) {
      return '—';
    }

    final parsed =
        DateTime.tryParse('$value');

    if (parsed == null) {
      return '$value';
    }

    final local = parsed.toLocal();

    String two(int value) =>
        value.toString().padLeft(2, '0');

    return '${local.year}-'
        '${two(local.month)}-'
        '${two(local.day)} '
        '${two(local.hour)}:'
        '${two(local.minute)}';
  }
}
