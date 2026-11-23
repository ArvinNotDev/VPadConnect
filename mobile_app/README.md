# VPadConnect Mobile

Native Flutter companion for the VPadConnect Windows application.

## Current milestone

The first milestone establishes the UX blueprint, Material 3 theme, secure QR/manual pairing, and connected navigation shell. Live gamepad streaming, touchpad gestures, motion controls, and PC Remote actions are implemented in later focused phases.

## Requirements

- Flutter SDK with Dart 3.8 or newer.
- Android SDK / Android Studio toolchain.
- Android 6.0 (API 23) or newer, required by the selected secure-storage package.
- Android build tools compatible with `sensors_plus` 7.1.1 (Java 17, Kotlin 2.2, AGP 8.12.1, Gradle 8.13).

## Generate Android platform files

The Flutter SDK is not bundled in this repository environment. From this directory, generate the standard Android runner files once:

    flutter create --platforms=android --project-name vpadconnect_mobile .

Then resolve dependencies:

    flutter pub get

The command should preserve the existing lib/ source and pubspec.yaml. Review generated Gradle and manifest files before committing them.

## Run and analyze

    flutter analyze
    flutter test
    flutter run

## Pairing behavior

The desktop Web Companion must be running on the Windows PC. The phone and PC should be on the same trusted LAN.

- QR pairing reads the existing desktop pairing URL and pins its SHA-256 TLS certificate fingerprint.
- Manual pairing accepts a host and six-digit code, discovers the fingerprint through the public /api/info endpoint, and requires explicit fingerprint comparison before sending the pairing code.
- The client never disables TLS validation for authenticated pairing requests.
