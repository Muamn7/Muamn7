import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mechsim/app.dart';
import 'package:mechsim/drawing/symbols.dart';
import 'package:mechsim/state/app_state.dart';
import 'package:mechsim_core/mechsim_core.dart';

AppState testState({AppSettings settings = const AppSettings()}) => AppState(
  settings: settings,
  repository: InMemoryProblemRepository(),
  settingsStore: MemorySettingsStore(),
);

/// A phone-sized test window (412 × 892 logical pixels).
void phoneSize(WidgetTester tester, {Size logical = const Size(412, 892)}) {
  tester.view.devicePixelRatio = 2.0;
  tester.view.physicalSize = logical * 2.0;
  addTearDown(tester.view.reset);
}

Future<Widget> app(AppState state, {Widget? home}) async =>
    RepaintBoundary(key: shotKey, child: MechSimApp(state: state, home: home));

final shotKey = GlobalKey();

/// Real fonts, so screenshots show text instead of the test font's boxes:
/// Roboto and the Material icons from the Flutter SDK, DejaVu Sans for
/// Arabic. Returns false when they cannot be found.
Future<bool> loadRealFonts() async {
  final engine = File(Platform.resolvedExecutable).parent; // …/engine/linux-x64
  final artifacts = engine.parent.parent; // …/bin/cache/artifacts
  final material = Directory('${artifacts.path}/material_fonts');
  const dejavu = '/usr/share/fonts/truetype/dejavu';
  if (!material.existsSync() || !Directory(dejavu).existsSync()) return false;

  Future<void> family(String name, List<String> files) async {
    final loader = FontLoader(name);
    for (final f in files) {
      final bytes = File(f).readAsBytesSync();
      loader.addFont(
        Future.value(ByteData.sublistView(Uint8List.fromList(bytes))),
      );
    }
    await loader.load();
  }

  await family('Roboto', [
    for (final w in ['Regular', 'Medium', 'Bold', 'Black'])
      '${material.path}/Roboto-$w.ttf',
  ]);
  await family('DejaVu Sans', [
    '$dejavu/DejaVuSans.ttf',
    '$dejavu/DejaVuSans-Bold.ttf',
  ]);
  await family('MaterialIcons', ['${material.path}/MaterialIcons-Regular.otf']);
  MechSimApp.fontFamily = 'Roboto';
  MechSimApp.fontFallback = const ['DejaVu Sans'];
  Symbols.fontFamily = 'Roboto';
  Symbols.fontFallback = const ['DejaVu Sans'];
  return true;
}

/// Writes what is on screen to [dir]/[name].png.
Future<void> shoot(WidgetTester tester, String dir, String name) async {
  await tester.runAsync(() async {
    final boundary =
        shotKey.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final scale =
        double.tryParse(Platform.environment['MECHSIM_SHOTS_SCALE'] ?? '') ??
        2.0;
    final image = await boundary.toImage(pixelRatio: scale);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    File('$dir/$name.png')
      ..createSync(recursive: true)
      ..writeAsBytesSync(bytes!.buffer.asUint8List());
  });
}
