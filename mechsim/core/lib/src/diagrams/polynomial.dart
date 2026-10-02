/// Polynomials in x and piecewise functions built from them.
///
/// With point loads only, shear is piecewise constant and moment piecewise
/// linear. A UDL makes them linear/quadratic and a UVL quadratic/cubic, so
/// the diagrams are represented as general piecewise polynomials from the
/// start: adding distributed loads later adds pieces, not a new engine.
library;

import 'dart:math' as math;

class Polynomial {
  /// [coefficients][i] multiplies xⁱ.
  Polynomial(List<double> coefficients)
      : c = List.unmodifiable(_trimmed(coefficients));

  Polynomial.constant(double value) : this([value]);

  /// a·(x − x0): the moment arm term of a force at x0.
  Polynomial.shiftedLinear(double a, double x0) : this([-a * x0, a]);

  static final zero = Polynomial(const [0]);

  final List<double> c;

  int get degree => c.length - 1;

  double eval(double x) {
    var result = 0.0;
    for (var i = c.length - 1; i >= 0; i--) {
      result = result * x + c[i];
    }
    return result;
  }

  Polynomial operator +(Polynomial other) {
    final n = math.max(c.length, other.c.length);
    return Polynomial([
      for (var i = 0; i < n; i++)
        (i < c.length ? c[i] : 0) + (i < other.c.length ? other.c[i] : 0),
    ]);
  }

  Polynomial operator -(Polynomial other) => this + other.scale(-1);

  Polynomial scale(double k) => Polynomial([for (final v in c) v * k]);

  Polynomial derivative() => c.length <= 1
      ? Polynomial.constant(0)
      : Polynomial([for (var i = 1; i < c.length; i++) c[i] * i]);

  /// p(x − x0) expanded into powers of x, so a term written about a local
  /// coordinate (x − a) can be added to the others.
  Polynomial shifted(double x0) {
    var result = Polynomial.zero;
    // (x − x0)^i built up one factor at a time.
    var power = Polynomial.constant(1);
    for (var i = 0; i < c.length; i++) {
      result += power.scale(c[i]);
      power = Polynomial([-x0 * 1, 1]).times(power);
    }
    return result;
  }

  Polynomial times(Polynomial other) {
    final out = List<double>.filled(c.length + other.c.length - 1, 0);
    for (var i = 0; i < c.length; i++) {
      for (var j = 0; j < other.c.length; j++) {
        out[i + j] += c[i] * other.c[j];
      }
    }
    return Polynomial(out);
  }

  /// The antiderivative that is zero at x = 0.
  Polynomial integral() =>
      Polynomial([0, for (var i = 0; i < c.length; i++) c[i] / (i + 1)]);

  double integrate(double a, double b) {
    final p = integral();
    return p.eval(b) - p.eval(a);
  }

  /// Real roots inside [a, b], found by splitting the interval at the roots
  /// of the derivative (where the polynomial is monotone in between) and
  /// bisecting each piece. Works for any degree.
  List<double> rootsIn(double a, double b, {double tol = 1e-12}) {
    if (degree <= 0) return const [];
    if (degree == 1) {
      final x = -c[0] / c[1];
      return (x >= a - tol && x <= b + tol) ? [x.clamp(a, b).toDouble()] : const [];
    }
    final cuts = [a, ...derivative().rootsIn(a, b, tol: tol), b];
    final roots = <double>[];
    for (var i = 0; i < cuts.length - 1; i++) {
      final lo = cuts[i], hi = cuts[i + 1];
      final flo = eval(lo), fhi = eval(hi);
      if (flo == 0) {
        _addUnique(roots, lo, tol);
      } else if (fhi == 0) {
        _addUnique(roots, hi, tol);
      } else if (flo.sign != fhi.sign) {
        _addUnique(roots, _bisect(lo, hi, flo, tol), tol);
      }
    }
    return roots;
  }

  double _bisect(double lo, double hi, double flo, double tol) {
    for (var i = 0; i < 200 && hi - lo > tol; i++) {
      final mid = (lo + hi) / 2;
      final fm = eval(mid);
      if (fm == 0) return mid;
      if (fm.sign == flo.sign) {
        lo = mid;
        flo = fm;
      } else {
        hi = mid;
      }
    }
    return (lo + hi) / 2;
  }

  static void _addUnique(List<double> list, double x, double tol) {
    if (list.every((v) => (v - x).abs() > tol * 10)) list.add(x);
  }

  bool closeTo(Polynomial other, double tol) {
    final n = math.max(c.length, other.c.length);
    for (var i = 0; i < n; i++) {
      final a = i < c.length ? c[i] : 0.0;
      final b = i < other.c.length ? other.c[i] : 0.0;
      if ((a - b).abs() > tol) return false;
    }
    return true;
  }

  static List<double> _trimmed(List<double> coefficients) {
    var end = coefficients.length;
    while (end > 1 && coefficients[end - 1] == 0) {
      end--;
    }
    return end == 0 ? const [0.0] : coefficients.sublist(0, end);
  }

