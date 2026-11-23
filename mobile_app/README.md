# VPadConnect Mobile

Native Flutter companion for the VPadConnect Windows application.

## Implemented

- QR scanning using the existing desktop pairing URL.
- Manual PC address and six-digit code entry.
- SHA-256 TLS certificate fingerprint verification and explicit comparison during manual pairing.
- Secure random installation identifier and in-memory paired session token.
- Shared authenticated WebSocket transport for gamepad and touchpad input, with 16 ms state coalescing, heartbeat, reconnect, and release-on-exit behavior.
- Multi-touch virtual controller with Xbox/PlayStation labels, Standard/Driving/Shooter presets, analog triggers, and gyro steering.
- Touchpad pointer movement, click gestures, two-finger scrolling, and optional gyroscope Air Mouse.
- Permission-aware PC Remote actions for keyboard, clipboard, media, quick launch, presentation, and power operations.
- Dark Material 3 interface and five-area mobile navigation.

## Requirements

- Flutter stable with Dart 3.8 or newer.
- Android SDK / Android Studio toolchain.
- Android 6.0 (API 23) or newer.
- Java 17, Kotlin 2.2, Android Gradle Plugin 8.12.1, and Gradle 8.13 for sensors_plus 7.1.1.

## Generate Android platform files

The Flutter SDK was not available in the source-editing environment, so the standard Android runner files are not generated in this commit. From this directory, generate them once:

    flutter create --platforms=android --project-name vpadconnect_mobile .

Then resolve dependencies:

    flutter pub get

Review android/app/src/main/AndroidManifest.xml and make sure INTERNET and CAMERA permissions are present. mobile_scanner requests camera access at runtime; handle camera denial and retain manual pairing as a fallback.

## Analyze, test, and build

    dart format lib test
    flutter analyze
    flutter test
    flutter build apk --release

The generated APK is normally written to build/app/outputs/flutter-apk/app-release.apk.

## Pairing behavior

The desktop Web Companion must be running on the Windows PC. The phone and PC should be on the same trusted LAN.

- QR pairing reads the existing desktop URL fragment and uses its SHA-256 fingerprint to pin the server certificate.
- Manual pairing accepts a host and six-digit code, discovers the certificate fingerprint through the public /api/info endpoint, and requires an explicit comparison with the desktop UI before sending the pairing code.
- Authenticated actions use the existing /api/action endpoint and its desktop permission model. Gamepad and touchpad state use the authenticated /api/stream WebSocket endpoint.

## Validation still required

This repository environment did not have the Flutter SDK or an Android device/emulator available. The Flutter analyzer, unit tests, APK build, camera permission flow, and real-device input latency have not yet been executed here. Run the commands above and complete device testing before distributing an APK.
