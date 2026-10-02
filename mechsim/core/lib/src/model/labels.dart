/// Names for the points and loads of a problem, the way a textbook writes
/// them: supports get the first letters (A, B, …) from left to right, the
/// remaining load points continue the alphabet, and point loads are P1, P2, …
/// from left to right.
library;

import 'beam_problem.dart';

class ProblemLabels {
  ProblemLabels._(this._pointLetters, this._loadNames, this._letterAtX);

  factory ProblemLabels.of(BeamProblem problem) {
    final letters = <String, String>{};
    final letterAtX = <double, String>{};
    var next = 0;

    String take() {
      final letter = _letter(next);
      next++;
      return letter;
    }

    String? existing(double x) {
      for (final entry in letterAtX.entries) {
        if ((entry.key - x).abs() < 1e-9) return entry.value;
      }
      return null;
    }

    final supports = [...problem.supports]..sort((a, b) => a.x.compareTo(b.x));
    for (final s in supports) {
      final letter = existing(s.x) ?? take();
      letters[s.id] = letter;
      letterAtX[s.x] = letter;
    }

    final loads = [...problem.loads]..sort((a, b) => a.x.compareTo(b.x));
    final positions = <(double, String)>[
      for (final l in loads)
        for (final x in l.positions) (x, l.id),
    ]..sort((a, b) => a.$1.compareTo(b.$1));
    for (final (x, id) in positions) {
      final letter = existing(x) ?? take();
      letters.putIfAbsent(id, () => letter);
      letterAtX[x] = letter;
    }

    // P1, P2… for forces, W1, W2… for distributed loads, C1, C2… for
    // couples, each numbered left to right.
    final names = <String, String>{};
    void number<T extends Load>(String prefix) {
      final list = loads.whereType<T>().toList();
      for (var i = 0; i < list.length; i++) {
        names[list[i].id] = '$prefix${i + 1}';
      }
    }

    number<PointLoad>('P');
    number<DistributedLoad>('W');
    number<PointMoment>('C');
    return ProblemLabels._(letters, names, letterAtX);
  }

  final Map<String, String> _pointLetters;
  final Map<String, String> _loadNames;
  final Map<double, String> _letterAtX;

  /// The letter of the point where a support or load sits.
  String pointOf(String elementId) => _pointLetters[elementId] ?? '?';

  /// The letter at position [x], if that position is a labelled point.
  String? pointAt(double x) {
    for (final entry in _letterAtX.entries) {
      if ((entry.key - x).abs() < 1e-9) return entry.value;
    }
    return null;
  }

  /// The name of a load: P1, W1, C1, …
  String loadName(String loadId) => _loadNames[loadId] ?? loadId;

  /// All labelled points, left to right.
  List<({String letter, double x})> get points {
    final list = [
      for (final e in _letterAtX.entries) (letter: e.value, x: e.key),
    ]..sort((a, b) => a.x.compareTo(b.x));
    return list;
  }

  static String _letter(int index) {
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    if (index < alphabet.length) return alphabet[index];
    return '${alphabet[index % alphabet.length]}${index ~/ alphabet.length}';
  }
}
