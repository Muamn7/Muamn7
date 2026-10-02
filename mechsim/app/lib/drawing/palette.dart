import 'package:flutter/material.dart';

/// The colours of the engineering sheet and its diagrams, for light and
/// dark themes. Loads are red and reactions teal everywhere in the app, so
/// a student learns to read them by colour as well as by arrow.
@immutable
class MechColors extends ThemeExtension<MechColors> {
  const MechColors({
    required this.paper,
    required this.gridMinor,
    required this.gridMajor,
    required this.ink,
    required this.inkSoft,
    required this.beam,
    required this.support,
    required this.load,
    required this.reaction,
    required this.highlight,
    required this.shear,
    required this.moment,
    required this.axial,
    required this.positive,
    required this.negative,
    required this.selection,
  });

  final Color paper;
  final Color gridMinor;
  final Color gridMajor;
  final Color ink;
  final Color inkSoft;
  final Color beam;
  final Color support;
  final Color load;
  final Color reaction;
  final Color highlight;
  final Color shear;
  final Color moment;
  final Color axial;
  final Color positive;
  final Color negative;
  final Color selection;

  static const light = MechColors(
    paper: Color(0xFFFBFAF5),
    gridMinor: Color(0xFFE6EEF3),
    gridMajor: Color(0xFFC9DAE6),
    ink: Color(0xFF1B2A38),
    inkSoft: Color(0xFF5B6B7A),
    beam: Color(0xFF2E4A62),
    support: Color(0xFF37474F),
    load: Color(0xFFD32F2F),
    reaction: Color(0xFF00897B),
    highlight: Color(0xFFFF8F00),
    shear: Color(0xFF1E66C9),
    moment: Color(0xFF8E3FB8),
    axial: Color(0xFF2E7D32),
    positive: Color(0xFF1565C0),
    negative: Color(0xFFC62828),
    selection: Color(0xFF1976D2),
  );

  static const dark = MechColors(
    paper: Color(0xFF0F1A24),
    gridMinor: Color(0xFF16263A),
    gridMajor: Color(0xFF213A55),
    ink: Color(0xFFE3ECF4),
    inkSoft: Color(0xFF9DB0C2),
    beam: Color(0xFF9CC3E6),
    support: Color(0xFFB0BEC5),
    load: Color(0xFFFF6B6B),
    reaction: Color(0xFF4DD0C0),
    highlight: Color(0xFFFFB74D),
    shear: Color(0xFF64A8FF),
    moment: Color(0xFFC792EA),
    axial: Color(0xFF81C784),
    positive: Color(0xFF64A8FF),
    negative: Color(0xFFFF7A7A),
    selection: Color(0xFF64B5F6),
  );

  static MechColors of(BuildContext context) =>
      Theme.of(context).extension<MechColors>() ?? light;

  @override
  MechColors copyWith() => this;

  @override
  MechColors lerp(MechColors? other, double t) =>
      t < 0.5 ? this : (other ?? this);
}
