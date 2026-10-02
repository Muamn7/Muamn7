import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/beam_scene.dart';
import '../../drawing/diagram_painter.dart';
import '../../drawing/palette.dart';
import '../../drawing/viewport.dart';
import '../../state/app_state.dart';
import '../analysis/analysis_screen.dart';
import '../editor/editor_screen.dart';
import '../saved/saved_tab.dart';

/// Tutorials, and the Mechanics example library.
class LearnTab extends StatelessWidget {
  const LearnTab({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final tutorials = Tutorials.all(app.lang);
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 8),
      children: [
        for (var i = 0; i < tutorials.length; i++)
          ListTile(
            leading: CircleAvatar(child: Text('${i + 1}')),
            title: Text(
              tutorials[i].title,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            subtitle: Text(tutorials[i].summary),
            trailing: const Icon(Icons.chevron_right),
            onTap:
                () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => TutorialScreen(tutorial: tutorials[i]),
                  ),
                ),
          ),
        const Divider(height: 24),
        ListTile(
          leading: const Icon(Icons.architecture),
          title: Text(
            s.examples,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w800,
            ),
          ),
          subtitle: Text(s.mechanicsSub),
          trailing: const Icon(Icons.chevron_right),
          onTap:
              () => Navigator.of(context).push(
                MaterialPageRoute<void>(builder: (_) => const ExamplesScreen()),
              ),
        ),
      ],
    );
  }
}

class TutorialScreen extends StatelessWidget {
  const TutorialScreen({super.key, required this.tutorial});

  final Tutorial tutorial;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(tutorial.title)),
      body: ListView(
        padding: const EdgeInsets.all(14),
        children: [
          Text(tutorial.summary, style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          for (final section in tutorial.sections)
            Card(
              margin: const EdgeInsets.only(bottom: 12),
              clipBehavior: Clip.antiAlias,
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      section.heading,
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(section.body, style: const TextStyle(height: 1.5)),
                    if (section.figure != null) ...[
                      const SizedBox(height: 10),
                      TutorialFigure(
                        problem: section.figure!,
                        kind: section.figureKind,
                      ),
                    ],
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// A figure for a tutorial: the beam, its FBD, or one of its diagrams,
/// computed from the real problem.
class TutorialFigure extends StatelessWidget {
  const TutorialFigure({super.key, required this.problem, required this.kind});

  final BeamProblem problem;
  final FigureKind kind;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final colors = MechColors.of(context);
    final solution = app.solve(problem);
    final diagram = kind == FigureKind.shear || kind == FigureKind.moment;
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: SizedBox(
        height: diagram ? 250 : 170,
        child: LayoutBuilder(
          builder: (context, c) {
            return CustomPaint(
              size: c.biggest,
              painter: _FigurePainter(solution, kind, colors),
            );
          },
        ),
      ),
    );
  }
}

class _FigurePainter extends CustomPainter {
  _FigurePainter(this.solution, this.kind, this.colors);

  final Solution solution;
  final FigureKind kind;
  final MechColors colors;

  @override
  void paint(Canvas canvas, Size size) {
    final diagram = kind == FigureKind.shear || kind == FigureKind.moment;
    final beamHeight = diagram ? size.height * 0.5 : size.height;
    final vp = SheetView.fit(
      solution.problem.length,
      Size(size.width, beamHeight),
      margin: 56,
      yFraction: 0.5,
    );
    paintGrid(canvas, size, vp, colors);
    BeamScene(
      problem: solution.problem,
      viewport: vp,
      colors: colors,
      units: solution.units,
      metrics: SceneMetrics.compact,
      mode: kind == FigureKind.beam ? SceneMode.problem : SceneMode.freeBody,
      statics: solution.statics,
    ).paint(canvas, Size(size.width, beamHeight));
    final forces = solution.forces;
    if (!diagram || forces == null) return;
    final dk =
        kind == FigureKind.shear ? DiagramKind.shear : DiagramKind.moment;
    final dim = dk == DiagramKind.shear ? Dimension.force : Dimension.moment;
    canvas.drawRect(
      Rect.fromLTWH(0, beamHeight, size.width, size.height - beamHeight),
      Paint()..color = colors.paper,
    );
    DiagramBand(
      kind: dk,
      function: forces.of(dk),
      geometry: GraphEngine.build(forces.of(dk), dk),
      rect: Rect.fromLTWH(0, beamHeight, size.width, size.height - beamHeight),
      viewport: vp,
      colors: colors,
      color: dk == DiagramKind.shear ? colors.shear : colors.moment,
      title:
          dk == DiagramKind.shear
              ? 'SFD  V (${solution.units.force.symbol})'
              : 'BMD  M (${solution.units.moment.symbol})',
      toDisplay: (si) => solution.units.toDisplay(si, dim),
    ).paint(canvas);
  }

  @override
  bool shouldRepaint(covariant _FigurePainter old) =>
      old.solution != solution || old.colors != colors;
}

/// "Mechanics": the example library.
class ExamplesScreen extends StatelessWidget {
  const ExamplesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    return Scaffold(
      appBar: AppBar(title: Text(s.examples)),
      body: ListView.separated(
        padding: const EdgeInsets.symmetric(vertical: 8),
        itemCount: ExampleLibrary.all.length,
        separatorBuilder:
            (_, _) => const Divider(height: 1, indent: 16, endIndent: 16),
        itemBuilder: (context, i) {
          final e = ExampleLibrary.all[i];
          return ListTile(
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 6,
            ),
            leading: ProblemThumbnail(problem: e.problem),
            title: Text(
              e.title(app.lang),
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            subtitle: Text(e.idea(app.lang)),
            isThreeLine: true,
            onTap:
                () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder:
                        (_) => EditorScreen(
                          problem: e.problem,
                          name: e.title(app.lang),
                        ),
                  ),
                ),
            trailing: IconButton(
              tooltip: s.analyze,
              icon: const Icon(Icons.calculate_outlined),
              onPressed:
                  () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => AnalysisScreen(problem: e.problem),
                    ),
                  ),
            ),
          );
        },
      ),
    );
  }
}
