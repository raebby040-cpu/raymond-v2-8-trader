import 'package:flutter/material.dart';

import 'api_service.dart';

class ChartPage extends StatefulWidget {
  const ChartPage({super.key, required this.api});

  final ApiService api;

  @override
  State<ChartPage> createState() => _ChartPageState();
}

class _ChartPageState extends State<ChartPage> {
  static const gold = Color(0xFFF5B82E);
  static const background = Color(0xFF030B14);
  static const card = Color(0xFF091724);
  static const border = Color(0xFF17334D);
  static const muted = Color(0xFF8EA4B8);

  String timeframe = 'H1';
  bool loading = true;
  String error = '';
  double price = 0;
  List<Candle> candles = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      error = '';
    });

    try {
      final priceResponse = await widget.api.marketPrice(
        symbol: 'XAUUSD',
      );

      final candleResponse =
          await widget.api.marketCandlesticks(
        symbol: 'XAUUSD',
        timeframe: timeframe,
        limit: 60,
      );

      final priceValue = priceResponse['price'];
      final raw = candleResponse['candles'];

      final parsed = <Candle>[];

      if (raw is List) {
        for (final item in raw) {
          if (item is! Map) continue;

          final open = _number(item['open']);
          final high = _number(item['high']);
          final low = _number(item['low']);
          final close = _number(item['close']);

          if (open == null ||
              high == null ||
              low == null ||
              close == null) {
            continue;
          }

          parsed.add(
            Candle(
              open: open,
              high: high,
              low: low,
              close: close,
            ),
          );
        }
      }

      if (!mounted) return;

      setState(() {
        price = priceValue is num
            ? priceValue.toDouble()
            : 0;

        candles = parsed;
        loading = false;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        loading = false;
        error = 'Unable to load XAUUSD chart data';
      });
    }
  }

  double? _number(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }

    return double.tryParse('$value');
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: background,
      child: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            16,
            12,
            16,
            24,
          ),
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'XAUUSD',
                    style: TextStyle(
                      fontSize: 25,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: loading ? null : _load,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),

            const Text(
              'Gold / US Dollar',
              style: TextStyle(color: muted),
            ),

            const SizedBox(height: 14),

            _priceCard(),

            const SizedBox(height: 14),

            _timeframes(),

            const SizedBox(height: 14),

            if (error.isNotEmpty) _errorCard(),

            _chartCard(),

            const SizedBox(height: 12),

            const Text(
              'Paper/read-only market view. '
              'Real-money trading remains disabled.',
              style: TextStyle(
                color: muted,
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _priceCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: border),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.show_chart,
            color: gold,
          ),

          const SizedBox(width: 12),

          const Expanded(
            child: Text(
              'Current price',
              style: TextStyle(color: muted),
            ),
          ),

          Text(
            loading || price == 0
                ? '--'
                : price.toStringAsFixed(2),
            style: const TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }

  Widget _timeframes() {
    const values = [
      'M15',
      'H1',
      'H4',
      'D1',
    ];

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: values.map((value) {
          final selected = value == timeframe;

          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ChoiceChip(
              label: Text(value),
              selected: selected,
              selectedColor: gold.withOpacity(.20),
              side: BorderSide(
                color: selected ? gold : border,
              ),
              labelStyle: TextStyle(
                color: selected ? gold : muted,
                fontWeight: FontWeight.bold,
              ),
              onSelected: (_) {
                if (selected) return;

                setState(() {
                  timeframe = value;
                });

                _load();
              },
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _chartCard() {
    return Container(
      height: 390,
      padding: const EdgeInsets.fromLTRB(
        8,
        16,
        16,
        16,
      ),
      decoration: BoxDecoration(
        color: card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: border),
      ),
      child: loading
          ? const Center(
              child: CircularProgressIndicator(),
            )
          : candles.isEmpty
              ? const Center(
                  child: Text(
                    'No candle data available.',
                    style: TextStyle(color: muted),
                  ),
                )
              : CustomPaint(
                  painter: CandleChartPainter(candles),
                  child: const SizedBox.expand(),
                ),
    );
  }

  Widget _errorCard() {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: chartRed.withOpacity(.10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: chartRed.withOpacity(.30),
        ),
      ),
      child: Text(
        error,
        style: const TextStyle(color: chartRed),
      ),
    );
  }
}

const chartGreen = Color(0xFF00E59B);
const chartRed = Color(0xFFFF5C6C);

class Candle {
  const Candle({
    required this.open,
    required this.high,
    required this.low,
    required this.close,
  });

  final double open;
  final double high;
  final double low;
  final double close;
}

class CandleChartPainter extends CustomPainter {
  CandleChartPainter(this.candles);

  final List<Candle> candles;

  @override
  void paint(
    Canvas canvas,
    Size size,
  ) {
    if (candles.isEmpty) return;

    final all = candles.expand(
      (c) => <double>[
        c.high,
        c.low,
      ],
    ).toList();

    var minPrice = all.reduce(
      (a, b) => a < b ? a : b,
    );

    var maxPrice = all.reduce(
      (a, b) => a > b ? a : b,
    );

    if (maxPrice == minPrice) {
      maxPrice += 1;
      minPrice -= 1;
    }

    final range = maxPrice - minPrice;

    const top = 12.0;
    final bottom = size.height - 12.0;
    final chartHeight = bottom - top;

    double y(double value) {
      return top +
          (maxPrice - value) /
              range *
              chartHeight;
    }

    final candleWidth =
        size.width / candles.length;

    final bodyWidth =
        (candleWidth * .58)
            .clamp(2.0, 16.0)
            .toDouble();

    final wickPaint = Paint()
      ..strokeWidth = 1.2
      ..style = PaintingStyle.stroke;

    final bodyPaint = Paint()
      ..style = PaintingStyle.fill;

    for (var i = 0;
        i < candles.length;
        i++) {
      final c = candles[i];

      final x =
          i * candleWidth +
          candleWidth / 2;

      final up = c.close >= c.open;

      final paintColor =
          up ? chartGreen : chartRed;

      wickPaint.color = paintColor;

      canvas.drawLine(
        Offset(
          x,
          y(c.high),
        ),
        Offset(
          x,
          y(c.low),
        ),
        wickPaint,
      );

      bodyPaint.color = paintColor;

      final bodyTop =
          y(up ? c.close : c.open);

      final bodyBottom =
          y(up ? c.open : c.close);

      final rect = Rect.fromLTRB(
        x - bodyWidth / 2,
        bodyTop,
        x + bodyWidth / 2,
        bodyBottom
            .clamp(
              bodyTop + 1,
              size.height,
            )
            .toDouble(),
      );

      canvas.drawRect(
        rect,
        bodyPaint,
      );
    }
  }

  @override
  bool shouldRepaint(
    covariant CandleChartPainter oldDelegate,
  ) {
    return oldDelegate.candles != candles;
  }
}
