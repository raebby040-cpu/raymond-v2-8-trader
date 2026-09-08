import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../providers/trading_provider.dart';

class JournalScreen extends StatefulWidget {
  const JournalScreen({Key? key}) : super(key: key);

  @override
  State<JournalScreen> createState() => _JournalScreenState();
}

class _JournalScreenState extends State<JournalScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TradingProvider>().fetchTradeHistory();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Trade Journal'),
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<TradingProvider>().fetchTradeHistory(),
          ),
        ],
      ),
      body: Consumer<TradingProvider>(
        builder: (context, trading, _) {
          if (trading.isLoading) {
            return const Center(child: CircularProgressIndicator());
          }
          if (trading.tradeHistory.isEmpty) {
            return const Center(child: Text('No trades yet'));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(8),
            itemCount: trading.tradeHistory.length,
            itemBuilder: (context, index) {
              final trade = trading.tradeHistory[index];
              return Card(
                margin: const EdgeInsets.symmetric(vertical: 8),
                child: ExpansionTile(
                  title: Text(
                    '${trade.symbol} - ${trade.tradeId}',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  subtitle: Text(
                    'P&L: \$${trade.pnl.toStringAsFixed(2)}',
                    style: TextStyle(
                      color: trade.pnl >= 0 ? Colors.green : Colors.red,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _buildInfoRow('Entry Price', '\$${trade.entryPrice.toStringAsFixed(2)}'),
                          _buildInfoRow('Exit Price', '\$${trade.exitPrice.toStringAsFixed(2)}'),
                          _buildInfoRow('Quantity', '${trade.quantity} lots'),
                          _buildInfoRow('Duration', '${trade.durationMinutes} minutes'),
                          _buildInfoRow('Opened', DateFormat('yyyy-MM-dd HH:mm').format(trade.openedAt)),
                          _buildInfoRow('Closed', DateFormat('yyyy-MM-dd HH:mm').format(trade.closedAt)),
                          _buildInfoRow('Status', trade.status),
                        ],
                      ),
                    ),
                  ],
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.grey)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}
