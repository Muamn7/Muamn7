import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/palette.dart';
import '../../drawing/truss_scene.dart';
import '../../state/app_state.dart';
import '../../state/highlight_controller.dart';
import '../analysis/math_view.dart';
import '../analysis/step_card.dart';
import '../widgets/layout.dart';

/// The result of ANALYZE for a truss: the drawing with every member's
/// force and the reactions, and two ways to get there: the method of joints
/// (every joint, in an order that always has at most two unknowns) and the
/// method of sections (cut up to three members by tapping them).
class TrussAnalysisScreen extends StatefulWidget {
  const TrussAnalysisScreen({super.key, required this.problem});

  final TrussProblem problem;

  @override
  State<TrussAnalysisScreen> createState() => _TrussAnalysisScreenState();
}

class _TrussAnalysisScreenState extends State<TrussAnalysisScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 2, vsync: this)
    ..addListener(_onTab);
  final highlights = HighlightController();
  final _jointKeys = <int, GlobalKey>{};
  final _cut = <String>[];
  bool _otherSide = false;
  TrussExplanation? _explanation;
  TrussSection? _section;
  AppSettings? _builtWith;

  @override
  void dispose() {
    _tabs.dispose();
    highlights.dispose();
    super.dispose();
  }

  void _onTab() {
    if (_tabs.indexIsChanging) return;
    highlights.clear();
    setState(() {});
  }

  TrussExplainer _explainer(AppState app) =>
      TrussExplainer(lang: app.lang, units: app.units);

  TrussExplanation _explain(AppState app) {
    if (_explanation == null || !identical(_builtWith, app.settings)) {
      _explanation = _explainer(app).explain(widget.problem);
      _section = null;
      _builtWith = app.settings;
      highlights.clear();
    }
    return _explanation!;
  }

  TrussSection? _sectionOf(AppState app) {
    if (_cut.isEmpty || !_explanation!.isSolved) return null;
    return _section ??= _explainer(
      app,
    ).section(widget.problem, List.of(_cut), otherSide: _otherSide);
  }

  void _setCut(void Function() change) {
    setState(() {
      change();
      _section = null;
    });
    highlights.clear();
  }

  /// A tap on the drawing: in the method of sections it cuts or uncuts a
  /// member; in the method of joints it opens that joint's step or shows
  /// that member's force.
  void _onTapDrawing(String? id, TrussExplanation e) {
    final p = widget.problem;
    if (id == null) {
      highlights.clear();
      return;
    }
    if (_tabs.index == 1) {
      if (p.member(id) == null || !e.isSolved) return;
      _setCut(() {
        if (!_cut.remove(id)) {
          if (_cut.length == 3) _cut.removeAt(0);
          _cut.add(id);
        }
      });
      return;
    }
    if (p.node(id) != null) {
      for (var i = 0; i < e.steps.length; i++) {
        final step = e.steps[i];
        if (step.kind == StepKind.trussJoint &&
            step.highlights.any((h) => h is JointHighlight && h.nodeId == id)) {
          final ctx = _jointKeys[i]?.currentContext;
          if (ctx != null) {
            Scrollable.ensureVisible(
              ctx,
              duration: const Duration(milliseconds: 400),
              alignment: 0.05,
            );
          }
          highlights.show(step.highlights, source: step);
          return;
        }
      }
    }
    final index = p.members.indexWhere((m) => m.id == id);
    if (index >= 0 && index < e.members.length) {
      final r = e.members[index];
      highlights.show(r.highlights, source: r);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final e = _explain(app);
    final section = _sectionOf(app);
    final sections = _tabs.index == 1;
    final valid = sections && section != null && section.isValid;
    final drawing = _TrussView(
      problem: widget.problem,
      solution: e.solution,
      highlights: highlights,
      cut: sections ? _cut.toSet() : const {},
      side: valid ? section.side : null,
      points: valid ? section.points : const [],
      onTap: (id) => _onTapDrawing(id, e),
    );
    final tabBar = TabBar(
      controller: _tabs,
      tabs: [
        Tab(key: const ValueKey('tab-joints'), text: s.methodJoints),
        Tab(key: const ValueKey('tab-sections'), text: s.methodSections),
      ],
    );
    final views = TabBarView(
      controller: _tabs,
      children: [
        _JointsView(explanation: e, highlights: highlights, keys: _jointKeys),
        _SectionsView(
          explanation: e,
          section: section,
          cut: _cut,
          otherSide: _otherSide,
          highlights: highlights,
          onRemove: (id) => _setCut(() => _cut.remove(id)),
          onClear:
              () => _setCut(() {
                _cut.clear();
                _otherSide = false;
              }),
          onOtherSide: () => _setCut(() => _otherSide = !_otherSide),
        ),
      ],
    );

    final height = MediaQuery.sizeOf(context).height;
    return Scaffold(
      appBar: AppBar(title: Text(s.trussAnalysis)),
      body:
          isWide(context)
              ? Row(
                children: [
                  Expanded(flex: 11, child: drawing),
                  const VerticalDivider(width: 1),
                  Expanded(
                    flex: 9,
                    child: Column(children: [tabBar, Expanded(child: views)]),
                  ),
                ],
              )
              : Column(
                children: [
                  SizedBox(
                    height: (height * 0.4).clamp(240.0, 440.0),
                    child: drawing,
                  ),
                  tabBar,
                  Expanded(child: views),
                ],
              ),
    );
  }
}

