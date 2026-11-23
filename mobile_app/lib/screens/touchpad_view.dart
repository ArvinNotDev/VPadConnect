import 'dart:async';

import 'package:flutter/material.dart';
import 'package:sensors_plus/sensors_plus.dart';

import '../services/remote_input_service.dart';

class TouchpadView extends StatefulWidget {
  const TouchpadView({required this.input, super.key});

  final RemoteInputService input;

  @override
  State<TouchpadView> createState() => _TouchpadViewState();
}

class _TouchpadViewState extends State<TouchpadView> {
  final Map<int, Offset> _active = {};
  final Map<int, Offset> _last = {};
  final Set<int> _moved = {};
  StreamSubscription<GyroscopeEvent>? _gyroSubscription;

  double _sensitivity = 1.7;
  double _scrollSensitivity = 1.0;
  double _airSensitivity = 1.0;
  double _gyroBiasX = 0;
  double _gyroBiasY = 0;
  double _calibrationX = 0;
  double _calibrationY = 0;
  int _calibrationSamples = 0;
  bool _calibrating = false;
  bool _airMouseEnabled = false;
  bool _tapToClick = true;
  String _airStatus = 'Air Mouse is off';

  @override
  void dispose() {
    _gyroSubscription?.cancel();
    widget.input.releaseAll();
    super.dispose();
  }

  void _pointerDown(PointerDownEvent event) {
    widget.input.setMode('mouse');
    _active[event.pointer] = event.localPosition;
    _last[event.pointer] = event.localPosition;
  }

  void _pointerMove(PointerMoveEvent event) {
    if (!_active.containsKey(event.pointer)) return;
    final previous = _last[event.pointer] ?? event.localPosition;
    final delta = event.localPosition - previous;
    _last[event.pointer] = event.localPosition;
    _active[event.pointer] = event.localPosition;

    if (delta.distance > 2) _moved.add(event.pointer);

    if (_active.length == 1 && !_airMouseEnabled) {
      widget.input.moveMouse(
        delta.dx * _sensitivity * 1.45,
        delta.dy * _sensitivity * 1.45,
      );
      return;
    }

    if (_active.length >= 2) {
      final scrollAmount = (-delta.dy * _scrollSensitivity / 18).round();
      if (scrollAmount != 0) widget.input.scroll(scrollAmount);
    }
  }

  void _pointerUp(PointerEvent event) {
    final wasSinglePointer = _active.length == 1;
    final wasTap = !_moved.contains(event.pointer);
    _active.remove(event.pointer);
    _last.remove(event.pointer);
    _moved.remove(event.pointer);

    if (_tapToClick && wasSinglePointer && wasTap) {
      _click('left');
    }
  }

  void _click(String button) {
    widget.input.setMouseButton(button, true);
    Timer(const Duration(milliseconds: 85), () {
      if (mounted) widget.input.setMouseButton(button, false);
    });
  }

  void _toggleAirMouse() {
    if (_airMouseEnabled) {
      _gyroSubscription?.cancel();
      _gyroSubscription = null;
      setState(() {
        _airMouseEnabled = false;
        _airStatus = 'Air Mouse is off';
      });
      return;
    }

    setState(() {
      _airMouseEnabled = true;
      _airStatus = 'Move your phone gently to control the pointer.';
    });
    widget.input.setMode('mouse');
    _gyroSubscription = gyroscopeEvents.listen(
      _onGyroscope,
      onError: (Object error) {
        if (!mounted) return;
        setState(() {
          _airMouseEnabled = false;
          _airStatus = 'Motion sensor is unavailable on this device.';
        });
        _gyroSubscription?.cancel();
        _gyroSubscription = null;
      },
      cancelOnError: true,
    );
  }

  void _onGyroscope(GyroscopeEvent event) {
    if (!mounted || !_airMouseEnabled) return;
    if (_calibrating) {
      _calibrationX += event.x;
      _calibrationY += event.y;
      _calibrationSamples++;
      if (_calibrationSamples >= 30) {
        _gyroBiasX = _calibrationX / _calibrationSamples;
        _gyroBiasY = _calibrationY / _calibrationSamples;
        _calibrating = false;
        setState(() => _airStatus = 'Air Mouse calibrated. Tilt to move the pointer.');
      }
      return;
    }

    final dx = (event.y - _gyroBiasY) * 24 * _airSensitivity;
    final dy = -(event.x - _gyroBiasX) * 24 * _airSensitivity;
    widget.input.moveMouse(dx, dy);
  }

