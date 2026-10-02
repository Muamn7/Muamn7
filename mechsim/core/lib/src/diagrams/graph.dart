/// Graph Engine: turns a piecewise function into something a renderer can
/// draw without knowing any mechanics — an outline in (x, value) space with
/// the vertical jumps at point loads, and the values worth labelling.
library;

import 'internal_forces.dart';
import 'polynomial.dart';

class DiagramPoint {
  const DiagramPoint(this.x, this.value);

  final double x;
  final double value;

  @override
  String toString() => '($x, $value)';
}

enum KeyRole {
  /// The value of a segment where the diagram is flat.
  plateau,

  /// A value at a breakpoint (the same on both sides).
  breakpoint,

  /// One of the two values at a jump.
  jump,

  /// A maximum or minimum inside a segment.
  extreme,
}

class KeyValue {
  const KeyValue(this.x, this.value, this.role, [this.side]);

  final double x;
  final double value;
  final KeyRole role;
  final Side? side;
}

class DiagramGeometry {
  const DiagramGeometry({
    required this.kind,
    required this.outline,
    required this.keyValues,
    required this.minValue,
    required this.maxValue,
    required this.length,
  });

  final DiagramKind kind;

  /// Starts and ends on the axis, so it can be filled as a closed shape.
  final List<DiagramPoint> outline;
  final List<KeyValue> keyValues;
  final double minValue;
  final double maxValue;
  final double length;

  double get span => maxValue - minValue;
}

abstract final class GraphEngine {
  static DiagramGeometry build(PiecewiseFunction f, DiagramKind kind,
      {int samplesPerCurvedPiece = 32}) {
    const tol = 1e-9;
    final outline = <DiagramPoint>[];
    final keys = <KeyValue>[];
    var minValue = 0.0, maxValue = 0.0;

    void point(double x, double v) {
      outline.add(DiagramPoint(x, v));
      if (v < minValue) minValue = v;
      if (v > maxValue) maxValue = v;
    }

    if (f.pieces.isEmpty) {
      return DiagramGeometry(
          kind: kind,
          outline: const [],
          keyValues: const [],
          minValue: 0,
          maxValue: 0,
          length: 0);
    }

    point(f.start, 0);
    for (final piece in f.pieces) {
      point(piece.x0, piece.start);
      if (piece.p.degree >= 2) {
        for (var i = 1; i < samplesPerCurvedPiece; i++) {
          final x = piece.x0 + (piece.x1 - piece.x0) * i / samplesPerCurvedPiece;
          point(x, piece.p.eval(x));
        }
      }
      point(piece.x1, piece.end);
    }
    point(f.end, 0);

    bool zero(double v) => v.abs() <= tol * (1 + maxValue.abs() + minValue.abs());

    for (var i = 0; i < f.pieces.length; i++) {
      final piece = f.pieces[i];
      if (piece.p.degree == 0) {
        if (!zero(piece.start)) {
          keys.add(KeyValue((piece.x0 + piece.x1) / 2, piece.start, KeyRole.plateau));
        }
        continue;
      }
      for (final x in piece.p.derivative().rootsIn(piece.x0, piece.x1)) {
        if (x > piece.x0 + tol && x < piece.x1 - tol) {
          keys.add(KeyValue(x, piece.p.eval(x), KeyRole.extreme));
        }
      }
    }

    for (final x in f.breakpoints) {
      final left = f.leftLimit(x);
      final right = f.rightLimit(x);
      final leftPiece = _pieceEndingAt(f, x);
      final rightPiece = _pieceStartingAt(f, x);
      // Flat pieces are already labelled once in their middle.
      final leftFlat = leftPiece == null || leftPiece.p.degree == 0;
      final rightFlat = rightPiece == null || rightPiece.p.degree == 0;
      if ((left - right).abs() <= tol * (1 + left.abs() + right.abs())) {
        if (!zero(left) && !(leftFlat && rightFlat)) {
          keys.add(KeyValue(x, left, KeyRole.breakpoint));
        }
      } else {
        if (!zero(left) && !leftFlat) {
          keys.add(KeyValue(x, left, KeyRole.jump, Side.left));
        }
        if (!zero(right) && !rightFlat) {
          keys.add(KeyValue(x, right, KeyRole.jump, Side.right));
        }
      }
    }

    keys.sort((a, b) => a.x.compareTo(b.x));
    return DiagramGeometry(
      kind: kind,
      outline: outline,
      keyValues: keys,
      minValue: minValue,
      maxValue: maxValue,
      length: f.end,
    );
  }

  static Piece? _pieceEndingAt(PiecewiseFunction f, double x) {
    for (final p in f.pieces) {
      if ((p.x1 - x).abs() < 1e-9) return p;
    }
    return null;
  }

  static Piece? _pieceStartingAt(PiecewiseFunction f, double x) {
    for (final p in f.pieces) {
      if ((p.x0 - x).abs() < 1e-9) return p;
    }
    return null;
  }
}
