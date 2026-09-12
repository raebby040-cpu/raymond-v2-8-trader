import 'package:flutter/material.dart';

import 'analysis_page.dart';
import 'api_service.dart';
import 'chart_page.dart';

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
  bool journalLoaded = false;

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
      bool fetchedJournal = false;

      try {
        status = await api.demoStatus();
      } catch (_) {}

      try {
        performance = await api.demoPerformance();
      } catch (_) {}

      // Step 10B-1: use the persistent paper-trade journal first.
      try {
        final journalResponse = await _loadPaperJournal();
        fetchedTrades = journalResponse;
        fetchedJournal = true;
      } catch (_) {
        // Keep the older demo endpoint as a safe fallback while the
        // backend is being upgraded.
        try {
          fetchedTrades = await api.demoTrades();
        } catch (_) {}
      }

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
        journalLoaded = fetchedJournal;
        loading = false;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        backendOnline = false;
        loading = false;
        errorMessage = 'Backend unavailable';
      });
    }
  }

  Future<List<Map<String, dynamic>>> _loadPaperJournal() async {
    final response = await api.paperJournalTrades(
      limit: 50,
      offset: 0,
    );

    final data = response;
    final rawTrades = data['trades'];

    if (rawTrades is! List) {
      throw const FormatException(
        'Expected a trades list from the paper journal API.',
      );
    }

    return rawTrades
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
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
            selectedIcon: Icon(Icons.analytics, color: gold),
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
    // Step 10B-2: functional XAUUSD chart.
    if (selectedIndex == 1) {
      return ChartPage(api: api);
    }

    // Analysis tab.
    if (selectedIndex == 2) {
      return AnalysisPage(api: api);
    }

    // Positions and Settings remain placeholders for now.
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
            if (errorMessage.isNotEmpty) _errorCard(),
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
