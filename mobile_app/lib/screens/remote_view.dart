import 'package:flutter/material.dart';

import '../services/pairing_service.dart';
import '../services/remote_action_service.dart';

class RemoteView extends StatefulWidget {
  const RemoteView({required this.session, super.key});

  final PairedSession session;

  @override
  State<RemoteView> createState() => _RemoteViewState();
}

class _RemoteViewState extends State<RemoteView> {
  late final RemoteActionService _actions;
  final TextEditingController _textController = TextEditingController();
  final TextEditingController _clipboardController = TextEditingController();
  final Set<String> _capabilities = {};
  bool _loading = true;
  String? _error;
  String? _lastAction;
  String _pcName = 'Windows PC';
  String _operatingSystem = 'Desktop';
  String? _selectedShortcut = 'copy';

  @override
  void initState() {
    super.initState();
    _actions = RemoteActionService(widget.session);
    _refreshStatus();
  }

  @override
  void dispose() {
    _textController.dispose();
    _clipboardController.dispose();
    _actions.dispose();
    super.dispose();
  }

  bool _allowed(String permission) => _capabilities.contains(permission);

  Future<void> _refreshStatus() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await _actions.send('pc_status');
      final capabilities = result['capabilities'];
      if (capabilities is Map<String, dynamic>) {
        _capabilities
          ..clear()
          ..addAll(
            capabilities.entries
                .where((entry) => entry.value == true)
                .map((entry) => entry.key),
          );
      }
      if (!mounted) return;
      setState(() {
        _pcName = (result['computer_name'] ?? 'Windows PC').toString();
        _operatingSystem = (result['operating_system'] ?? 'Desktop').toString();
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _run(
    String action, [
    Map<String, dynamic> payload = const {},
  ]) async {
    setState(() {
      _error = null;
      _lastAction = 'Sending…';
    });
    try {
      final result = await _actions.send(action, payload);
      if (!mounted) return;
      setState(() {
        _lastAction = action.replaceAll('_', ' ') + ' completed';
      });
      if (action == 'clipboard_get') {
        _clipboardController.text = (result['text'] ?? '').toString();
      }
      if (result['truncated'] == true && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Clipboard text was shortened to 3000 characters.')),
        );
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _lastAction = null;
      });
    }
  }

