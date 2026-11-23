import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:sensors_plus/sensors_plus.dart';

import '../services/remote_input_service.dart';

class GamepadView extends StatefulWidget {
  const GamepadView({
    required this.input,
    required this.gamepadAvailable,
    super.key,
  });

  final RemoteInputService input;
  final bool gamepadAvailable;

  @override
  State<GamepadView> createState() => _GamepadViewState();
}

class _GamepadViewState extends State<GamepadView> {
  bool _playStationLayout = false;
  String _preset = 'Standard';
  double _leftTrigger = 0;
  double _rightTrigger = 0;
  StreamSubscription<AccelerometerEvent>? _tiltSubscription;
  bool _tiltEnabled = false;
  double _tiltCenter = 0;
  double _tiltAngle = 0;
  double _filteredTiltAngle = 0;
  double _tiltSensitivity = 1.0;
  String _tiltStatus = 'Enable tilt steering while using Driving mode.';

  @override
  void dispose() {
    _tiltSubscription?.cancel();
    widget.input.releaseAll();
    super.dispose();
  }

  void _setTrigger(String key, double value) {
    setState(() {
      if (key == 'L2') {
        _leftTrigger = value;
      } else {
        _rightTrigger = value;
      }
    });
    widget.input.setAnalog(key, value);
  }

  void _setTiltEnabled(bool enabled) {
    if (enabled == _tiltEnabled) return;
    if (!enabled) {
      _tiltSubscription?.cancel();
      _tiltSubscription = null;
      setState(() {
        _tiltEnabled = false;
        _tiltStatus = 'Tilt steering is off.';
      });
      widget.input.setStick('left', 0, 0);
      return;
    }

    setState(() {
      _tiltEnabled = true;
      _tiltStatus = 'Hold the phone still, then calibrate the center.';
    });
    _tiltSubscription = accelerometerEvents.listen(
      (event) {
        if (!mounted || !_tiltEnabled) return;
        final angle = math.atan2(event.x, math.sqrt(event.y * event.y + event.z * event.z));
        _tiltAngle = angle;
        _filteredTiltAngle = (_filteredTiltAngle * .78) + (angle * .22);
        final steering = ((_filteredTiltAngle - _tiltCenter) / .65 * _tiltSensitivity)
            .clamp(-1.0, 1.0)
            .toDouble();
        widget.input.setStick('left', steering, 0);
      },
      onError: (Object error) {
        if (!mounted) return;
        _tiltSubscription?.cancel();
        _tiltSubscription = null;
        setState(() {
          _tiltEnabled = false;
          _tiltStatus = 'Motion sensor is unavailable on this device.';
        });
      },
      cancelOnError: true,
    );
  }

