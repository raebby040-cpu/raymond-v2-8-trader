import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/market_provider.dart';

class IndicatorsDisplay extends StatelessWidget {
  const IndicatorsDisplay({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Consumer<MarketProvider>(
      builder: (context, market, _) {
        final indicators = market.indicators;
        if (indicators == null) {
          return const Center(child: CircularProgressIndicator());
        }
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Technical Indicators',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 12),
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    _IndicatorCard('EMA20', '${indicators.ema20.toStringAsFixed(2)}'),
                    _IndicatorCard('EMA50', '${indicators.ema50.toStringAsFixed(2)}'),
                    _IndicatorCard('RSI', '${indicators.rsi.toStringAsFixed(2)}'),
                    _IndicatorCard('ATR', '${indicators.atr.toStringAsFixed(2)}'),
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

class _IndicatorCard extends StatelessWidget {
  final String label;
  final String value;

  const _IndicatorCard(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.grey[850],
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(label, style: const TextStyle(color: Colors.grey)),
            const SizedBox(height: 4),
            Text(value, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }
}
