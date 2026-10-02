/// The 2D model a student draws: one horizontal beam, its supports and its
/// loads. Everything is immutable; an edit produces a new [BeamProblem],
/// which is what makes undo/redo a plain stack of snapshots.
///
/// Coordinates: x runs along the beam from its left end (x = 0) to its right
/// end (x = length), y points up. All values are SI (N, m).
library;

import 'dart:math' as math;

enum SupportType {
  /// Resists horizontal and vertical movement, allows rotation.
  pin,

  /// Resists movement perpendicular to its rolling surface only.
  roller,

  /// Resists both translations and rotation (a built-in end).
  fixed,
}

class Support {
  const Support({
    required this.id,
    required this.type,
    required this.x,
    this.known = const {},
  });

  final String id;
  final SupportType type;
  final double x;

  /// Reaction components the student has given a value, so they are not
  /// unknowns: 'horizontal', 'vertical' or 'moment' → value in SI with the
  /// physical sign (→, ↑, ↺ positive). Components this type of support
  /// does not have are ignored.
  final Map<String, double> known;

  Support copyWith(
          {SupportType? type, double? x, Map<String, double>? known}) =>
      Support(
        id: id,
        type: type ?? this.type,
        x: x ?? this.x,
        known: known ?? this.known,
      );

  /// The same support with [component] given [value], or made unknown again
  /// when [value] is null.
  Support withKnown(String component, double? value) => copyWith(known: {
        for (final e in known.entries)
          if (e.key != component) e.key: e.value,
        if (value != null) component: value,
      });

  Map<String, Object?> toJson() => {
        'id': id,
        'type': type.name,
        'x': x,
        if (known.isNotEmpty) 'known': known,
      };

  factory Support.fromJson(Map<String, Object?> json) => Support(
        id: json['id'] as String,
        type: SupportType.values.byName(json['type'] as String),
        x: (json['x'] as num).toDouble(),
        known: {
          for (final e in ((json['known'] as Map?) ?? const {}).entries)
            e.key as String: (e.value as num).toDouble(),
        },
      );

  @override
  bool operator ==(Object other) =>
      other is Support &&
      other.id == id &&
      other.type == type &&
      other.x == x &&
      other.known.length == known.length &&
      known.entries.every((e) => other.known[e.key] == e.value);

  @override
  int get hashCode => Object.hash(
      id,
      type,
      x,
      Object.hashAllUnordered(
          known.entries.map((e) => Object.hash(e.key, e.value))));
}

/// Every kind of load the beam can carry. The family is sealed so that adding
/// a new kind (a UDL, a UVL, an applied couple) makes the compiler point at
/// every place in the engine that has to learn about it.
sealed class Load {
  const Load();

  String get id;

  /// Where the load sits (for a distributed load, where it starts).
  double get x;

  /// Where the load ends; the same as [x] for a concentrated one.
  double get end => x;

  /// The positions worth labelling and dimensioning.
  List<double> get positions => end == x ? [x] : [x, end];

  /// The same load with its start at [x]; a distributed load keeps its span.
  Load movedTo(double x);

  /// Whether the student made this load's size an unknown to solve for
  /// (its direction stays as drawn).
  bool get isUnknown => false;

  Map<String, Object?> toJson();

  static Load fromJson(Map<String, Object?> json) {
    final kind = json['kind'] as String? ?? 'point';
    return switch (kind) {
      'point' => PointLoad.fromJson(json),
      'distributed' => DistributedLoad.fromJson(json),
      'moment' => PointMoment.fromJson(json),
      _ => throw FormatException('Unknown load kind "$kind"'),
    };
  }
}

/// A concentrated force. [angleDeg] is the direction the force points,
/// measured counter-clockwise from +x: −90 points straight down, 90 straight
/// up, 0 to the right, 180 to the left.
final class PointLoad extends Load {
  const PointLoad({
    required this.id,
    required this.x,
    required this.magnitude,
    this.angleDeg = -90,
    this.unknown = false,
  });

  @override
  final String id;
  @override
  final double x;

  /// Size of the force in newtons. Always non-negative; the direction lives
  /// in [angleDeg]. Ignored while [unknown].
  final double magnitude;
  final double angleDeg;

  /// The size is to be found from equilibrium. Only a vertical or a
  /// horizontal load can be unknown.
  final bool unknown;

