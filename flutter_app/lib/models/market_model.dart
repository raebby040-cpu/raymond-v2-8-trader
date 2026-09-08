class MarketPrice {
  final String symbol;
  final double price;
  final double bid;
  final double ask;
  final DateTime timestamp;

  MarketPrice({
    required this.symbol,
    required this.price,
    required this.bid,
    required this.ask,
    required this.timestamp,
  });

  factory MarketPrice.fromJson(Map<String, dynamic> json) {
    return MarketPrice(
      symbol: json['symbol'] ?? 'XAUUSD',
      price: (json['price'] ?? 0.0).toDouble(),
      bid: (json['bid'] ?? 0.0).toDouble(),
      ask: (json['ask'] ?? 0.0).toDouble(),
      timestamp: DateTime.parse(json['timestamp'] ?? DateTime.now().toIso8601String()),
    );
  }
}

class Candlestick {
  final DateTime time;
  final double open;
  final double high;
  final double low;
  final double close;
  final int volume;
  final double ema20;
  final double ema50;
  final double rsi;
  final double atr;

  Candlestick({
    required this.time,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    required this.volume,
    required this.ema20,
    required this.ema50,
    required this.rsi,
    required this.atr,
  });

  factory Candlestick.fromJson(Map<String, dynamic> json) {
    return Candlestick(
      time: DateTime.parse(json['time'] ?? DateTime.now().toIso8601String()),
      open: (json['open'] ?? 0.0).toDouble(),
      high: (json['high'] ?? 0.0).toDouble(),
      low: (json['low'] ?? 0.0).toDouble(),
      close: (json['close'] ?? 0.0).toDouble(),
      volume: json['volume'] ?? 0,
      ema20: (json['ema20'] ?? 0.0).toDouble(),
      ema50: (json['ema50'] ?? 0.0).toDouble(),
      rsi: (json['rsi'] ?? 50.0).toDouble(),
      atr: (json['atr'] ?? 0.0).toDouble(),
    );
  }
}

class Indicators {
  final double ema20;
  final double ema50;
  final double rsi;
  final double atr;

  Indicators({
    required this.ema20,
    required this.ema50,
    required this.rsi,
    required this.atr,
  });

  factory Indicators.fromJson(Map<String, dynamic> json) {
    final indicators = json['indicators'] ?? {};
    return Indicators(
      ema20: (indicators['ema20'] ?? 0.0).toDouble(),
      ema50: (indicators['ema50'] ?? 0.0).toDouble(),
      rsi: (indicators['rsi'] ?? 50.0).toDouble(),
      atr: (indicators['atr'] ?? 0.0).toDouble(),
    );
  }
}
