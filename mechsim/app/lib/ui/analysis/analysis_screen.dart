import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/linked_diagrams.dart';
import '../../drawing/palette.dart';
import '../../state/app_state.dart';
import '../../state/highlight_controller.dart';
import '../player/player_screen.dart';
import '../practice/practice_screen.dart';
import '../tour/tour_screen.dart';
import '../widgets/layout.dart';
import 'step_card.dart';

/// The result of ANALYZE: the FBD, SFD and BMD on one axis at the top, and
/// below them the reactions, key results, the checks and every step.
class AnalysisScreen extends StatefulWidget {
  const AnalysisScreen({super.key, required this.problem, this.focusStep});

  final BeamProblem problem;

  /// A step to scroll to and open (from practice: "Show Solution").
  final int? focusStep;

  @override
  State<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends State<AnalysisScreen> {
  final highlights = HighlightController();
  final _stepKeys = <int, GlobalKey>{};
  Solution? _solution;
  AppSettings? _builtWith;
  bool _diagramsOpen = true;

  @override
  void initState() {
    super.initState();
    if (widget.focusStep != null) {
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => _scrollToStep(widget.focusStep!),
      );
    }
  }

  @override
  void dispose() {
    highlights.dispose();
    super.dispose();
  }

  Solution _solve(AppState app) {
    if (_solution == null || !identical(_builtWith, app.settings)) {
      _solution = app.solve(widget.problem);
      _builtWith = app.settings;
      highlights.clear();
    }
    return _solution!;
  }

  void _openTour(BuildContext context) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => TourScreen(problem: widget.problem),
    ),
  );

  void _scrollToStep(int index) {
    final ctx = _stepKeys[index]?.currentContext;
    if (ctx != null) {
      Scrollable.ensureVisible(
        ctx,
        duration: const Duration(milliseconds: 400),
        alignment: 0.05,
      );
      final step = _solution!.steps[index];
      if (step.highlights.isNotEmpty) {
        highlights.show(step.highlights, source: step);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final solution = _solve(app);
    final height = MediaQuery.sizeOf(context).height;
    final diagramHeight = (height * 0.42).clamp(260.0, 470.0);
    final wide = isWide(context);
    final details = ListView(
      padding: const EdgeInsets.only(bottom: 32),
      children: [
        if (solution.isSolved) ...[
          _ReactionsCard(solution: solution, highlights: highlights),
          _KeyResultsCard(solution: solution, highlights: highlights),
          // The animated walk along the beam that draws the SFD and BMD.
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 2),
            child: FilledButton.tonalIcon(
              key: const ValueKey('open-tour'),
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(48),
              ),
              onPressed: () => _openTour(context),
              icon: const Icon(Icons.animation),
              label: Text(s.tourButton),
            ),
          ),
          _VerificationCard(solution: solution),
        ] else
          Padding(
            padding: const EdgeInsets.all(12),
            child: FilledButton.tonalIcon(
              onPressed: () => Navigator.pop(context),
              icon: const Icon(Icons.edit_outlined),
              label: Text(s.backToEdit),
            ),
          ),
        _SectionTitle(s.steps),
        for (var i = 0; i < solution.steps.length; i++)
          StepCard(
            key: _stepKeys.putIfAbsent(i, GlobalKey.new),
            step: solution.steps[i],
            index: i,
            highlights: highlights,
            emphasised: i == widget.focusStep,
            initiallyExplained: i == widget.focusStep,
          ),
      ],
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(s.analysis),
        actions: [
          if (solution.isSolved) ...[
            IconButton(
              tooltip: s.tourButton,
              icon: const Icon(Icons.animation),
              onPressed: () => _openTour(context),
            ),
            IconButton(
              tooltip: s.playSteps,
              icon: const Icon(Icons.play_circle_outline),
              onPressed:
                  () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => PlayerScreen(problem: widget.problem),
                    ),
                  ),
            ),
            IconButton(
              tooltip: s.quizMe,
              icon: const Icon(Icons.quiz_outlined),
              onPressed:
                  () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => PracticeScreen(problem: widget.problem),
                    ),
                  ),
            ),
          ],
          IconButton(
            tooltip: s.copyText,
            icon: const Icon(Icons.copy_all_outlined),
            onPressed: () async {
              await Clipboard.setData(
                ClipboardData(
                  text: TextRenderer.render(solution, withDetail: true),
                ),
              );
              if (context.mounted) {
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(SnackBar(content: Text(s.copied)));
              }
            },
          ),
        ],
      ),
      body:
          wide && solution.isSolved
              // Sideways: the drawings take the full height on one side and
              // the explanation scrolls beside them, so both stay in view.
              ? Row(
                children: [
                  Expanded(
                    flex: 11,
                    child: LinkedDiagrams(
                      solution: solution,
                      highlights: highlights,
                    ),
                  ),
                  const VerticalDivider(width: 1),
                  Expanded(flex: 9, child: details),
                ],
              )
              : Column(
                children: [
                  if (solution.isSolved) ...[
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 250),
                      height: _diagramsOpen ? diagramHeight : 0,
                      child: ClipRect(
                        child: LinkedDiagrams(
                          solution: solution,
                          highlights: highlights,
                        ),
                      ),
                    ),
                    _DiagramHandle(
                      open: _diagramsOpen,
                      onToggle:
                          () => setState(() => _diagramsOpen = !_diagramsOpen),
                    ),
                  ],
                  Expanded(child: details),
                ],
              ),
    );
  }
}

