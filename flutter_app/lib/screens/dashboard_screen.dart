import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/market_provider.dart';
import '../providers/trading_provider.dart';
import '../widgets/price_ticker.dart';
import '../widgets/indicators_display.dart';
import '../widgets/positions_summary.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({Key? key}) : super(key: key);

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<MarketProvider>().refreshAll();
      context.read<TradingProvider>().fetchPositions();
      context.read<TradingProvider>().fetchStrategyDecision();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('RAYMOND v2.8 - Dashboard'),
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              context.read<MarketProvider>().refreshAll();
              context.read<TradingProvider>().fetchPositions();
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await context.read<MarketProvider>().refreshAll();
          await context.read<TradingProvider>().fetchPositions();
        },
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const PriceTicker(),
              const SizedBox(height: 20),
              const IndicatorsDisplay(),
              const SizedBox(height: 20),
              const Text(
                'Open Positions',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              const PositionsSummary(),
              const SizedBox(height: 20),
              Consumer<TradingProvider>(
                builder: (context, trading, _) {
                  final decision = trading.strategyDecision;
                  if (decision == null) return const SizedBox();
                  return Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'AI Strategy Decision',
                            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 8),
                          Chip(
                            label: Text(decision.decision.toUpperCase()),
                            backgroundColor: decision.decision == 'buy' ? Colors.green : Colors.red,
                          ),
                          const SizedBox(height: 8),
                          Text('Confidence: ${(decision.confidence * 100).toStringAsFixed(1)}%'),
                          const SizedBox(height: 4),
                          Text('Reason: ${decision.reason}'),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}
