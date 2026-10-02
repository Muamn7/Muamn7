// Placing and editing distributed loads and couples on the sheet.

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

const _labels = [
  'Select',
  'Beam',
  'Pin',
  'Roller',
  'Fixed',
  'Delete',
  'Point Load',
  'UDL',
  'UVL',
  'Moment',
  'Dimension',
  'ANALYZE',
];

const _sideways = [
  'Select',
  'Point Load',
  'Distributed Load',
  'Moment',
  'Beam',
  'Support',
  'Dimension',
];

void main() {
  const bare = BeamProblem(
    length: 6,
    supports: [
      Support(id: 's1', type: SupportType.pin, x: 0),
      Support(id: 's2', type: SupportType.roller, x: 6),
    ],
  );

  Future<({double left, double perMetre, double y})> open(
    WidgetTester tester,
    BeamProblem problem,
  ) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(
        testState(settings: const AppSettings(lang: Lang.en)),
        home: EditorScreen(problem: problem),
      ),
    );
    await tester.pumpAndSettle();
    final canvas = tester.getRect(
      find
          .descendant(
            of: find.byType(EditorCanvas),
            matching: find.byType(CustomPaint),
          )
          .first,
    );
    final left = canvas.left + 56, right = canvas.right - 56;
    return (
      left: left,
      perMetre: (right - left) / problem.length,
      y: canvas.top + canvas.height * 0.45,
    );
  }

  testWidgets('every tool is on screen at once on a small phone upright', (
    tester,
  ) async {
    const size = Size(360, 740);
    phoneSize(tester, logical: size);
    await tester.pumpWidget(
      await app(
        testState(settings: const AppSettings(lang: Lang.en)),
        home: const EditorScreen(problem: bare),
      ),
    );
    await tester.pumpAndSettle();
    final screen = Offset.zero & size;
    for (final label in _labels) {
      final rect = tester.getRect(find.byKey(ValueKey('tool-$label')));
      expect(
        screen.contains(rect.topLeft) && screen.contains(rect.bottomRight),
        isTrue,
        reason: '$label at $rect',
      );
      expect(rect.width, greaterThanOrEqualTo(44), reason: label);
      expect(rect.height, greaterThanOrEqualTo(40), reason: label);
    }
    // Tapping one really picks it.
    await tester.tap(find.byKey(const ValueKey('tool-UDL')));
    await tester.pump();
    expect(editorOf(tester).tool, Tool.udl);
    expect(tester.takeException(), isNull);
  });

  for (final (name, size) in [
    ('a phone sideways', const Size(892, 412)),
    ('a small phone sideways', const Size(740, 360)),
  ]) {
    testWidgets('sideways, the tool list and ANALYZE fit on $name', (
      tester,
    ) async {
      phoneSize(tester, logical: size);
      await tester.pumpWidget(
        await app(
          testState(settings: const AppSettings(lang: Lang.en)),
          home: const EditorScreen(problem: bare),
        ),
      );
      await tester.pumpAndSettle();
      final screen = Offset.zero & size;
      for (final label in _sideways) {
        final rect = tester.getRect(find.byKey(ValueKey('tool-$label')));
        expect(
          screen.contains(rect.topLeft) && screen.contains(rect.bottomRight),
          isTrue,
          reason: '$label at $rect',
        );
        expect(rect.width, greaterThanOrEqualTo(100), reason: label);
        expect(rect.height, greaterThanOrEqualTo(32), reason: label);
      }
      final analyze = tester.getRect(find.byKey(const ValueKey('analyze')));
      expect(screen.contains(analyze.bottomRight), isTrue);
      // One entry for both kinds of distributed load and of support; the
      // side panel picks the kind.
      await tester.tap(find.byKey(const ValueKey('tool-Distributed Load')));
      await tester.pump();
      expect(editorOf(tester).tool, Tool.udl);
      await tester.tap(find.text('Varying UVL'));
      await tester.pump();
      expect(editorOf(tester).tool, Tool.uvl);
      await tester.tap(find.byKey(const ValueKey('tool-Support')));
      await tester.pump();
      expect(editorOf(tester).tool, Tool.pin);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('drag a UDL along the beam, set w, and analyse', (tester) async {
    final g = await open(tester, bare);
    await tester.tap(find.byKey(const ValueKey('tool-UDL')));
    await tester.pump();
    // From 1 m to 4 m.
    await tester.dragFrom(
      Offset(g.left + 1 * g.perMetre, g.y),
      Offset(3 * g.perMetre, 0),
    );
    await tester.pumpAndSettle();
    final c = editorOf(tester);
    final w = c.problem.distributedLoads.single;
    expect((w.x, w.x2, w.w1, w.w2), (1.0, 4.0, 10000.0, 10000.0));
    expect(c.selected, w.id);

    // The new load is selected: 5 kN/m in its properties.
    await tester.enterText(find.widgetWithText(TextField, 'Intensity w'), '5');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    final edited = c.problem.distributedLoads.single;
    expect((edited.w1, edited.w2), (5000.0, 5000.0));
    expect(find.textContaining('W1 = 15 kN'), findsOneWidget); // resultant

    // 15 kN at x̄ = 2.5 m: RB = 15 × 2.5 / 6 = 6.25, RA = 8.75.
    await tester.tap(find.text('ANALYZE'));
    await tester.pumpAndSettle();
    expect(find.byType(AnalysisScreen), findsOneWidget);
    expect(find.text('RA = 8.75 kN ↑'), findsWidgets);
    expect(find.text('RB = 6.25 kN ↑'), findsWidgets);
  });

  testWidgets('drag a distributed load to slide it along the beam', (
    tester,
  ) async {
    final problem = bare.withLoad(
      const DistributedLoad(id: 'w1', x: 1, x2: 3, w1: 10000, w2: 10000),
    );
    final g = await open(tester, problem);
    // Pick it up by its middle, 2 m along, and move it 2 m right.
    await tester.dragFrom(
      Offset(g.left + 2 * g.perMetre, g.y - 20),
      Offset(2 * g.perMetre, 0),
    );
    await tester.pumpAndSettle();
    final w = editorOf(tester).problem.distributedLoads.single;
    expect((w.x, w.x2), (3.0, 5.0));
    // It stops at the end of the beam, keeping its length.
    await tester.dragFrom(
      Offset(g.left + 4 * g.perMetre, g.y - 20),
      Offset(4 * g.perMetre, 0),
    );
    await tester.pumpAndSettle();
    final end = editorOf(tester).problem.distributedLoads.single;
    expect((end.x, end.x2), (4.0, 6.0));
  });

  testWidgets(
    'tap with UVL places a 2 m triangle; uniform turns it into a UDL',
    (tester) async {
      final g = await open(tester, bare);
      await tester.tap(find.byKey(const ValueKey('tool-UVL')));
      await tester.pump();
      await tester.tapAt(Offset(g.left + 5 * g.perMetre, g.y));
      await tester.pumpAndSettle();
      final c = editorOf(tester);
      final w = c.problem.distributedLoads.single;
      // Pulled back so that it ends at the end of the beam.
      expect((w.x, w.x2, w.w1, w.w2), (4.0, 6.0, 0.0, 10000.0));
      expect(find.widgetWithText(TextField, 'w at start'), findsOneWidget);

      await tester.tap(find.text('Uniform (UDL)'));
      await tester.pumpAndSettle();
      final u = c.problem.distributedLoads.single;
      expect((u.w1, u.w2), (10000.0, 10000.0));
      expect(find.widgetWithText(TextField, 'Intensity w'), findsOneWidget);

      await tester.tap(find.text('↑ Up'));
      await tester.pumpAndSettle();
      expect(c.problem.distributedLoads.single.upward, isTrue);
      c.undo();
      expect(c.problem.distributedLoads.single.upward, isFalse);
    },
  );

  testWidgets('tap with Moment places a couple; flip its sense', (
    tester,
  ) async {
    final g = await open(tester, bare);
    await tester.tap(find.byKey(const ValueKey('tool-Moment')));
    await tester.pump();
    await tester.tapAt(Offset(g.left + 2 * g.perMetre, g.y));
    await tester.pumpAndSettle();
    final c = editorOf(tester);
    final m = c.problem.moments.single;
    expect((m.x, m.magnitude, m.counterClockwise), (2.0, 10000.0, true));

    await tester.enterText(find.widgetWithText(TextField, 'Magnitude'), '12');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    await tester.tap(find.text('↻ Clockwise'));
    await tester.pumpAndSettle();
    final edited = c.problem.moments.single;
    expect((edited.magnitude, edited.counterClockwise), (12000.0, false));

    // A clockwise 12 kN·m couple on a 6 m span: RB = 2 ↑, RA = 2 ↓.
    await tester.tap(find.text('ANALYZE'));
    await tester.pumpAndSettle();
    expect(find.text('RB = 2.00 kN ↑'), findsWidgets);
    expect(find.textContaining('RA = −2.00 kN ⇒ 2.00 kN ↓'), findsWidgets);
  });

  testWidgets('a tap off the beam with a load tool explains why', (
    tester,
  ) async {
    final g = await open(tester, bare);
    await tester.tap(find.byKey(const ValueKey('tool-Moment')));
    await tester.pump();
    await tester.tapAt(Offset(g.left + 3 * g.perMetre, g.y + 200));
    await tester.pump();
    expect(editorOf(tester).problem.moments, isEmpty);
    expect(find.byType(SnackBar), findsOneWidget);
  });

  testWidgets('the analysis of a UDL shows its resultant step', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(
        testState(settings: const AppSettings(lang: Lang.en)),
        home: AnalysisScreen(problem: ExampleLibrary.byId('udl').problem),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('RA = 15.00 kN ↑'), findsWidgets);
    expect(find.textContaining('Mmax = 22.50 kN·m'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
