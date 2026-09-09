import 'package:flutter/material.dart';

void main() => runApp(const RaymondApp());

class RaymondApp extends StatelessWidget {
  const RaymondApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'Raymond V2.8 Trader',
      debugShowCheckedModeBanner: false,
      home: DashboardScreen(),
      themeMode: ThemeMode.dark,
    );
  }
}

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context).copyWith(
      colorScheme: ColorScheme.dark(
        primary: Colors.tealAccent.shade200,
        secondary: Colors.blueAccent,
        surface: const Color(0xFF0F1720),
        background: const Color(0xFF071018),
      ),
      useMaterial3: true,
    );

    return Theme(
      data: theme,
      child: Scaffold(
        backgroundColor: theme.colorScheme.background,
        appBar: AppBar(
          surfaceTintColor: Colors.transparent,
          backgroundColor: Colors.transparent,
          elevation: 0,
          leading: const _RaymondLogo(),
          title: const _HeaderTitle(),
          actions: const [_ConnectionStatus(), _NotificationButton()],
        ),
        body: const SafeArea(child: _DashboardBody()),
        bottomNavigationBar: const _MainNavigation(),
      ),
    );
  }
}

class _RaymondLogo extends StatelessWidget {
  const _RaymondLogo({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(8.0),
      child: Semantics(
        label: 'Raymond logo',
        child: CircleAvatar(
          radius: 18,
          backgroundColor: Colors.teal.shade800,
          child: const Icon(Icons.show_chart, color: Colors.white, size: 20),
        ),
      ),
    );
  }
}

class _HeaderTitle extends StatelessWidget {
  const _HeaderTitle({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: const [
        Text('RAYMOND', style: TextStyle(fontWeight: FontWeight.w700, letterSpacing: 1.2)),
        SizedBox(height: 2),
        Text('V2.8 TRADER', style: TextStyle(fontSize: 12, color: Colors.white70)),
      ],
    );
  }
}

class _ConnectionStatus extends StatelessWidget {
  const _ConnectionStatus({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8.0),
      child: Row(
        children: [
          Tooltip(message: 'Connection status: DEMO / OFFLINE', child: _StatusDot(color: Colors.amber)),
        ],
      ),
    );
  }
}

class _StatusDot extends StatelessWidget {
  final Color color;
  const _StatusDot({required this.color, super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 12,
      height: 12,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle, boxShadow: const [BoxShadow(blurRadius: 4, color: Colors.black54)]),
    );
  }
}

class _NotificationButton extends StatelessWidget {
  const _NotificationButton({super.key});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: 'Notifications',
      icon: const Icon(Icons.notifications_rounded),
      onPressed: () => ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Notifications are not configured.'))),
    );
  }
}

class _DashboardBody extends StatelessWidget {
  const _DashboardBody({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      final isWide = constraints.maxWidth > 600;
      return Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(
          children: [
            // Market overview & Account summary
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: _MarketOverviewCard()),
                const SizedBox(width: 12),
                SizedBox(width: isWide ? 300 : 0, child: isWide ? const _AccountSummaryCard() : const SizedBox.shrink()),
              ],
            ),
            const SizedBox(height: 12),
            // Chart and controls
            Expanded(
              child: Row(
                children: [
                  Expanded(flex: 3, child: Column(children: const [_PriceChartCard(), SizedBox(height: 12), _TradingControlsCard()])),
                  const SizedBox(width: 12),
                  Expanded(flex: 1, child: Column(children: const [_StrategyPanelCard(), SizedBox(height: 12), _OpenPositionsCard()])),
                ],
              ),
            ),
          ],
        ),
      );
    });
  }
}

// Market overview
class _MarketOverviewCard extends StatelessWidget {
  const _MarketOverviewCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF0B1220),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: const [Text('Market', style: TextStyle(color: Colors.white70)), Text('DEMO / OFFLINE', style: TextStyle(color: Colors.amber))]),
          const SizedBox(height: 8),
          const Text('XAUUSD', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: Colors.white)),
          const SizedBox(height: 8),
          Row(children: const [
            _PriceBox(label: 'Price', value: '1,910.45', valueColor: Colors.teal),
            SizedBox(width: 8),
            _PriceBox(label: 'Bid', value: '1,910.40', valueColor: Colors.green),
            SizedBox(width: 8),
            _PriceBox(label: 'Ask', value: '1,910.50', valueColor: Colors.red),
            SizedBox(width: 8),
            _PriceBox(label: 'Spread', value: '0.10', valueColor: Colors.white70),
          ]),
          const SizedBox(height: 12),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: const [Text('Market status', style: TextStyle(color: Colors.white70)), Text('CLOSED (demo)', style: TextStyle(color: Colors.amber))]),
        ]),
      ),
    );
  }
}

