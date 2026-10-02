import 'dart:io';

import 'package:flutter/material.dart';
import 'package:mechsim_core/io.dart';
import 'package:path_provider/path_provider.dart';

import 'app.dart';
import 'state/app_state.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final dir = await getApplicationSupportDirectory();
  final settingsStore = FileSettingsStore(File('${dir.path}/settings.json'));
  final settings = await settingsStore.load() ?? const AppSettings();
  final state = AppState(
    settings: settings,
    repository: FileProblemRepository(File('${dir.path}/problems.json')),
    settingsStore: settingsStore,
  );
  runApp(MechSimApp(state: state));
}
