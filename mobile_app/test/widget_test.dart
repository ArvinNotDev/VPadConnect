import 'package:flutter_test/flutter_test.dart';

import 'package:vpadconnect_mobile/main.dart';

void main() {
  testWidgets('shows QR and manual pairing options on launch', (tester) async {
    await tester.pumpWidget(const VPadConnectApp());

    expect(find.text('Scan desktop QR code'), findsOneWidget);
    expect(find.text('Enter details manually'), findsOneWidget);
  });
}