  void _calibrateTilt() {
    if (!_tiltEnabled) return;
    _tiltCenter = _tiltAngle;
    setState(() => _tiltStatus = 'Steering center calibrated.');
    widget.input.setStick('left', 0, 0);
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final landscape = constraints.maxWidth > constraints.maxHeight;
        final stickSize = landscape ? 104.0 : 116.0;
        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 24),
          children: [
            Row(
              children: [
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _Eyebrow('GAMING'),
                      SizedBox(height: 4),
                      Text('Virtual controller', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900)),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Switch controller style',
                  onPressed: () => setState(() => _playStationLayout = !_playStationLayout),
                  icon: Icon(
                    _playStationLayout ? Icons.sports_esports_rounded : Icons.gamepad_rounded,
                    color: const Color(0xFF9AB7FF),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 5),
            Text(
              widget.gamepadAvailable
                  ? 'Multi-touch input · low-latency desktop connection'
                  : 'Install ViGEmBus on the PC to enable virtual XInput output.',
              style: const TextStyle(color: Color(0xFF94A5BE), fontSize: 11),
            ),
            if (!widget.gamepadAvailable) ...[
              const SizedBox(height: 12),
              const _Notice('Virtual gamepad is unavailable. The other companion tools can still work.', warning: true),
            ],
            const SizedBox(height: 16),
            _PresetSelector(
              selected: _preset,
              onChanged: (value) {
                setState(() => _preset = value);
                widget.input.setMode('gamepad');
                if (value != 'Driving' && _tiltEnabled) _setTiltEnabled(false);
                if (value != 'Driving') {
                  _setTrigger('L2', 0);
                  _setTrigger('R2', 0);
                }
              },
            ),
            if (_preset == 'Driving') ...[
              const SizedBox(height: 12),
              _TiltSteeringCard(
                enabled: _tiltEnabled,
                status: _tiltStatus,
                sensitivity: _tiltSensitivity,
                onToggle: _setTiltEnabled,
                onCalibrate: _calibrateTilt,
                onSensitivityChanged: (value) => setState(() => _tiltSensitivity = value),
              ),
            ],
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.fromLTRB(13, 14, 13, 12),
              decoration: BoxDecoration(
                color: const Color(0xFF101A2A),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: const Color(0xFF2B405D)),
              ),
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: _HoldButton(
                          label: 'LB',
                          onChanged: (value) => widget.input.setButton('LB', value),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _HoldButton(
                          label: 'RB',
                          onChanged: (value) => widget.input.setButton('RB', value),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: _TriggerControl(
                          label: 'LEFT TRIGGER',
                          value: _leftTrigger,
                          digital: _preset == 'Shooter',
                          onChanged: (value) => _setTrigger('L2', value),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _TriggerControl(
                          label: 'RIGHT TRIGGER',
                          value: _rightTrigger,
                          digital: _preset == 'Shooter',
                          onChanged: (value) => _setTrigger('R2', value),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Expanded(
                        child: Column(
                          children: [
                            _AnalogStick(
                              label: 'LEFT STICK',
                              size: stickSize,
                              onChanged: (x, y) => widget.input.setStick('left', x, y),
                            ),
                            const SizedBox(height: 18),
                            _Dpad(
                              onChanged: (key, pressed) => widget.input.setButton(key, pressed),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Column(
                          children: [
                            _FacePad(
                              playStation: _playStationLayout,
                              onChanged: (key, pressed) => widget.input.setButton(key, pressed),
                            ),
                            const SizedBox(height: 18),
                            _AnalogStick(
                              label: 'RIGHT STICK',
                              size: stickSize,
                              onChanged: (x, y) => widget.input.setStick('right', x, y),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _HoldButton(
                        label: 'VIEW',
                        compact: true,
                        onChanged: (value) => widget.input.setButton('BACK', value),
                      ),
                      const SizedBox(width: 8),
                      _HoldButton(
                        label: _playStationLayout ? 'PS' : 'GUIDE',
                        compact: true,
                        onChanged: (value) => widget.input.setButton('GUIDE', value),
                      ),
                      const SizedBox(width: 8),
                      _HoldButton(
                        label: 'MENU',
                        compact: true,
                        onChanged: (value) => widget.input.setButton('START', value),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            const _Notice(
              'Release a control at any time to return it to neutral. Switching tabs also clears held inputs.',
            ),
          ],
        );
      },
    );
  }
}

class _PresetSelector extends StatelessWidget {
  const _PresetSelector({required this.selected, required this.onChanged});

  final String selected;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: const Color(0xFF111D2E),
        borderRadius: BorderRadius.circular(15),
      ),
      child: Row(
        children: ['Standard', 'Driving', 'Shooter'].map((preset) {
          final active = selected == preset;
          return Expanded(
            child: Material(
              color: active ? const Color(0xFF304B79) : Colors.transparent,
              borderRadius: BorderRadius.circular(11),
              child: InkWell(
                onTap: () => onChanged(preset),
                borderRadius: BorderRadius.circular(11),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 11),
                  child: Text(
                    preset,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: active ? Colors.white : const Color(0xFF879AB5),
                      fontSize: 10,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _HoldButton extends StatefulWidget {
  const _HoldButton({
    required this.label,
    required this.onChanged,
    this.compact = false,
  });

  final String label;
  final ValueChanged<bool> onChanged;
  final bool compact;

  @override
  State<_HoldButton> createState() => _HoldButtonState();
}

class _HoldButtonState extends State<_HoldButton> {
  final Set<int> _pointers = {};
  bool _pressed = false;

  void _press(PointerEvent event) {
    if (!_pointers.add(event.pointer)) return;
    if (!_pressed) {
      setState(() => _pressed = true);
      widget.onChanged(true);
    }
  }

  void _release(PointerEvent event) {
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
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.opaque,
      onPointerDown: _press,
      onPointerUp: _release,
      onPointerCancel: _release,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 90),
        constraints: BoxConstraints(minHeight: widget.compact ? 38 : 44),
        padding: EdgeInsets.symmetric(
          horizontal: widget.compact ? 14 : 10,
          vertical: 9,
        ),
        decoration: BoxDecoration(
          color: _pressed ? const Color(0xFF365987) : const Color(0xFF1B2D46),
          borderRadius: BorderRadius.circular(widget.compact ? 10 : 13),
          border: Border.all(
            color: _pressed ? const Color(0xFF8FB5FF) : const Color(0xFF3B5475),
          ),
          boxShadow: _pressed
              ? const [BoxShadow(color: Color(0x335D91FF), blurRadius: 12)]
              : const [],
        ),
        child: Center(
          child: Text(
            widget.label,
            style: TextStyle(
              color: _pressed ? Colors.white : const Color(0xFFD7E3F4),
              fontSize: widget.compact ? 9 : 11,
              fontWeight: FontWeight.w900,
              letterSpacing: .5,
            ),
          ),
        ),
      ),
    );
  }
}

class _TiltSteeringCard extends StatelessWidget {
  const _TiltSteeringCard({
    required this.enabled,
    required this.status,
    required this.sensitivity,
    required this.onToggle,
    required this.onCalibrate,
    required this.onSensitivityChanged,
  });

  final bool enabled;
  final String status;
  final double sensitivity;
  final ValueChanged<bool> onToggle;
  final VoidCallback onCalibrate;
  final ValueChanged<double> onSensitivityChanged;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF101A2A),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: const Color(0xFF293B56)),
        ),
        child: Column(
          children: [
            SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              value: enabled,
              onChanged: onToggle,
              title: const Text('Tilt steering', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800)),
              activeColor: const Color(0xFF6B96FF),
            ),
            Row(
              children: [
                Expanded(child: Text(status, style: const TextStyle(color: Color(0xFF94A5BE), fontSize: 10))),
                TextButton(onPressed: enabled ? onCalibrate : null, child: const Text('Calibrate')),
              ],
            ),
            Row(
              children: [
                const Expanded(child: Text('Sensitivity', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700))),
                Text(sensitivity.toStringAsFixed(1) + '×', style: const TextStyle(color: Color(0xFF8AB0FF), fontSize: 10)),
              ],
            ),
            Slider(min: .5, max: 2.5, value: sensitivity, onChanged: enabled ? onSensitivityChanged : null),
          ],
        ),
      );
}

class _TriggerControl extends StatelessWidget {
  const _TriggerControl({
    required this.label,
    required this.value,
    required this.onChanged,
    this.digital = false,
  });

  final String label;
  final double value;
  final ValueChanged<double> onChanged;
  final bool digital;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: Color(0xFF8196B5), fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: .7)),
          if (digital)
            _HoldButton(
              label: 'HOLD TRIGGER',
              onChanged: (pressed) => onChanged(pressed ? 255 : 0),
            )
          else
            Slider(min: 0, max: 255, divisions: 255, value: value, onChanged: onChanged),
        ],
      );
}