class _DiagramHandle extends StatelessWidget {
  const _DiagramHandle({required this.open, required this.onToggle});

  final bool open;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surfaceContainer,
      child: InkWell(
        onTap: onToggle,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  'FBD · SFD · BMD',
                  style: Theme.of(context).textTheme.bodySmall,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Icon(open ? Icons.expand_less : Icons.expand_more, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
    child: Text(
      text,
      style: Theme.of(
        context,
      ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
    ),
  );
}

class _ReactionsCard extends StatelessWidget {
  const _ReactionsCard({required this.solution, required this.highlights});

  final Solution solution;
  final HighlightController highlights;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 10, 12, 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              s.reactions,
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final r in solution.results!.reactions)
                  ResultChip(result: r, highlights: highlights),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _KeyResultsCard extends StatelessWidget {
  const _KeyResultsCard({required this.solution, required this.highlights});

  final Solution solution;
  final HighlightController highlights;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final r = solution.results!;
    final items = [
      if (r.maxMoment != null) r.maxMoment!,
      if (r.maxPositiveMoment != null && r.maxNegativeMoment != null) ...[
        r.maxPositiveMoment!,
        r.maxNegativeMoment!,
      ],
      if (r.maxShear != null) r.maxShear!,
      if (r.maxAxial != null) r.maxAxial!,
    ];
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 6, 12, 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              s.keyResults,
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final item in items)
                  ResultChip(result: item, highlights: highlights),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _VerificationCard extends StatelessWidget {
  const _VerificationCard({required this.solution});

  final Solution solution;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final report = solution.validation!;
    final colors = MechColors.of(context);
    final ok = report.allPassed;
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 6, 12, 4),
      clipBehavior: Clip.antiAlias,
      child: ExpansionTile(
        leading: Icon(
          ok ? Icons.verified_outlined : Icons.error_outline,
          color: ok ? colors.reaction : colors.negative,
        ),
        title: Text(
          ok ? s.allChecksPassed : s.someChecksFailed,
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(s.verification),
        children: [
          for (final item in report.items)
            ListTile(
              dense: true,
              leading: Icon(
                item.passed ? Icons.check_circle : Icons.cancel,
                size: 18,
                color: item.passed ? colors.reaction : colors.negative,
              ),
              title: Text(app.texts.checkName(item.kind)),
              trailing: Text(
                '|r| = ${item.residual.abs().toStringAsExponential(1)}',
                textDirection: TextDirection.ltr,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
        ],
      ),
    );
  }
}