  @override
  bool get isUnknown => unknown && !isInclined;

  double get fx => magnitude * cosDeg(angleDeg);
  double get fy => magnitude * sinDeg(angleDeg);

  bool get isVertical => cosDeg(angleDeg) == 0;
  bool get isHorizontal => sinDeg(angleDeg) == 0;
  bool get isInclined => !isVertical && !isHorizontal;

  @override
  PointLoad movedTo(double x) => copyWith(x: x);

  PointLoad copyWith({
    double? x,
    double? magnitude,
    double? angleDeg,
    bool? unknown,
  }) =>
      PointLoad(
        id: id,
        x: x ?? this.x,
        magnitude: magnitude ?? this.magnitude,
        angleDeg: angleDeg ?? this.angleDeg,
        unknown: unknown ?? this.unknown,
      );

  @override
  Map<String, Object?> toJson() => {
        'kind': 'point',
        'id': id,
        'x': x,
        'magnitude': magnitude,
        'angle': angleDeg,
        if (unknown) 'unknown': true,
      };

  factory PointLoad.fromJson(Map<String, Object?> json) => PointLoad(
        id: json['id'] as String,
        x: (json['x'] as num).toDouble(),
        magnitude: (json['magnitude'] as num).toDouble(),
        angleDeg: (json['angle'] as num?)?.toDouble() ?? -90,
        unknown: json['unknown'] as bool? ?? false,
      );

  @override
  bool operator ==(Object other) =>
      other is PointLoad &&
      other.id == id &&
      other.x == x &&
      other.magnitude == magnitude &&
      other.angleDeg == angleDeg &&
      other.unknown == unknown;

  @override
  int get hashCode => Object.hash(id, x, magnitude, angleDeg, unknown);
}

/// A load spread over part of the beam, perpendicular to it. Its intensity
/// varies linearly from [w1] (N/m) at [x] to [w2] at [x2]: equal values make
/// a UDL, different ones a UVL (a triangle when one end is zero, otherwise
/// a trapezoid).
final class DistributedLoad extends Load {
  const DistributedLoad({
    required this.id,
    required this.x,
    required this.x2,
    required this.w1,
    required this.w2,
    this.upward = false,
  });

  @override
  final String id;
  @override
  final double x;
  final double x2;

  /// Intensities in N/m, never negative; the direction is [upward].
  final double w1;
  final double w2;
  final bool upward;

  @override
  double get end => x2;

  double get span => x2 - x;
  bool get isUniform => w1 == w2;

  /// The resultant force: the area of the load diagram.
  double get resultant => (w1 + w2) / 2 * span;

  /// The resultant as a vertical component (up positive).
  double get fy => upward ? resultant : -resultant;

  /// Where the resultant acts: the centroid of the load diagram.
  double get centroid {
    final sum = w1 + w2;
    if (sum == 0 || span == 0) return x + span / 2;
    return x + span * (w1 + 2 * w2) / (3 * sum);
  }

  /// Intensity (up positive) at the start and the end.
  double get q1 => upward ? w1 : -w1;
  double get q2 => upward ? w2 : -w2;

  @override
  DistributedLoad movedTo(double x) => copyWith(x: x, x2: x + span);

  DistributedLoad copyWith({
    double? x,
    double? x2,
    double? w1,
    double? w2,
    bool? upward,
  }) =>
      DistributedLoad(
        id: id,
        x: x ?? this.x,
        x2: x2 ?? this.x2,
        w1: w1 ?? this.w1,
        w2: w2 ?? this.w2,
        upward: upward ?? this.upward,
      );

  @override
  Map<String, Object?> toJson() => {
        'kind': 'distributed',
        'id': id,
        'x': x,
        'x2': x2,
        'w1': w1,
        'w2': w2,
        'up': upward,
      };

  factory DistributedLoad.fromJson(Map<String, Object?> json) =>
      DistributedLoad(
        id: json['id'] as String,
        x: (json['x'] as num).toDouble(),
        x2: (json['x2'] as num).toDouble(),
        w1: (json['w1'] as num).toDouble(),
        w2: (json['w2'] as num).toDouble(),
        upward: json['up'] as bool? ?? false,
      );