class _AnalogStick extends StatefulWidget {
  const _AnalogStick({
    required this.label,
    required this.size,
    required this.onChanged,
  });

  final String label;
  final double size;
  final void Function(double x, double y) onChanged;

  @override
  State<_AnalogStick> createState() => _AnalogStickState();
}

class _AnalogStickState extends State<_AnalogStick> {
  int? _pointer;
  double _x = 0;
  double _y = 0;

  void _update(PointerEvent event) {
    final box = context.findRenderObject() as RenderBox?;
    if (box == null) return;
    final local = box.globalToLocal(event.position);
    final center = Offset(box.size.width / 2, box.size.height / 2);
    final radius = math.min(box.size.width, box.size.height) * .37;
    var x = (local.dx - center.dx) / radius;
    var y = (local.dy - center.dy) / radius;
    final length = math.sqrt(x * x + y * y);
    if (length > 1) {
      x /= length;
      y /= length;
    }
    setState(() {
      _x = x;
      _y = y;
    });
    widget.onChanged(x, y);
  }

  void _release(PointerEvent event) {
    if (_pointer != event.pointer) return;
    _pointer = null;
    setState(() {
      _x = 0;
      _y = 0;
    });
    widget.onChanged(0, 0);
  }

  @override
  void dispose() {
    widget.onChanged(0, 0);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(widget.label, style: const TextStyle(color: Color(0xFF8196B5), fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: .7)),
        const SizedBox(height: 8),
        SizedBox(
          width: widget.size,
          height: widget.size,
          child: Listener(
            behavior: HitTestBehavior.opaque,
            onPointerDown: (event) {
              if (_pointer != null) return;
              _pointer = event.pointer;
              _update(event);
            },
            onPointerMove: (event) {
              if (_pointer == event.pointer) _update(event);
            },
            onPointerUp: _release,
            onPointerCancel: _release,
            child: DecoratedBox(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF0A1320),
                border: Border.all(color: const Color(0xFF3C567A), width: 2),
                boxShadow: const [BoxShadow(color: Color(0x55000000), blurRadius: 14, offset: Offset(0, 5))],
              ),
              child: Align(
                alignment: Alignment(_x * .68, _y * .68),
                child: Container(
                  width: widget.size * .34,
                  height: widget.size * .34,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: const LinearGradient(
                      colors: [Color(0xFF789BC9), Color(0xFF293E5F)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    border: Border.all(color: const Color(0xFF9DB9E4), width: 1.2),
                    boxShadow: const [BoxShadow(color: Color(0x88000000), blurRadius: 10, offset: Offset(0, 4))],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _Dpad extends StatelessWidget {
  const _Dpad({required this.onChanged});
  final void Function(String key, bool pressed) onChanged;

  @override
  Widget build(BuildContext context) {
    Widget button(String label, String key) => SizedBox(
          width: 40,
          height: 39,
          child: _HoldButton(
            label: label,
            compact: true,
            onChanged: (pressed) => onChanged(key, pressed),
          ),
        );

    return Column(
      children: [
        const Text('D-PAD', style: TextStyle(color: Color(0xFF8196B5), fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: .7)),
        const SizedBox(height: 7),
        button('▲', 'DPAD_UP'),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            button('◀', 'DPAD_LEFT'),
            const SizedBox(width: 4),
            Container(
              width: 30,
              height: 30,
              decoration: const BoxDecoration(color: Color(0xFF1C2B41), shape: BoxShape.circle),
              child: const Icon(Icons.add, color: Color(0xFF6D84A5), size: 17),
            ),
            const SizedBox(width: 4),
            button('▶', 'DPAD_RIGHT'),
          ],
        ),
        button('▼', 'DPAD_DOWN'),
      ],
    );
  }
}

class _FacePad extends StatelessWidget {
  const _FacePad({required this.playStation, required this.onChanged});

  final bool playStation;
  final void Function(String key, bool pressed) onChanged;

  @override
  Widget build(BuildContext context) {
    final labels = playStation
        ? const {'Y': '△', 'X': '□', 'B': '○', 'A': '×'}
        : const {'Y': 'Y', 'X': 'X', 'B': 'B', 'A': 'A'};

    Widget button(String key, Color color) => SizedBox(
          width: 43,
          height: 43,
          child: _FaceButton(
            label: labels[key]!,
            color: color,
            onChanged: (pressed) => onChanged(key, pressed),
          ),
        );

    return Column(
      children: [
        const Text('ACTION BUTTONS', style: TextStyle(color: Color(0xFF8196B5), fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: .7)),
        const SizedBox(height: 7),
        button('Y', const Color(0xFFE6C36D)),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            button('X', const Color(0xFF9E91F0)),
            const SizedBox(width: 18),
            button('B', const Color(0xFFEF8DA3)),
          ],
        ),
        button('A', const Color(0xFF69D8B0)),
      ],
    );
  }
}

class _FaceButton extends StatefulWidget {
  const _FaceButton({required this.label, required this.color, required this.onChanged});

  final String label;
  final Color color;
  final ValueChanged<bool> onChanged;

  @override
  State<_FaceButton> createState() => _FaceButtonState();
}

class _FaceButtonState extends State<_FaceButton> {
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
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: _pressed ? widget.color.withOpacity(.48) : widget.color.withOpacity(.15),
            border: Border.all(color: widget.color, width: _pressed ? 2.4 : 1.3),
            boxShadow: _pressed ? [BoxShadow(color: widget.color.withOpacity(.3), blurRadius: 12)] : const [],
          ),
          child: Center(
            child: Text(
              widget.label,
              style: TextStyle(color: widget.color, fontWeight: FontWeight.w900, fontSize: 14),
            ),
          ),
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
  const _Notice(this.message, {this.warning = false});
  final String message;
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
          Icon(warning ? Icons.info_outline_rounded : Icons.touch_app_rounded, color: color, size: 17),
          const SizedBox(width: 9),
          Expanded(child: Text(message, style: const TextStyle(color: Color(0xFFB5C4D9), fontSize: 10, height: 1.45))),
        ],
      ),
    );
  }
}