/// The truss with its forces, fitted to the space it has; highlights glow.
class _TrussView extends StatefulWidget {
  const _TrussView({
    required this.problem,
    required this.solution,
    required this.highlights,
    required this.cut,
    required this.side,
    required this.points,
    required this.onTap,
  });

  final TrussProblem problem;
  final TrussSolution solution;
  final HighlightController highlights;
  final Set<String> cut;
  final Set<String>? side;
  final List<(String, double, double)> points;
  final ValueChanged<String?> onTap;

  @override
  State<_TrussView> createState() => _TrussViewState();
}

class _TrussViewState extends State<_TrussView>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );

  @override
  void initState() {
    super.initState();
    widget.highlights.addListener(_onHighlight);
  }

  @override
  void didUpdateWidget(_TrussView old) {
    super.didUpdateWidget(old);
    if (old.highlights != widget.highlights) {
      old.highlights.removeListener(_onHighlight);
      widget.highlights.addListener(_onHighlight);
    }
  }

  void _onHighlight() {
    if (widget.highlights.isEmpty) {
      _pulse.stop();
      _pulse.value = 0;
    } else if (!_pulse.isAnimating) {
      _pulse.repeat(reverse: true);
    }
    setState(() {});
  }

  @override
  void dispose() {
    widget.highlights.removeListener(_onHighlight);
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final colors = MechColors.of(context);
    return ColoredBox(
      color: colors.paper,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final size = constraints.biggest;
          final view = fitTruss(widget.problem, size, margin: 64);
          // Pinch to look closer at a crowded corner; taps still find
          // the joint or member under the finger.
          return InteractiveViewer(
            maxScale: 6,
            child: AnimatedBuilder(
              animation: _pulse,
              builder: (context, _) {
                final scene = TrussScene(
                  problem: widget.problem,
                  view: view,
                  colors: colors,
                  units: app.units,
                  solution: widget.solution,
                  highlights: widget.highlights.items,
                  cut: widget.cut,
                  side: widget.side,
                  points: widget.points,
                  pulse: _pulse.value,
                );
                return GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTapUp: (d) => widget.onTap(scene.hitTest(d.localPosition)),
                  child: CustomPaint(
                    key: const ValueKey('truss-result'),
                    size: size,
                    painter: TrussPainter(scene),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}

class _StepList extends StatelessWidget {
  const _StepList({required this.storageKey, required this.children});

  final String storageKey;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    key: PageStorageKey(storageKey),
    padding: const EdgeInsets.only(bottom: 32),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: children,
    ),
  );
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: Theme.of(
      context,
    ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
  );
}

class _ChipsCard extends StatelessWidget {
  const _ChipsCard({
    required this.title,
    required this.items,
    required this.highlights,
  });

  final String title;
  final List<ResultValue> items;
  final HighlightController highlights;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.fromLTRB(12, 10, 12, 4),
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Heading(title),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final r in items)
                ResultChip(result: r, highlights: highlights),
            ],
          ),
        ],
      ),
    ),
  );
}

