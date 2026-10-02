import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../state/app_state.dart';

class SettingsTab extends StatelessWidget {
  const SettingsTab({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final settings = app.settings;
    final theme = Theme.of(context);
    final c = settings.convention;

    Widget section(String title) => Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 6),
      child: Text(
        title,
        style: theme.textTheme.titleSmall?.copyWith(
          color: theme.colorScheme.primary,
          fontWeight: FontWeight.w800,
        ),
      ),
    );

    Widget choice<T>(
      String label,
      List<(T, String)> options,
      T value,
      ValueChanged<T> onChanged,
    ) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 12,
        runSpacing: 6,
        children: [
          Text(label),
          SegmentedButton<T>(
            showSelectedIcon: false,
            style: const ButtonStyle(visualDensity: VisualDensity.compact),
            segments: [
              for (final (v, text) in options)
                ButtonSegment<T>(
                  value: v,
                  label: Text(text, textDirection: TextDirection.ltr),
                ),
            ],
            selected: {value},
            onSelectionChanged: (v) => onChanged(v.single),
          ),
        ],
      ),
    );

    void units(UnitSystem u) => app.updateSettings(settings.copyWith(units: u));
    void convention(SignConvention v) =>
        app.updateSettings(settings.copyWith(convention: v));

    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        section(s.language),
        choice<Lang>(
          s.language,
          const [(Lang.ar, 'العربية'), (Lang.en, 'English')],
          settings.lang,
          (v) => app.updateSettings(settings.copyWith(lang: v)),
        ),
        section(s.units),
        choice<Unit>(
          s.force,
          [for (final u in Units.of(Dimension.force)) (u, u.symbol)],
          settings.units.force,
          (v) => units(settings.units.copyWith(force: v)),
        ),
        choice<Unit>(
          s.lengthUnit,
          [for (final u in Units.of(Dimension.length)) (u, u.symbol)],
          settings.units.length,
          (v) => units(settings.units.copyWith(length: v)),
        ),
        choice<Unit>(
          s.momentUnit,
          [for (final u in Units.of(Dimension.moment)) (u, u.symbol)],
          settings.units.moment,
          (v) => units(settings.units.copyWith(moment: v)),
        ),
        section(s.signConvention),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Text(s.signConventionHelp, style: theme.textTheme.bodySmall),
        ),
        choice<bool>(
          s.positiveY,
          const [(true, '↑ +'), (false, '↓ +')],
          c.upPositive,
          (v) => convention(c.copyWith(upPositive: v)),
        ),
        choice<bool>(
          s.positiveX,
          const [(true, '→ +'), (false, '← +')],
          c.rightPositive,
          (v) => convention(c.copyWith(rightPositive: v)),
        ),
        choice<bool>(
          s.positiveMoment,
          const [(true, '↺ +'), (false, '↻ +')],
          c.counterClockwisePositive,
          (v) => convention(c.copyWith(counterClockwisePositive: v)),
        ),
        Card(
          margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  s.beamConventionTitle,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 4),
                Text(s.beamConvention, style: const TextStyle(height: 1.5)),
              ],
            ),
          ),
        ),
        section(s.theme),
        choice<ThemePref>(
          s.theme,
          [
            (ThemePref.system, s.themeSystem),
            (ThemePref.light, s.themeLight),
            (ThemePref.dark, s.themeDark),
          ],
          settings.theme,
          (v) => app.updateSettings(settings.copyWith(theme: v)),
        ),
        section(s.about),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Text(s.aboutText, style: const TextStyle(height: 1.5)),
        ),
      ],
    );
  }
}
