import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:mechsim_core/mechsim_core.dart';

import 'drawing/palette.dart';
import 'state/app_state.dart';
import 'ui/home/home_shell.dart';

class MechSimApp extends StatelessWidget {
  const MechSimApp({super.key, required this.state, this.home});

  final AppState state;

  /// Replaces the home shell (used by tests and screenshots).
  final Widget? home;

  /// Fallback fonts for the theme; only screenshot tests set this.
  static List<String>? fontFallback;
  static String? fontFamily;

  static ThemeData theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF2E5E8C),
      brightness: brightness,
    );
    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      fontFamily: fontFamily,
      fontFamilyFallback: fontFallback,
      extensions: [dark ? MechColors.dark : MechColors.light],
      cardTheme: const CardThemeData(margin: EdgeInsets.zero),
      visualDensity: VisualDensity.standard,
    );
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: state,
      child: ListenableBuilder(
        listenable: state,
        builder: (context, _) {
          final settings = state.settings;
          return MaterialApp(
            title: 'MechSim 2D',
            debugShowCheckedModeBanner: false,
            theme: theme(Brightness.light),
            darkTheme: theme(Brightness.dark),
            themeMode: switch (settings.theme) {
              ThemePref.system => ThemeMode.system,
              ThemePref.light => ThemeMode.light,
              ThemePref.dark => ThemeMode.dark,
            },
            locale: Locale(settings.lang == Lang.ar ? 'ar' : 'en'),
            supportedLocales: const [Locale('ar'), Locale('en')],
            localizationsDelegates: GlobalMaterialLocalizations.delegates,
            home: home ?? const HomeShell(),
          );
        },
      ),
    );
  }
}
