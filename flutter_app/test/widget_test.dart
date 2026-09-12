import 'package:flutter_test/flutter_test.dart';
import 'package:raymond_v2_8/main.dart';

void main() {
  testWidgets(
    'RaymondApp starts and shows main dashboard elements',
    (WidgetTester tester) async {
      await tester.pumpWidget(const RaymondApp());
      await tester.pumpAndSettle();

      // Branding
      expect(find.text('RAYMOND'), findsOneWidget);
      expect(find.text('V2.8 TRADER'), findsOneWidget);

      // Market
      expect(find.text('XAUUSD'), findsOneWidget);

      // Trading controls
      expect(find.text('BUY'), findsOneWidget);
      expect(find.text('SELL'), findsOneWidget);
      expect(find.text('Trading Controls'), findsOneWidget);
    },
  );
}