  @override
  bool operator ==(Object other) =>
      other is DistributedLoad &&
      other.id == id &&
      other.x == x &&
      other.x2 == x2 &&
      other.w1 == w1 &&
      other.w2 == w2 &&
      other.upward == upward;

  @override
  int get hashCode => Object.hash(id, x, x2, w1, w2, upward);
}

/// A concentrated couple applied to the beam, in N·m.
final class PointMoment extends Load {
  const PointMoment({
    required this.id,
    required this.x,
    required this.magnitude,
    this.counterClockwise = true,
    this.unknown = false,
  });

  @override
  final String id;
  @override
  final double x;

  /// Ignored while [unknown].
  final double magnitude;
  final bool counterClockwise;

  /// The size is to be found from equilibrium; the sense stays as drawn.
  final bool unknown;

  @override
  bool get isUnknown => unknown;

  /// The couple with its sign, counter-clockwise positive.
  double get moment => counterClockwise ? magnitude : -magnitude;

  @override
  PointMoment movedTo(double x) => copyWith(x: x);

  PointMoment copyWith({
    double? x,
    double? magnitude,
    bool? counterClockwise,
    bool? unknown,
  }) =>
      PointMoment(
        id: id,
        x: x ?? this.x,
        magnitude: magnitude ?? this.magnitude,
        counterClockwise: counterClockwise ?? this.counterClockwise,
        unknown: unknown ?? this.unknown,
      );

  @override
  Map<String, Object?> toJson() => {
        'kind': 'moment',
        'id': id,
        'x': x,
        'magnitude': magnitude,
        'ccw': counterClockwise,
        if (unknown) 'unknown': true,
      };

  factory PointMoment.fromJson(Map<String, Object?> json) => PointMoment(
        id: json['id'] as String,
        x: (json['x'] as num).toDouble(),
        magnitude: (json['magnitude'] as num).toDouble(),
        counterClockwise: json['ccw'] as bool? ?? true,
        unknown: json['unknown'] as bool? ?? false,
      );

  @override
  bool operator ==(Object other) =>
      other is PointMoment &&
      other.id == id &&
      other.x == x &&
      other.magnitude == magnitude &&
      other.counterClockwise == counterClockwise &&
      other.unknown == unknown;

  @override
  int get hashCode => Object.hash(id, x, magnitude, counterClockwise, unknown);
}

/// Cosine of an angle in degrees that is exact on the multiples of 90°, so a
/// vertical load has a horizontal component of exactly zero and not 6e−17.
double cosDeg(double degrees) {
  final a = normaliseAngle(degrees);
  if (a == 90 || a == -90) return 0;
  if (a == 0) return 1;
  if (a == 180) return -1;
  if (a == 60 || a == -60) return 0.5;
  if (a == 120 || a == -120) return -0.5;
  return math.cos(a * math.pi / 180);
}

double sinDeg(double degrees) {
  final a = normaliseAngle(degrees);
  if (a == 0 || a == 180) return 0;
  if (a == 90) return 1;
  if (a == -90) return -1;
  if (a == 30 || a == 150) return 0.5;
  if (a == -30 || a == -150) return -0.5;
  return math.sin(a * math.pi / 180);
}

/// Maps any angle into (−180, 180].
double normaliseAngle(double degrees) {
  var a = degrees % 360; // [0, 360)
  if (a > 180) a -= 360;
  return a;
}

class BeamProblem {
  const BeamProblem({
    this.title = '',
    this.length = 0,
    this.supports = const [],
    this.loads = const [],
  });

  final String title;

  /// Length of the beam in metres. Zero means no beam has been drawn yet.
  final double length;
  final List<Support> supports;
  final List<Load> loads;

  bool get hasBeam => length > 0;

  List<PointLoad> get pointLoads => loads.whereType<PointLoad>().toList();
  List<DistributedLoad> get distributedLoads =>
      loads.whereType<DistributedLoad>().toList();
  List<PointMoment> get moments => loads.whereType<PointMoment>().toList();

  BeamProblem copyWith({
    String? title,
    double? length,
    List<Support>? supports,
    List<Load>? loads,
  }) =>
      BeamProblem(
        title: title ?? this.title,
        length: length ?? this.length,
        supports: supports ?? this.supports,
        loads: loads ?? this.loads,
      );

  Support? supportById(String id) {
    for (final s in supports) {
      if (s.id == id) return s;
    }
    return null;
  }

