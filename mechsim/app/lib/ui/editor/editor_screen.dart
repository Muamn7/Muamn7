import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/beam_scene.dart';
import '../../drawing/palette.dart';
import '../../drawing/viewport.dart';
import '../../state/app_state.dart';
import '../../state/editor_controller.dart';
import '../analysis/analysis_screen.dart';
import '../widgets/layout.dart';
import '../widgets/tool_icons.dart';
import 'properties_panel.dart';
import 'wide_editor.dart';

/// "New Problem": an engineering sheet the student draws the problem on.
class EditorScreen extends StatefulWidget {
  const EditorScreen({super.key, this.problem, this.savedId, this.name});

  final BeamProblem? problem;
  final String? savedId;
  final String? name;

  @override
  State<EditorScreen> createState() => _EditorScreenState();
}

class _EditorScreenState extends State<EditorScreen> {
  late final EditorController controller = EditorController(
    problem: widget.problem,
    savedId: widget.savedId,
    name: widget.name,
  );

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  void _snack(String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(text), duration: const Duration(seconds: 2)),
      );
  }

  Future<void> _save() async {
    final app = AppScope.read(context);
    final s = app.s;
    final text = TextEditingController(
      text: controller.name ?? controller.problem.title,
    );
    final name = await showDialog<String>(
      context: context,
      builder:
          (context) => AlertDialog(
            title: Text(s.nameProblem),
            content: TextField(
              controller: text,
              autofocus: true,
              onSubmitted: (v) => Navigator.pop(context, v),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text(s.cancel),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, text.text),
                child: Text(s.save),
              ),
            ],
          ),
    );
    if (name == null || !mounted) return;
    final finalName = name.trim().isEmpty ? s.untitled : name.trim();
    final entry = await app.saveProblem(
      id: controller.savedId,
      name: finalName,
      problem: controller.problem,
    );
    controller.savedId = entry.id;
    controller.name = finalName;
    _snack(s.saved);
  }

  void _analyze() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AnalysisScreen(problem: controller.problem),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final analyze = controller.problem.hasBeam ? _analyze : null;
        final canvas = EditorCanvas(controller: controller, onMessage: _snack);
        if (isWide(context)) {
          return WideEditor(
            controller: controller,
            canvas: canvas,
            onSave: _save,
            onAnalyze: analyze,
            onMessage: _snack,
          );
        }
        return Scaffold(
          appBar: AppBar(
            title: Text(
              controller.name ?? s.untitled,
              overflow: TextOverflow.ellipsis,
            ),
            actions: [_ActionRail(controller: controller, onSave: _save)],
          ),
          body: Column(
            children: [
              _HintBar(controller: controller),
              Expanded(child: canvas),
            ],
          ),
          bottomNavigationBar: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (controller.selected != null)
                  PropertiesPanel(controller: controller, onMessage: _snack),
                _Toolbar(controller: controller, onAnalyze: analyze),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Undo, redo, save and the menu, in the upright app bar.
class _ActionRail extends StatelessWidget {
  const _ActionRail({required this.controller, required this.onSave});

  final EditorController controller;
  final VoidCallback onSave;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          tooltip: s.undo,
          onPressed: controller.canUndo ? controller.undo : null,
          icon: const Icon(Icons.undo),
        ),
        IconButton(
          tooltip: s.redo,
          onPressed: controller.canRedo ? controller.redo : null,
          icon: const Icon(Icons.redo),
        ),
        IconButton(
          tooltip: s.save,
          onPressed: onSave,
          icon: const Icon(Icons.save_outlined),
        ),
        PopupMenuButton<String>(
          onSelected: (v) {
            if (v == 'fit') controller.requestFit();
            if (v == 'clear') controller.clear();
          },
          itemBuilder:
              (_) => [
                PopupMenuItem(value: 'fit', child: Text(s.fitView)),
                PopupMenuItem(value: 'clear', child: Text(s.clearAll)),
              ],
        ),
      ],
    );
  }
}

class _HintBar extends StatelessWidget {
  const _HintBar({required this.controller});

  final EditorController controller;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final theme = Theme.of(context);
    final text =
        controller.problem.hasBeam
            ? s.hintFor(controller.tool.name)
            : s.hintEmpty;
    return Container(
      width: double.infinity,
      color: theme.colorScheme.secondaryContainer.withValues(alpha: 0.6),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      child: Text(text, style: theme.textTheme.bodySmall),
    );
  }
}

class _Toolbar extends StatelessWidget {
  const _Toolbar({required this.controller, required this.onAnalyze});

  final EditorController controller;

