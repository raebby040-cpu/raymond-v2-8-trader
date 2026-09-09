import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:raymond_v2_8_trader/main.dart';

void main() {
  testWidgets('App starts and shows dashboard title', (WidgetTester tester) async {
    await tester.pumpWidget(RaymondApp());
    expect(find.text('Raymond v2.8 — Dashboard (placeholder)'), findsOneWidget);
  });
}
