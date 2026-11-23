import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/pairing_target.dart';

class PairingException implements Exception {
  const PairingException(this.message);
  final String message;

  @override
  String toString() => message;
}

class PairedSession {
  const PairedSession({
    required this.baseUri,
    required this.token,
    required this.deviceName,
    required this.fingerprint,
    required this.gamepadAvailable,
  });

  final Uri baseUri;
  final String token;
  final String deviceName;
  final String fingerprint;
  final bool gamepadAvailable;
}

class PairingService {
  PairingService({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  Future<String> discoverFingerprint(Uri baseUri) async {
    final client = _newClient();
    String? observedFingerprint;

    // This public identity request contains no pairing credentials.
    client.badCertificateCallback = (certificate, host, port) {
      observedFingerprint = sha256.convert(certificate.der).toString();
      return true;
    };

    try {
      final info = await _readInfo(client, baseUri);
      final reported = normalizeFingerprint((info['fingerprint'] ?? '').toString());
      if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(reported)) {
        throw const PairingException('The PC did not provide a valid TLS fingerprint.');
      }
      if (info['secure'] != true) {
        throw const PairingException('The desktop companion is not using HTTPS.');
      }
      if (observedFingerprint != null &&
          normalizeFingerprint(observedFingerprint!) != reported) {
        throw const PairingException('The presented TLS certificate does not match the PC fingerprint.');
      }
      return reported;
    } on PairingException {
      rethrow;
    } on SocketException {
      throw const PairingException('Could not reach the PC. Check the address, port, firewall, and Wi-Fi network.');
    } on HandshakeException {
      throw const PairingException('The TLS handshake failed. Check that VPadConnect is running on the PC.');
    } on HttpException {
      throw const PairingException('The PC returned an invalid HTTP response.');
    } on FormatException {
      throw const PairingException('The PC returned an invalid server identity.');
    } catch (error) {
      throw PairingException('Could not read the PC identity: $error');
    } finally {
      client.close(force: true);
    }
  }

  Future<PairedSession> pair({
    required PairingTarget target,
    required String deviceName,
  }) async {
    final fingerprint = normalizeFingerprint(target.fingerprint ?? '');
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(fingerprint)) {
      throw const PairingException('A verified certificate fingerprint is required before pairing.');
    }

    final client = _newClient();
    client.badCertificateCallback = (certificate, host, port) {
      final actual = sha256.convert(certificate.der).toString();
      return normalizeFingerprint(actual) == fingerprint;
    };

    try {
      final info = await _readInfo(client, target.baseUri);
      final reported = normalizeFingerprint((info['fingerprint'] ?? '').toString());
      if (reported != fingerprint || info['secure'] != true) {
        throw const PairingException('TLS fingerprint verification failed. Pairing was stopped.');
      }

      final installationId = await _installationId();
      final request = await client.postUrl(_endpoint(target.baseUri, '/api/pair'));
      request.headers.contentType = ContentType.json;
      request.headers.set(HttpHeaders.cacheControlHeader, 'no-store');
      request.add(utf8.encode(jsonEncode({
        'code': target.code,
        'name': deviceName.trim().isEmpty ? 'VPadConnect Mobile' : deviceName.trim(),
        'device_id': installationId,
      })));

      final response = await request.close().timeout(const Duration(seconds: 12));
      final body = await response.transform(utf8.decoder).join();
      final data = _decodeObject(body);
      if (response.statusCode < 200 || response.statusCode >= 300 || data['ok'] != true) {
        throw PairingException(
          '${data['error'] ?? 'Pairing failed.'} (HTTP ${response.statusCode})',
        );
      }

      final token = data['token'];
      if (token is! String || token.isEmpty) {
        throw const PairingException('The PC did not return a valid session token.');
      }

      return PairedSession(
        baseUri: target.baseUri,
        token: token,
        deviceName: (data['name'] ?? deviceName).toString(),
        fingerprint: fingerprint,
        gamepadAvailable: data['gamepad_available'] != false,
      );
    } on PairingException {
      rethrow;
    } on SocketException {
      throw const PairingException('Could not reach the PC. Check the address, port, firewall, and Wi-Fi network.');
    } on HandshakeException {
      throw const PairingException('The PC certificate did not match the verified fingerprint.');
    } on HttpException {
      throw const PairingException('The PC returned an invalid HTTP response.');
    } on FormatException {
      throw const PairingException('The PC returned an invalid pairing response.');
    } catch (error) {
      throw PairingException('Pairing failed: $error');
    } finally {
      client.close(force: true);
    }
  }

  Future<void> disconnect(PairedSession session) async {
    final client = _newClient();
    final fingerprint = normalizeFingerprint(session.fingerprint);
    client.badCertificateCallback = (certificate, host, port) {
      return normalizeFingerprint(sha256.convert(certificate.der).toString()) == fingerprint;
    };

    try {
      final request = await client.postUrl(_endpoint(session.baseUri, '/api/disconnect'));
      request.headers.contentType = ContentType.json;
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer ${session.token}');
      request.add(utf8.encode('{}'));
      await request.close().timeout(const Duration(seconds: 5));
    } catch (_) {
      // The server may already have stopped; the local session still ends.
    } finally {
      client.close(force: true);
    }
  }

  HttpClient _newClient() {
    return HttpClient()
      ..connectionTimeout = const Duration(seconds: 6)
      ..idleTimeout = const Duration(seconds: 5);
  }

  Uri _endpoint(Uri baseUri, String path) {
    return baseUri.replace(path: path, query: null, fragment: null);
  }

  Future<Map<String, dynamic>> _readInfo(HttpClient client, Uri baseUri) async {
    final request = await client.getUrl(_endpoint(baseUri, '/api/info'));
    request.headers.set(HttpHeaders.cacheControlHeader, 'no-store');
    final response = await request.close().timeout(const Duration(seconds: 10));
    final body = await response.transform(utf8.decoder).join();
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw PairingException(
        'Could not read the PC identity (HTTP ${response.statusCode}).',
      );
    }
    return _decodeObject(body);
  }

  Map<String, dynamic> _decodeObject(String body) {
    final value = jsonDecode(body);
    if (value is! Map<String, dynamic>) {
      throw const FormatException('Expected a JSON object.');
    }
    return value;
  }

  Future<String> _installationId() async {
    const key = 'vpadconnect.installation_id';
    final existing = await _storage.read(key: key);
    if (existing != null && RegExp(r'^[a-f0-9]{32}$').hasMatch(existing)) {
      return existing;
    }

    final random = Random.secure();
    final generated = List<int>.generate(16, (_) => random.nextInt(256))
        .map((value) => value.toRadixString(16).padLeft(2, '0'))
        .join();
    await _storage.write(key: key, value: generated);
    return generated;
  }
}
