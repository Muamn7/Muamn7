/// Problem Generator: random beams with textbook-friendly numbers, always
/// statically determinate and always with every load away from the supports
/// (a load sitting on a support goes straight into it and teaches nothing).
library;

import 'dart:math' as math;

import '../model/beam_problem.dart';
import '../statics/equilibrium.dart';

enum PracticeLevel {
  /// Simply supported, one downward load.
  basic,

  /// Two loads, an overhang, or a cantilever.
  intermediate,

  /// Overhangs on both sides, upward or inclined loads, three loads.
  advanced,
}

class ProblemGenerator {
  ProblemGenerator([int? seed]) : _rng = math.Random(seed);

  final math.Random _rng;

  static const _kN = 1000.0;

  BeamProblem generate([PracticeLevel level = PracticeLevel.basic]) {
    for (var attempt = 0; attempt < 50; attempt++) {
      final problem = switch (level) {
        PracticeLevel.basic => _simplySupported(loads: 1),
        PracticeLevel.intermediate => switch (_rng.nextInt(4)) {
            0 => _simplySupported(loads: 2),
            1 => _overhang(loads: 1 + _rng.nextInt(2), bothSides: false),
            2 => _cantilever(loads: 1 + _rng.nextInt(2)),
            _ => _withUdl(_simplySupported(loads: _rng.nextInt(2))),
          },
        PracticeLevel.advanced => switch (_rng.nextInt(5)) {
            0 => _overhang(loads: 2 + _rng.nextInt(2), bothSides: true),
            1 => _simplySupported(loads: 2, inclined: true),
            2 => _overhang(loads: 2, bothSides: false, upward: true),
            3 => _withUdl(_simplySupported(loads: 1), triangle: true),
            _ => _withCouple(_withUdl(_simplySupported(loads: 0))),
          },
      };
      if (StaticsSolver.solve(problem).isSolved) return problem;
    }
    // Unreachable with the shapes above, but never hand back nonsense.
    return _simplySupported(loads: 1);
  }

  T _pick<T>(List<T> options) => options[_rng.nextInt(options.length)];

  double _magnitude() => _pick(const [10, 15, 20, 25, 30, 40, 50]) * _kN;

  /// Distinct positions on a half-metre grid, strictly between [from] and
  /// [to], avoiding [taken].
  List<double> _positions(int count, double from, double to,
      {List<double> taken = const []}) {
    final grid = <double>[
      for (var x = from + 0.5; x < to - 1e-9; x += 0.5)
        if (taken.every((t) => (t - x).abs() > 1e-9)) x,
    ];
    grid.shuffle(_rng);
    // Prefer whole metres: easier arithmetic, like most textbook problems.
    grid.sort((a, b) => (a % 1 == 0 ? 0 : 1).compareTo(b % 1 == 0 ? 0 : 1));
    final chosen = grid.take(count).toList()..sort();
    return chosen;
  }

  BeamProblem _simplySupported({required int loads, bool inclined = false}) {
    final length = _pick(const [4.0, 5.0, 6.0, 8.0, 10.0]);
    var p = BeamProblem(length: length, supports: [
      const Support(id: 's1', type: SupportType.pin, x: 0),
      Support(id: 's2', type: SupportType.roller, x: length),
    ]);
    final xs = _positions(loads, 0, length);
    for (var i = 0; i < xs.length; i++) {
      final angle = inclined && i == 0 ? _pick(const [-30.0, -45.0, -60.0, -120.0, -135.0, -150.0]) : -90.0;
      p = p.withLoad(PointLoad(
          id: p.nextId('p'), x: xs[i], magnitude: _magnitude(), angleDeg: angle));
    }
    return p;
  }

  BeamProblem _overhang(
      {required int loads, required bool bothSides, bool upward = false}) {
    final length = _pick(const [6.0, 7.0, 8.0, 10.0]);
    final right = _pick(const [1.0, 1.5, 2.0]);
    final left = bothSides ? _pick(const [1.0, 1.5]) : 0.0;
    final pinLeft = _rng.nextBool();
    var p = BeamProblem(length: length, supports: [
      Support(id: 's1', type: pinLeft ? SupportType.pin : SupportType.roller, x: left),
      Support(
          id: 's2',
          type: pinLeft ? SupportType.roller : SupportType.pin,
          x: length - right),
    ]);
    // One load always sits on an overhang: that is the point of the problem.
    final xs = <double>[length];
    if (bothSides && loads > 1) xs.add(0);
    xs.addAll(_positions(loads - xs.length, left, length - right));
    xs.sort();
    for (var i = 0; i < xs.length; i++) {
      final up = upward && i == 0 && xs[i] > left && xs[i] < length - right;
      p = p.withLoad(PointLoad(
          id: p.nextId('p'), x: xs[i], magnitude: _magnitude(), angleDeg: up ? 90 : -90));
    }
    return p;
  }

  /// Adds a distributed load over the whole span or a whole-metre part of
  /// it: uniform, or a triangle rising to one end.
  BeamProblem _withUdl(BeamProblem p, {bool triangle = false}) {
    final w = _pick(const [2.0, 4.0, 5.0, 6.0, 10.0]) * _kN;
    final full = triangle || _rng.nextBool();
    final a = full ? 0.0 : (1 + _rng.nextInt((p.length / 2).floor())).toDouble();
    final b = full ? p.length : math.min(p.length, a + 2 + _rng.nextInt(2));
    final rising = _rng.nextBool();
    return p.withLoad(DistributedLoad(
      id: p.nextId('w'),
      x: a,
      x2: b,
      w1: triangle ? (rising ? 0 : w) : w,
      w2: triangle ? (rising ? w : 0) : w,
    ));
  }

  BeamProblem _withCouple(BeamProblem p) {
    final x = _positions(1, 0, p.length).first;
    return p.withLoad(PointMoment(
      id: p.nextId('c'),
      x: x,
      magnitude: _pick(const [10.0, 15.0, 20.0, 30.0]) * _kN,
      counterClockwise: _rng.nextBool(),
    ));
  }

  BeamProblem _cantilever({required int loads}) {
    final length = _pick(const [2.0, 3.0, 4.0, 5.0]);
    final fixedLeft = _rng.nextBool();
    var p = BeamProblem(length: length, supports: [
      Support(id: 's1', type: SupportType.fixed, x: fixedLeft ? 0 : length),
    ]);
    final free = fixedLeft ? length : 0.0;
    final xs = <double>[free];
    xs.addAll(_positions(loads - 1, 0, length, taken: [free]));
    xs.sort();
    for (final x in xs) {
      p = p.withLoad(PointLoad(id: p.nextId('p'), x: x, magnitude: _magnitude()));
    }
    return p;
  }
}
