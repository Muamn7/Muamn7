import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/beam_scene.dart';
import '../../drawing/palette.dart';
import '../../drawing/viewport.dart';
import '../../i18n/strings.dart';
import '../../state/app_state.dart';
import '../analysis/analysis_screen.dart';
import '../analysis/math_view.dart';
import '../widgets/layout.dart';

/// Practice for one given problem (from the analysis screen).
class PracticeScreen extends StatelessWidget {
  const PracticeScreen({super.key, required this.problem});

  final BeamProblem problem;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    return Scaffold(
      appBar: AppBar(title: Text(s.practice)),
      body: PracticeView(problem: problem),
    );
  }
}

/// The practice flow: a problem, one question at a time, an answer box,
/// Check, a hint that names the likely mistake, and the solution only when
/// asked for. Without a [problem] it generates them by level.
class PracticeView extends StatefulWidget {
  const PracticeView({super.key, this.problem});

  final BeamProblem? problem;

  @override
  State<PracticeView> createState() => _PracticeViewState();
}

enum _Status { correct, wrong, revealed }

class _PracticeViewState extends State<PracticeView> {
  PracticeLevel level = PracticeLevel.basic;
  int _seed = DateTime.now().millisecondsSinceEpoch;
  late BeamProblem problem =
      widget.problem ?? ProblemGenerator(_seed).generate(level);
  PracticeSession? _session;
  AppSettings? _builtWith;
  int q = 0;
  final _answer = TextEditingController();
  AnswerFeedback? feedback;
  final statuses = <int, _Status>{};
  final firstTry = <int, bool>{};

  @visibleForTesting
  PracticeSession? get sessionForTest => _session;

  PracticeSession _sessionFor(AppState app) {
    if (_session == null || !identical(_builtWith, app.settings)) {
      _session = PracticeSession(app.solve(problem));
      _builtWith = app.settings;
    }
    return _session!;
  }

  void _newProblem() {
    setState(() {
      _seed++;
      problem = ProblemGenerator(_seed).generate(level);
      _session = null;
      q = 0;
      feedback = null;
      statuses.clear();
      firstTry.clear();
      _answer.clear();
    });
  }

  void _check(PracticeSession session) {
    final value = Num.parse(_answer.text);
    if (value == null) {
      setState(
        () =>
            feedback = AnswerFeedback(
              correct: false,
              mistake: Mistake.other,
              message: AppScope.read(context).s.enterNumber,
            ),
      );
      return;
    }
    final f = session.check(session.questions[q], value);
    setState(() {
      feedback = f;
      firstTry.putIfAbsent(q, () => f.correct);
      if (statuses[q] != _Status.revealed) {
        statuses[q] = f.correct ? _Status.correct : _Status.wrong;
      }
    });
  }

  void _next() {
    setState(() {
      q++;
      feedback = null;
      _answer.clear();
    });
  }

  @override
  void dispose() {
    _answer.dispose();
    super.dispose();
  }

