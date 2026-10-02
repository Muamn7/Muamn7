import 'package:flutter/foundation.dart';
import 'package:mechsim_core/mechsim_core.dart';

enum Tool {
  select,
  beam,
  pin,
  roller,
  fixed,
  pointLoad,
  udl,
  uvl,
  moment,
  dimension,
  delete;

  /// Tools that are drawn in the toolbar but not available yet.
  bool get comingSoon => false;

  /// Tools that put something on the beam where it is tapped.
  bool get places =>
      this == pin ||
      this == roller ||
      this == fixed ||
      this == pointLoad ||
      this == udl ||
      this == uvl ||
      this == moment;

  bool get isSupport => this == pin || this == roller || this == fixed;
  bool get isDistributed => this == udl || this == uvl;
}

/// What a newly placed load starts as: set beforehand in the side panel
/// (sideways), so a student can choose 25 kN up before tapping the beam.
class PlacementDefaults {
  double pointMagnitude = 10000;
  double pointAngle = -90;
  double intensity = 10000;
  bool distributedUpward = false;
  double moment = 10000;
  bool counterClockwise = true;
}

/// The state of the drawing screen: the problem, its history, the active
/// tool and the selection. Every committed edit is a new immutable
/// [BeamProblem] pushed on the undo stack.
class EditorController extends ChangeNotifier {
  EditorController({BeamProblem? problem, this.savedId, String? name})
    : _problem = problem ?? const BeamProblem(),
      _name = name,
      _tool = (problem?.hasBeam ?? false) ? Tool.select : Tool.beam;

  BeamProblem _problem;
  final List<BeamProblem> _undo = [];
  final List<BeamProblem> _redo = [];
  BeamProblem? _gestureBase;
  Tool _tool;
  String? _selected;
  bool _showDimensions = true;
  bool _showGrid = true;
  bool _snap = true;
  final PlacementDefaults defaults = PlacementDefaults();

  /// The kind of support and of distributed load used last, which the
  /// sideways tool list's single Support and Distributed Load entries pick.
  Tool lastSupport = Tool.pin;
  Tool lastDistributed = Tool.udl;
  String? savedId;
  String? _name;

  /// Bumped when the view should be refitted to the beam.
  int fitRequest = 0;

  BeamProblem get problem => _problem;
  Tool get tool => _tool;
  String? get selected => _selected;
  bool get showDimensions => _showDimensions;
  bool get showGrid => _showGrid;

  /// Whether dragged and placed elements snap to the grid and to each other.
  bool get snap => _snap;
  bool get canUndo => _undo.isNotEmpty;
  bool get canRedo => _redo.isNotEmpty;
  String? get name => _name;

  set name(String? value) {
    _name = value;
    notifyListeners();
  }

  void setTool(Tool tool) {
    if (tool == Tool.dimension) {
      _showDimensions = !_showDimensions;
    } else {
      _tool = tool;
      if (tool.isSupport) lastSupport = tool;
      if (tool.isDistributed) lastDistributed = tool;
      if (tool != Tool.select) _selected = null;
    }
    notifyListeners();
  }

  void setShowGrid(bool value) {
    _showGrid = value;
    notifyListeners();
  }

  void setShowDimensions(bool value) {
    _showDimensions = value;
    notifyListeners();
  }

  void setSnap(bool value) {
    _snap = value;
    notifyListeners();
  }

  void updateDefaults(void Function(PlacementDefaults d) change) {
    change(defaults);
    notifyListeners();
  }

  void select(String? id) {
    _selected = id;
    notifyListeners();
  }

  /// Replaces the problem as one undoable step.
  void commit(BeamProblem next) {
    if (next == _problem) return;
    _undo.add(_problem);
    _redo.clear();
    _problem = next;
    if (_selected != null &&
        _selected != 'beam' &&
        !_problem.contains(_selected!)) {
      _selected = null;
    }
    notifyListeners();
  }

  /// Starts a drag: changes are shown live and committed once at the end.
  void beginGesture() => _gestureBase ??= _problem;

