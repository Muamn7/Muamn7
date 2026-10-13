import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/palette.dart';
import '../../drawing/truss_scene.dart';
import '../../drawing/viewport.dart';
import '../../state/app_state.dart';
import '../../state/editor_controller.dart' show Tool;
import '../../state/truss_controller.dart';
import '../editor/panel_card.dart';
import '../widgets/layout.dart';
import '../widgets/number_field.dart';
import '../widgets/tool_icons.dart';
import 'truss_analysis_screen.dart';

/// "New truss": joints, members between them, supports and loads at the
/// joints, on the same engineering sheet as the beams.
class TrussEditorScreen extends StatefulWidget {
  const TrussEditorScreen({super.key, this.problem});

  final TrussProblem? problem;

  @override
  State<TrussEditorScreen> createState() => _TrussEditorScreenState();
}

class _TrussEditorScreenState extends State<TrussEditorScreen> {
  late final TrussController controller = TrussController(
    problem: widget.problem,
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

  void _analyze() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => TrussAnalysisScreen(problem: controller.problem),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final wide = isWide(context);
        final canAnalyze = controller.problem.members.isNotEmpty;
        final canvas = _TrussCanvas(controller: controller, onMessage: _snack);
        final hint = s.trussHint(controller.tool.name);
        final actions = [
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
          _TemplatesButton(controller: controller),
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
        ];
        final properties =
            controller.selected == null
                ? null
                : _TrussProperties(controller: controller);

        if (wide) {
          return Scaffold(
            body: SafeArea(
              child: Column(
                children: [
                  SizedBox(
                    height: 44,
                    child: Row(
                      children: [
                        const BackButton(),
                        Expanded(
                          child: Text(
                            s.trussEditor,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                        ...actions,
                      ],
                    ),
                  ),
                  Expanded(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        SizedBox(
                          width: 112,
                          child: _TrussTools(
                            controller: controller,
                            vertical: true,
                            onAnalyze: canAnalyze ? _analyze : null,
                          ),
                        ),
                        Expanded(
                          child: Stack(
                            children: [
                              Positioned.fill(child: canvas),
                              PositionedDirectional(
                                top: 6,
                                start: 8,
                                end: 8,
                                child: IgnorePointer(child: _Hint(hint)),
                              ),
                            ],
                          ),
                        ),
                        if (properties != null)
                          SizedBox(
                            width: 220,
                            child: SingleChildScrollView(
                              padding: const EdgeInsets.all(4),
                              child: properties,
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          );
        }
        return Scaffold(
          appBar: AppBar(title: Text(s.trussEditor), actions: actions),
          // The hint floats over the sheet, so changing tools never moves
          // the drawing under the finger.
          body: Stack(
            children: [
              Positioned.fill(child: canvas),
              PositionedDirectional(
                top: 6,
                start: 8,
                end: 8,
                child: IgnorePointer(child: _Hint(hint, maxLines: 2)),
              ),
            ],
          ),
          bottomNavigationBar: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (properties != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(6, 4, 6, 2),
                    child: properties,
                  ),
                _TrussTools(
                  controller: controller,
                  onAnalyze: canAnalyze ? _analyze : null,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _Hint extends StatelessWidget {
  const _Hint(this.text, {this.maxLines = 1});

  final String text;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Align(
      alignment: AlignmentDirectional.topStart,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: theme.colorScheme.secondaryContainer.withValues(alpha: 0.85),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          text,
          maxLines: maxLines,
          overflow: TextOverflow.ellipsis,
          style: theme.textTheme.bodySmall,
        ),
      ),
    );
  }
}

class _TemplatesButton extends StatelessWidget {
  const _TemplatesButton({required this.controller});

  final TrussController controller;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final names = s.templateNames.split('|');
    return PopupMenuButton<String>(
      key: const ValueKey('truss-templates'),
      tooltip: s.templates,
      icon: const Icon(Icons.change_history),
      onSelected: controller.loadTemplate,
      itemBuilder:
          (_) => [
            for (var i = 0; i < TrussTemplates.kinds.length; i++)
              PopupMenuItem(
                key: ValueKey('template-${TrussTemplates.kinds[i]}'),
                value: TrussTemplates.kinds[i],
                child: Text(names[i]),
              ),
          ],
    );
  }
}

/// The tools: two rows under the sheet, or a column beside it sideways.
class _TrussTools extends StatelessWidget {
  const _TrussTools({
    required this.controller,
    required this.onAnalyze,
    this.vertical = false,
  });

  final TrussController controller;
  final VoidCallback? onAnalyze;
  final bool vertical;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final scheme = Theme.of(context).colorScheme;
    final tools = <(TrussTool, String, Widget)>[
      (TrussTool.select, s.toolSelect, const ToolIcon(Tool.select)),
      (TrussTool.joint, s.toolJoint, const Icon(Icons.adjust)),
      (TrussTool.member, s.toolMember, const Icon(Icons.linear_scale)),
      (TrussTool.pin, s.toolPin, const ToolIcon(Tool.pin)),
      (TrussTool.roller, s.toolRoller, const ToolIcon(Tool.roller)),
      (TrussTool.load, s.toolLoad, const ToolIcon(Tool.pointLoad)),
      (TrussTool.delete, s.toolDelete, const ToolIcon(Tool.delete)),
    ];

    Widget button((TrussTool, String, Widget) item) {
      final (tool, label, icon) = item;
      final active = controller.tool == tool;
      final fg = active ? scheme.onPrimary : scheme.onSurfaceVariant;
      return Padding(
        key: ValueKey('truss-tool-${tool.name}'),
        padding: const EdgeInsets.all(2),
        child: Material(
          color: active ? scheme.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
          child: InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: () => controller.setTool(tool),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
              child:
                  vertical
                      ? Row(
                        children: [
                          IconTheme(
                            data: IconThemeData(color: fg, size: 20),
                            child: icon,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: FittedBox(
                              fit: BoxFit.scaleDown,
                              alignment: AlignmentDirectional.centerStart,
                              child: Text(
                                label,
                                style: TextStyle(
                                  color: fg,
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ),
                        ],
                      )
                      : Center(
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              IconTheme(
                                data: IconThemeData(color: fg, size: 24),
                                child: icon,
                              ),
                              const SizedBox(height: 2),
                              Text(
                                label,
                                style: TextStyle(
                                  color: fg,
                                  fontSize: 10.5,
                                  fontWeight: FontWeight.w700,
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

    final analyze = Padding(
      padding: const EdgeInsets.all(3),
      child: FilledButton.icon(
        key: const ValueKey('truss-analyze'),
        onPressed: onAnalyze,
        style: FilledButton.styleFrom(
          minimumSize: const Size(0, 42),
          padding: const EdgeInsets.symmetric(horizontal: 10),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
        icon: const Icon(Icons.play_arrow_rounded, size: 20),
        label: FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(
            s.analyze,
            style: const TextStyle(fontWeight: FontWeight.w900),
          ),
        ),
      ),
    );

    if (vertical) {
      return Column(
        children: [for (final t in tools) Expanded(child: button(t)), analyze],
      );
    }
    return Material(
      elevation: 6,
      color: scheme.surfaceContainer,
      child: Padding(
        padding: const EdgeInsets.all(2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              height: 54,
              child: Row(
                children: [
                  for (final t in tools.take(4)) Expanded(child: button(t)),
                ],
              ),
            ),
            SizedBox(
              height: 54,
              child: Row(
                children: [
                  for (final t in tools.skip(4)) Expanded(child: button(t)),
                  Expanded(child: analyze),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The selected joint's coordinates, a member's length, a support's type
/// or a load's size and direction.
class _TrussProperties extends StatelessWidget {
  const _TrussProperties({required this.controller});

  final TrussController controller;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final u = app.units;
    final p = controller.problem;
    final id = controller.selected!;
    final labels = TrussLabels.of(p);
    double toL(double si) => u.toDisplay(si, Dimension.length);
    double fromL(double v) => u.fromDisplay(v, Dimension.length);
    const w = _fieldWidth;

    final actions = [
      IconButton(
        style: PanelCard.smallButton,
        iconSize: 18,
        tooltip: s.delete,
        onPressed: () => controller.delete(id),
        icon: const Icon(Icons.delete_outline),
      ),
      IconButton(
        style: PanelCard.smallButton,
        iconSize: 18,
        tooltip: s.cancel,
        onPressed: () => controller.select(null),
        icon: const Icon(Icons.close),
      ),
    ];

    if (p.node(id) case final node?) {
      return PanelCard(
        key: ValueKey('truss-props-$id'),
        icon: const Icon(Icons.adjust),
        title: '${s.jointProps} ${labels.node(id)}',
        actions: actions,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              NumberField(
                key: ValueKey('joint-x-$id'),
                label: 'x',
                value: toL(node.x),
                unit: u.length.symbol,
                width: w,
                dense: true,
                allowNegative: true,
                onChanged:
                    (v) => controller.updateNode(node.copyWith(x: fromL(v))),
              ),
              NumberField(
                key: ValueKey('joint-y-$id'),
                label: 'y',
                value: toL(node.y),
                unit: u.length.symbol,
                width: w,
                dense: true,
                allowNegative: true,
                onChanged:
                    (v) => controller.updateNode(node.copyWith(y: fromL(v))),
              ),
            ],
          ),
        ],
      );
    }
    if (p.member(id) case final m?) {
      return PanelCard(
        key: ValueKey('truss-props-$id'),
        icon: const Icon(Icons.linear_scale),
        title: '${s.memberProps} ${labels.member(m)}',
        actions: actions,
        children: [
          Text(
            '${s.memberLength} = ${Num.compact(toL(p.lengthOf(m)), maxDecimals: 3)} ${u.length.symbol}',
            textDirection: TextDirection.ltr,
          ),
        ],
      );
    }
    for (final sup in p.supports) {
      if (sup.id != id) continue;
      return PanelCard(
        key: ValueKey('truss-props-$id'),
        icon: ToolIcon(
          sup.type == TrussSupportType.pin ? Tool.pin : Tool.roller,
        ),
        title: '${s.supportProps} ${labels.node(sup.node)}',
        actions: actions,
        children: [
          SegmentedButton<TrussSupportType>(
            showSelectedIcon: false,
            expandedInsets: EdgeInsets.zero,
            segments: [
              ButtonSegment(
                value: TrussSupportType.pin,
                label: Text(s.toolPin),
                icon: const ToolIcon(Tool.pin, size: 18),
              ),
              ButtonSegment(
                value: TrussSupportType.roller,
                label: Text(s.toolRoller),
                icon: const ToolIcon(Tool.roller, size: 18),
              ),
            ],
            selected: {sup.type},
            onSelectionChanged:
                (v) => controller.updateSupport(sup.copyWith(type: v.single)),
          ),
        ],
      );
    }
    if (p.load(id) case final load?) {
      return PanelCard(
        key: ValueKey('truss-props-$id'),
        icon: const ToolIcon(Tool.pointLoad),
        title: '${s.trussLoadProps} @ ${labels.node(load.node)}',
        actions: actions,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              NumberField(
                key: ValueKey('truss-load-$id'),
                label: s.magnitude,
                value: u.toDisplay(load.magnitude, Dimension.force),
                unit: u.force.symbol,
                width: w,
                dense: true,
                validator: (v) => v > 0 ? null : s.mustBePositive,
                onChanged:
                    (v) => controller.updateLoad(
                      load.copyWith(
                        magnitude: u.fromDisplay(v, Dimension.force),
                      ),
                    ),
              ),
              SizedBox(
                width: w,
                child: DirectionDropdown(
                  label: s.direction,
                  angleDeg: normaliseAngle(load.angleDeg),
                  onChanged:
                      (a) => controller.updateLoad(load.copyWith(angleDeg: a)),
                ),
              ),
              NumberField(
                key: ValueKey('truss-angle-$id'),
                label: s.angle,
                value: normaliseAngle(load.angleDeg),
                unit: '°',
                width: w,
                dense: true,
                allowNegative: true,
                onChanged:
                    (v) => controller.updateLoad(
                      load.copyWith(angleDeg: normaliseAngle(v)),
                    ),
              ),
            ],
          ),
        ],
      );
    }
    return const SizedBox.shrink();
  }
}

const _fieldWidth = 96.0;

enum _Gesture { none, pan, zoom, dragJoint, drawMember }

/// The sheet: tap to place joints, drag between joints to draw members,
/// tap joints for supports and loads, drag joints to move them, pinch to
/// zoom, drag empty space to pan.
class _TrussCanvas extends StatefulWidget {
  const _TrussCanvas({required this.controller, required this.onMessage});

  final TrussController controller;
  final ValueChanged<String> onMessage;

  @override
  State<_TrussCanvas> createState() => _TrussCanvasState();
}

class _TrussCanvasState extends State<_TrussCanvas> {
  SheetView? _vp;
  Size _size = Size.zero;
  int _fitSeen = -1;
  _Gesture _gesture = _Gesture.none;
  SheetView? _startVp;
  Offset _startFocal = Offset.zero;
  Offset? _down;
  String? _dragId;
  String? _from;
  Offset? _ghostEnd;

  TrussController get c => widget.controller;

  void _ensureViewport(Size size) {
    if (_vp == null ||
        c.fitRequest != _fitSeen ||
        (size != _size && _size == Size.zero)) {
      _fitSeen = c.fitRequest;
      _vp = fitTruss(c.problem, size);
    }
    _size = size;
  }

  (double, double) _world(Offset p) {
    final vp = _vp!;
    return ((p.dx - vp.origin.dx) / vp.scale, (vp.origin.dy - p.dy) / vp.scale);
  }

  /// A joint within a fingertip, else the nearest grid point.
  (double, double) _snap(Offset p) {
    final (x, y) = _world(p);
    final near = c.problem.nodeNear(x, y, 16 / _vp!.scale);
    if (near != null) return (near.x, near.y);
    final step = _vp!.scale >= 25 ? 0.5 : 1.0;
    // + 0.0 turns −0.0 into 0.0.
    return (
      (x / step).roundToDouble() * step + 0.0,
      (y / step).roundToDouble() * step + 0.0,
    );
  }

  bool _isJoint(String? id) => id != null && c.problem.node(id) != null;

  TrussScene _scene(MechColors colors, UnitSystem units) => TrussScene(
    problem: c.problem,
    view: _vp!,
    colors: colors,
    units: units,
    selectedId: c.selected,
    pending: c.pending,
    ghost:
        _from != null && _ghostEnd != null && c.problem.node(_from!) != null
            ? (
              _vp!.toScreen(
                c.problem.node(_from!)!.x,
                c.problem.node(_from!)!.y,
              ),
              _ghostEnd!,
            )
            : null,
  );

  String _newJointAt(Offset p) {
    final (x, y) = _snap(p);
    final existing = c.problem.nodeNear(x, y, 1e-9);
    return existing?.id ?? c.addJoint(x, y);
  }

  void _onTap(Offset p, TrussScene scene, AppState app) {
    final s = app.s;
    final hit = scene.hitTest(p);
    switch (c.tool) {
      case TrussTool.joint:
        if (_isJoint(hit)) {
          c.select(hit);
        } else {
          c.select(_newJointAt(p));
        }
      case TrussTool.member:
        final target = _isJoint(hit) ? hit! : _newJointAt(p);
        final from = c.pending;
        if (from != null && from != target) {
          if (!c.addMember(from, target)) {
            widget.onMessage(s.trussHint('member'));
          }
        }
        c.setPending(target);
      case TrussTool.pin || TrussTool.roller:
        if (!_isJoint(hit)) {
          widget.onMessage(s.trussHint(c.tool.name));
          return;
        }
        c.setSupport(
          hit!,
          c.tool == TrussTool.pin
              ? TrussSupportType.pin
              : TrussSupportType.roller,
        );
      case TrussTool.load:
        if (!_isJoint(hit)) {
          widget.onMessage(s.trussHint('load'));
          return;
        }
        c.addLoad(hit!);
      case TrussTool.delete:
        if (hit != null) c.delete(hit);
      case TrussTool.select:
        c.select(hit);
    }
  }

  void _onScaleStart(ScaleStartDetails d, TrussScene scene) {
    _startVp = _vp;
    final down = _down ?? d.localFocalPoint;
    _startFocal = down;
    if (d.pointerCount >= 2) {
      _gesture = _Gesture.zoom;
      return;
    }
    final hit = scene.hitTest(down);
    if (c.tool == TrussTool.member && _isJoint(hit)) {
      _gesture = _Gesture.drawMember;
      _from = hit;
      _ghostEnd = down;
      setState(() {});
      return;
    }
    if ((c.tool == TrussTool.select || c.tool == TrussTool.joint) &&
        _isJoint(hit)) {
      _gesture = _Gesture.dragJoint;
      _dragId = hit;
      c.select(hit);
      c.beginGesture();
      return;
    }
    _gesture = _Gesture.pan;
  }

  void _onScaleUpdate(ScaleUpdateDetails d) {
    if (d.pointerCount >= 2 && _gesture != _Gesture.zoom) {
      if (_gesture == _Gesture.dragJoint) c.endGesture();
      _gesture = _Gesture.zoom;
      _startVp = _vp;
      _startFocal = d.localFocalPoint;
      _from = null;
      _ghostEnd = null;
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
      case _Gesture.dragJoint:
        final (x, y) = _snap(d.localFocalPoint);
        final near = c.problem.nodeNear(x, y, 1e-9);
        if (near == null || near.id == _dragId) c.moveJoint(_dragId!, x, y);
      case _Gesture.drawMember:
        setState(() => _ghostEnd = d.localFocalPoint);
      case _Gesture.none:
        break;
    }
  }

  void _onScaleEnd(TrussScene scene) {
    switch (_gesture) {
      case _Gesture.dragJoint:
        c.endGesture();
      case _Gesture.drawMember:
        final from = _from, end = _ghostEnd;
        _from = null;
        _ghostEnd = null;
        if (from != null && end != null && (end - _startFocal).distance > 12) {
          final hit = scene.hitTest(end);
          final target = _isJoint(hit) ? hit! : _newJointAt(end);
          if (target != from) c.addMember(from, target);
          c.setPending(target);
        }
        setState(() {});
      default:
        break;
    }
    _gesture = _Gesture.none;
    _dragId = null;
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
                  onTapUp: (d) => _onTap(d.localPosition, scene, app),
                  onScaleStart: (d) => _onScaleStart(d, scene),
                  onScaleUpdate: _onScaleUpdate,
                  onScaleEnd: (_) => _onScaleEnd(scene),
                  child: ClipRect(
                    child: CustomPaint(
                      key: const ValueKey('truss-canvas'),
                      size: constraints.biggest,
                      painter: TrussPainter(scene),
                    ),
                  ),
                ),
              );
            },
          ),
    );
  }
}