  Future<void> _confirmPower(String command) async {
    final destructive = const {'logoff', 'restart', 'shutdown', 'sleep'}.contains(command);
    if (destructive) {
      final confirmed = await showDialog<bool>(
            context: context,
            builder: (dialogContext) => AlertDialog(
              title: Text(_powerTitle(command) + '?'),
              content: Text('This action will be sent to ' + _pcName + '. Continue?'),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(dialogContext, false),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(dialogContext, true),
                  child: const Text('Confirm'),
                ),
              ],
            ),
          ) ??
          false;
      if (!confirmed) return;
    }
    await _run('power_action', {'command': command});
  }

  String _powerTitle(String command) {
    switch (command) {
      case 'restart':
        return 'Restart PC';
      case 'shutdown':
        return 'Shut down PC';
      case 'sleep':
        return 'Put PC to sleep';
      case 'logoff':
        return 'Sign out';
      case 'display_off':
        return 'Turn display off';
      default:
        return 'Lock PC';
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(18, 12, 18, 28),
      children: [
        const _Eyebrow('DESKTOP TOOLS'),
        const SizedBox(height: 5),
        const Text('PC Remote', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
        const SizedBox(height: 5),
        const Text(
          'Send commands to your connected Windows PC.',
          style: TextStyle(color: Color(0xFF94A5BE), fontSize: 12),
        ),
        const SizedBox(height: 16),
        _RemoteCard(
          title: 'Connected PC',
          subtitle: 'Desktop identity and permission status.',
          child: Row(
            children: [
              const Icon(Icons.computer_rounded, color: Color(0xFF8FB1FF), size: 24),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(_pcName, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
                    const SizedBox(height: 3),
                    Text(_operatingSystem, style: const TextStyle(color: Color(0xFF879AB5), fontSize: 10)),
                  ],
                ),
              ),
              IconButton(
                onPressed: _loading ? null : _refreshStatus,
                icon: _loading
                    ? const SizedBox(width: 17, height: 17, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.refresh_rounded),
                tooltip: 'Refresh permissions',
              ),
            ],
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: 10),
          _Notice(_error!, warning: true),
        ],
        if (_lastAction != null) ...[
          const SizedBox(height: 10),
          _Notice(_lastAction!),
        ],
        if (!_loading && _capabilities.isEmpty) ...[
          const SizedBox(height: 10),
          const _Notice(
            'No optional PC Remote permissions are enabled on the desktop. Enable the required permissions in VPadConnect settings.',
            warning: true,
          ),
        ],
        const SizedBox(height: 14),
        _RemoteCard(
          title: 'Keyboard & text',
          subtitle: 'Send text to the currently focused desktop app.',
          enabled: _allowed('keyboard') && !_loading,
          child: Column(
            children: [
              TextField(
                controller: _textController,
                minLines: 2,
                maxLines: 4,
                maxLength: 4096,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  hintText: 'Type text to send to your PC…',
                  counterText: '',
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: !_allowed('keyboard') || _loading || _textController.text.isEmpty
                      ? null
                      : () => _run('keyboard_text', {'text': _textController.text}),
                  icon: const Icon(Icons.send_rounded),
                  label: const Text('Send text'),
                ),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 7,
                runSpacing: 7,
                children: [
                  _ActionButton('Enter', Icons.keyboard_return_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'ENTER'})),
                  _ActionButton('Tab', Icons.keyboard_tab_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'TAB'})),
                  _ActionButton('Esc', Icons.cancel_outlined, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'ESCAPE'})),
                  _ActionButton('Backspace', Icons.backspace_outlined, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'BACKSPACE'})),
                  _ActionButton('↑', Icons.keyboard_arrow_up_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'UP'})),
                  _ActionButton('↓', Icons.keyboard_arrow_down_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'DOWN'})),
                  _ActionButton('←', Icons.keyboard_arrow_left_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'LEFT'})),
                  _ActionButton('→', Icons.keyboard_arrow_right_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'RIGHT'})),
                  _ActionButton('Delete', Icons.delete_outline_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'DELETE'})),
                  _ActionButton('Home', Icons.first_page_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'HOME'})),
                  _ActionButton('End', Icons.last_page_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'END'})),
                  _ActionButton('PgUp', Icons.keyboard_double_arrow_up_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'PAGE_UP'})),
                  _ActionButton('PgDn', Icons.keyboard_double_arrow_down_rounded, !_allowed('keyboard'), () => _run('keyboard_key', {'key': 'PAGE_DOWN'})),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 7,
                runSpacing: 7,
                children: [
                  _ModifierButton(label: 'CTRL', keyName: 'CTRL', onChanged: (pressed) => _run('keyboard_modifier', {'key': 'CTRL', 'pressed': pressed})),
                  _ModifierButton(label: 'SHIFT', keyName: 'SHIFT', onChanged: (pressed) => _run('keyboard_modifier', {'key': 'SHIFT', 'pressed': pressed})),
                  _ModifierButton(label: 'ALT', keyName: 'ALT', onChanged: (pressed) => _run('keyboard_modifier', {'key': 'ALT', 'pressed': pressed})),
                  _ModifierButton(label: 'WIN', keyName: 'WIN', onChanged: (pressed) => _run('keyboard_modifier', {'key': 'WIN', 'pressed': pressed})),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: _selectedShortcut,
                      decoration: const InputDecoration(labelText: 'Shortcut'),
                      items: const [
                        DropdownMenuItem(value: 'copy', child: Text('Copy')),
                        DropdownMenuItem(value: 'paste', child: Text('Paste')),
                        DropdownMenuItem(value: 'cut', child: Text('Cut')),
                        DropdownMenuItem(value: 'undo', child: Text('Undo')),
                        DropdownMenuItem(value: 'redo', child: Text('Redo')),
                        DropdownMenuItem(value: 'select_all', child: Text('Select all')),
                        DropdownMenuItem(value: 'save', child: Text('Save')),
                        DropdownMenuItem(value: 'find', child: Text('Find')),
                        DropdownMenuItem(value: 'alt_tab', child: Text('Switch window')),
                        DropdownMenuItem(value: 'show_desktop', child: Text('Show desktop')),
                      ],
                      onChanged: (value) => setState(() => _selectedShortcut = value),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: !_allowed('keyboard') || _loading || _selectedShortcut == null
                        ? null
                        : () => _run('keyboard_shortcut', {'shortcut': _selectedShortcut}),
                    child: const Text('Run'),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        _RemoteCard(
          title: 'Media & volume',
          subtitle: 'Playback controls and system volume.',
          enabled: _allowed('media') && !_loading,
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _ActionButton('Previous', Icons.skip_previous_rounded, !_allowed('media'), () => _run('media', {'command': 'previous_track'})),
              _ActionButton('Play / pause', Icons.play_arrow_rounded, !_allowed('media'), () => _run('media', {'command': 'play_pause'})),
              _ActionButton('Next', Icons.skip_next_rounded, !_allowed('media'), () => _run('media', {'command': 'next_track'})),
              _ActionButton('Volume −', Icons.volume_down_rounded, !_allowed('media'), () => _run('media', {'command': 'volume_down'})),
              _ActionButton('Mute', Icons.volume_off_rounded, !_allowed('media'), () => _run('media', {'command': 'mute'})),
              _ActionButton('Volume +', Icons.volume_up_rounded, !_allowed('media'), () => _run('media', {'command': 'volume_up'})),
              _ActionButton('Stop', Icons.stop_rounded, !_allowed('media'), () => _run('media', {'command': 'stop'})),
            ],
          ),
        ),
        const SizedBox(height: 10),
        _RemoteCard(
          title: 'Clipboard',
          subtitle: 'Transfer text between your phone and PC.',
          enabled: _allowed('clipboard') && !_loading,
          child: Column(
            children: [
              TextField(
                controller: _clipboardController,
                minLines: 2,
                maxLines: 4,
                maxLength: 4096,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(hintText: 'Clipboard text…', counterText: ''),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: !_allowed('clipboard') || _loading
                          ? null
                          : () => _run('clipboard_set', {'text': _clipboardController.text}),
                      child: const Text('Send to PC'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: FilledButton(
                      onPressed: !_allowed('clipboard') || _loading
                          ? null
                          : () => _run('clipboard_get'),
                      child: const Text('Read PC clipboard'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        _RemoteCard(
          title: 'Quick launch',
          subtitle: 'Open supported desktop applications.',
          enabled: _allowed('app_launch') && !_loading,
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _ActionButton('Browser', Icons.language_rounded, !_allowed('app_launch'), () => _run('launch_app', {'app': 'browser'})),
              _ActionButton('Explorer', Icons.folder_open_rounded, !_allowed('app_launch'), () => _run('launch_app', {'app': 'explorer'})),
              _ActionButton('Calculator', Icons.calculate_rounded, !_allowed('app_launch'), () => _run('launch_app', {'app': 'calculator'})),
              _ActionButton('Notepad', Icons.notes_rounded, !_allowed('app_launch'), () => _run('launch_app', {'app': 'notepad'})),
              _ActionButton('Downloads', Icons.download_rounded, !_allowed('app_launch'), () => _run('launch_app', {'app': 'downloads'})),
            ],
          ),
        ),
        const SizedBox(height: 10),
        _RemoteCard(
          title: 'Presentation',
          subtitle: 'Navigate and control slide presentations.',
          enabled: _allowed('presentation') && !_loading,
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _ActionButton('Previous', Icons.arrow_back_rounded, !_allowed('presentation'), () => _run('presentation', {'command': 'previous'})),
              _ActionButton('Next', Icons.arrow_forward_rounded, !_allowed('presentation'), () => _run('presentation', {'command': 'next'})),
              _ActionButton('Start', Icons.play_arrow_rounded, !_allowed('presentation'), () => _run('presentation', {'command': 'start'})),
              _ActionButton('End', Icons.stop_rounded, !_allowed('presentation'), () => _run('presentation', {'command': 'end'})),
              _ActionButton('Black screen', Icons.visibility_off_rounded, !_allowed('presentation'), () => _run('presentation', {'command': 'black_screen'})),
            ],
          ),
        ),
        const SizedBox(height: 10),
        _RemoteCard(
          title: 'Power actions',
          subtitle: 'These operations run on the Windows PC.',
          enabled: _allowed('power') && !_loading,
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _ActionButton('Lock', Icons.lock_rounded, !_allowed('power'), () => _confirmPower('lock')),
              _ActionButton('Sleep', Icons.bedtime_rounded, !_allowed('power'), () => _confirmPower('sleep')),
              _ActionButton('Log off', Icons.logout_rounded, !_allowed('power'), () => _confirmPower('logoff')),
              _ActionButton('Display off', Icons.monitor_rounded, !_allowed('power'), () => _confirmPower('display_off')),
              _ActionButton('Restart', Icons.restart_alt_rounded, !_allowed('power'), () => _confirmPower('restart'), danger: true),
              _ActionButton('Shut down', Icons.power_settings_new_rounded, !_allowed('power'), () => _confirmPower('shutdown'), danger: true),
            ],
          ),
        ),
        const SizedBox(height: 12),
        const _Notice('Controls are enabled only when the matching permission is granted in the VPadConnect desktop app.'),
      ],
    );
  }
}