  void preview(BeamProblem next) {
    _problem = next;
    notifyListeners();
  }

  void endGesture() {
    final base = _gestureBase;
    _gestureBase = null;
    if (base == null || base == _problem) return;
    _undo.add(base);
    _redo.clear();
    notifyListeners();
  }

  void undo() {
    if (_undo.isEmpty) return;
    _redo.add(_problem);
    _problem = _undo.removeLast();
    _fixSelection();
    notifyListeners();
  }

  void redo() {
    if (_redo.isEmpty) return;
    _undo.add(_problem);
    _problem = _redo.removeLast();
    _fixSelection();
    notifyListeners();
  }

  void _fixSelection() {
    if (_selected == 'beam' && !_problem.hasBeam) _selected = null;
    if (_selected != null &&
        _selected != 'beam' &&
        !_problem.contains(_selected!)) {
      _selected = null;
    }
  }

  // ---- edits -------------------------------------------------------------

  /// Draws (or redraws) the beam with the given length.
  void setBeam(double length) {
    commit(
      _problem.hasBeam
          ? _problem.withLength(length)
          : _problem.copyWith(length: length),
    );
    _tool = Tool.select;
    _selected = 'beam';
    fitRequest++;
    notifyListeners();
  }

  void setLength(double length) => commit(_problem.withLength(length));

  String addSupport(SupportType type, double x) {
    final id = _problem.nextId('s');
    commit(_problem.withSupport(Support(id: id, type: type, x: x)));
    _selected = id;
    notifyListeners();
    return id;
  }

  String addLoad(double x) {
    final id = _problem.nextId('p');
    commit(
      _problem.withLoad(
        PointLoad(
          id: id,
          x: x,
          magnitude: defaults.pointMagnitude,
          angleDeg: defaults.pointAngle,
        ),
      ),
    );
    _selected = id;
    notifyListeners();
    return id;
  }

  /// A distributed load from [a] to [b]: uniform at the default intensity
  /// (10 kN/m), or rising from 0 to it.
  String addDistributed(double a, double b, {required bool uniform}) {
    final id = _problem.nextId('w');
    commit(
      _problem.withLoad(
        DistributedLoad(
          id: id,
          x: a,
          x2: b,
          w1: uniform ? defaults.intensity : 0,
          w2: defaults.intensity,
          upward: defaults.distributedUpward,
        ),
      ),
    );
    _selected = id;
    notifyListeners();
    return id;
  }

  String addMoment(double x) {
    final id = _problem.nextId('c');
    commit(
      _problem.withLoad(
        PointMoment(
          id: id,
          x: x,
          magnitude: defaults.moment,
          counterClockwise: defaults.counterClockwise,
        ),
      ),
    );
    _selected = id;
    notifyListeners();
    return id;
  }

  void updateAnyLoad(Load l) => commit(_problem.replaceLoad(l));

  void delete(String id) {
    if (id == 'beam') {
      commit(const BeamProblem());
      _tool = Tool.beam;
    } else {
      commit(_problem.remove(id));
    }
    _selected = null;
    notifyListeners();
  }

  void clear() {
    commit(BeamProblem(title: _problem.title));
    _tool = Tool.beam;
    _selected = null;
    notifyListeners();
  }

  void updateSupport(Support s) => commit(_problem.replaceSupport(s));

  void updateLoad(PointLoad l) => commit(_problem.replaceLoad(l));

  void flipLoad(String id) {
    final l = _problem.loadById(id);
    switch (l) {
      case PointLoad():
        updateLoad(l.copyWith(angleDeg: normaliseAngle(l.angleDeg + 180)));
      case DistributedLoad():
        updateAnyLoad(l.copyWith(upward: !l.upward));
      case PointMoment():
        updateAnyLoad(l.copyWith(counterClockwise: !l.counterClockwise));
      case null:
        break;
    }
  }

  void toggleDimensions() {
    _showDimensions = !_showDimensions;
    notifyListeners();
  }

  void requestFit() {
    fitRequest++;
    notifyListeners();
  }
}
