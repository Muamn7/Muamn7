import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mechsim_core/mechsim_core.dart';

import '../../drawing/linked_diagrams.dart';
import '../../state/app_state.dart';
import '../../state/highlight_controller.dart';
import '../analysis/step_card.dart';

/// Plays the solution like a video: the load, the FBD, each equation with
/// its reaction appearing on the drawing, then the SFD and the BMD drawn
/// from left to right. Start, pause, next and previous.
class PlayerScreen extends StatefulWidget {
  const PlayerScreen({super.key, required this.problem});

  final BeamProblem problem;

  @override
  State<PlayerScreen> createState() => _PlayerScreenState();
}

class _PlayerScreenState extends State<PlayerScreen> {
  final highlights = HighlightController();
  late Solution solution;
  int index = 0;
  bool playing = false;
  Timer? _timer;
  bool _ready = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final next = AppScope.of(context).solve(widget.problem);
    if (!_ready) {
      solution = next;
      _ready = true;
      _show(0);
    } else {
      solution = next;
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    highlights.dispose();
    super.dispose();
  }

  void _show(int i) {
    index = i.clamp(0, solution.steps.length - 1);
    final step = solution.steps[index];
    if (step.highlights.isNotEmpty) {
      highlights.show(step.highlights, source: step);
    } else {
      highlights.clear();
    }
    if (mounted) setState(() {});
  }

  /// Long enough to read the step: a base plus a little per line.
  Duration _dwell(SolutionStep step) {
    final ms = 3200 + 700 * step.lines.length + 25 * step.explanation.length;
    return Duration(milliseconds: ms.clamp(3500, 11000));
  }

  void _schedule() {
    _timer?.cancel();
    if (!playing) return;
    _timer = Timer(_dwell(solution.steps[index]), () {
      if (!mounted) return;
      if (index >= solution.steps.length - 1) {
        setState(() => playing = false);
        return;
      }
      _show(index + 1);
      _schedule();
    });
  }

  void _toggle() {
    setState(() => playing = !playing);
    if (playing && index >= solution.steps.length - 1) _show(0);
    _schedule();
  }

  void _step(int delta) {
    _show(index + delta);
    _schedule();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context).s;
    final step = solution.steps[index];
    final total = solution.steps.length;
    final height = MediaQuery.sizeOf(context).height;
    return Scaffold(
      appBar: AppBar(title: Text(s.playSteps)),
      body: Column(
        children: [
          SizedBox(
            height: (height * 0.4).clamp(240.0, 440.0),
            child: LinkedDiagrams(
              solution: solution,
              highlights: highlights,
              reveal: step.reveal,
              showCursorHint: false,
            ),
          ),
          LinearProgressIndicator(value: (index + 1) / total, minHeight: 3),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.only(top: 6, bottom: 12),
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 300),
                child: StepCard(
                  key: ValueKey(index),
                  step: step,
                  index: index,
                  highlights: highlights,
                ),
              ),
            ),
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Material(
          elevation: 6,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            // Media controls keep their left-to-right order in every language.
            child: Row(
              textDirection: TextDirection.ltr,
              children: [
                Expanded(
                  child: Text(
                    s.step(index + 1, total),
                    style: Theme.of(context).textTheme.labelLarge,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                IconButton(
                  tooltip: s.previous,
                  onPressed: index > 0 ? () => _step(-1) : null,
                  icon: const Icon(Icons.skip_previous),
                ),
                const SizedBox(width: 4),
                FilledButton.icon(
                  onPressed: _toggle,
                  icon: Icon(playing ? Icons.pause : Icons.play_arrow),
                  label: Text(playing ? s.pause : s.start),
                ),
                const SizedBox(width: 4),
                IconButton(
                  tooltip: s.next,
                  onPressed: index < total - 1 ? () => _step(1) : null,
                  icon: const Icon(Icons.skip_next),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
