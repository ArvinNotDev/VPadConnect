import 'package:material_ui/material_ui.dart';
import 'package:flutter/services.dart';

import '../models/pairing_target.dart';
import '../services/pairing_service.dart';
import 'qr_scanner_screen.dart';

class PairingScreen extends StatefulWidget {
  const PairingScreen({super.key});

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  final _service = PairingService();
  final _addressController = TextEditingController();
  final _codeController = TextEditingController();
  final _nameController = TextEditingController(text: 'VPadConnect Mobile');

  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _addressController.dispose();
    _codeController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _scanQr() async {
    final value = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => const QrScannerScreen()),
    );
    if (value == null || !mounted) return;

    try {
      await _connect(PairingTarget.fromQr(value));
    } on FormatException catch (error) {
      setState(() => _error = error.message);
    }
  }

  Future<void> _manualPair() async {
    final formKey = GlobalKey<FormState>();
    final accepted = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF101A2A),
      builder: (sheetContext) {
        return Padding(
          padding: EdgeInsets.fromLTRB(
            20,
            24,
            20,
            MediaQuery.of(sheetContext).viewInsets.bottom + 24,
          ),
          child: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Enter connection details',
                  style: TextStyle(fontSize: 21, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Use the HTTPS address and six-digit code shown in the desktop Web Companion page.',
                  style: TextStyle(color: Color(0xFF94A5BE), height: 1.45),
                ),
                const SizedBox(height: 20),
                TextFormField(
                  controller: _addressController,
                  keyboardType: TextInputType.url,
                  decoration: const InputDecoration(
                    labelText: 'PC address',
                    hintText: '192.168.1.20:8765',
                    prefixIcon: Icon(Icons.computer_rounded),
                  ),
                  validator: (value) {
                    try {
                      PairingTarget.fromManual(
                        address: value ?? '',
                        code: '000000',
                      );
                      return null;
                    } on FormatException catch (error) {
                      return error.message;
                    }
                  },
                ),
                const SizedBox(height: 14),
                TextFormField(
                  controller: _codeController,
                  keyboardType: TextInputType.number,
                  maxLength: 6,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: const InputDecoration(
                    labelText: 'Six-digit pairing code',
                    hintText: '000000',
                    prefixIcon: Icon(Icons.password_rounded),
                    counterText: '',
                  ),
                  validator: (value) => (value?.trim().length == 6)
                      ? null
                      : 'Enter all six digits.',
                ),
                const SizedBox(height: 18),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: () {
                      if (formKey.currentState?.validate() ?? false) {
                        Navigator.pop(sheetContext, true);
                      }
                    },
                    child: const Text('Continue securely'),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );

    if (accepted != true || !mounted) return;
    try {
      final target = PairingTarget.fromManual(
        address: _addressController.text,
        code: _codeController.text,
      );
      await _connect(target);
    } on FormatException catch (error) {
      setState(() => _error = error.message);
    }
  }

  Future<bool> _confirmManualFingerprint(String fingerprint) async {
    if (!mounted) return false;
    return await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Verify this PC'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Compare this SHA-256 fingerprint with the fingerprint displayed in VPadConnect on your PC. Continue only when every character matches.',
                  style: TextStyle(height: 1.45),
                ),
                const SizedBox(height: 16),
                SelectableText(
                  formatFingerprint(fingerprint),
                  style: const TextStyle(
                    fontFamily: 'monospace',
                    color: Color(0xFF54D6D0),
                    fontWeight: FontWeight.w700,
                    height: 1.8,
                  ),
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: const Text('Fingerprint matches'),
              ),
            ],
          ),
        ) ??
        false;
  }

  Future<void> _connect(PairingTarget target) async {
    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      var verifiedTarget = target;
      if (target.fingerprint == null) {
        final fingerprint = await _service.discoverFingerprint(target.baseUri);
        if (!await _confirmManualFingerprint(fingerprint)) return;
        verifiedTarget = target.withFingerprint(fingerprint);
      }

      final session = await _service.pair(
        target: verifiedTarget,
        deviceName: _nameController.text,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed(
        '/companion',
        arguments: session,
      );
    } on PairingException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (error) {
      if (mounted) setState(() => _error = 'Could not connect: $error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
              children: [
                Row(
                  children: [
                    Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(16),
                        gradient: const LinearGradient(
                          colors: [Color(0xFF6B96FF), Color(0xFF54D6D0)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                      ),
                      child: const Icon(
                        Icons.sports_esports_rounded,
                        color: Color(0xFF07101F),
                        size: 27,
                      ),
                    ),
                    const SizedBox(width: 13),
                    const Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'VPADCONNECT',
                          style: TextStyle(
                            fontWeight: FontWeight.w900,
                            letterSpacing: 1.5,
                            fontSize: 14,
                          ),
                        ),
                        SizedBox(height: 2),
                        Text(
                          'Mobile Companion',
                          style: TextStyle(color: Color(0xFF94A5BE), fontSize: 12),
                        ),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 54),
                const Text(
                  'Your PC.\nYour controls.',
                  style: TextStyle(
                    fontSize: 38,
                    height: 1.08,
                    letterSpacing: -1.2,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 14),
                const Text(
                  'Connect your phone to VPadConnect and turn it into a game controller, touchpad, and remote control.',
                  style: TextStyle(
                    color: Color(0xFF9AAAC0),
                    height: 1.55,
                    fontSize: 15,
                  ),
                ),
                const SizedBox(height: 30),
                _ConnectionCard(
                  icon: Icons.qr_code_scanner_rounded,
                  title: 'Scan desktop QR code',
                  subtitle: 'Fastest and most secure way to connect',
                  primary: true,
                  onTap: _busy ? null : _scanQr,
                ),
                const SizedBox(height: 12),
                _ConnectionCard(
                  icon: Icons.keyboard_alt_outlined,
                  title: 'Enter details manually',
                  subtitle: 'Use the PC address and six-digit code',
                  onTap: _busy ? null : _manualPair,
                ),
                const SizedBox(height: 28),
                TextField(
                  controller: _nameController,
                  maxLength: 64,
                  decoration: const InputDecoration(
                    labelText: 'This device name',
                    prefixIcon: Icon(Icons.phone_android_rounded),
                    counterText: '',
                  ),
                ),
                const SizedBox(height: 18),
                if (_busy) ...[
                  const LinearProgressIndicator(minHeight: 3),
                  const SizedBox(height: 12),
                  const Text(
                    'Verifying the desktop identity and pairing securely…',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Color(0xFF94A5BE), fontSize: 12),
                  ),
                ],
                if (_error != null) ...[
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: const Color(0xFF391D2B),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0xFF7B354D)),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.error_outline_rounded, color: Color(0xFFFF8791)),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            _error!,
                            style: const TextStyle(color: Color(0xFFFFC2C7), height: 1.4),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 26),
                const Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.shield_outlined, color: Color(0xFF54D6D0), size: 19),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'Local connection · HTTPS certificate verification · No account required',
                        style: TextStyle(color: Color(0xFF778AA6), fontSize: 11, height: 1.5),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ConnectionCard extends StatelessWidget {
  const _ConnectionCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.primary = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    final border = primary ? const Color(0xFF557AC6) : const Color(0xFF293B56);
    return Material(
      color: primary ? const Color(0xFF172947) : const Color(0xFF101A2A),
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: border),
          ),
          child: Row(
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: primary
                      ? const Color(0xFF6B96FF).withValues(alpha: 0.16)
                      : const Color(0xFF22334D),
                  borderRadius: BorderRadius.circular(15),
                ),
                child: Icon(
                  icon,
                  color: primary ? const Color(0xFF9AB7FF) : const Color(0xFFB6C6DE),
                  size: 23,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: const TextStyle(color: Color(0xFF94A5BE), fontSize: 12),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded, color: Color(0xFF8194B0)),
            ],
          ),
        ),
      ),
    );
  }
}
