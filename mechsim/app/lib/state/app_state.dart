import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../i18n/strings.dart';

enum ThemePref { system, light, dark }

/// Which way the screen may turn. [auto] follows the phone (and its
/// rotation lock); [landscape] keeps the app sideways even when the phone
/// is locked upright.
enum OrientationPref { auto, landscape, portrait }

class AppSettings {
  const AppSettings({
    this.lang = Lang.ar,
    this.units = UnitSystem.knM,
    this.convention = SignConvention.standard,
    this.theme = ThemePref.system,
    this.orientation = OrientationPref.auto,
  });

  final Lang lang;
  final UnitSystem units;
  final SignConvention convention;
  final ThemePref theme;
  final OrientationPref orientation;

  AppSettings copyWith({
    Lang? lang,
    UnitSystem? units,
    SignConvention? convention,
    ThemePref? theme,
    OrientationPref? orientation,
  }) => AppSettings(
    lang: lang ?? this.lang,
    units: units ?? this.units,
    convention: convention ?? this.convention,
    theme: theme ?? this.theme,
    orientation: orientation ?? this.orientation,
  );

  Map<String, Object?> toJson() => {
    'lang': lang.name,
    'units': units.toJson(),
    'convention': convention.toJson(),
    'theme': theme.name,
    'orientation': orientation.name,
  };

  factory AppSettings.fromJson(Map<String, Object?> json) {
    T byName<T extends Enum>(List<T> values, Object? name, T fallback) =>
        values.where((v) => v.name == name).firstOrNull ?? fallback;
    return AppSettings(
      lang: byName(Lang.values, json['lang'], Lang.ar),
      units:
          json['units'] is Map<String, Object?>
              ? UnitSystem.fromJson(json['units']! as Map<String, Object?>)
              : UnitSystem.knM,
      convention:
          json['convention'] is Map<String, Object?>
              ? SignConvention.fromJson(
                json['convention']! as Map<String, Object?>,
              )
              : SignConvention.standard,
      theme: byName(ThemePref.values, json['theme'], ThemePref.system),
      orientation: byName(
        OrientationPref.values,
        json['orientation'],
        OrientationPref.auto,
      ),
    );
  }
}

abstract interface class SettingsStore {
  Future<AppSettings?> load();
  Future<void> save(AppSettings settings);
}

class MemorySettingsStore implements SettingsStore {
  AppSettings? value;

  @override
  Future<AppSettings?> load() async => value;

  @override
  Future<void> save(AppSettings settings) async => value = settings;
}

class FileSettingsStore implements SettingsStore {
  FileSettingsStore(this.file);

  final File file;

  @override
  Future<AppSettings?> load() async {
    try {
      if (!await file.exists()) return null;
      return AppSettings.fromJson(
        jsonDecode(await file.readAsString()) as Map<String, Object?>,
      );
    } on Object {
      return null; // unreadable settings fall back to the defaults
    }
  }

  @override
  Future<void> save(AppSettings settings) async {
    await file.parent.create(recursive: true);
    await file.writeAsString(jsonEncode(settings.toJson()), flush: true);
  }
}

/// App-wide state: settings and saved problems. Screens read it through
/// [AppScope.of] and rebuild when it changes.
class AppState extends ChangeNotifier {
  AppState({
    required AppSettings settings,
    required this.repository,
    required this.settingsStore,
  }) : _settings = settings;

  AppSettings _settings;
  final ProblemRepository repository;
  final SettingsStore settingsStore;
  List<SavedProblem> _saved = const [];
  bool _savedLoaded = false;

  AppSettings get settings => _settings;
  Lang get lang => _settings.lang;
  UnitSystem get units => _settings.units;
  S get s => S.of(_settings.lang);
  Texts get texts => Texts.of(_settings.lang);

  SolutionBuilder get builder => SolutionBuilder(
    lang: _settings.lang,
    units: _settings.units,
    convention: _settings.convention,
  );

  Solution solve(BeamProblem problem) => builder.build(problem);

  void updateSettings(AppSettings next) {
    final turned = next.orientation != _settings.orientation;
    _settings = next;
    notifyListeners();
    settingsStore.save(next);
    if (turned) applyOrientation(next.orientation);
  }

  /// Tells the platform which orientations the app allows.
  static Future<void> applyOrientation(OrientationPref pref) async {
    final allowed = switch (pref) {
      OrientationPref.auto => DeviceOrientation.values,
      OrientationPref.landscape => const [
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ],
      OrientationPref.portrait => const [
        DeviceOrientation.portraitUp,
        DeviceOrientation.portraitDown,
      ],
    };
    try {
      await SystemChrome.setPreferredOrientations(allowed);
    } on Object {
      // Desktop platforms have no orientation; nothing to do there.
    }
  }

  List<SavedProblem> get saved => _saved;
  bool get savedLoaded => _savedLoaded;

  Future<void> loadSaved() async {
    _saved = await repository.list();
    _savedLoaded = true;
    notifyListeners();
  }

  Future<SavedProblem> saveProblem({
    String? id,
    required String name,
    required BeamProblem problem,
  }) async {
    final entry = SavedProblem(
      id: id ?? DateTime.now().microsecondsSinceEpoch.toRadixString(36),
      name: name,
      savedAt: DateTime.now(),
      problem: problem.copyWith(title: name),
    );
    await repository.save(entry);
    await loadSaved();
    return entry;
  }

  Future<void> deleteSaved(String id) async {
    await repository.delete(id);
    await loadSaved();
  }

  Future<void> restoreSaved(SavedProblem p) async {
    await repository.save(p);
    await loadSaved();
  }
}

class AppScope extends InheritedNotifier<AppState> {
  const AppScope({super.key, required AppState state, required super.child})
    : super(notifier: state);

  static AppState of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppScope>()!.notifier!;

  /// For callbacks that must not subscribe the widget to changes.
  static AppState read(BuildContext context) =>
      context.getInheritedWidgetOfExactType<AppScope>()!.notifier!;
}
