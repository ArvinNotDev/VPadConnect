import 'package:material_ui/material_ui.dart';

import 'core/theme/app_theme.dart';
import 'screens/app_shell.dart';
import 'screens/pairing_screen.dart';
import 'services/pairing_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const VPadConnectApp());
}

class VPadConnectApp extends StatelessWidget {
  const VPadConnectApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VPadConnect',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      home: const PairingScreen(),
      onGenerateRoute: (settings) {
        if (settings.name != '/companion') return null;
        final session = settings.arguments! as PairedSession;
        return MaterialPageRoute<void>(
          builder: (routeContext) => AppShell(
            session: session,
            onDisconnect: () => Navigator.of(routeContext).pushAndRemoveUntil(
              MaterialPageRoute<void>(
                builder: (_) => const PairingScreen(),
              ),
              (route) => false,
            ),
          ),
        );
      },
    );
  }
}