  void _calibrateAirMouse() {
    if (!_airMouseEnabled) {
      setState(() => _airStatus = 'Enable Air Mouse before calibration.');
      return;
    }
    _calibrationX = 0;
    _calibrationY = 0;
    _calibrationSamples = 0;
    _calibrating = true;
    setState(() => _airStatus = 'Hold the phone still while it calibrates…');
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(18, 12, 18, 24),
      children: [
        const _Eyebrow('POINTER CONTROL'),
        const SizedBox(height: 5),
        const Text('Touchpad', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
        const SizedBox(height: 5),
        const Text(
          'A touch-first surface for precise desktop control.',
          style: TextStyle(color: Color(0xFF94A5BE), fontSize: 12),
        ),
        const SizedBox(height: 16),
        Container(
          height: 260,
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(
            color: const Color(0xFF0C1625),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: const Color(0xFF2B405D)),
          ),
          child: Listener(
            behavior: HitTestBehavior.opaque,
            onPointerDown: _pointerDown,
            onPointerMove: _pointerMove,
            onPointerUp: _pointerUp,
            onPointerCancel: _pointerUp,
            child: Stack(
              children: [
                const Positioned.fill(child: CustomPaint(painter: _TouchGridPainter())),
                Center(
                  child: IgnorePointer(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          _airMouseEnabled ? Icons.explore_rounded : Icons.touch_app_rounded,
                          color: const Color(0xFF7295BD),
                          size: 38,
                        ),
                        const SizedBox(height: 9),
                        Text(
                          _airMouseEnabled ? 'AIR MOUSE ACTIVE' : 'TOUCH SURFACE',
                          style: const TextStyle(
                            color: Color(0xFF7188A7),
                            fontWeight: FontWeight.w900,
                            letterSpacing: 1.5,
                            fontSize: 10,
                          ),
                        ),
                        const SizedBox(height: 5),
                        const Text(
                          'Drag to move · Two fingers to scroll',
                          style: TextStyle(color: Color(0xFF7188A7), fontSize: 10),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(child: _MouseButton(label: 'Left click', icon: Icons.mouse_rounded, onTap: () => _click('left'))),
            const SizedBox(width: 8),
            Expanded(child: _MouseButton(label: 'Right click', icon: Icons.more_horiz_rounded, onTap: () => _click('right'))),
            const SizedBox(width: 8),
            Expanded(child: _MouseButton(label: 'Middle', icon: Icons.circle_outlined, onTap: () => _click('middle'))),
          ],
        ),
        const SizedBox(height: 16),
        _SettingsCard(
          title: 'Air Mouse',
          subtitle: 'Use the phone gyroscope to control pointer movement.',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: _toggleAirMouse,
                      icon: Icon(_airMouseEnabled ? Icons.pause_rounded : Icons.motion_photos_on_rounded),
                      label: Text(_airMouseEnabled ? 'Disable Air Mouse' : 'Enable Air Mouse'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton(
                    onPressed: _calibrateAirMouse,
                    child: const Text('Calibrate'),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(_airStatus, style: const TextStyle(color: Color(0xFF94A5BE), fontSize: 11)),
              const SizedBox(height: 8),
              _ValueSlider(
                label: 'Air Mouse sensitivity',
                value: _airSensitivity,
                min: .5,
                max: 3,
                onChanged: (value) => setState(() => _airSensitivity = value),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _SettingsCard(
          title: 'Touchpad preferences',
          subtitle: 'Adjust pointer speed and scrolling behavior.',
          child: Column(
            children: [
              _ValueSlider(
                label: 'Pointer sensitivity',
                value: _sensitivity,
                min: .5,
                max: 4,
                onChanged: (value) => setState(() => _sensitivity = value),
              ),
              _ValueSlider(
                label: 'Scroll sensitivity',
                value: _scrollSensitivity,
                min: .5,
                max: 3,
                onChanged: (value) => setState(() => _scrollSensitivity = value),
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                value: _tapToClick,
                onChanged: (value) => setState(() => _tapToClick = value),
                title: const Text('Tap to click', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
                activeColor: const Color(0xFF6B96FF),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ValueSlider extends StatelessWidget {
  const _ValueSlider({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
  });

  final String label;
  final double value;
  final double min;
  final double max;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700))),
              Text(value.toStringAsFixed(1) + '×', style: const TextStyle(color: Color(0xFF8AB0FF), fontSize: 11, fontWeight: FontWeight.w800)),
            ],
          ),
          Slider(min: min, max: max, value: value, onChanged: onChanged),
        ],
      );
}

class _MouseButton extends StatelessWidget {
  const _MouseButton({required this.label, required this.icon, required this.onTap});

  final String label;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
        onPressed: onTap,
        icon: Icon(icon, size: 16),
        label: Text(label, style: const TextStyle(fontSize: 9)),
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, 46),
          padding: const EdgeInsets.symmetric(horizontal: 5),
        ),
      );
}

class _SettingsCard extends StatelessWidget {
  const _SettingsCard({required this.title, required this.subtitle, required this.child});

  final String title;
  final String subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(15),
        decoration: BoxDecoration(
          color: const Color(0xFF101A2A),
          borderRadius: BorderRadius.circular(19),
          border: Border.all(color: const Color(0xFF293B56)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
            const SizedBox(height: 3),
            Text(subtitle, style: const TextStyle(color: Color(0xFF879AB5), fontSize: 10)),
            const SizedBox(height: 12),
            child,
          ],
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

class _TouchGridPainter extends CustomPainter {
  const _TouchGridPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF3D5878).withOpacity(.23)
      ..strokeWidth = .6;
    const step = 28.0;
    for (double x = 0; x <= size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y <= size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
