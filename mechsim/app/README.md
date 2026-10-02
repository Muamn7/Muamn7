# MechSim 2D — the Flutter app

The interface of MechSim 2D. All mechanics live in [`../core`](../core); this
package draws, edits, links and explains. See [`../README.md`](../README.md)
for the project, its architecture and how to build it.

```bash
flutter pub get
flutter test                 # widget tests
flutter run                  # on a phone, an emulator, Linux or Windows
flutter build apk --release  # Android
```

Screenshots of every main screen can be rendered without a device:

```bash
MECHSIM_SHOTS=/tmp/shots flutter test test/screenshots_test.dart
```
