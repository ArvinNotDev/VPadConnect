import 'package:flutter_test/flutter_test.dart';
import 'package:vpadconnect_mobile/models/pairing_target.dart';

void main() {
  group('PairingTarget', () {
    const fingerprint = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

    test('parses the existing VPadConnect pairing URL fragment', () {
      final target = PairingTarget.fromQr(
        'https://192.168.1.20:8765/#pair=123456&fp=$fingerprint',
      );

      expect(target.baseUri.scheme, 'https');
      expect(target.baseUri.host, '192.168.1.20');
      expect(target.baseUri.port, 8765);
      expect(target.code, '123456');
      expect(target.fingerprint, fingerprint);
    });

    test('normalizes manually entered host and defaults the port', () {
      final target = PairingTarget.fromManual(
        address: '192.168.1.20',
        code: '654321',
      );

      expect(target.baseUri.toString(), 'https://192.168.1.20:8765');
      expect(target.code, '654321');
    });

    test('rejects HTTP QR pairing URLs', () {
      expect(
        () => PairingTarget.fromQr(
          'http://192.168.1.20:8765/#pair=123456&fp=$fingerprint',
        ),
        throwsFormatException,
      );
    });

    test('rejects a QR code with a malformed fingerprint', () {
      expect(
        () => PairingTarget.fromQr(
          'https://192.168.1.20:8765/#pair=123456&fp=1234',
        ),
        throwsFormatException,
      );
    });

    test('rejects pairing codes that are not six digits', () {
      expect(
        () => PairingTarget.fromManual(
          address: '192.168.1.20:8765',
          code: '12345',
        ),
        throwsFormatException,
      );
    });
  });
}