  Load? loadById(String id) {
    for (final l in loads) {
      if (l.id == id) return l;
    }
    return null;
  }

  bool contains(String id) => supportById(id) != null || loadById(id) != null;

  BeamProblem withSupport(Support support) =>
      copyWith(supports: [...supports, support]);

  BeamProblem withLoad(Load load) => copyWith(loads: [...loads, load]);

  BeamProblem replaceSupport(Support support) => copyWith(
      supports: [for (final s in supports) s.id == support.id ? support : s]);

  BeamProblem replaceLoad(Load load) =>
      copyWith(loads: [for (final l in loads) l.id == load.id ? load : l]);

  BeamProblem remove(String id) => copyWith(
        supports: supports.where((s) => s.id != id).toList(),
        loads: loads.where((l) => l.id != id).toList(),
      );

  /// Moves a support or load to [x], clamped onto the beam.
  BeamProblem move(String id, double x) {
    final clamped = x.clamp(0.0, length).toDouble();
    final support = supportById(id);
    if (support != null) return replaceSupport(support.copyWith(x: clamped));
    final load = loadById(id);
    if (load is DistributedLoad) {
      // The whole load slides; it stops when an end reaches the beam's end.
      final start = x.clamp(0.0, math.max(0.0, length - load.span)).toDouble();
      return replaceLoad(load.movedTo(start));
    }
    if (load != null) return replaceLoad(load.movedTo(clamped));
    return this;
  }

  /// Changes the beam length. Supports and loads keep their distance from
  /// the left end; anything that would fall off the end is pulled back onto
  /// it, and anything sitting exactly on the old right end follows the end.
  BeamProblem withLength(double newLength) {
    double place(double x) {
      if (x >= length - 1e-9 && length > 0) return newLength;
      return math.min(x, newLength);
    }

    Load fit(Load l) {
      if (l is! DistributedLoad) return l.movedTo(place(l.x));
      final end = place(l.x2);
      var start = place(l.x);
      if (end - start < 1e-9) start = math.max(0, end - l.span);
      return l.copyWith(x: start, x2: end);
    }

    return copyWith(
      length: newLength,
      supports: [for (final s in supports) s.copyWith(x: place(s.x))],
      loads: [for (final l in loads) fit(l)],
    );
  }

  /// A fresh id such as "s3" or "p2" that no element uses yet.
  String nextId(String prefix) {
    var highest = 0;
    for (final id in [
      ...supports.map((s) => s.id),
      ...loads.map((l) => l.id)
    ]) {
      if (!id.startsWith(prefix)) continue;
      final n = int.tryParse(id.substring(prefix.length));
      if (n != null && n > highest) highest = n;
    }
    return '$prefix${highest + 1}';
  }

  static const int schemaVersion = 1;

  Map<String, Object?> toJson() => {
        'schema': schemaVersion,
        'title': title,
        'length': length,
        'supports': [for (final s in supports) s.toJson()],
        'loads': [for (final l in loads) l.toJson()],
      };

  factory BeamProblem.fromJson(Map<String, Object?> json) {
    final schema = json['schema'] as int? ?? 1;
    if (schema > schemaVersion) {
      throw FormatException(
          'Problem saved by a newer version (schema $schema)');
    }
    return BeamProblem(
      title: json['title'] as String? ?? '',
      length: (json['length'] as num? ?? 0).toDouble(),
      supports: [
        for (final s in (json['supports'] as List<Object?>? ?? const []))
          Support.fromJson(s! as Map<String, Object?>),
      ],
      loads: [
        for (final l in (json['loads'] as List<Object?>? ?? const []))
          Load.fromJson(l! as Map<String, Object?>),
      ],
    );
  }

  @override
  bool operator ==(Object other) {
    if (other is! BeamProblem) return false;
    if (other.title != title || other.length != length) return false;
    if (other.supports.length != supports.length) return false;
    if (other.loads.length != loads.length) return false;
    for (var i = 0; i < supports.length; i++) {
      if (other.supports[i] != supports[i]) return false;
    }
    for (var i = 0; i < loads.length; i++) {
      if (other.loads[i] != loads[i]) return false;
    }
    return true;
  }

  @override
  int get hashCode => Object.hash(
      title, length, Object.hashAll(supports), Object.hashAll(loads));
}
