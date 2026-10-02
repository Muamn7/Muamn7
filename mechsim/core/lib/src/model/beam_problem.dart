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
  const Support({required this.id, required this.type, required this.x});

  final String id;
  final SupportType type;
  final double x;

  Support copyWith({SupportType? type, double? x}) =>
      Support(id: id, type: type ?? this.type, x: x ?? this.x);

  Map<String, Object?> toJson() => {'id': id, 'type': type.name, 'x': x};

  factory Support.fromJson(Map<String, Object?> json) => Support(
        id: json['id'] as String,
        type: SupportType.values.byName(json['type'] as String),
        x: (json['x'] as num).toDouble(),
      );

  @override
  bool operator ==(Object other) =>
      other is Support && other.id == id && other.type == type && other.x == x;

  @override
  int get hashCode => Object.hash(id, type, x);
}

/// Every kind of load the beam can carry. The family is sealed so that adding
/// a new kind (a UDL, a UVL, an applied couple) makes the compiler point at
/// every place in the engine that has to learn about it.
sealed class Load {
  const Load();

  String get id;

  /// Where the load sits (for a distributed load, where it starts).
  double get x;

  Load movedTo(double x);

  Map<String, Object?> toJson();

  static Load fromJson(Map<String, Object?> json) {
    final kind = json['kind'] as String? ?? 'point';
    return switch (kind) {
      'point' => PointLoad.fromJson(json),
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
  });

  @override
  final String id;
  @override
  final double x;

  /// Size of the force in newtons. Always non-negative; the direction lives
  /// in [angleDeg].
  final double magnitude;
  final double angleDeg;

  double get fx => magnitude * cosDeg(angleDeg);
  double get fy => magnitude * sinDeg(angleDeg);

  bool get isVertical => cosDeg(angleDeg) == 0;
  bool get isHorizontal => sinDeg(angleDeg) == 0;
  bool get isInclined => !isVertical && !isHorizontal;

  @override
  PointLoad movedTo(double x) => copyWith(x: x);

  PointLoad copyWith({double? x, double? magnitude, double? angleDeg}) =>
      PointLoad(
        id: id,
        x: x ?? this.x,
        magnitude: magnitude ?? this.magnitude,
        angleDeg: angleDeg ?? this.angleDeg,
      );

  @override
  Map<String, Object?> toJson() => {
        'kind': 'point',
        'id': id,
        'x': x,
        'magnitude': magnitude,
        'angle': angleDeg,
      };

  factory PointLoad.fromJson(Map<String, Object?> json) => PointLoad(
        id: json['id'] as String,
        x: (json['x'] as num).toDouble(),
        magnitude: (json['magnitude'] as num).toDouble(),
        angleDeg: (json['angle'] as num?)?.toDouble() ?? -90,
      );

  @override
  bool operator ==(Object other) =>
      other is PointLoad &&
      other.id == id &&
      other.x == x &&
      other.magnitude == magnitude &&
      other.angleDeg == angleDeg;

  @override
  int get hashCode => Object.hash(id, x, magnitude, angleDeg);
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

    return copyWith(
      length: newLength,
      supports: [for (final s in supports) s.copyWith(x: place(s.x))],
      loads: [for (final l in loads) l.movedTo(place(l.x))],
    );
  }

  /// A fresh id such as "s3" or "p2" that no element uses yet.
  String nextId(String prefix) {
    var highest = 0;
    for (final id in [...supports.map((s) => s.id), ...loads.map((l) => l.id)]) {
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
      throw FormatException('Problem saved by a newer version (schema $schema)');
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