  @override
  String toString() => 'Polynomial($c)';
}

/// Which side of a point a value is taken from. At a point load the shear
/// has two values, V(x⁻) just before and V(x⁺) just after.
enum Side { left, right }

class Piece {
  const Piece(this.x0, this.x1, this.p);

  final double x0;
  final double x1;
  final Polynomial p;

  double get start => p.eval(x0);
  double get end => p.eval(x1);
}

/// A value of a piecewise function at a point, with the side it was taken on.
class PointValue {
  const PointValue(this.x, this.value, [this.side]);

  final double x;
  final double value;
  final Side? side;
}

class PiecewiseFunction {
  PiecewiseFunction(List<Piece> pieces) : pieces = List.unmodifiable(pieces);

  final List<Piece> pieces;

  double get start => pieces.isEmpty ? 0 : pieces.first.x0;
  double get end => pieces.isEmpty ? 0 : pieces.last.x1;

  List<double> get breakpoints =>
      pieces.isEmpty ? const [] : [pieces.first.x0, ...pieces.map((p) => p.x1)];

  /// The value at [x]. At a breakpoint [side] picks the piece; outside the
  /// beam the value is zero (nothing is there).
  double valueAt(double x, {Side side = Side.right}) {
    const tol = 1e-9;
    if (pieces.isEmpty) return 0;
    if (x < start - tol || x > end + tol) return 0;
    if (side == Side.left && (x - start).abs() <= tol) return 0;
    if (side == Side.right && (x - end).abs() <= tol) return 0;
    for (var i = 0; i < pieces.length; i++) {
      final piece = pieces[i];
      final atEnd = (x - piece.x1).abs() <= tol;
      final atStart = (x - piece.x0).abs() <= tol;
      if (side == Side.left && atEnd) return piece.end;
      if (side == Side.right && atStart) return piece.start;
      if (x > piece.x0 + tol && x < piece.x1 - tol) return piece.p.eval(x);
    }
    return 0;
  }

  double leftLimit(double x) => valueAt(x, side: Side.left);
  double rightLimit(double x) => valueAt(x, side: Side.right);

  /// The piece that contains [x] (the right-hand one at a breakpoint).
  Piece? pieceAt(double x) {
    for (final piece in pieces) {
      if (x >= piece.x0 - 1e-9 && x < piece.x1 - 1e-9) return piece;
    }
    return pieces.isEmpty ? null : pieces.last;
  }

  /// Every value worth inspecting for an extreme: both one-sided limits at
  /// each breakpoint, and the stationary points inside each piece.
  List<PointValue> candidates() {
    final list = <PointValue>[];
    for (final piece in pieces) {
      list.add(PointValue(piece.x0, piece.start, Side.right));
      for (final x in piece.p.derivative().rootsIn(piece.x0, piece.x1)) {
        if (x > piece.x0 + 1e-9 && x < piece.x1 - 1e-9) {
          list.add(PointValue(x, piece.p.eval(x)));
        }
      }
      list.add(PointValue(piece.x1, piece.end, Side.left));
    }
    return list;
  }

  PointValue? get maximum => _pick((a, b) => a.value > b.value + _eps(a, b));
  PointValue? get minimum => _pick((a, b) => a.value < b.value - _eps(a, b));

  /// The value of greatest magnitude, with its sign.
  PointValue? get absMaximum =>
      _pick((a, b) => a.value.abs() > b.value.abs() + _eps(a, b));

  static double _eps(PointValue a, PointValue b) =>
      1e-9 * math.max(1, math.max(a.value.abs(), b.value.abs()));

  PointValue? _pick(bool Function(PointValue a, PointValue b) better) {
    PointValue? best;
    for (final v in candidates()) {
      if (best == null || better(v, best)) best = v;
    }
    return best;
  }

  /// Positions where the function changes sign: a root inside a piece, or a
  /// jump across zero at a breakpoint. A function that merely touches zero
  /// at the ends of the beam does not count.
  List<double> signChanges({double tol = 1e-9}) {
    final xs = <double>[];
    void add(double x) {
      if (xs.every((v) => (v - x).abs() > 1e-9)) xs.add(x);
    }

    double? previous;
    for (final piece in pieces) {
      final startValue = piece.start;
      if (previous != null &&
          previous.abs() > tol &&
          startValue.abs() > tol &&
          previous.sign != startValue.sign) {
        add(piece.x0);
      }
      for (final x in piece.p.rootsIn(piece.x0, piece.x1)) {
        final before = piece.p.eval(math.max(piece.x0, x - 1e-6));
        final after = piece.p.eval(math.min(piece.x1, x + 1e-6));
        if (before.abs() > tol && after.abs() > tol && before.sign != after.sign) {
          add(x);
        }
      }
      final endValue = piece.end;
      if (endValue.abs() > tol) previous = endValue;
    }
    return xs;
  }
}