class _ModifierButton extends StatefulWidget {
  const _ModifierButton({
    required this.label,
    required this.keyName,
    required this.onChanged,
  });

  final String label;
  final String keyName;
  final ValueChanged<bool> onChanged;

  @override
  State<_ModifierButton> createState() => _ModifierButtonState();
}

class _ModifierButtonState extends State<_ModifierButton> {
  final Set<int> _pointers = {};
  bool _pressed = false;

  void _down(PointerEvent event) {
    if (!_pointers.add(event.pointer) || _pressed) return;
    setState(() => _pressed = true);
    widget.onChanged(true);
  }

  void _up(PointerEvent event) {
    if (!_pointers.remove(event.pointer) || _pointers.isNotEmpty) return;
    setState(() => _pressed = false);
    widget.onChanged(false);
  }

  @override
  void dispose() {
    if (_pressed) widget.onChanged(false);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Listener(
        behavior: HitTestBehavior.opaque,
        onPointerDown: _down,
        onPointerUp: _up,
        onPointerCancel: _up,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 80),
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
          decoration: BoxDecoration(
            color: _pressed ? const Color(0xFF355A86) : const Color(0xFF182840),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: _pressed ? const Color(0xFF8FB5FF) : const Color(0xFF344B68)),
          ),
          child: Text(
            widget.label,
            style: TextStyle(
              color: _pressed ? Colors.white : const Color(0xFFCAD8EA),
              fontSize: 10,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
      );
}

class _RemoteCard extends StatelessWidget {
  const _RemoteCard({
    required this.title,
    required this.subtitle,
    required this.child,
    this.enabled = true,
  });

