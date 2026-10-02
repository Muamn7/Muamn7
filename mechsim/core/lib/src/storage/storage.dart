/// Storage: saved problems as JSON. The repository is an interface so the
/// app can keep problems in a file, a test can keep them in memory, and a
/// future device can keep them wherever it likes.
library;

import 'dart:convert';

import '../model/beam_problem.dart';

class SavedProblem {
  const SavedProblem({
    required this.id,
    required this.name,
    required this.savedAt,
    required this.problem,
  });

  final String id;
  final String name;
  final DateTime savedAt;
  final BeamProblem problem;

  SavedProblem copyWith({String? name, DateTime? savedAt, BeamProblem? problem}) =>
      SavedProblem(
        id: id,
        name: name ?? this.name,
        savedAt: savedAt ?? this.savedAt,
        problem: problem ?? this.problem,
      );

  Map<String, Object?> toJson() => {
        'id': id,
        'name': name,
        'savedAt': savedAt.toUtc().toIso8601String(),
        'problem': problem.toJson(),
      };

  factory SavedProblem.fromJson(Map<String, Object?> json) => SavedProblem(
        id: json['id'] as String,
        name: json['name'] as String? ?? '',
        savedAt: DateTime.parse(json['savedAt'] as String),
        problem: BeamProblem.fromJson(json['problem'] as Map<String, Object?>),
      );
}

abstract interface class ProblemRepository {
  /// Newest first.
  Future<List<SavedProblem>> list();

  /// Adds the problem, or replaces the one with the same id.
  Future<void> save(SavedProblem problem);

  Future<void> delete(String id);
}

/// The file format of a whole library of saved problems.
abstract final class ProblemLibraryCodec {
  static const int version = 1;

  static String encode(List<SavedProblem> problems) =>
      const JsonEncoder.withIndent('  ').convert({
        'version': version,
        'problems': [for (final p in problems) p.toJson()],
      });

  /// Problems that cannot be read are skipped rather than losing the rest.
  static List<SavedProblem> decode(String text) {
    if (text.trim().isEmpty) return [];
    final json = jsonDecode(text);
    if (json is! Map<String, Object?>) return [];
    final list = json['problems'];
    if (list is! List<Object?>) return [];
    final result = <SavedProblem>[];
    for (final item in list) {
      try {
        result.add(SavedProblem.fromJson(item! as Map<String, Object?>));
      } on Object {
        // A corrupt entry is dropped; the others still load.
      }
    }
    return result;
  }

  static List<SavedProblem> upsert(List<SavedProblem> all, SavedProblem p) {
    final next = [for (final x in all) if (x.id != p.id) x, p];
    next.sort((a, b) => b.savedAt.compareTo(a.savedAt));
    return next;
  }
}

class InMemoryProblemRepository implements ProblemRepository {
  List<SavedProblem> _items = [];

  @override
  Future<List<SavedProblem>> list() async => List.unmodifiable(_items);

  @override
  Future<void> save(SavedProblem problem) async {
    _items = ProblemLibraryCodec.upsert(_items, problem);
  }

  @override
  Future<void> delete(String id) async {
    _items = [for (final x in _items) if (x.id != id) x];
  }
}