/// The method of joints: the forces at a glance, then every step.
class _JointsView extends StatelessWidget {
  const _JointsView({
    required this.explanation,
    required this.highlights,
    required this.keys,
  });

  final TrussExplanation explanation;
  final HighlightController highlights;
  final Map<int, GlobalKey> keys;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final e = explanation;
    // Every step is built (not lazily), so a tap on a joint in the
    // drawing can scroll to its step.
    return _StepList(
      storageKey: 'joints',
      children: [
        if (e.isSolved) ...[
          _ChipsCard(
            title: s.reactions,
            items: e.reactions,
            highlights: highlights,
          ),
          _ChipsCard(
            title: s.memberForces,
            items: e.members,
            highlights: highlights,
          ),
        ] else
          Padding(
            padding: const EdgeInsets.all(12),
            child: FilledButton.tonalIcon(
              onPressed: () => Navigator.pop(context),
              icon: const Icon(Icons.edit_outlined),
              label: Text(s.backToEdit),
            ),
          ),
        for (var i = 0; i < e.steps.length; i++)
          StepCard(
            key: keys.putIfAbsent(i, GlobalKey.new),
            step: e.steps[i],
            index: i,
            highlights: highlights,
          ),
      ],
    );
  }
}

/// The method of sections: which members are cut, which part is kept, and
/// the equations for that part.
class _SectionsView extends StatelessWidget {
  const _SectionsView({
    required this.explanation,
    required this.section,
    required this.cut,
    required this.otherSide,
    required this.highlights,
    required this.onRemove,
    required this.onClear,
    required this.onOtherSide,
  });

  final TrussExplanation explanation;
  final TrussSection? section;
  final List<String> cut;
  final bool otherSide;
  final HighlightController highlights;
  final ValueChanged<String> onRemove;
  final VoidCallback onClear;
  final VoidCallback onOtherSide;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final e = explanation;
    if (!e.isSolved) {
      return _StepList(
        storageKey: 'sections',
        children: [
          StepCard(step: e.steps.last, index: 0, highlights: highlights),
        ],
      );
    }
    final labels = TrussLabels.of(e.problem);
    final sec = section;
    return _StepList(
      storageKey: 'sections',
      children: [
        Card(
          margin: const EdgeInsets.fromLTRB(12, 10, 12, 4),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.content_cut, size: 18, color: scheme.primary),
                    const SizedBox(width: 8),
                    Expanded(child: _Heading(s.methodSections)),
                  ],
                ),
                const SizedBox(height: 6),
                Text(s.sectionHelp, style: theme.textTheme.bodySmall),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    for (final id in cut)
                      InputChip(
                        key: ValueKey('cut-$id'),
                        label: MathText(
                          'F_${labels.member(e.problem.member(id)!)}',
                        ),
                        onDeleted: () => onRemove(id),
                      ),
                    if (cut.isNotEmpty) ...[
                      FilterChip(
                        key: const ValueKey('other-side'),
                        selected: otherSide,
                        label: Text(s.otherSide),
                        avatar: const Icon(Icons.swap_horiz, size: 18),
                        showCheckmark: false,
                        onSelected: (_) => onOtherSide(),
                      ),
                      ActionChip(
                        key: const ValueKey('clear-cut'),
                        label: Text(s.clearCut),
                        avatar: const Icon(Icons.clear_all, size: 18),
                        onPressed: onClear,
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
        ),
        if (sec != null && !sec.isValid)
          Card(
            key: const ValueKey('cut-error'),
            color: scheme.errorContainer,
            margin: const EdgeInsets.fromLTRB(12, 6, 12, 4),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.info_outline, color: scheme.onErrorContainer),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      sec.error!,
                      style: TextStyle(color: scheme.onErrorContainer),
                    ),
                  ),
                ],
              ),
            ),
          ),
        if (sec != null)
          for (var i = 0; i < sec.steps.length; i++)
            StepCard(
              key: ValueKey('section-step-$i-${sec.cut.join()}-$otherSide'),
              step: sec.steps[i],
              index: i,
              highlights: highlights,
            ),
      ],
    );
  }
}
