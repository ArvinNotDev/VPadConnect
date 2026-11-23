import 'package:flutter/material.dart';

import '../models/pairing_target.dart';
import '../services/pairing_service.dart';
import '../services/remote_input_service.dart';
import 'gamepad_view.dart' show GamepadView;
import 'touchpad_view.dart' show TouchpadView;
import 'remote_view.dart' show RemoteView;

class AppShell extends StatefulWidget {
  const AppShell({
    required this.session,
    required this.onDisconnect,
    super.key,
  });

  final PairedSession session;
  final VoidCallback onDisconnect;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> with WidgetsBindingObserver {
  int _selectedIndex = 0;
  bool _disconnecting = false;
  late final RemoteInputService _input;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _input = RemoteInputService(widget.session);
    _input.connect();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _input.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _input.connect();
    } else {
      _input.releaseAll();
    }
  }

  Future<void> _disconnect() async {
    if (_disconnecting) return;
    setState(() => _disconnecting = true);
    await PairingService().disconnect(widget.session);
    if (mounted) widget.onDisconnect();
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      HomeView(session: widget.session, onOpenTab: _selectTab),
      GamepadView(input: _input, gamepadAvailable: widget.session.gamepadAvailable),
      TouchpadView(input: _input),
      RemoteView(session: widget.session),
      SettingsView(
        session: widget.session,
        disconnecting: _disconnecting,
        onDisconnect: _disconnect,
      ),
    ];

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _ConnectionHeader(input: _input),
            Expanded(
              child: IndexedStack(
                index: _selectedIndex,
                children: pages,
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: _selectTab,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.space_dashboard_rounded), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.sports_esports_rounded), label: 'Gaming'),
          NavigationDestination(icon: Icon(Icons.mouse_rounded), label: 'Touchpad'),
          NavigationDestination(icon: Icon(Icons.desktop_windows_rounded), label: 'PC Remote'),
          NavigationDestination(icon: Icon(Icons.tune_rounded), label: 'Settings'),
        ],
      ),
    );
  }

  void _selectTab(int index) {
    if (index != _selectedIndex) _input.releaseAll();
    setState(() => _selectedIndex = index);
  }
}

class _ConnectionHeader extends StatelessWidget {
  const _ConnectionHeader({required this.input});

  final RemoteInputService input;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 14),
      child: Row(
        children: [
          Container(
            height: 38,
            width: 38,
            decoration: BoxDecoration(
              color: const Color(0xFF1A2B46),
              borderRadius: BorderRadius.circular(13),
            ),
            child: const Icon(Icons.sports_esports_rounded, color: Color(0xFF8FB1FF)),
          ),
          const SizedBox(width: 11),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('VPADCONNECT', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w900, letterSpacing: 1.2)),
                SizedBox(height: 2),
                Text('Mobile Companion', style: TextStyle(color: Color(0xFF8496B0), fontSize: 10)),
              ],
            ),
          ),
          ValueListenableBuilder<String>(
            valueListenable: input.status,
            builder: (context, value, _) => _StatePill(
              label: value.toUpperCase(),
              positive: value == 'Connected',
            ),
          ),
        ],
      ),
    );
  }
}

class HomeView extends StatelessWidget {
  const HomeView({required this.session, required this.onOpenTab, super.key});

  final PairedSession session;
  final ValueChanged<int> onOpenTab;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
      children: [
        const _PageEyebrow('CONNECTED WORKSPACE'),
        const SizedBox(height: 8),
        const Text('Everything\nyou need to control.',
          style: TextStyle(fontSize: 31, height: 1.1, fontWeight: FontWeight.w900, letterSpacing: -.8)),
        const SizedBox(height: 18),
        _SurfaceCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.computer_rounded, color: Color(0xFF8FB1FF), size: 21),
                  const SizedBox(width: 9),
                  const Expanded(child: Text('Connected PC', style: TextStyle(fontWeight: FontWeight.w800))),
                  _StatePill(
                    label: session.gamepadAvailable ? 'GAMEPAD READY' : 'LIMITED',
                    positive: session.gamepadAvailable,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Text(session.baseUri.host, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
              const SizedBox(height: 5),
              Text(session.deviceName, style: const TextStyle(color: Color(0xFF94A5BE), fontSize: 12)),
              if (!session.gamepadAvailable) ...[
                const SizedBox(height: 13),
                const _InfoBanner(
                  icon: Icons.info_outline_rounded,
                  text: 'ViGEmBus is unavailable on this PC. Touchpad and PC Remote can still be used.',
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 22),
        const _SectionHeading(title: 'YOUR TOOLS', subtitle: 'Choose how you want to use your phone.'),
        const SizedBox(height: 12),
        _ToolCard(
          icon: Icons.sports_esports_rounded,
          title: 'Gaming controller',
          subtitle: 'Dual sticks, triggers and game presets',
          accent: const Color(0xFF769CFF),
          onTap: () => onOpenTab(1),
        ),
        const SizedBox(height: 10),
        _ToolCard(
          icon: Icons.mouse_rounded,
          title: 'Touchpad & Air Mouse',
          subtitle: 'Control the pointer with touch or motion',
          accent: const Color(0xFF56D4C5),
          onTap: () => onOpenTab(2),
        ),
        const SizedBox(height: 10),
        _ToolCard(
          icon: Icons.desktop_windows_rounded,
          title: 'PC Remote',
          subtitle: 'Keyboard, media, clipboard and desktop tools',
          accent: const Color(0xFFBA9BFF),
          onTap: () => onOpenTab(3),
        ),
        const SizedBox(height: 22),
        const _InfoBanner(
          icon: Icons.shield_outlined,
          text: 'Paired over HTTPS with a verified desktop certificate. Keep this connection on a trusted network.',
        ),
      ],
    );
  }
}

