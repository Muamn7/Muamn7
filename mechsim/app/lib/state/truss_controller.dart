import 'package:flutter/foundation.dart';
import 'package:mechsim_core/mechsim_core.dart';

enum TrussTool { select, joint, member, pin, roller, load, delete }

/// The state of the truss editor: the problem with its history, the tool,
/// the selection, and a joint a member is being drawn from.
class TrussController extends ChangeNotifier {
  TrussController({TrussProblem? problem})
    : _problem = problem ?? const TrussProblem(),
      _tool =
          (problem?.nodes.isNotEmpty ?? false)
              ? TrussTool.select
              : TrussTool.joint;

  TrussProblem _problem;
  final List<TrussProblem> _undo = [];
  final List<TrussProblem> _redo = [];
  TrussProblem? _gestureBase;
  TrussTool _tool;
  String? _selected;
  String? _pending;

  /// What a new load starts as.
  double loadMagnitude = 10000;
  double loadAngle = -90;

  /// Bumped when the view should be refitted to the truss.
  int fitRequest = 0;

  TrussProblem get problem => _problem;
  TrussTool get tool => _tool;
  String? get selected => _selected;

  /// The joint the next member starts from (member tool).
  String? get pending => _pending;
  bool get canUndo => _undo.isNotEmpty;
  bool get canRedo => _redo.isNotEmpty;

  void setTool(TrussTool tool) {
    _tool = tool;
    _pending = null;
    if (tool != TrussTool.select) _selected = null;
    notifyListeners();
  }

  void select(String? id) {
    _selected = id;
    notifyListeners();
  }

  void setPending(String? node) {
    _pending = node;
    notifyListeners();
  }

  void commit(TrussProblem next) {
    if (next == _problem) return;
    _undo.add(_problem);
    _redo.clear();
    _problem = next;
    if (_selected != null && !_problem.contains(_selected!)) _selected = null;
    if (_pending != null && _problem.node(_pending!) == null) _pending = null;
    notifyListeners();
  }

  void beginGesture() => _gestureBase ??= _problem;

  void preview(TrussProblem next) {
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
    _selected = null;
    _pending = null;
    notifyListeners();
  }

  void redo() {
    if (_redo.isEmpty) return;
    _undo.add(_problem);
    _problem = _redo.removeLast();
    _selected = null;
    _pending = null;
    notifyListeners();
  }

  String addJoint(double x, double y) {
    final id = _problem.nextId('n');
    commit(_problem.withNode(TrussNode(id: id, x: x, y: y)));
    return id;
  }

  /// Adds a member; false when it would duplicate one or join a joint to
  /// itself.
  bool addMember(String a, String b) {
    final before = _problem;
    commit(
      _problem.withMember(TrussMember(id: _problem.nextId('m'), a: a, b: b)),
    );
    return !identical(before, _problem);
  }

  void setSupport(String node, TrussSupportType type) {
    final existing = _problem.supportAt(node);
    commit(
      _problem.withSupport(
        TrussSupport(
          id: existing?.id ?? _problem.nextId('s'),
          node: node,
          type: type,
        ),
      ),
    );
    _selected = _problem.supportAt(node)?.id;
    notifyListeners();
  }

  String addLoad(String node) {
    final id = _problem.nextId('f');
    commit(
      _problem.withLoad(
        TrussLoad(
          id: id,
          node: node,
          magnitude: loadMagnitude,
          angleDeg: loadAngle,
        ),
      ),
    );
    _selected = id;
    notifyListeners();
    return id;
  }

  void delete(String id) {
    commit(_problem.remove(id));
    _selected = null;
    notifyListeners();
  }

  void moveJoint(String id, double x, double y) =>
      preview(_problem.moveNode(id, x, y));

  void updateNode(TrussNode n) => commit(_problem.replaceNode(n));
  void updateSupport(TrussSupport s) => commit(_problem.replaceSupport(s));
  void updateLoad(TrussLoad l) => commit(_problem.replaceLoad(l));

  void loadTemplate(String kind) {
    commit(TrussTemplates.build(kind));
    _tool = TrussTool.select;
    _selected = null;
    _pending = null;
    fitRequest++;
    notifyListeners();
  }

  void clear() {
    commit(const TrussProblem());
    _tool = TrussTool.joint;
    _selected = null;
    _pending = null;
    notifyListeners();
  }

  void requestFit() {
    fitRequest++;
    notifyListeners();
  }
}
