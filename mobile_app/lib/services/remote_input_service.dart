import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

import 'pairing_service.dart';

class RemoteInputService {
  RemoteInputService(this.session);

  final PairedSession session;
  final ValueNotifier<String> status = ValueNotifier<String>('Connecting');
  final ValueNotifier<bool> connected = ValueNotifier<bool>(false);

  WebSocket? _socket;
  HttpClient? _client;
  StreamSubscription<dynamic>? _subscription;
  Timer? _flushTimer;
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;
  bool _disposed = false;
  bool _connecting = false;
  bool _dirty = false;
  bool _sessionEnded = false;
  DateTime _lastPong = DateTime.now();
  String _mode = 'gamepad';

  final Map<String, int> _buttons = {
    for (final key in const [
      'A', 'B', 'X', 'Y', 'LB', 'RB', 'BACK', 'START', 'GUIDE',
      'L3', 'R3', 'DPAD_UP', 'DPAD_DOWN', 'DPAD_LEFT', 'DPAD_RIGHT',
    ]) key: 0,
  };
  final Map<String, int> _analog = {'L2': 0, 'R2': 0};
  final Map<String, int> _joystick = {
    'left_x': 128, 'left_y': 128, 'right_x': 128, 'right_y': 128,
  };
  final Map<String, int> _mouse = {
    'dx': 0, 'dy': 0, 'scroll': 0, 'left': 0, 'right': 0, 'middle': 0,
  };

  Future<void> connect() async {
    if (_disposed || _sessionEnded || _connecting || connected.value) return;
    _connecting = true;
    status.value = 'Connecting';
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 6)
      ..idleTimeout = const Duration(seconds: 0);
    final fingerprint = session.fingerprint;
    client.badCertificateCallback = (certificate, host, port) {
      final actual = sha256.convert(certificate.der).toString();
      return _normalize(actual) == _normalize(fingerprint);
    };
    _client = client;