class SettingsView extends StatelessWidget {
  const SettingsView({
    required this.session,
    required this.disconnecting,
    required this.onDisconnect,
    super.key,
  });

  final PairedSession session;
  final bool disconnecting;
  final VoidCallback onDisconnect;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
      children: [
        const _PageEyebrow('PREFERENCES'),
        const SizedBox(height: 5),
        const Text('Settings', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
        const SizedBox(height: 18),
        const _SettingsGroup(
          title: 'Controller',
          icon: Icons.sports_esports_rounded,
          rows: [
            _SettingRowData('Button layout', 'Xbox or PlayStation'),
            _SettingRowData('Control presets', 'Standard, Driving, Shooter'),
            _SettingRowData('Motion steering', 'Enable and calibrate'),
          ],
        ),
        const SizedBox(height: 12),
        const _SettingsGroup(
          title: 'Touch & feedback',
          icon: Icons.touch_app_rounded,
          rows: [
            _SettingRowData('Pointer sensitivity', 'Adjust movement speed'),
            _SettingRowData('Air Mouse sensitivity', 'Tune motion response'),
            _SettingRowData('Haptic feedback', 'Optional touch feedback'),
          ],
        ),
        const SizedBox(height: 12),
        _SurfaceCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.verified_user_outlined, color: Color(0xFF55D5C6)),
                  SizedBox(width: 9),
                  Text('Secure connection', style: TextStyle(fontWeight: FontWeight.w800)),
                ],
              ),
              const SizedBox(height: 14),
              Text(session.baseUri.toString(), style: const TextStyle(color: Color(0xFFBAC9DD), fontSize: 12)),
              const SizedBox(height: 10),
              const Text('TLS SHA-256 fingerprint', style: TextStyle(color: Color(0xFF8296B2), fontSize: 10)),
              const SizedBox(height: 6),
              SelectableText(
                formatFingerprint(session.fingerprint),
                style: const TextStyle(fontFamily: 'monospace', color: Color(0xFF69D7CE), fontSize: 10, height: 1.7),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _SurfaceCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Session', style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              Text(session.deviceName, style: const TextStyle(color: Color(0xFF94A5BE), fontSize: 12)),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: disconnecting ? null : onDisconnect,
                  icon: disconnecting
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.link_off_rounded),
                  label: Text(disconnecting ? 'Disconnecting…' : 'Disconnect this device'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFFFF929C),
                    side: const BorderSide(color: Color(0xFF713847)),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _PageEyebrow extends StatelessWidget {
  const _PageEyebrow(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Text(
        text,
        style: const TextStyle(color: Color(0xFF66BFC5), fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1.8),
      );
}

class _SectionHeading extends StatelessWidget {
  const _SectionHeading({required this.title, required this.subtitle});
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w900, letterSpacing: 1.5, color: Color(0xFF8194B0))),
          const SizedBox(height: 5),
          Text(subtitle, style: const TextStyle(color: Color(0xFF9AAAC0), fontSize: 12)),
        ],
      );
}

class _SurfaceCard extends StatelessWidget {
  const _SurfaceCard({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: const Color(0xFF101A2A),
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: const Color(0xFF293B56)),
        ),
        child: child,
      );
}

class _StatePill extends StatelessWidget {
  const _StatePill({required this.label, required this.positive});
  final String label;
  final bool positive;

  @override
  Widget build(BuildContext context) {
    final color = positive ? const Color(0xFF58D7A3) : const Color(0xFFF0BA72);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(color: color.withOpacity(.12), borderRadius: BorderRadius.circular(30)),
      child: Text(label, style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.w900)),
    );
  }
}

class _ToolCard extends StatelessWidget {
  const _ToolCard({required this.icon, required this.title, required this.subtitle, required this.accent, required this.onTap});
  final IconData icon;
  final String title;
  final String subtitle;
  final Color accent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: const Color(0xFF101A2A),
        borderRadius: BorderRadius.circular(18),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(18),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: const Color(0xFF293B56)),
            ),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(color: accent.withOpacity(.13), borderRadius: BorderRadius.circular(14)),
                  child: Icon(icon, color: accent, size: 23),
                ),
                const SizedBox(width: 13),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
                      const SizedBox(height: 4),
                      Text(subtitle, style: const TextStyle(color: Color(0xFF879AB5), fontSize: 10)),
                    ],
                  ),
                ),
                const Icon(Icons.arrow_forward_ios_rounded, color: Color(0xFF7185A1), size: 15),
              ],
            ),
          ),
        ),
      );
}

