import 'package:flutter/material.dart';

import 'api_service.dart';

void main() {
  runApp(const RaymondApp());
}

class RaymondApp extends StatelessWidget {
  const RaymondApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'RAYMOND V2.8',
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF030B14),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFF5B82E),
          brightness: Brightness.dark,
        ),
        fontFamily: 'Roboto',
      ),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  static const gold = Color(0xFFF5B82E);
  static const green = Color(0xFF00E59B);
  static const red = Color(0xFFFF5C6C);
  static const background = Color(0xFF030B14);
  static const card = Color(0xFF091724);
  static const border = Color(0xFF17334D);
  static const muted = Color(0xFF8EA4B8);

  final ApiService api = ApiService();

  int selectedIndex = 0;

  bool loading = true;
  bool backendOnline = false;

  String errorMessage = '';

  double balance = 10000.0;
  double totalPnl = 0.0;
  int openTrades = 0;
  int totalTrades = 0;

  List<Map<String, dynamic>> trades = [];

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      loading = true;
      errorMessage = '';
    });

    try {
      final health = await api.health();

      Map<String, dynamic> status = {};
      Map<String, dynamic> performance = {};
      List<Map<String, dynamic>> fetchedTrades = [];

      try {
        status = await api.demoStatus();
      } catch (_) {}

      try {
        performance = await api.demoPerformance();
      } catch (_) {}

      try {
        fetchedTrades = await api.demoTrades();
      } catch (_) {}

      if (!mounted) return;

      setState(() {
        backendOnline = health['status'] == 'healthy';

        final balanceValue = status['balance'];
        if (balanceValue is num) {
          balance = balanceValue.toDouble();
        }

        final pnlValue = performance['total_pnl'];
        if (pnlValue is num) {
          totalPnl = pnlValue.toDouble();
        }

        final openValue = performance['open_trades'];
        if (openValue is num) {
          openTrades = openValue.toInt();
        } else {
          final statusOpen = status['open_trades'];
          if (statusOpen is num) {
            openTrades = statusOpen.toInt();
          }
        }

        final totalValue = performance['total_trades'];
        if (totalValue is num) {
          totalTrades = totalValue.toInt();
        }

        trades = fetchedTrades;
        loading = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        backendOnline = false;
        loading = false;
        errorMessage = 'Backend unavailable';
      });
    }
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
              'RAYMOND',
              style: TextStyle(
                fontWeight: FontWeight.w800,
                letterSpacing: 1.2,
              ),
            ),
            SizedBox(width: 6),
            Text(
              'V2.8',
              style: TextStyle(
                color: gold,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        actions: [
          _connectionBadge(),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: loading ? null : _refresh,
          ),
        ],
      ),
      body: _buildBody(),
      bottomNavigationBar: NavigationBar(
        backgroundColor: const Color(0xFF06111C),
        selectedIndex: selectedIndex,
        indicatorColor: gold.withOpacity(.16),
        onDestinationSelected: (index) {
          setState(() {
            selectedIndex = index;
          });
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home, color: gold),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.candlestick_chart_outlined),
            label: 'Chart',
          ),
          NavigationDestination(
            icon: Icon(Icons.analytics_outlined),
            label: 'Analysis',
          ),
          NavigationDestination(
            icon: Icon(Icons.swap_vert),
            label: 'Positions',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            label: 'Settings',
          ),
        ],
      ),
    );
  }

  Widget _connectionBadge() {
    return Container(
      margin: const EdgeInsets.only(right: 8),
      padding: const EdgeInsets.symmetric(
        horizontal: 9,
        vertical: 5,
      ),
      decoration: BoxDecoration(
        color: (backendOnline ? green : red).withOpacity(.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: (backendOnline ? green : red).withOpacity(.35),
        ),
      ),
      child: Row(
        children: [
          Icon(
            Icons.circle,
            size: 8,
            color: backendOnline ? green : red,
          ),
          const SizedBox(width: 5),
          Text(
            backendOnline ? 'ONLINE' : 'OFFLINE',
            style: TextStyle(
              color: backendOnline ? green : red,
              fontSize: 11,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (selectedIndex != 0) {
      return _placeholderPage();
    }

    return RefreshIndicator(
      onRefresh: _refresh,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (errorMessage.isNotEmpty)
              _errorCard(),

            const Text(
              'XAUUSD',
              style: TextStyle(
                color: muted,
                fontSize: 13,
              ),
            ),

            const SizedBox(height: 4),

            const Text(
              'Live market connection',
              style: TextStyle(
                fontSize: 26,
                fontWeight: FontWeight.w800,
              ),
            ),

            const SizedBox(height: 16),

            _paperCard(),

            const SizedBox(height: 14),

            Row(
              children: [
                Expanded(
                  child: _metricCard(
                    'OPEN',
                    '$openTrades',
                    'Positions',
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _metricCard(
                    'TRADES',
                    '$totalTrades',
                    'Total',
                  ),
                ),
              ],
            ),

            const SizedBox(height: 14),

            _performanceCard(),

            const SizedBox(height: 14),

            _tradesCard(),
          ],
        ),
      ),
    );
  }

  Widget _paperCard() {
    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'PAPER TRADING',
                style: TextStyle(
                  color: gold,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Icon(
                Icons.account_balance_wallet_outlined,
                color: gold,
              ),
            ],
          ),
          const SizedBox(height: 18),
          loading
              ? const LinearProgressIndicator()
              : Text(
                  '\$${balance.toStringAsFixed(2)}',
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                  ),
                ),
          const SizedBox(height: 12),
          const Text(
            'Real-money trading is disabled.',
            style: TextStyle(color: muted),
          ),
        ],
      ),
    );
  }

  Widget _performanceCard() {
    final positive = totalPnl >= 0;

    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'PERFORMANCE',
            style: TextStyle(
              color: gold,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Total P&L',
                style: TextStyle(color: muted),
              ),
              Text(
                '${positive ? '+' : ''}\$${totalPnl.toStringAsFixed(2)}',
                style: TextStyle(
                  color: positive ? green : red,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _tradesCard() {
    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'RECENT PAPER TRADES',
            style: TextStyle(
              color: gold,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          if (loading)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: CircularProgressIndicator(),
              ),
            )
          else if (trades.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 20),
              child: Center(
                child: Text(
                  'No paper trades yet.',
                  style: TextStyle(color: muted),
                ),
              ),
            )
          else
            ...trades.take(5).map(_tradeRow),
        ],
      ),
    );
  }

  Widget _tradeRow(Map<String, dynamic> trade) {
    final direction =
        '${trade['direction'] ?? ''}'.toUpperCase();

    final pnlValue = trade['pnl'];
    final pnl = pnlValue is num ? pnlValue.toDouble() : 0.0;

    final positive = pnl >= 0;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF06111C),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(
            direction == 'BUY'
                ? Icons.arrow_upward
                : Icons.arrow_downward,
            color: direction == 'BUY' ? green : red,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${trade['symbol'] ?? 'XAUUSD'} $direction',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  '${trade['status'] ?? 'unknown'}',
                  style: const TextStyle(
                    color: muted,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          Text(
            '${positive ? '+' : ''}\$${pnl.toStringAsFixed(2)}',
            style: TextStyle(
              color: positive ? green : red,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _metricCard(
    String title,
    String value,
    String subtitle,
  ) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(color: muted),
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: const TextStyle(
              fontSize: 23,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            subtitle,
            style: const TextStyle(
              color: gold,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Widget _card({required Widget child}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: border),
      ),
      child: child,
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

  Widget _placeholderPage() {
    const names = [
      'Home',
      'Chart',
      'Analysis',
      'Positions',
      'Settings',
    ];

    return Center(
      child: Text(
        '${names[selectedIndex]} screen — Step 10B',
        style: const TextStyle(
          color: muted,
          fontSize: 18,
        ),
      ),
    );
  }
}
