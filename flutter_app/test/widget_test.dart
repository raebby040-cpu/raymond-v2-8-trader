import 'package:flutter_test/flutter_test.dart';
import 'package:raymond_v2_8/main.dart';

void main() {
  testWidgets(
    'RaymondApp starts and shows the main dashboard',
    (WidgetTester tester) async {
      await tester.pumpWidget(const RaymondApp());

      // HomePage starts an HTTP health check during initState.
      // The test environment does not run the backend, so allow
      // the real Dio timeout to finish before disposing the widget.
      await tester.runAsync(() async {
        await Future<void>.delayed(
          const Duration(seconds: 6),
        );
      });

      await tester.pump();

      // App branding.
      expect(
        find.text('RAYMOND'),
        findsOneWidget,
      );

      expect(
        find.text('V2.8'),
        findsOneWidget,
      );

      // Main market.
      expect(
        find.text('XAUUSD'),
        findsOneWidget,
      );

      // Dashboard.
      expect(
        find.text('Live market connection'),
        findsOneWidget,
      );

      expect(
        find.text('PAPER TRADING'),
        findsOneWidget,
      );

      expect(
        find.text('Real-money trading is disabled.'),
        findsOneWidget,
      );

      // Dashboard sections.
      expect(
        find.text('PERFORMANCE'),
        findsOneWidget,
      );

      expect(
        find.text('RECENT PAPER TRADES'),
        findsOneWidget,
      );

      // Navigation.
      expect(
        find.text('Home'),
        findsOneWidget,
      );

      expect(
        find.text('Chart'),
        findsOneWidget,
      );

      expect(
        find.text('Analysis'),
        findsOneWidget,
      );

      expect(
        find.text('Positions'),
        findsWidgets,
      );

      expect(
        find.text('Settings'),
        findsOneWidget,
      );
    },
  );
}