  List<Highlight> _questionHighlights(PracticeSession session) {
    if (q >= session.questions.length) return const [];
    final question = session.questions[q];
    return switch (question.kind) {
      QuestionKind.reaction => [
        SupportHighlight(
          session.solution.statics.reaction(question.reactionId!).supportId,
        ),
      ],
      QuestionKind.shearAt => [SectionHighlight(question.x!)],
      _ => const [],
    };
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final session = _sessionFor(app);
    final theme = Theme.of(context);
    final colors = MechColors.of(context);
    final done = q >= session.questions.length;

    final problemSide = <Widget>[
      if (widget.problem == null)
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
          child: Row(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: [
                      for (final l in PracticeLevel.values)
                        Padding(
                          padding: const EdgeInsetsDirectional.only(end: 6),
                          child: ChoiceChip(
                            label: Text(s.levelName(l)),
                            selected: level == l,
                            onSelected: (_) {
                              level = l;
                              _newProblem();
                            },
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              IconButton.filledTonal(
                tooltip: s.newPracticeProblem,
                onPressed: _newProblem,
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
        ),
      Card(
        margin: const EdgeInsets.fromLTRB(12, 10, 12, 6),
        clipBehavior: Clip.antiAlias,
        child: SizedBox(
          height: 210,
          child: LayoutBuilder(
            builder: (context, c) {
              final vp = SheetView.fit(
                problem.length,
                c.biggest,
                margin: 54,
                yFraction: 0.42,
              );
              return CustomPaint(
                size: c.biggest,
                painter: BeamScenePainter(
                  BeamScene(
                    problem: problem,
                    viewport: vp,
                    colors: colors,
                    units: app.units,
                    metrics: SceneMetrics.compact,
                    showDimensions: true,
                    highlights: _questionHighlights(session),
                  ),
                  grid: true,
                ),
              );
            },
          ),
        ),
      ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        child: Row(
          children: [
            for (var i = 0; i < session.questions.length; i++)
              Container(
                margin: const EdgeInsetsDirectional.only(end: 6),
                width: i == q ? 22 : 10,
                height: 10,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(5),
                  color: switch (statuses[i]) {
                    _Status.correct => colors.reaction,
                    _Status.wrong => colors.negative,
                    _Status.revealed => colors.highlight,
                    _ => theme.colorScheme.outlineVariant,
                  },
                ),
              ),
          ],
        ),
      ),
    ];
    final Widget questionSide =
        done
            ? _DoneCard(
              correct: firstTry.values.where((v) => v).length,
              total: session.questions.length,
              onNew: widget.problem == null ? _newProblem : null,
              onSolution: () => _openSolution(null),
            )
            : _questionCard(session, s, theme, colors);
    if (isWide(context)) {
      // Sideways: the problem on one side, the question on the other.
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.only(bottom: 24),
              children: problemSide,
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.only(top: 4, bottom: 24),
              children: [questionSide],
            ),
          ),
        ],
      );
    }
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [...problemSide, questionSide],
    );
  }

  void _openSolution(int? step) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AnalysisScreen(problem: problem, focusStep: step),
      ),
    );
  }

  Widget _questionCard(
    PracticeSession session,
    S s,
    ThemeData theme,
    MechColors colors,
  ) {
    final question = session.questions[q];
    final status = statuses[q];
    final f = feedback;
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 6, 12, 6),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              s.question(q + 1, session.questions.length),
              style: theme.textTheme.labelMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              session.prompt(question),
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 12),
            Directionality(
              textDirection: TextDirection.ltr,
              child: Row(
                children: [
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: MathText(
                      '${question.symbol} =',
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                  Expanded(
                    child: TextField(
                      key: const ValueKey('practice-answer'),
                      controller: _answer,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                        signed: true,
                      ),
                      textInputAction: TextInputAction.done,
                      onSubmitted: (_) => _check(session),
                      decoration: InputDecoration(
                        isDense: true,
                        hintText: s.yourAnswer,
                        suffixText: session.unitOf(question),
                        border: const OutlineInputBorder(),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    key: const ValueKey('practice-check'),
                    onPressed: () => _check(session),
                    child: Text(s.check),
                  ),
                ],
              ),
            ),
            if (f != null) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: (f.correct ? colors.reaction : colors.negative)
                      .withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: f.correct ? colors.reaction : colors.negative,
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      f.correct ? Icons.check_circle : Icons.lightbulb_outline,
                      color: f.correct ? colors.reaction : colors.negative,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        f.message,
                        style: const TextStyle(height: 1.4),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            if (status == _Status.revealed) ...[
              const SizedBox(height: 10),
              Text(
                session.answerText(question),
                textDirection: TextDirection.ltr,
                style: theme.textTheme.titleMedium?.copyWith(
                  color: colors.highlight,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              alignment: WrapAlignment.end,
              children: [
                if (status != _Status.correct)
                  TextButton.icon(
                    onPressed:
                        () => setState(() {
                          statuses[q] = _Status.revealed;
                          firstTry.putIfAbsent(q, () => false);
                        }),
                    icon: const Icon(Icons.visibility_outlined),
                    label: Text(s.showSolution),
                  ),
                if (status == _Status.revealed || status == _Status.wrong)
                  TextButton.icon(
                    onPressed:
                        () => _openSolution(
                          f?.reviewStep ?? _reviewStepOf(session, question),
                        ),
                    icon: const Icon(Icons.menu_book_outlined),
                    label: Text(s.openFullSolution),
                  ),
                if (status == _Status.correct || status == _Status.revealed)
                  FilledButton.tonalIcon(
                    onPressed: _next,
                    icon: const Icon(Icons.arrow_forward),
                    label: Text(s.nextQuestion),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  int? _reviewStepOf(PracticeSession session, PracticeQuestion question) =>
      session.reviewStep(question);
}

class _DoneCard extends StatelessWidget {
  const _DoneCard({
    required this.correct,
    required this.total,
    this.onNew,
    required this.onSolution,
  });

  final int correct;
  final int total;
  final VoidCallback? onNew;
  final VoidCallback onSolution;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final colors = MechColors.of(context);
    return Card(
      margin: const EdgeInsets.all(12),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          children: [
            Icon(
              Icons.emoji_events_outlined,
              size: 40,
              color: colors.highlight,
            ),
            const SizedBox(height: 8),
            Text(
              s.practiceDone,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            Text(s.score(correct, total)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: onSolution,
                  icon: const Icon(Icons.menu_book_outlined),
                  label: Text(s.openFullSolution),
                ),
                if (onNew != null)
                  FilledButton.icon(
                    onPressed: onNew,
                    icon: const Icon(Icons.refresh),
                    label: Text(s.newPracticeProblem),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
