import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/beam_scene.dart';
import '../../drawing/palette.dart';
import '../../drawing/viewport.dart';
import '../../state/app_state.dart';
import '../../state/editor_controller.dart';
import '../analysis/analysis_screen.dart';
import '../widgets/tool_icons.dart';
import 'properties_panel.dart';

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
        return Scaffold(
          appBar: AppBar(
            title: Text(
              controller.name ?? s.untitled,
              overflow: TextOverflow.ellipsis,
            ),
            actions: [
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
                onPressed: _save,
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
          ),
          body: Column(
            children: [
              _HintBar(controller: controller),
              Expanded(
                child: EditorCanvas(controller: controller, onMessage: _snack),
              ),
            ],
          ),
          floatingActionButton:
              controller.problem.hasBeam
                  ? FloatingActionButton.extended(
                    onPressed: _analyze,
                    icon: const Icon(Icons.calculate_outlined),
                    label: Text(
                      s.analyze,
                      style: const TextStyle(
                        fontWeight: FontWeight.w900,
                        letterSpacing: 1.2,
                      ),
                    ),
                  )
                  : null,
          bottomNavigationBar: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (controller.selected != null)
                  PropertiesPanel(controller: controller, onMessage: _snack),
                _Toolbar(controller: controller, onMessage: _snack),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _HintBar extends StatelessWidget {
  const _HintBar({required this.controller});

  final EditorController controller;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final text =
        controller.problem.hasBeam
            ? s.hintFor(controller.tool.name)
            : s.hintEmpty;
    return Container(
      width: double.infinity,
      color: Theme.of(
        context,
      ).colorScheme.secondaryContainer.withValues(alpha: 0.6),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      child: Text(text, style: Theme.of(context).textTheme.bodySmall),
    );
  }
}

class _Toolbar extends StatelessWidget {
  const _Toolbar({required this.controller, required this.onMessage});

  final EditorController controller;
  final ValueChanged<String> onMessage;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final scheme = Theme.of(context).colorScheme;
    final tools = <(Tool, String)>[
      (Tool.select, s.toolSelect),
      (Tool.beam, s.toolBeam),
      (Tool.pin, s.toolPin),
      (Tool.roller, s.toolRoller),
      (Tool.fixed, s.toolFixed),
      (Tool.pointLoad, s.toolPointLoad),
      (Tool.udl, s.toolUdl),
      (Tool.uvl, s.toolUvl),
      (Tool.moment, s.toolMoment),
      (Tool.dimension, s.toolDimension),
      (Tool.delete, s.toolDelete),
    ];
    Widget button(
      Widget icon,
      String label,
      bool active,
      bool enabled,
      VoidCallback onTap, {
      bool soon = false,
    }) {
      final color =
          !enabled
              ? scheme.onSurface.withValues(alpha: 0.35)
              : active
              ? scheme.onPrimaryContainer
              : scheme.onSurfaceVariant;
      return Padding(
        key: ValueKey('tool-$label'),
        padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 4),
        child: Material(
          color: active ? scheme.primaryContainer : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          child: InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: onTap,
            child: SizedBox(
              width: 66,
              height: 58,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      IconTheme(data: IconThemeData(color: color), child: icon),
                      const SizedBox(height: 3),
                      Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 10.5,
                          color: color,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                  if (soon)
                    Positioned(
                      top: 3,
                      right: 4,
                      child: Icon(
                        Icons.schedule,
                        size: 11,
                        color: scheme.outline,
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      );
    }

    return Material(
      elevation: 6,
      color: scheme.surfaceContainer,
      child: SizedBox(
        height: 66,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 6),
          children: [
            for (final (tool, label) in tools)
              button(
                ToolIcon(tool),
                label,
                tool == Tool.dimension
                    ? controller.showDimensions
                    : controller.tool == tool,
                !tool.comingSoon,
                () =>
                    tool.comingSoon
                        ? onMessage(s.notInMvp)
                        : controller.setTool(tool),
                soon: tool.comingSoon,
              ),
            button(
              const Icon(Icons.undo),
              s.undo,
              false,
              controller.canUndo,
              controller.undo,
            ),
            button(
              const Icon(Icons.redo),
              s.redo,
              false,
              controller.canRedo,
              controller.redo,
            ),
          ],
        ),
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

enum _Gesture { none, pan, zoom, drag, drawBeam }

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

  EditorController get c => widget.controller;

  void _ensureViewport(Size size) {
    if (size != _size || _vp == null || c.fitRequest != _fitSeen) {
      final refit = _vp == null || c.fitRequest != _fitSeen;
      _size = size;
      if (refit) {
        _fitSeen = c.fitRequest;
        _vp =
            c.problem.hasBeam
                ? SheetView.fit(
                  c.problem.length,
                  size,
                  margin: 56,
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
  );

  /// Snaps a world x to the ends, to other elements within a fingertip, or
  /// else to a quarter-metre grid.
  double _snap(double x, {String? ignore}) {
    final p = c.problem;
    final tol = 12 / _vp!.scale;
    final targets = <double>[
      0,
      p.length,
      for (final s in p.supports)
        if (s.id != ignore) s.x,
      for (final l in p.loads)
        if (l.id != ignore) l.x,
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
    final hit = scene.hitTest(down);
    if (hit != null && hit != 'beam' && c.tool != Tool.delete) {
      _gesture = _Gesture.drag;
      _dragId = hit;
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
      case _Gesture.drag:
        final x = _snap(_vp!.worldX(d.localFocalPoint.dx), ignore: _dragId);
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
      case _Gesture.drag:
        c.endGesture();
      default:
        break;
    }
    _gesture = _Gesture.none;
    _dragId = null;
  }

  void _onTap(Offset p, BeamScene scene, AppState app) {
    final s = app.s;
    final tool = c.tool;
    if (tool.comingSoon) {
      widget.onMessage(s.notInMvp);
      return;
    }
    final placing =
        tool == Tool.pin ||
        tool == Tool.roller ||
        tool == Tool.fixed ||
        tool == Tool.pointLoad;
    if (placing) {
      if (!c.problem.hasBeam) {
        widget.onMessage(s.drawBeamFirst);
        return;
      }
      if ((p.dy - _vp!.origin.dy).abs() > 70 ||
          p.dx < _vp!.sx(0) - 24 ||
          p.dx > _vp!.sx(c.problem.length) + 24) {
        widget.onMessage(s.tapOnBeam);
        return;
      }
      var x = _snap(_vp!.worldX(p.dx).clamp(0.0, c.problem.length).toDouble());
      switch (tool) {
        case Tool.pin:
          c.addSupport(SupportType.pin, x);
        case Tool.roller:
          c.addSupport(SupportType.roller, x);
        case Tool.fixed:
          x = x < c.problem.length / 2 ? 0 : c.problem.length;
          c.addSupport(SupportType.fixed, x);
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
                      painter: BeamScenePainter(scene, grid: true),
                    ),
                  ),
                ),
              );
            },
          ),
    );
  }
}
