import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/market_provider.dart';

class PriceTicker extends StatelessWidget {
  const PriceTicker({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Consumer<MarketProvider>(
      builder: (context, market, _) {
        final price = market.currentPrice;
        if (price == null) {
          return const Center(child: CircularProgressIndicator());
        }
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  price.symbol,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                Text(
                  '\$${price.price.toStringAsFixed(2)}',
                  style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Bid: \$${price.bid.toStringAsFixed(2)}'),
                    Text('Ask: \$${price.ask.toStringAsFixed(2)}'),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
