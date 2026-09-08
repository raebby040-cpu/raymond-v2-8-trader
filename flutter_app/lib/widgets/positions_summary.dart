import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class PositionsSummary extends StatelessWidget {
  const PositionsSummary({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Consumer<TradingProvider>(
      builder: (context, trading, _) {
        if (trading.positions.isEmpty) {
          return const Text('No open positions');
        }
        return ListView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: trading.positions.length,
          itemBuilder: (context, index) {
            final position = trading.positions[index];
            return Card(
              child: ListTile(
                title: Text('${position.symbol} - ${position.quantity} lots'),
                subtitle: Text('Entry: \$${position.entryPrice.toStringAsFixed(2)}'),
                trailing: Text(
                  '\$${position.pnl.toStringAsFixed(2)}',
                  style: TextStyle(
                    color: position.pnl >= 0 ? Colors.green : Colors.red,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }
}
