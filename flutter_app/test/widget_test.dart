import 'package:flutter_test/flutter_test.dart';
import 'package:raymond_v2_8/main.dart';

void main() {
  testWidgets(
    'RaymondApp starts and shows the main dashboard',
    (WidgetTester tester) async {
      await tester.pumpWidget(const RaymondApp());

      // Allow the first Flutter frame to render.
      await tester.pump();

      // App branding.
      expect(find.text('RAYMOND'), findsOneWidget);
      expect(find.text('V2.8'), findsOneWidget);

      // Main market.
      expect(find.text('XAUUSD'), findsOneWidget);

      // Current dashboard.
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

      // Positions appears more than once in the current UI.
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
