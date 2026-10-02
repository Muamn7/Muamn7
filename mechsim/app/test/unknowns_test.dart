// The student decides what is known: a reaction given a value, a load
// whose size is the unknown.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mechsim/state/app_state.dart';
import 'package:mechsim/state/editor_controller.dart';
import 'package:mechsim/ui/analysis/analysis_screen.dart';
import 'package:mechsim/ui/editor/editor_screen.dart';
import 'package:mechsim_core/mechsim_core.dart';

import 'support/harness.dart';

EditorController editorOf(WidgetTester tester) =>
    (tester.state(find.byType(EditorScreen)) as dynamic).controller
        as EditorController;

void main() {
  const bare = BeamProblem(
    length: 6,
    supports: [
      Support(id: 's1', type: SupportType.pin, x: 0),
      Support(id: 's2', type: SupportType.roller, x: 6),
    ],
  );

  Future<void> open(WidgetTester tester, Size size, BeamProblem p) async {
    phoneSize(tester, logical: size);
    await tester.pumpWidget(
      await app(
        testState(settings: const AppSettings(lang: Lang.en)),
        home: EditorScreen(problem: p),
      ),
    );
    await tester.pumpAndSettle();
  }

  for (final size in [const Size(740, 360), const Size(800, 360)]) {
    testWidgets('support kinds sit in the bottom bar (${size.width})', (
      tester,
    ) async {
      await open(tester, size, bare);
      final c = editorOf(tester);
      // Hide the side panel: the kinds are still at hand in the bar.
      await tester.tap(find.byKey(const ValueKey('toggle-panel')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('tool-Support')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('bar-options')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('bar-Fixed')));
      await tester.pump();
      expect(c.tool, Tool.fixed);
      await tester.tap(find.byKey(const ValueKey('tool-Distributed Load')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('bar-UVL')));
      await tester.pump();
      expect(c.tool, Tool.uvl);
      // Nothing to choose for a point load.
      await tester.tap(find.byKey(const ValueKey('tool-Point Load')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('bar-options')), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('give RB, make P unknown, and the analysis finds P', (
    tester,
  ) async {
    await open(
      tester,
      const Size(412, 892),
      bare.withLoad(const PointLoad(id: 'p1', x: 3, magnitude: 10000)),
    );
    final c = editorOf(tester);

    // Before: three unknown reactions, a known load.
    c.select('s2');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('known-s2-vertical')));
    await tester.pumpAndSettle();
    expect(c.problem.supportById('s2')!.known, {'vertical': 0.0});
    await tester.enterText(
      find.descendant(
        of: find.byKey(const ValueKey('known-value-s2-vertical')),
        matching: find.byType(TextField),
      ),
      '15',
    );
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(c.problem.supportById('s2')!.known, {'vertical': 15000.0});

    // Now there are only two unknowns: make the load the third.
    c.select('p1');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('unknown-p1')));
    await tester.pumpAndSettle();
    expect((c.problem.loads.single as PointLoad).unknown, isTrue);
    expect(find.text('P1 = ?'), findsOneWidget);

    await tester.tap(find.text('ANALYZE'));
    await tester.pumpAndSettle();
    expect(find.byType(AnalysisScreen), findsOneWidget);
    expect(find.text('P1 = 30.00 kN ↓'), findsWidgets);
    expect(find.text('RA = 15.00 kN ↑'), findsWidgets);
  });

  testWidgets('an inclined load cannot be made unknown', (tester) async {
    await open(
      tester,
      const Size(412, 892),
      bare.withLoad(
        const PointLoad(id: 'p1', x: 3, magnitude: 10000, angleDeg: -45),
      ),
    );
    editorOf(tester).select('p1');
    await tester.pumpAndSettle();
    final chip = tester.widget<FilterChip>(
      find.byKey(const ValueKey('unknown-p1')),
    );
    expect(chip.onSelected, isNull);
  });
}