class _PriceBox extends StatelessWidget {
  final String label;
  final String value;
  final Color valueColor;
  const _PriceBox({required this.label, required this.value, required this.valueColor, super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(color: const Color(0xFF071018), borderRadius: BorderRadius.circular(8)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: const TextStyle(fontSize: 11, color: Colors.white70)),
        const SizedBox(height: 4),
        Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: valueColor)),
      ]),
    );
  }
}

// Account summary
class _AccountSummaryCard extends StatelessWidget {
  const _AccountSummaryCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF0B1220),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Account Summary', style: TextStyle(color: Colors.white70)),
          const SizedBox(height: 8),
          _SummaryRow(label: 'Balance', value: r'10,000.00', valueColor: Colors.tealAccent),
          _SummaryRow(label: 'Equity', value: r'10,150.00', valueColor: Colors.tealAccent),
          _SummaryRow(label: "Today's P&L", value: r'+150.00', valueColor: Colors.green),
          _SummaryRow(label: 'Margin', value: r'500.00', valueColor: Colors.white70),
          _SummaryRow(label: 'Free Margin', value: r'9,650.00', valueColor: Colors.white70),
        ]),
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  final String label;
  final String value;
  final Color valueColor;
  const _SummaryRow({required this.label, required this.value, required this.valueColor, super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6.0),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(label, style: const TextStyle(color: Colors.white70)), Text(value, style: TextStyle(color: valueColor, fontWeight: FontWeight.w600))]),
    );
  }
}

// Chart card
class _PriceChartCard extends StatelessWidget {
  const _PriceChartCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF071018),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: const [Text('XAUUSD Chart', style: TextStyle(color: Colors.white70)), _ChartTimeframeButtons()]),
          const SizedBox(height: 8),
          const SizedBox(height: 220, child: _DemoPriceChart()),
        ]),
      ),
    );
  }
}

class _ChartTimeframeButtons extends StatelessWidget {
  const _ChartTimeframeButtons({super.key});

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      FilledButton.tonal(onPressed: () {}, child: const Text('15M')),
      const SizedBox(width: 8),
      FilledButton.tonal(onPressed: () {}, child: const Text('1H')),
      const SizedBox(width: 8),
      FilledButton.tonal(onPressed: () {}, child: const Text('4H')),
    ]);
  }
}

class _DemoPriceChart extends StatelessWidget {
  const _DemoPriceChart({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      return CustomPaint(size: Size(constraints.maxWidth, constraints.maxHeight), painter: _ChartPainter());
    });
  }
}

class _ChartPainter extends CustomPainter {
  final List<double> data = const [1910.4, 1910.7, 1910.2, 1911.0, 1910.5, 1910.8, 1911.2, 1910.9, 1910.6, 1910.45];

  @override
  void paint(Canvas canvas, Size size) {
    final bg = Rect.fromLTWH(0, 0, size.width, size.height);
    final paintBg = Paint()..shader = const LinearGradient(colors: [Color(0xFF071018), Color(0xFF0B1220)]).createShader(bg);
    canvas.drawRect(bg, paintBg);

    final padding = 8.0;
    final chartRect = Rect.fromLTWH(padding, padding, size.width - padding * 2, size.height - padding * 2);

    // draw grid
    final gridPaint = Paint()..color = Colors.white10..strokeWidth = 0.6;
    for (var i = 0; i <= 4; i++) {
      final y = chartRect.top + i * (chartRect.height / 4);
      canvas.drawLine(Offset(chartRect.left, y), Offset(chartRect.right, y), gridPaint);
    }

    // scale data
    final min = data.reduce((a, b) => a < b ? a : b);
    final max = data.reduce((a, b) => a > b ? a : b);
    final scaleY = (max - min) == 0 ? 1 : chartRect.height / (max - min);
    final stepX = chartRect.width / (data.length - 1);

    final path = Path();
    for (var i = 0; i < data.length; i++) {
      final x = chartRect.left + stepX * i;
      final y = chartRect.bottom - (data[i] - min) * scaleY;
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }

    final linePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..shader = const LinearGradient(colors: [Color(0xFF00E5A8), Color(0xFF00B0FF)]).createShader(chartRect);
    canvas.drawPath(path, linePaint);

    // draw last price
    final last = data.last;
    final lastX = chartRect.left + stepX * (data.length - 1);
    final lastY = chartRect.bottom - (last - min) * scaleY;
    final dotPaint = Paint()..color = Colors.tealAccent.shade200;
    canvas.drawCircle(Offset(lastX, lastY), 4, dotPaint);

    // labels
    final tp = TextPainter(textDirection: TextDirection.ltr);
    tp.text = TextSpan(text: '${max.toStringAsFixed(2)}', style: const TextStyle(color: Colors.white70, fontSize: 10));
    tp.layout();
    tp.paint(canvas, Offset(chartRect.right - tp.width, chartRect.top - tp.height));

    tp.text = TextSpan(text: '${min.toStringAsFixed(2)}', style: const TextStyle(color: Colors.white70, fontSize: 10));
    tp.layout();
    tp.paint(canvas, Offset(chartRect.right - tp.width, chartRect.bottom - tp.height));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// Trading controls
class _TradingControlsCard extends StatelessWidget {
  const _TradingControlsCard({super.key});

  void _showDemoSnack(BuildContext context, String action) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$action: backend not connected (DEMO).')));
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF0B1220),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Trading Controls', style: TextStyle(color: Colors.white70)),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: FilledButton(
                onPressed: () => _showDemoSnack(context, 'BUY'),
                style: FilledButton.styleFrom(backgroundColor: Colors.teal.shade700, textStyle: const TextStyle(fontWeight: FontWeight.bold)),
                child: const Padding(padding: EdgeInsets.symmetric(vertical: 14.0), child: Text('BUY')),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                onPressed: () => _showDemoSnack(context, 'SELL'),
                style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700, textStyle: const TextStyle(fontWeight: FontWeight.bold)),
                child: const Padding(padding: EdgeInsets.symmetric(vertical: 14.0), child: Text('SELL')),
              ),
            ),
          ]),
          const SizedBox(height: 12),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: const [
            Text('Auto Trading', style: TextStyle(color: Colors.white70)),
            _AutoTradingSwitch(),
          ]),
          const SizedBox(height: 8),
          const _RiskStatus(),
        ]),
      ),
    );
  }
}

