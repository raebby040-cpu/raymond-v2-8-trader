import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class TradingScreen extends StatefulWidget {
  const TradingScreen({Key? key}) : super(key: key);

  @override
  State<TradingScreen> createState() => _TradingScreenState();
}

class _TradingScreenState extends State<TradingScreen> {
  final _quantityController = TextEditingController();
  String _orderType = 'market';
  String _direction = 'buy';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TradingProvider>().fetchPositions();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Trading Panel'),
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Place Order',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Expanded(
                          child: SegmentedButton<String>(
                            segments: const <ButtonSegment<String>>[
                              ButtonSegment<String>(value: 'buy', label: Text('BUY')),
                              ButtonSegment<String>(value: 'sell', label: Text('SELL')),
                            ],
                            selected: <String>{_direction},
                            onSelectionChanged: (Set<String> newSelection) {
                              setState(() => _direction = newSelection.first);
                            },
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      value: _orderType,
                      decoration: const InputDecoration(
                        labelText: 'Order Type',
                        border: OutlineInputBorder(),
                      ),
                      items: const [
                        DropdownMenuItem(value: 'market', child: Text('Market')),
                        DropdownMenuItem(value: 'limit', child: Text('Limit')),
                        DropdownMenuItem(value: 'stop', child: Text('Stop')),
                      ],
                      onChanged: (value) => setState(() => _orderType = value ?? 'market'),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _quantityController,
                      decoration: const InputDecoration(
                        labelText: 'Quantity (lots)',
                        border: OutlineInputBorder(),
                      ),
                      keyboardType: TextInputType.number,
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: () {
                          final quantity = double.tryParse(_quantityController.text) ?? 0.1;
                          context.read<TradingProvider>().placeOrder(
                            symbol: 'XAUUSD',
                            orderType: _orderType,
                            direction: _direction,
                            quantity: quantity,
                          );
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Order placed successfully')),
                          );
                        },
                        child: const Text('Place Order'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Open Positions',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            Consumer<TradingProvider>(
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
                        trailing: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text(
                              '\$${position.pnl.toStringAsFixed(2)}',
                              style: TextStyle(
                                color: position.pnl >= 0 ? Colors.green : Colors.red,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            ElevatedButton(
                              onPressed: () => context.read<TradingProvider>().closePosition(position.positionId),
                              child: const Text('Close'),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _quantityController.dispose();
    super.dispose();
  }
}
