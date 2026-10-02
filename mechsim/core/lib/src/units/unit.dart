/// Unit Conversion Engine.
///
/// Every quantity inside the engine is stored in SI base units (N, m, N·m,
/// Pa, m²). Units only exist at the edges: when a value is typed in, and when
/// it is shown. That keeps the solver free of conversion factors and makes a
/// change of display units a pure formatting concern.
library;

/// The physical dimension a unit measures. Two units convert into each other
/// only when they share a dimension.
enum Dimension { force, length, moment, stress, area }

class Unit {
  const Unit(this.symbol, this.dimension, this.toSi);

  final String symbol;
  final Dimension dimension;

  /// Multiply a value expressed in this unit by [toSi] to get SI.
  final double toSi;

  double toSiValue(double value) => value * toSi;
  double fromSiValue(double si) => si / toSi;

  @override
  String toString() => symbol;
}

abstract final class Units {
  static const newton = Unit('N', Dimension.force, 1);
  static const kilonewton = Unit('kN', Dimension.force, 1e3);

  static const millimetre = Unit('mm', Dimension.length, 1e-3);
  static const centimetre = Unit('cm', Dimension.length, 1e-2);
  static const metre = Unit('m', Dimension.length, 1);

  static const newtonMillimetre = Unit('N·mm', Dimension.moment, 1e-3);
  static const newtonMetre = Unit('N·m', Dimension.moment, 1);
  static const kilonewtonMetre = Unit('kN·m', Dimension.moment, 1e3);

  static const pascal = Unit('Pa', Dimension.stress, 1);
  static const kilopascal = Unit('kPa', Dimension.stress, 1e3);
  static const megapascal = Unit('MPa', Dimension.stress, 1e6);

  static const squareMillimetre = Unit('mm²', Dimension.area, 1e-6);
  static const squareCentimetre = Unit('cm²', Dimension.area, 1e-4);
  static const squareMetre = Unit('m²', Dimension.area, 1);

  static const List<Unit> all = [
    newton,
    kilonewton,
    millimetre,
    centimetre,
    metre,
    newtonMillimetre,
    newtonMetre,
    kilonewtonMetre,
    pascal,
    kilopascal,
    megapascal,
    squareMillimetre,
    squareCentimetre,
    squareMetre,
  ];

  static List<Unit> of(Dimension dimension) =>
      all.where((u) => u.dimension == dimension).toList(growable: false);

  static Unit bySymbol(String symbol) => all.firstWhere(
        (u) => u.symbol == symbol,
        orElse: () => throw ArgumentError.value(symbol, 'symbol', 'unknown unit'),
      );

  /// Converts [value] from one unit to another of the same dimension.
  static double convert(double value, Unit from, Unit to) {
    if (from.dimension != to.dimension) {
      throw ArgumentError(
          'Cannot convert ${from.symbol} (${from.dimension.name}) '
          'to ${to.symbol} (${to.dimension.name})');
    }
    if (identical(from, to)) return value;
    return value * from.toSi / to.toSi;
  }
}

/// The units a person reads and types in. Force, length and moment are chosen
/// independently, so "kN with mm" works as well as the usual presets.
class UnitSystem {
  const UnitSystem({
    required this.force,
    required this.length,
    required this.moment,
    this.stress = Units.megapascal,
  });

  final Unit force;
  final Unit length;
  final Unit moment;
  final Unit stress;

  static const knM = UnitSystem(
      force: Units.kilonewton,
      length: Units.metre,
      moment: Units.kilonewtonMetre);
  static const nM = UnitSystem(
      force: Units.newton, length: Units.metre, moment: Units.newtonMetre);
  static const nMm = UnitSystem(
      force: Units.newton,
      length: Units.millimetre,
      moment: Units.newtonMillimetre);

  static const presets = [knM, nM, nMm];

  Unit unitFor(Dimension dimension) => switch (dimension) {
        Dimension.force => force,
        Dimension.length => length,
        Dimension.moment => moment,
        Dimension.stress => stress,
        Dimension.area => Units.squareMillimetre,
      };

  double toDisplay(double si, Dimension dimension) =>
      unitFor(dimension).fromSiValue(si);

  double fromDisplay(double value, Dimension dimension) =>
      unitFor(dimension).toSiValue(value);

  UnitSystem copyWith({Unit? force, Unit? length, Unit? moment, Unit? stress}) {
    final next = UnitSystem(
      force: force ?? this.force,
      length: length ?? this.length,
      moment: moment ?? this.moment,
      stress: stress ?? this.stress,
    );
    next._check();
    return next;
  }

  void _check() {
    if (force.dimension != Dimension.force ||
        length.dimension != Dimension.length ||
        moment.dimension != Dimension.moment ||
        stress.dimension != Dimension.stress) {
      throw ArgumentError('UnitSystem given a unit of the wrong dimension');
    }
  }

  Map<String, Object?> toJson() => {
        'force': force.symbol,
        'length': length.symbol,
        'moment': moment.symbol,
        'stress': stress.symbol,
      };

  factory UnitSystem.fromJson(Map<String, Object?> json) {
    final system = UnitSystem(
      force: Units.bySymbol(json['force'] as String? ?? 'kN'),
      length: Units.bySymbol(json['length'] as String? ?? 'm'),
      moment: Units.bySymbol(json['moment'] as String? ?? 'kN·m'),
      stress: Units.bySymbol(json['stress'] as String? ?? 'MPa'),
    );
    system._check();
    return system;
  }

  @override
  bool operator ==(Object other) =>
      other is UnitSystem &&
      other.force == force &&
      other.length == length &&
      other.moment == moment &&
      other.stress == stress;

  @override
  int get hashCode => Object.hash(force, length, moment, stress);

  @override
  String toString() => '$force, $length, $moment';
}
