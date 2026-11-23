class PairingTarget {
  const PairingTarget({
    required this.baseUri,
    required this.code,
    this.fingerprint,
  });

  final Uri baseUri;
  final String code;
  final String? fingerprint;

  PairingTarget withFingerprint(String value) => PairingTarget(
        baseUri: baseUri,
        code: code,
        fingerprint: normalizeFingerprint(value),
      );

  factory PairingTarget.fromQr(String rawValue) {
    final uri = Uri.tryParse(rawValue.trim());
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      throw const FormatException('This is not a valid VPadConnect HTTPS pairing QR code.');
    }
    if (uri.userInfo.isNotEmpty ||
        (uri.path.isNotEmpty && uri.path != '/') ||
        uri.hasQuery) {
      throw const FormatException('The QR code contains an unsupported connection URL.');
    }

    final fragment = Uri.splitQueryString(uri.fragment);
    final code = fragment['pair'] ?? '';
    final fingerprint = normalizeFingerprint(fragment['fp'] ?? '');
    if (!RegExp(r'^\d{6}$').hasMatch(code)) {
      throw const FormatException('The QR code does not contain a valid six-digit pairing code.');
    }
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(fingerprint)) {
      throw const FormatException('The QR code does not contain a valid SHA-256 certificate fingerprint.');
    }

    return PairingTarget(
      baseUri: _normalizeBaseUri(uri),
      code: code,
      fingerprint: fingerprint,
    );
  }

  factory PairingTarget.fromManual({
    required String address,
    required String code,
  }) {
    final normalizedCode = code.trim();
    if (!RegExp(r'^\d{6}$').hasMatch(normalizedCode)) {
      throw const FormatException('Enter the six-digit code displayed on the PC.');
    }

    var input = address.trim();
    if (input.isEmpty) {
      throw const FormatException('Enter the PC address shown by VPadConnect.');
    }
    if (!input.contains('://')) {
      input = 'https://$input';
    }

    final uri = Uri.tryParse(input);
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      throw const FormatException('Enter a valid HTTPS address, including the PC port.');
    }
    if (uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      throw const FormatException('Enter only the PC host and optional port, without a path or query.');
    }

    return PairingTarget(
      baseUri: _normalizeBaseUri(uri),
      code: normalizedCode,
    );
  }

  static Uri _normalizeBaseUri(Uri uri) {
    return uri.replace(
      port: uri.hasPort ? uri.port : 8765,
      path: '',
      query: '',
      fragment: '',
    );
  }
}

String normalizeFingerprint(String value) {
  return value.toLowerCase().replaceAll(RegExp(r'[:\s-]'), '');
}

String formatFingerprint(String value) {
  final normalized = normalizeFingerprint(value);
  return RegExp(r'.{1,4}')
      .allMatches(normalized.toUpperCase())
      .map((match) => match.group(0)!)
      .join(' ');
}
