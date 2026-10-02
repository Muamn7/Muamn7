import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/beam_scene.dart';
import '../../drawing/palette.dart';
import '../../drawing/viewport.dart';
import '../../state/app_state.dart';
import '../editor/editor_screen.dart';

class SavedTab extends StatefulWidget {
  const SavedTab({super.key});

  @override
  State<SavedTab> createState() => _SavedTabState();
}

class _SavedTabState extends State<SavedTab> {
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final app = AppScope.of(context);
    if (!app.savedLoaded) app.loadSaved();
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final s = app.s;
    final items = app.saved;
    if (items.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.bookmark_border,
                size: 48,
                color: Theme.of(context).colorScheme.outline,
              ),
              const SizedBox(height: 12),
              Text(s.noSaved, textAlign: TextAlign.center),
            ],
          ),
        ),
      );
    }
    final units = app.units;
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: items.length,
      separatorBuilder:
          (_, _) => const Divider(height: 1, indent: 16, endIndent: 16),
      itemBuilder: (context, i) {
        final item = items[i];
        final p = item.problem;
        final length =
            '${Num.compact(units.toDisplay(p.length, Dimension.length))} ${units.length.symbol}';
        return Dismissible(
          key: ValueKey(item.id),
          direction: DismissDirection.horizontal,
          background: Container(
            color: Theme.of(context).colorScheme.errorContainer,
          ),
          onDismissed: (_) async {
            await app.deleteSaved(item.id);
            if (!context.mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(s.deleted),
                action: SnackBarAction(
                  label: s.undo,
                  onPressed: () => app.restoreSaved(item),
                ),
              ),
            );
          },
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 4,
            ),
            leading: ProblemThumbnail(problem: p),
            title: Text(
              item.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: Text(
              '${s.savedSummary(length, p.supports.length, p.loads.length)}\n'
              '${MaterialLocalizations.of(context).formatShortDate(item.savedAt)}',
            ),
            isThreeLine: true,
            onTap:
                () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder:
                        (_) => EditorScreen(
                          problem: p,
                          savedId: item.id,
                          name: item.name,
                        ),
                  ),
                ),
          ),
        );
      },
    );
  }
}

/// A small drawing of a problem for lists.
class ProblemThumbnail extends StatelessWidget {
  const ProblemThumbnail({
    super.key,
    required this.problem,
    this.width = 96,
    this.height = 56,
  });

  final BeamProblem problem;
  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    final colors = MechColors.of(context);
    final units = AppScope.of(context).units;
    final size = Size(width, height);
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: CustomPaint(
        size: size,
        painter: BeamScenePainter(
          BeamScene(
            problem: problem,
            viewport: SheetView.fit(
              problem.length,
              size,
              margin: 10,
              yFraction: 0.55,
            ),
            colors: colors,
            units: units,
            metrics: SceneMetrics.thumbnail,
            showLabels: false,
          ),
          grid: true,
        ),
      ),
    );
  }
}
