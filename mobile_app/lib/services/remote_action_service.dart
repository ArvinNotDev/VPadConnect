import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';

import 'pairing_service.dart';

class RemoteActionException implements Exception {
  const RemoteActionException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class RemoteActionService {
  RemoteActionService(this.session);

  final PairedSession session;
  HttpClient? _client;
  bool _identityVerified = false;
  final Random _random = Random.secure();

  HttpClient _getClient() {
    final existing = _client;
    if (existing != null) return existing;

    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 6)
      ..idleTimeout = const Duration(seconds: 20)
      ..badCertificateCallback = (certificate, host, port) {
        final actual = sha256.convert(certificate.der).toString();
        return _normalize(actual) == _normalize(session.fingerprint);
      };
    _client = client;
    return client;
  }

  String _normalize(String value) =>
      value.toLowerCase().replaceAll(RegExp(r'[:\s-]'), '');

  Uri _endpoint(String path) =>
      session.baseUri.replace(path: path, query: '', fragment: '');

  Future<void> _verifyIdentity() async {
    if (_identityVerified) return;
    final request = await _getClient().getUrl(_endpoint('/api/info'));
    request.headers.set(HttpHeaders.cacheControlHeader, 'no-store');
    final response = await request.close().timeout(const Duration(seconds: 8));
    final body = await response.transform(utf8.decoder).join();
    final decoded = jsonDecode(body);
    if (decoded is! Map<String, dynamic> || response.statusCode != 200) {
      throw const RemoteActionException('Could not verify the connected PC.');
    }

    final fingerprint = _normalize((decoded['fingerprint'] ?? '').toString());
    if (decoded['secure'] != true ||
        fingerprint != _normalize(session.fingerprint)) {
      throw const RemoteActionException('The PC certificate changed. Disconnect and pair again.');
    }
    _identityVerified = true;
  }

  Future<Map<String, dynamic>> send(
    String action, [
    Map<String, dynamic> payload = const {},
  ]) async {
    try {
      await _verifyIdentity();
      final request = await _getClient().postUrl(_endpoint('/api/action'));
      request.headers.contentType = ContentType.json;
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer ' + session.token);
      request.headers.set(HttpHeaders.cacheControlHeader, 'no-store');
      final requestId = 'mobile_' +
          List<int>.generate(12, (_) => _random.nextInt(16))
              .map((value) => value.toRadixString(16))
              .join();
      request.add(utf8.encode(jsonEncode({
        'request_id': requestId,
        'action': action,
        'payload': payload,
      })));

      final response = await request.close().timeout(const Duration(seconds: 12));
      final body = await response.transform(utf8.decoder).join();
      final decoded = jsonDecode(body);
      if (decoded is! Map<String, dynamic>) {
        throw const RemoteActionException('The PC returned an invalid response.');
      }
      if (response.statusCode < 200 ||
          response.statusCode >= 300 ||
          decoded['ok'] != true) {
        throw RemoteActionException(
          (decoded['error'] ?? 'The desktop action failed.').toString(),
          statusCode: response.statusCode,
        );
      }

      final result = decoded['result'];
      return result is Map<String, dynamic> ? result : <String, dynamic>{};
    } on RemoteActionException {
      rethrow;
    } on SocketException {
      throw const RemoteActionException('Could not reach the PC. Check the local network connection.');
    } on HandshakeException {
      throw const RemoteActionException('The PC certificate changed. Disconnect and pair again.');
    } on FormatException {
      throw const RemoteActionException('The PC returned an invalid response.');
    } catch (error) {
      throw RemoteActionException('Remote action failed: ' + error.toString());
    }
  }

  Future<void> dispose() async {
    _client?.close(force: true);
    _client = null;
  }
}
