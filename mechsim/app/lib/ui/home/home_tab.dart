import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/beam_scene.dart';
import '../../drawing/palette.dart';
import '../../drawing/viewport.dart';
import '../../state/app_state.dart';
import '../editor/editor_screen.dart';
import '../learn/learn_tab.dart';
import '../som/som_screen.dart';
import '../widgets/layout.dart';

class HomeTab extends StatelessWidget {
  const HomeTab({super.key, required this.onGo});

  /// Switches the bottom navigation to another tab.
  final ValueChanged<int> onGo;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final theme = Theme.of(context);
    final colors = MechColors.of(context);

    void push(Widget screen) => Navigator.of(
      context,
    ).push(MaterialPageRoute<void>(builder: (_) => screen));

    final cards = <_HomeCard>[
      _HomeCard(
        Icons.edit_square,
        s.newProblem,
        s.newProblemSub,
        colors.shear,
        () => push(const EditorScreen()),
      ),
      _HomeCard(
        Icons.quiz_outlined,
        s.practice,
        s.practiceSub,
        colors.reaction,
        () => onGo(1),
      ),
      _HomeCard(
        Icons.architecture,
        s.mechanics,
        s.mechanicsSub,
        colors.moment,
        () => push(const ExamplesScreen()),
      ),
      _HomeCard(
        Icons.science_outlined,
        s.strength,
        s.strengthSub,
        colors.inkSoft,
        () => push(const SomScreen()),
        locked: true,
      ),
      _HomeCard(
        Icons.bookmark_outline,
        s.savedProblems,
        s.savedSub,
        colors.highlight,
        () => onGo(2),
      ),
      _HomeCard(
        Icons.school_outlined,
        s.tutorials,
        s.tutorialsSub,
        colors.load,
        () => onGo(3),
      ),
    ];

    return SafeArea(
      child: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(18, 18, 18, 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    s.appName,
                    style: theme.textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    s.appTagline,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SliverToBoxAdapter(child: _HeroBeam()),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
            sliver: SliverGrid.count(
              crossAxisCount: MediaQuery.sizeOf(context).width > 640 ? 3 : 2,
              mainAxisSpacing: 10,
              crossAxisSpacing: 10,
              childAspectRatio: isWide(context) ? 1.7 : 1.3,
              children: [for (final c in cards) _HomeCardView(card: c)],
            ),
          ),
        ],
      ),
    );
  }
}

class _HomeCard {
  const _HomeCard(
    this.icon,
    this.title,
    this.subtitle,
    this.color,
    this.onTap, {
    this.locked = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;
  final bool locked;
}

class _HomeCardView extends StatelessWidget {
  const _HomeCardView({required this.card});

  final _HomeCard card;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final s = AppScope.of(context).s;
    return Card(
      elevation: 0,
      color: theme.colorScheme.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: theme.colorScheme.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: card.onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(9),
                    decoration: BoxDecoration(
                      color: card.color.withValues(alpha: 0.14),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(card.icon, color: card.color),
                  ),
                  const Spacer(),
                  if (card.locked)
                    Flexible(
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 3,
                        ),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          s.comingSoon,
                          style: theme.textTheme.labelSmall,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 6),
              // The words take what room is left and shrink rather than
              // overflow, whatever the card's shape on the screen.
              Expanded(
                child: LayoutBuilder(
                  builder:
                      (context, box) => Align(
                        alignment: AlignmentDirectional.bottomStart,
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: AlignmentDirectional.bottomStart,
                          child: SizedBox(
                            width: box.maxWidth,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  card.title,
                                  style: theme.textTheme.titleSmall?.copyWith(
                                    fontWeight: FontWeight.w800,
                                  ),
                                  maxLines: 2,
                                ),
                                const SizedBox(height: 3),
                                Text(
                                  card.subtitle,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The classic beam, drawn small as the home page's banner.
class _HeroBeam extends StatelessWidget {
  const _HeroBeam();

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final colors = MechColors.of(context);
    final problem = ExampleLibrary.byId('central-load').problem;
    return Container(
      height: 130,
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: LayoutBuilder(
        builder: (context, c) {
          final vp = SheetView.fit(
            problem.length,
            c.biggest,
            margin: 70,
            yFraction: 0.52,
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
                mode: SceneMode.freeBody,
                statics: StaticsSolver.solve(problem),
                showLabels: false,
              ),
              grid: true,
            ),
          );
        },
      ),
    );
  }
}