  /// Null until there is a beam to analyse.
  final VoidCallback? onAnalyze;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final scheme = Theme.of(context).colorScheme;
    // Every tool in view at once, nothing to scroll: the beam and its
    // supports in one row, the loads in the other, with ANALYZE closing
    // the loads row so it never covers the drawing.
    final groups = <List<(Tool, String)>>[
      [
        (Tool.select, s.toolSelect),
        (Tool.beam, s.toolBeam),
        (Tool.pin, s.toolPin),
        (Tool.roller, s.toolRoller),
        (Tool.fixed, s.toolFixed),
        (Tool.delete, s.toolDelete),
      ],
      [
        (Tool.pointLoad, s.toolPointLoad),
        (Tool.udl, s.toolUdl),
        (Tool.uvl, s.toolUvl),
        (Tool.moment, s.toolMoment),
        (Tool.dimension, s.toolDimension),
      ],
    ];

    Widget slot({
      required Key key,
      required Widget icon,
      required String label,
      required Color background,
      required Color foreground,
      required VoidCallback? onTap,
      FontWeight weight = FontWeight.w700,
    }) {
      return Padding(
        key: key,
        padding: const EdgeInsets.all(2),
        child: Material(
          color: background,
          borderRadius: BorderRadius.circular(12),
          child: InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 3),
              child: Center(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconTheme(
                        data: IconThemeData(color: foreground),
                        child: icon,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        label,
                        maxLines: 1,
                        style: TextStyle(
                          fontSize: 10.5,
                          color: foreground,
                          fontWeight: weight,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    Widget button(Tool tool, String label) {
      final active =
          tool == Tool.dimension
              ? controller.showDimensions
              : controller.tool == tool;
      return slot(
        key: ValueKey('tool-$label'),
        icon: ToolIcon(tool),
        label: label,
        background: active ? scheme.primaryContainer : Colors.transparent,
        foreground:
            active ? scheme.onPrimaryContainer : scheme.onSurfaceVariant,
        onTap: () => controller.setTool(tool),
      );
    }

    final analyze = slot(
      key: const ValueKey('tool-ANALYZE'),
      icon: const Icon(Icons.calculate_outlined),
      label: s.analyze,
      background:
          onAnalyze == null
              ? scheme.onSurface.withValues(alpha: 0.08)
              : scheme.primary,
      foreground:
          onAnalyze == null
              ? scheme.onSurface.withValues(alpha: 0.38)
              : scheme.onPrimary,
      onTap: onAnalyze,
      weight: FontWeight.w900,
    );

    Widget group(List<(Tool, String)> tools, {bool loads = false}) {
      final children = [
        for (final (tool, label) in tools) Expanded(child: button(tool, label)),
        if (loads) Expanded(child: analyze),
      ];
      final tint =
          loads
              ? scheme.tertiaryContainer.withValues(alpha: 0.35)
              : Colors.transparent;
      return Container(
        color: tint,
        child: SizedBox(height: 54, child: Row(children: children)),
      );
    }

    final both = [group(groups[0]), group(groups[1], loads: true)];
    return Material(
      elevation: 6,
      color: scheme.surfaceContainer,
      child: Padding(
        padding: const EdgeInsets.all(2),
        child: Column(mainAxisSize: MainAxisSize.min, children: both),
      ),
    );
  }
}

/// The drawing surface: draw the beam with a finger, tap to place supports
/// and loads, drag to move them, pinch to zoom, two fingers (or an empty
/// spot) to pan, long-press for options.
class EditorCanvas extends StatefulWidget {
  const EditorCanvas({
    super.key,
    required this.controller,
    required this.onMessage,
  });

  final EditorController controller;
  final ValueChanged<String> onMessage;

  @override
  State<EditorCanvas> createState() => _EditorCanvasState();
}

enum _Gesture { none, pan, zoom, drag, drawBeam, drawRange }

class _EditorCanvasState extends State<EditorCanvas> {
  SheetView? _vp;
  Size _size = Size.zero;
  int _fitSeen = -1;

  _Gesture _gesture = _Gesture.none;
  SheetView? _startVp;
  Offset _startFocal = Offset.zero;
  String? _dragId;
  double? _ghost;
  double _beamStartX = 0;
  Offset? _down;

  /// A distributed load being dragged out: where the finger started, and
  /// where it is now.
  (double, double)? _range;

  /// Where along a distributed load the finger picked it up.
  double _grab = 0;

  EditorController get c => widget.controller;

  void _ensureViewport(Size size) {
    if (size != _size || _vp == null || c.fitRequest != _fitSeen) {
      var refit = _vp == null || c.fitRequest != _fitSeen;
      // After a rotation or a side panel opening, refit if the beam no
      // longer sits inside the sheet.
      if (!refit && size != _size && c.problem.hasBeam) {
        final left = _vp!.sx(0), right = _vp!.sx(c.problem.length);
        final y = _vp!.origin.dy;
        refit =
            left < 8 ||
            right > size.width - 8 ||
            y < 40 ||
            y > size.height - 40;
      }
      _size = size;
      if (refit) {
        _fitSeen = c.fitRequest;
        _vp =
            c.problem.hasBeam
                ? SheetView.fit(
                  c.problem.length,
                  size,
                  // Sideways the sheet is short and wide: thinner margins
                  // give the beam more of it.
                  margin: size.width > size.height ? 40 : 56,
                  yFraction: 0.45,
                )
                : SheetView(scale: 50, origin: Offset(40, size.height * 0.45));
      }
    }
  }

  BeamScene _scene(MechColors colors, UnitSystem units) => BeamScene(
    problem: c.problem,
    viewport: _vp!,
    colors: colors,
    units: units,
    selectedId: c.selected,
    showDimensions: c.showDimensions,
    ghostLength: _ghost,
    ghostRange: _range,
  );

  /// Snaps a world x to the ends, to other elements within a fingertip, or
  /// else to a quarter-metre grid. With snapping off, only to the nearest
  /// centimetre.
  double _snap(double x, {String? ignore}) {
    final p = c.problem;
    if (!c.snap) {
      return ((x * 100).round() / 100).clamp(0.0, p.length).toDouble();
    }
    final tol = 12 / _vp!.scale;
    final targets = <double>[
      0,
      p.length,
      for (final s in p.supports)
        if (s.id != ignore) s.x,
      for (final l in p.loads)
        if (l.id != ignore) ...l.positions,
    ];
    for (final t in targets) {
      if ((t - x).abs() < tol) return t;
    }
    final grid = _vp!.scale >= 60 ? 0.25 : (_vp!.scale >= 25 ? 0.5 : 1.0);
    return ((x / grid).round() * grid).clamp(0.0, p.length).toDouble();
  }

  void _onScaleStart(ScaleStartDetails d, BeamScene scene) {
    _startVp = _vp;
    // A gesture is only recognised after the finger has moved a little;
    // hit-test and start drawing where it first touched down.
    final down = _down ?? d.localFocalPoint;
    _startFocal = down;
    if (d.pointerCount >= 2) {
      _gesture = _Gesture.zoom;
      return;
    }
    if (c.tool == Tool.beam) {
      _gesture = _Gesture.drawBeam;
      _beamStartX = down.dx;
      _vp = SheetView(scale: _vp!.scale, origin: down);
      _ghost = 0;
      setState(() {});
      return;
    }
    if ((c.tool == Tool.udl || c.tool == Tool.uvl) && _onBeam(down)) {
      _gesture = _Gesture.drawRange;
      final x = _snap(_beamX(down));
      setState(() => _range = (x, x));
      return;
    }
    final hit = scene.hitTest(down);
    if (hit != null && hit != 'beam' && c.tool != Tool.delete) {
      _gesture = _Gesture.drag;
      _dragId = hit;
      final load = c.problem.loadById(hit);
      _grab = load is DistributedLoad ? _vp!.worldX(down.dx) - load.x : 0;
      c.select(hit);
      c.beginGesture();
      return;
    }
    _gesture = _Gesture.pan;
  }

  void _onScaleUpdate(ScaleUpdateDetails d) {
    if (d.pointerCount >= 2 && _gesture != _Gesture.zoom) {
      // A second finger turns any gesture into a zoom.
      if (_gesture == _Gesture.drag) c.endGesture();
      _gesture = _Gesture.zoom;
      _startVp = _vp;
      _startFocal = d.localFocalPoint;
      _ghost = null;
      _range = null;
    }
    switch (_gesture) {
      case _Gesture.zoom:
        setState(
          () =>
              _vp = _startVp!
                  .zoom(d.scale, _startFocal)
                  .pan(d.localFocalPoint - _startFocal),
        );
      case _Gesture.pan:
        setState(() => _vp = _startVp!.pan(d.localFocalPoint - _startFocal));
      case _Gesture.drawBeam:
        final x = d.localFocalPoint.dx;
        final left = math.min(_beamStartX, x);
        final length = ((x - _beamStartX).abs() / _vp!.scale * 2).round() / 2;
        setState(() {
          _vp = SheetView(
            scale: _vp!.scale,
            origin: Offset(left, _vp!.origin.dy),
          );
          _ghost = length;
        });
      case _Gesture.drawRange:
        final x = _snap(_beamX(d.localFocalPoint));
        setState(() => _range = (_range!.$1, x));
      case _Gesture.drag:
        final x = _snap(
          _vp!.worldX(d.localFocalPoint.dx) - _grab,
          ignore: _dragId,
        );
        c.preview(c.problem.move(_dragId!, x));
      case _Gesture.none:
        break;
    }
  }

  void _onScaleEnd() {
    switch (_gesture) {
      case _Gesture.drawBeam:
        final length = _ghost ?? 0;
        _ghost = null;
        if (length >= 0.5) {
          c.setBeam(length);
        } else {
          setState(() {});
        }
      case _Gesture.drawRange:
        final (a, b) = _range!;
        _range = null;
        if ((a - b).abs() >= 0.25 - 1e-9) {
          c.addDistributed(
            math.min(a, b),
            math.max(a, b),
            uniform: c.tool == Tool.udl,
          );
        } else {
          // Barely moved: treat it as a tap.
          _placeDistributed(a);
        }
      case _Gesture.drag:
        c.endGesture();
      default:
        break;
    }
    _gesture = _Gesture.none;
    _dragId = null;
    _grab = 0;
  }

  /// Whether a touch is on (or close enough to) the beam to place
  /// something there.
  bool _onBeam(Offset p) =>
      c.problem.hasBeam &&
      (p.dy - _vp!.origin.dy).abs() <= 70 &&
      p.dx >= _vp!.sx(0) - 24 &&
      p.dx <= _vp!.sx(c.problem.length) + 24;

  double _beamX(Offset p) =>
      _vp!.worldX(p.dx).clamp(0.0, c.problem.length).toDouble();

  /// A tap with the UDL or UVL tool: a 2 m load starting where the finger
  /// touched (pulled back if it would run off the end).
  void _placeDistributed(double x) {
    final length = c.problem.length;
    final span = math.min(2.0, length);
    final a = x.clamp(0.0, length - span).toDouble();
    c.addDistributed(a, a + span, uniform: c.tool == Tool.udl);
  }

  void _onTap(Offset p, BeamScene scene, AppState app) {
    final s = app.s;
    final tool = c.tool;
    if (tool.comingSoon) {
      widget.onMessage(s.notInMvp);
      return;
    }
    if (tool.places) {
      if (!c.problem.hasBeam) {
        widget.onMessage(s.drawBeamFirst);
        return;
      }
      if (!_onBeam(p)) {
        widget.onMessage(s.tapOnBeam);
        return;
      }
      var x = _snap(_beamX(p));
      switch (tool) {
        case Tool.pin:
          c.addSupport(SupportType.pin, x);
        case Tool.roller:
          c.addSupport(SupportType.roller, x);
        case Tool.fixed:
          x = x < c.problem.length / 2 ? 0 : c.problem.length;
          c.addSupport(SupportType.fixed, x);
        case Tool.udl || Tool.uvl:
          _placeDistributed(x);
        case Tool.moment:
          c.addMoment(x);
        default:
          c.addLoad(x);
      }
      return;
    }
    final hit = scene.hitTest(p);
    if (tool == Tool.delete) {
      if (hit != null) c.delete(hit);
      return;
    }
    c.select(hit);
  }

  Future<void> _onLongPress(Offset p, BeamScene scene, AppState app) async {
    final hit = scene.hitTest(p);
    if (hit == null) return;
    c.select(hit);
    final s = app.s;
    final isLoad = c.problem.loadById(hit) != null;
    final action = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder:
          (context) => SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ListTile(
                  leading: const Icon(Icons.tune),
                  title: Text(s.edit),
                  onTap: () => Navigator.pop(context, 'edit'),
                ),
                if (isLoad)
                  ListTile(
                    leading: const Icon(Icons.swap_vert),
                    title: Text(s.flip),
                    onTap: () => Navigator.pop(context, 'flip'),
                  ),
                ListTile(
                  leading: const Icon(Icons.delete_outline),
                  title: Text(s.delete),
                  onTap: () => Navigator.pop(context, 'delete'),
                ),
              ],
            ),
          ),
    );
    if (action == 'flip') c.flipLoad(hit);
    if (action == 'delete') c.delete(hit);
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final colors = MechColors.of(context);
    return ListenableBuilder(
      listenable: c,
      builder:
          (context, _) => LayoutBuilder(
            builder: (context, constraints) {
              _ensureViewport(constraints.biggest);
              final scene = _scene(colors, app.units);
              return Listener(
                onPointerDown: (e) => _down = e.localPosition,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onScaleStart: (d) => _onScaleStart(d, scene),
                  onScaleUpdate: _onScaleUpdate,
                  onScaleEnd: (_) => _onScaleEnd(),
                  onTapUp: (d) => _onTap(d.localPosition, scene, app),
                  onLongPressStart:
                      (d) => _onLongPress(d.localPosition, scene, app),
                  child: ClipRect(
                    child: CustomPaint(
                      size: constraints.biggest,
                      painter: BeamScenePainter(scene, grid: c.showGrid),
                    ),
                  ),
                ),
              );
            },
          ),
    );
  }
}