class _InfoBanner extends StatelessWidget {
  const _InfoBanner({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(13),
        decoration: BoxDecoration(
          color: const Color(0xFF14243A),
          borderRadius: BorderRadius.circular(15),
          border: Border.all(color: const Color(0xFF2B4567)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: const Color(0xFF8AB0FF), size: 18),
            const SizedBox(width: 10),
            Expanded(child: Text(text, style: const TextStyle(color: Color(0xFFB3C2D8), fontSize: 11, height: 1.45))),
          ],
        ),
      );
}

class _SegmentPreview extends StatelessWidget {
  const _SegmentPreview({required this.labels});
  final List<String> labels;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(color: const Color(0xFF111D2E), borderRadius: BorderRadius.circular(15)),
        child: Row(
          children: labels.asMap().entries.map((entry) {
            final selected = entry.key == 0;
            return Expanded(
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(
                  color: selected ? const Color(0xFF304B79) : Colors.transparent,
                  borderRadius: BorderRadius.circular(11),
                ),
                child: Text(
                  entry.value,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: selected ? Colors.white : const Color(0xFF879AB5), fontSize: 10, fontWeight: FontWeight.w800),
                ),
              ),
            );
          }).toList(),
        ),
      );
}

class _MiniKey extends StatelessWidget {
  const _MiniKey(this.label);
  final String label;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: const Color(0xFF22344E),
          border: Border.all(color: const Color(0xFF405B80)),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(label, style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w900, color: Color(0xFFD5E2F4))),
      );
}

class _StickPreview extends StatelessWidget {
  const _StickPreview({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) => Column(
        children: [
          Text(label, textAlign: TextAlign.center, style: const TextStyle(color: Color(0xFF7D91AD), fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: .6)),
          const SizedBox(height: 8),
          AspectRatio(
            aspectRatio: 1,
            child: Container(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF0A1320),
                border: Border.all(color: const Color(0xFF344D70), width: 2),
                boxShadow: const [BoxShadow(color: Color(0x44000000), blurRadius: 12, offset: Offset(0, 5))],
              ),
              child: Center(
                child: Container(
                  width: 38,
                  height: 38,
                  decoration: const BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: LinearGradient(colors: [Color(0xFF6688B8), Color(0xFF293D5D)], begin: Alignment.topLeft, end: Alignment.bottomRight),
                  ),
                ),
              ),
            ),
          ),
        ],
      );
}

class _DpadPreview extends StatelessWidget {
  const _DpadPreview();

  @override
  Widget build(BuildContext context) {
    Widget key(String value) => Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(color: const Color(0xFF2B405D), borderRadius: BorderRadius.circular(5)),
          child: Center(child: Text(value, style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w900))),
        );
    return Column(
      children: [
        const SizedBox(height: 15),
        key('▲'),
        Row(mainAxisSize: MainAxisSize.min, children: [key('◀'), const SizedBox(width: 3), key('✦'), const SizedBox(width: 3), key('▶')]),
        key('▼'),
      ],
    );
  }
}

class _FaceButtonsPreview extends StatelessWidget {
  const _FaceButtonsPreview();

  @override
  Widget build(BuildContext context) {
    Widget key(String label, Color color) => Container(
          width: 23,
          height: 23,
          decoration: BoxDecoration(color: color.withOpacity(.2), border: Border.all(color: color.withOpacity(.7)), shape: BoxShape.circle),
          child: Center(child: Text(label, style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.w900))),
        );
    return Column(
      children: [
        const SizedBox(height: 15),
        key('Y', const Color(0xFFE6C36D)),
        Row(mainAxisSize: MainAxisSize.min, children: [key('X', const Color(0xFF9E91F0)), const SizedBox(width: 3), key('B', const Color(0xFFEF8DA3))]),
        key('A', const Color(0xFF69D8B0)),
      ],
    );
  }
}

class _SettingsGroup extends StatelessWidget {
  const _SettingsGroup({required this.title, required this.icon, required this.rows});
  final String title;
  final IconData icon;
  final List<_SettingRowData> rows;

  @override
  Widget build(BuildContext context) => _SurfaceCard(
        child: Column(
          children: [
            Row(children: [Icon(icon, color: const Color(0xFF8FB1FF)), const SizedBox(width: 9), Text(title, style: const TextStyle(fontWeight: FontWeight.w800))]),
            const SizedBox(height: 8),
            ...rows.map((row) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 9),
                  child: Row(
                    children: [
                      Expanded(child: Text(row.title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700))),
                      Text(row.subtitle, style: const TextStyle(fontSize: 10, color: Color(0xFF8194B0))),
                      const SizedBox(width: 4),
                      const Icon(Icons.chevron_right_rounded, size: 15, color: Color(0xFF7185A1)),
                    ],
                  ),
                )),
          ],
        ),
      );
}

class _SettingRowData {
  const _SettingRowData(this.title, this.subtitle);
  final String title;
  final String subtitle;
}

