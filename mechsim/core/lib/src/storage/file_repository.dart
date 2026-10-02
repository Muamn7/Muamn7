/// A [ProblemRepository] backed by one JSON file. Uses dart:io, so it is
/// exported from `package:mechsim_core/io.dart` and not from the main
/// library, which stays free of platform APIs.
library;

import 'dart:io';

import 'storage.dart';

class FileProblemRepository implements ProblemRepository {
  FileProblemRepository(this.file);

  final File file;
  List<SavedProblem>? _cache;

  Future<List<SavedProblem>> _load() async {
    if (_cache != null) return _cache!;
    if (!await file.exists()) return _cache = [];
    try {
      return _cache = ProblemLibraryCodec.decode(await file.readAsString());
    } on FormatException {
      // Keep the unreadable file for inspection and start afresh.
      await file.rename('${file.path}.corrupt');
      return _cache = [];
    }
  }

  Future<void> _write(List<SavedProblem> items) async {
    _cache = items;
    await file.parent.create(recursive: true);
    // Write next to the real file and rename over it, so a crash mid-write
    // never leaves half a library behind.
    final temp = File('${file.path}.tmp');
    await temp.writeAsString(ProblemLibraryCodec.encode(items), flush: true);
    await temp.rename(file.path);
  }

  @override
  Future<List<SavedProblem>> list() async => List.unmodifiable(await _load());

  @override
  Future<void> save(SavedProblem problem) async =>
      _write(ProblemLibraryCodec.upsert(await _load(), problem));

  @override
  Future<void> delete(String id) async =>
      _write([for (final x in await _load()) if (x.id != id) x]);
}
