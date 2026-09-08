class Position {
  final String positionId;
  final String symbol;
  final double quantity;
  final double entryPrice;
  final double currentPrice;
  final double pnl;
  final double pnlPercent;
  final DateTime openedAt;
  final double? stopLoss;
  final double? takeProfit;

  Position({
    required this.positionId,
    required this.symbol,
    required this.quantity,
    required this.entryPrice,
    required this.currentPrice,
    required this.pnl,
    required this.pnlPercent,
    required this.openedAt,
    this.stopLoss,
    this.takeProfit,
  });

  factory Position.fromJson(Map<String, dynamic> json) {
    return Position(
      positionId: json['position_id'] ?? '',
      symbol: json['symbol'] ?? 'XAUUSD',
      quantity: (json['quantity'] ?? 0.0).toDouble(),
      entryPrice: (json['entry_price'] ?? 0.0).toDouble(),
      currentPrice: (json['current_price'] ?? 0.0).toDouble(),
      pnl: (json['pnl'] ?? 0.0).toDouble(),
      pnlPercent: (json['pnl_percent'] ?? 0.0).toDouble(),
      openedAt: DateTime.parse(json['opened_at'] ?? DateTime.now().toIso8601String()),
      stopLoss: json['stop_loss'] != null ? (json['stop_loss'] as num).toDouble() : null,
      takeProfit: json['take_profit'] != null ? (json['take_profit'] as num).toDouble() : null,
    );
  }
}

class Trade {
  final String tradeId;
  final String symbol;
  final double entryPrice;
  final double exitPrice;
  final double quantity;
  final double pnl;
  final int durationMinutes;
  final DateTime openedAt;
  final DateTime closedAt;
  final String status;

  Trade({
    required this.tradeId,
    required this.symbol,
    required this.entryPrice,
    required this.exitPrice,
    required this.quantity,
    required this.pnl,
    required this.durationMinutes,
    required this.openedAt,
    required this.closedAt,
    required this.status,
  });

  factory Trade.fromJson(Map<String, dynamic> json) {
    return Trade(
      tradeId: json['trade_id'] ?? '',
      symbol: json['symbol'] ?? 'XAUUSD',
      entryPrice: (json['entry_price'] ?? 0.0).toDouble(),
      exitPrice: (json['exit_price'] ?? 0.0).toDouble(),
      quantity: (json['quantity'] ?? 0.0).toDouble(),
      pnl: (json['pnl'] ?? 0.0).toDouble(),
      durationMinutes: json['duration_minutes'] ?? 0,
      openedAt: DateTime.parse(json['opened_at'] ?? DateTime.now().toIso8601String()),
      closedAt: DateTime.parse(json['closed_at'] ?? DateTime.now().toIso8601String()),
      status: json['status'] ?? 'closed',
    );
  }
}

class StrategyDecision {
  final String decision;
  final double confidence;
  final String reason;
  final double suggestedEntry;
  final double stopLoss;
  final double takeProfit;

  StrategyDecision({
    required this.decision,
    required this.confidence,
    required this.reason,
    required this.suggestedEntry,
    required this.stopLoss,
    required this.takeProfit,
  });

  factory StrategyDecision.fromJson(Map<String, dynamic> json) {
    return StrategyDecision(
      decision: json['decision'] ?? 'hold',
      confidence: (json['confidence'] ?? 0.0).toDouble(),
      reason: json['reason'] ?? 'No signal',
      suggestedEntry: (json['recommended_entry'] ?? 0.0).toDouble(),
      stopLoss: (json['stop_loss'] ?? 0.0).toDouble(),
      takeProfit: (json['take_profit'] ?? 0.0).toDouble(),
    );
  }
}