  final String title;
  final String subtitle;
  final Widget child;
  final bool enabled;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(15),
        decoration: BoxDecoration(
          color: const Color(0xFF101A2A),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xFF293B56)),
        ),
        child: Opacity(
          opacity: enabled ? 1 : .48,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800)),
              const SizedBox(height: 3),
              Text(subtitle, style: const TextStyle(color: Color(0xFF879AB5), fontSize: 10)),
              const SizedBox(height: 13),
              child,
            ],
          ),
        ),
      );
}

class _ActionButton extends StatelessWidget {
  const _ActionButton(
    this.label,
    this.icon,
    this.disabled,
    this.onPressed, {
    this.danger = false,
  });

  final String label;
  final IconData icon;
  final bool disabled;
  final VoidCallback onPressed;
  final bool danger;

  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
        onPressed: disabled ? null : onPressed,
        icon: Icon(icon, size: 16),
        label: Text(label, style: const TextStyle(fontSize: 10)),
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, 42),
          padding: const EdgeInsets.symmetric(horizontal: 10),
          foregroundColor: danger ? const Color(0xFFFF929C) : const Color(0xFFD1DEF0),
          side: BorderSide(color: danger ? const Color(0xFF713847) : const Color(0xFF354B69)),
        ),
      );
}

class _Eyebrow extends StatelessWidget {
  const _Eyebrow(this.label);
  final String label;

  @override
  Widget build(BuildContext context) => Text(
        label,
        style: const TextStyle(color: Color(0xFF66BFC5), fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1.8),
      );
}

class _Notice extends StatelessWidget {
  const _Notice(this.text, {this.warning = false});
  final String text;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    final color = warning ? const Color(0xFFE8B46C) : const Color(0xFF8AB0FF);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(.09),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withOpacity(.25)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(warning ? Icons.info_outline_rounded : Icons.shield_outlined, color: color, size: 17),
          const SizedBox(width: 9),
          Expanded(child: Text(text, style: const TextStyle(color: Color(0xFFB5C4D9), fontSize: 10, height: 1.45))),
        ],
      ),
    );
  }
}