class _AutoTradingSwitch extends StatefulWidget {
  const _AutoTradingSwitch({super.key});

  @override
  State<_AutoTradingSwitch> createState() => _AutoTradingSwitchState();
}

class _AutoTradingSwitchState extends State<_AutoTradingSwitch> {
  bool enabled = false;

  @override
  Widget build(BuildContext context) {
    return Switch.adaptive(
      value: enabled,
      activeColor: Colors.tealAccent.shade200,
      onChanged: (v) => setState(() {
        enabled = v;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Auto Trading ${enabled ? 'enabled (demo)' : 'disabled'} - backend not connected')));
      }),
    );
  }
}

class _RiskStatus extends StatelessWidget {
  const _RiskStatus({super.key});

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6), decoration: BoxDecoration(color: Colors.teal.shade900, borderRadius: BorderRadius.circular(8)), child: const Text('RISK: LOW', style: TextStyle(color: Colors.white70))),
      const SizedBox(width: 8),
      const Text('Mode: DEMO', style: TextStyle(color: Colors.amber)),
    ]);
  }
}

// Open positions
class _OpenPositionsCard extends StatelessWidget {
  const _OpenPositionsCard({super.key});

  @override
  Widget build(BuildContext context) {
    // demo empty state
    final hasPositions = false;
    return Card(
      color: const Color(0xFF0B1220),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Open Positions', style: TextStyle(color: Colors.white70)),
          const SizedBox(height: 8),
          if (!hasPositions) ...[
            const SizedBox(height: 20),
            Center(child: Column(children: const [Icon(Icons.folder_open, size: 48, color: Colors.white24), SizedBox(height: 8), Text('No open positions', style: TextStyle(color: Colors.white70))])),
          ] else ...[
            // list of positions
          ]
        ]),
      ),
    );
  }
}

// Strategy panel
class _StrategyPanelCard extends StatelessWidget {
  const _StrategyPanelCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF0B1220),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Raymond Strategy', style: TextStyle(color: Colors.white70)),
          const SizedBox(height: 8),
          const _StrategyRow(label: 'Signal', value: 'WAITING', color: Colors.amber),
          const _StrategyRow(label: 'Confidence', value: '—', color: Colors.white70),
          const _StrategyRow(label: 'Trend', value: '—', color: Colors.white70),
          const _StrategyRow(label: 'RSI', value: '—', color: Colors.white70),
          const _StrategyRow(label: 'MACD', value: '—', color: Colors.white70),
          const _StrategyRow(label: 'Risk Mode', value: 'DEMO', color: Colors.amber),
        ]),
      ),
    );
  }
}

class _StrategyRow extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  const _StrategyRow({required this.label, required this.value, required this.color, super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6.0),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(label, style: const TextStyle(color: Colors.white70)), Text(value, style: TextStyle(color: color, fontWeight: FontWeight.w600))]),
    );
  }
}

// Bottom navigation
class _MainNavigation extends StatefulWidget {
  const _MainNavigation({super.key});

  @override
  State<_MainNavigation> createState() => _MainNavigationState();
}

class _MainNavigationState extends State<_MainNavigation> {
  int _index = 0;

  static const _labels = ['Home', 'Positions', 'Strategy', 'Settings'];

  @override
  Widget build(BuildContext context) {
    return NavigationBar(
      selectedIndex: _index,
      onDestinationSelected: (i) => setState(() => _index = i),
      destinations: const [
        NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
        NavigationDestination(icon: Icon(Icons.swap_horiz), label: 'Positions'),
        NavigationDestination(icon: Icon(Icons.psychology_alt), label: 'Strategy'),
        NavigationDestination(icon: Icon(Icons.settings), label: 'Settings'),
      ],
    );
  }
}