    try {
      final wsUri = session.baseUri.replace(
        scheme: 'wss',
        path: '/api/stream',
        query: '',
        fragment: '',
      );
      final socket = await WebSocket.connect(
        wsUri.toString(),
        customClient: client,
      ).timeout(const Duration(seconds: 10));
      if (_disposed) {
        await socket.close();
        client.close(force: true);
        return;
      }

      _socket = socket;
      final ready = Completer<void>();
      _subscription = socket.listen(
        (message) {
          _handleMessage(message, ready);
        },
        onError: (Object error) {
          if (!ready.isCompleted) {
            ready.completeError(error);
          }
          _handleClosed(error.toString());
        },
        onDone: () => _handleClosed('Connection closed'),
        cancelOnError: true,
      );

      socket.add(jsonEncode({'type': 'auth', 'token': session.token}));
      await ready.future.timeout(const Duration(seconds: 6));
      if (_disposed) return;

      connected.value = true;
      status.value = 'Connected';
      _lastPong = DateTime.now();
      _heartbeatTimer?.cancel();
      _heartbeatTimer = Timer.periodic(const Duration(seconds: 3), (_) {
        _sendHeartbeat();
      });
      _scheduleFlush();
    } catch (error) {
      _handleClosed(error.toString());
      _scheduleReconnect();
    } finally {
      _connecting = false;
    }
  }

  void _handleMessage(dynamic message, Completer<void> ready) {
    if (message is! String) return;
    Map<String, dynamic> packet;
    try {
      final decoded = jsonDecode(message);
      if (decoded is! Map<String, dynamic>) return;
      packet = decoded;
    } on FormatException {
      return;
    }

    if (packet['type'] == 'ready') {
      if (!ready.isCompleted) ready.complete();
      return;
    }
    if (packet['type'] == 'pong') {
      _lastPong = DateTime.now();
      return;
    }
    if (packet['type'] == 'error') {
      final reason = packet['error']?.toString() ?? 'Remote session error';
      if (reason == 'session_expired' || reason == 'server_shutdown') {
        _sessionEnded = true;
        status.value = reason == 'session_expired' ? 'Session expired' : 'Desktop stopped';
      }
      if (!ready.isCompleted) {
        ready.completeError(StateError(reason));
      }
    }
  }

  void _handleClosed(String reason) {
    if (_disposed) return;
    connected.value = false;
    status.value = _sessionEnded ? 'Session expired' : 'Reconnecting';
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _flushTimer?.cancel();
    _flushTimer = null;
    _subscription = null;
    _socket = null;
    _client?.close(force: true);
    _client = null;
    _resetInput();
    if (!_sessionEnded) _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_disposed || _sessionEnded || _reconnectTimer != null) return;
    status.value = 'Reconnecting';
    _reconnectTimer = Timer(const Duration(seconds: 5), () {
      _reconnectTimer = null;
      connect();
    });
  }

  void _sendHeartbeat() {
    final socket = _socket;
    if (socket == null || socket.readyState != WebSocket.open) return;
    if (DateTime.now().difference(_lastPong) > const Duration(seconds: 10)) {
      socket.close();
      return;
    }
    try {
      socket.add(jsonEncode({'type': 'ping'}));
    } catch (_) {
      socket.close();
    }
  }

  void setMode(String mode) {
    _mode = mode == 'mouse' ? 'mouse' : 'gamepad';
    _scheduleFlush();
  }

  void setButton(String key, bool pressed) {
    if (!_buttons.containsKey(key)) return;
    _mode = 'gamepad';
    _buttons[key] = pressed ? 1 : 0;
    _scheduleFlush();
  }

  void setAnalog(String key, double value) {
    if (!_analog.containsKey(key)) return;
    _mode = 'gamepad';
    _analog[key] = value.round().clamp(0, 255).toInt();
    _scheduleFlush();
  }

  void setStick(String stick, double x, double y) {
    if (stick != 'left' && stick != 'right') return;
    _mode = 'gamepad';
    _joystick[stick + '_x'] = (128 + x.clamp(-1.0, 1.0) * 127).round().clamp(0, 255).toInt();
    _joystick[stick + '_y'] = (128 + y.clamp(-1.0, 1.0) * 127).round().clamp(0, 255).toInt();
    _scheduleFlush();
  }

  void moveMouse(double dx, double dy) {
    _mode = 'mouse';
    _mouse['dx'] = (_mouse['dx']! + dx.round()).clamp(-2048, 2048).toInt();
    _mouse['dy'] = (_mouse['dy']! + dy.round()).clamp(-2048, 2048).toInt();
    _scheduleFlush();
  }

  void setMouseButton(String key, bool pressed) {
    if (!const {'left', 'right', 'middle'}.contains(key)) return;
    _mode = 'mouse';
    _mouse[key] = pressed ? 1 : 0;
    _scheduleFlush();
  }

  void scroll(int amount) {
    _mode = 'mouse';
    _mouse['scroll'] = (_mouse['scroll']! + amount).clamp(-20, 20).toInt();
    _scheduleFlush();
  }

  void releaseAll() {
    _resetInput();
    _scheduleFlush();
  }

  void _resetInput() {
    for (final key in _buttons.keys) {
      _buttons[key] = 0;
    }
    for (final key in _analog.keys) {
      _analog[key] = 0;
    }
    for (final key in _joystick.keys) {
      _joystick[key] = 128;
    }
    for (final key in _mouse.keys) {
      _mouse[key] = 0;
    }
    _mode = 'gamepad';
    _dirty = true;
  }

  void _scheduleFlush() {
    _dirty = true;
    if (_flushTimer != null || _disposed) return;
    _flushTimer = Timer(const Duration(milliseconds: 16), _flush);
  }

  void _flush() {
    _flushTimer = null;
    final socket = _socket;
    if (!_dirty || socket == null || socket.readyState != WebSocket.open) return;
    final payload = {
      'mode': _mode,
      'buttons': Map<String, int>.from(_buttons),
      'analog': Map<String, int>.from(_analog),
      'joystick': Map<String, int>.from(_joystick),
      'mouse': Map<String, int>.from(_mouse),
    };

    // Relative pointer movement and scroll are consumed once, not replayed.
    _mouse['dx'] = 0;
    _mouse['dy'] = 0;
    _mouse['scroll'] = 0;
    _dirty = false;
    try {
      socket.add(jsonEncode({'type': 'state', 'state': payload}));
    } catch (_) {
      socket.close();
    }
  }

  String _normalize(String value) {
    return value.toLowerCase().replaceAll(RegExp(r'[:\s-]'), '');
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    _reconnectTimer?.cancel();
    _heartbeatTimer?.cancel();
    _flushTimer?.cancel();

    final socket = _socket;
    _socket = null;
    connected.value = false;
    status.value = 'Disconnected';
    _subscription?.cancel();
    _subscription = null;

    if (socket != null && socket.readyState == WebSocket.open) {
      try {
        socket.add(jsonEncode({
          'type': 'state',
          'state': {
            'mode': 'gamepad',
            'buttons': {for (final key in _buttons.keys) key: 0},
            'analog': {'L2': 0, 'R2': 0},
            'joystick': {
              'left_x': 128, 'left_y': 128, 'right_x': 128, 'right_y': 128,
            },
            'mouse': {
              'dx': 0, 'dy': 0, 'scroll': 0, 'left': 0, 'right': 0, 'middle': 0,
            },
          },
        }));
        await Future<void>.delayed(const Duration(milliseconds: 20));
        await socket.close();
      } catch (_) {
        // Closing the server stream also releases all held input.
      }
    }
    _client?.close(force: true);
    _client = null;
    status.dispose();
    connected.dispose();
  }
}
