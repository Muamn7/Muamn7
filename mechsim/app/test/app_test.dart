import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mechsim/drawing/linked_diagrams.dart';
import 'package:mechsim/state/app_state.dart';
import 'package:mechsim/state/editor_controller.dart';
import 'package:mechsim/ui/analysis/analysis_screen.dart';
import 'package:mechsim/ui/editor/editor_screen.dart';
import 'package:mechsim/ui/player/player_screen.dart';
import 'package:mechsim/ui/practice/practice_screen.dart';
import 'package:mechsim_core/mechsim_core.dart';

import 'support/harness.dart';

EditorController editorOf(WidgetTester tester) =>
    (tester.state(find.byType(EditorScreen)) as dynamic).controller
        as EditorController;

void main() {
  final example = ExampleLibrary.byId('central-load').problem;

  testWidgets('draw a beam, add supports and a load, then ANALYZE', (
    tester,
  ) async {
    phoneSize(tester);
    await tester.pumpWidget(await app(testState(), home: const EditorScreen()));
    await tester.pumpAndSettle();

    final canvas = tester.getRect(
      find
          .descendant(
            of: find.byType(EditorCanvas),
            matching: find.byType(CustomPaint),
          )
          .first,
    );
    final y = canvas.top + canvas.height * 0.45;

    // The Beam tool is active on an empty sheet; 300 px at 50 px/m is 6 m.
    await tester.dragFrom(Offset(canvas.left + 50, y), const Offset(300, 0));
    await tester.pumpAndSettle();
    final c = editorOf(tester);
    expect(c.problem.length, 6);

    // The view refits the beam to the width with 56 px margins.
    final left = canvas.left + 56, right = canvas.right - 56;
    final mid = (left + right) / 2;

    await tester.tap(find.byKey(const ValueKey('tool-Pin')));
    await tester.pump();
    await tester.tapAt(Offset(left, y));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('tool-Roller')));
    await tester.pump();
    await tester.tapAt(Offset(right, y));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('tool-Point Load')));
    await tester.pump();
    await tester.tapAt(Offset(mid, y));
    await tester.pumpAndSettle();

    expect(c.problem.supports.map((s) => (s.type, s.x)), [
      (SupportType.pin, 0.0),
      (SupportType.roller, 6.0),
    ]);
    expect(c.problem.pointLoads.single.x, 3);

    // The new load is selected: set it to 20 kN in the properties panel.
    await tester.enterText(find.widgetWithText(TextField, 'Magnitude'), '20');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(c.problem.pointLoads.single.magnitude, 20000);

    // Undo restores 10 kN, redo brings 20 kN back.
    c.undo();
    expect(c.problem.pointLoads.single.magnitude, 10000);
    c.redo();
    expect(c.problem.pointLoads.single.magnitude, 20000);

    await tester.tap(find.text('ANALYZE'));
    await tester.pumpAndSettle();
    expect(find.byType(AnalysisScreen), findsOneWidget);
    expect(find.text('RB = 10.00 kN ↑'), findsWidgets);
    expect(find.text('RA = 10.00 kN ↑'), findsWidgets);
    expect(find.textContaining('Mmax = 30.00 kN·m'), findsWidgets);
  });

  testWidgets('dragging a load moves it along the beam, snapped', (
    tester,
  ) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(testState(), home: EditorScreen(problem: example)),
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
    final perMetre = (right - left) / 6;
    final y = canvas.top + canvas.height * 0.45;
    // Grab the load arrow above the beam and drag it one metre right.
    await tester.dragFrom(
      Offset(left + 3 * perMetre, y - 30),
      Offset(perMetre, 0),
    );
    await tester.pumpAndSettle();
    expect(editorOf(tester).problem.pointLoads.single.x, 4);
    editorOf(tester).undo();
    expect(editorOf(tester).problem.pointLoads.single.x, 3);
  });

  testWidgets('tapping a result lights it up on the drawing', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(testState(), home: AnalysisScreen(problem: example)),
    );
    await tester.pumpAndSettle();
    LinkedDiagrams diagrams() =>
        tester.widget<LinkedDiagrams>(find.byType(LinkedDiagrams));

    await tester.tap(find.text('RB = 10.00 kN ↑').first);
    await tester.pump(const Duration(milliseconds: 100));
    expect(diagrams().highlights.items, [
      const ReactionHighlight('s2.vertical'),
    ]);

    await tester.tap(find.textContaining('Mmax = 30.00').first);
    await tester.pump(const Duration(milliseconds: 100));
    final h = diagrams().highlights.items.single as DiagramPointHighlight;
    expect((h.kind, h.x), (DiagramKind.moment, 3.0));
  });

  testWidgets('tapping a term explains it and shows its arm', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(testState(), home: AnalysisScreen(problem: example)),
    );
    await tester.pumpAndSettle();
    final term = find.text('RB × 6', findRichText: true);
    final list = find.byType(Scrollable).last;
    for (var i = 0; i < 40 && term.evaluate().isEmpty; i++) {
      await tester.drag(list, const Offset(0, -200));
      await tester.pump();
    }
    await tester.ensureVisible(term.first);
    await tester.pumpAndSettle();
    await tester.tap(term.first);
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.textContaining('هي قوة رد الفعل عند المسند'), findsOneWidget);
    final items =
        tester
            .widget<LinkedDiagrams>(find.byType(LinkedDiagrams))
            .highlights
            .items;
    expect(items, contains(const ArmHighlight(0, 6)));
    expect(items, contains(const MomentCentreHighlight(0)));
  });

  testWidgets('practice: a right answer and a hinted wrong one', (
    tester,
  ) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(testState(settings: const AppSettings(lang: Lang.en))),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Practice').last);
    await tester.pumpAndSettle();

    final answer = find.byKey(const ValueKey('practice-answer'));
    await tester.enterText(answer, '-1234');
    await tester.tap(find.byKey(const ValueKey('practice-check')));
    await tester.pump();
    expect(find.textContaining('Review'), findsOneWidget);
    expect(find.text('Show Solution'), findsOneWidget);

    // Read the right answer out of the engine and type it in.
    final state = tester.state(find.byType(PracticeView)) as dynamic;
    final session = state.sessionForTest as PracticeSession;
    final q = session.questions.first;
    final right = session.units.toDisplay(q.answerSi, q.dimension);
    await tester.enterText(answer, right.toStringAsFixed(3));
    await tester.tap(find.byKey(const ValueKey('practice-check')));
    await tester.pump();
    expect(find.text('✓ Correct'), findsOneWidget);
    expect(find.text('Next question'), findsOneWidget);
  });

  testWidgets('player: start at the problem, step forward and back', (
    tester,
  ) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(
        testState(settings: const AppSettings(lang: Lang.en)),
        home: PlayerScreen(problem: example),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Step 1 of 12'), findsOneWidget);
    expect(find.text('The problem'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.skip_next));
    // The highlight pulses while a step points at something, so the
    // frames never settle: pump a fixed time instead.
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('Step 2 of 12'), findsOneWidget);
    expect(find.text('Free Body Diagram (FBD)'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.skip_previous));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('Step 1 of 12'), findsOneWidget);
  });

  testWidgets('save a problem and find it in Saved', (tester) async {
    phoneSize(tester);
    final state = testState(settings: const AppSettings(lang: Lang.en));
    await tester.pumpWidget(
      await app(state, home: EditorScreen(problem: example)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.save_outlined));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Homework 1');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(state.saved.single.name, 'Homework 1');
    expect(state.saved.single.problem.length, 6);
  });

  testWidgets('switching the language to English', (tester) async {
    phoneSize(tester);
    final state = testState();
    await tester.pumpWidget(await app(state));
    await tester.pumpAndSettle();
    expect(find.text('الرئيسية'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.settings_outlined));
    await tester.pumpAndSettle();
    await tester.tap(find.text('English'));
    await tester.pumpAndSettle();
    expect(state.lang, Lang.en);
    expect(find.text('Home'), findsOneWidget);
  });

  group('landscape', () {
    const sideways = Size(892, 412);

    testWidgets('home uses a navigation rail instead of the bottom bar', (
      tester,
    ) async {
      phoneSize(tester, logical: sideways);
      await tester.pumpWidget(await app(testState()));
      await tester.pumpAndSettle();
      expect(find.byType(NavigationRail), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);
    });

    testWidgets('editor: tool list, sheet, side panel and bottom bar', (
      tester,
    ) async {
      phoneSize(tester, logical: sideways);
      const start = BeamProblem(
        length: 6,
        supports: [Support(id: 's1', type: SupportType.pin, x: 0)],
      );
      await tester.pumpWidget(
        await app(
          testState(settings: const AppSettings(lang: Lang.en)),
          home: const EditorScreen(problem: start),
        ),
      );
      await tester.pumpAndSettle();
      final c = editorOf(tester);

      // The tool list down the start side, the panel down the end side,
      // the sheet between them and ANALYZE in the bottom bar.
      final select = tester.getRect(find.byKey(const ValueKey('tool-Select')));
      final beam = tester.getRect(find.byKey(const ValueKey('tool-Beam')));
      expect(select.left, lessThan(20));
      expect(beam.top, greaterThan(select.top));
      final canvas = tester.getRect(find.byType(EditorCanvas));
      expect(canvas.left, greaterThan(select.right));
      expect(canvas.width, greaterThan(892 - 132 - 236 - 40));
      final status = tester.getRect(find.byKey(const ValueKey('status-card')));
      expect(status.left, greaterThan(canvas.right));
      // One support only: the panel says why it cannot be solved yet.
      expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);

      final left = canvas.left + 56, right = canvas.right - 56;
      final perMetre = (right - left) / 6;
      final y = canvas.top + canvas.height * 0.45;

      // Support: pick Roller in the panel, then tap the end of the beam.
      await tester.tap(find.byKey(const ValueKey('tool-Support')));
      await tester.pump();
      await tester.tap(find.byTooltip('Roller'));
      await tester.pump();
      await tester.tapAt(Offset(right, y));
      await tester.pumpAndSettle();
      expect(c.problem.supports.last.type, SupportType.roller);
      expect(c.problem.supports.last.x, 6);
      expect(find.byIcon(Icons.check_circle), findsOneWidget);

      // Point Load: set 25 kN in the panel before placing it.
      await tester.tap(find.byKey(const ValueKey('tool-Point Load')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.descendant(
          of: find.byKey(const ValueKey('next-magnitude')),
          matching: find.byType(TextField),
        ),
        '25',
      );
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
      await tester.tapAt(Offset(left + 3 * perMetre, y));
      await tester.pumpAndSettle();
      expect(c.problem.pointLoads.single.magnitude, 25000);
      expect(c.problem.pointLoads.single.x, 3);
      // The new load is selected and its values fill the panel's card.
      final magnitude = tester.getRect(
        find.widgetWithText(TextField, 'Magnitude'),
      );
      expect(magnitude.left, greaterThan(canvas.right));

      // Display switches.
      await tester.ensureVisible(find.byKey(const ValueKey('switch-grid')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('switch-grid')));
      await tester.pump();
      expect(c.showGrid, isFalse);

      // The side panel can be hidden for a wider sheet.
      await tester.tap(find.byKey(const ValueKey('toggle-panel')));
      await tester.pumpAndSettle();
      expect(
        tester.getRect(find.byType(EditorCanvas)).width,
        greaterThan(canvas.width + 200),
      );

      await tester.tap(find.byKey(const ValueKey('analyze')));
      await tester.pumpAndSettle();
      expect(find.byType(AnalysisScreen), findsOneWidget);
      expect(find.text('RA = 12.50 kN ↑'), findsWidgets);
    });

    testWidgets('editor: typing a length on an empty sheet draws the beam', (
      tester,
    ) async {
      phoneSize(tester, logical: sideways);
      await tester.pumpWidget(
        await app(
          testState(settings: const AppSettings(lang: Lang.en)),
          home: const EditorScreen(),
        ),
      );
      await tester.pumpAndSettle();
      await tester.enterText(
        find.descendant(
          of: find.byKey(const ValueKey('bottom-length')),
          matching: find.byType(TextField),
        ),
        '8',
      );
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
      expect(editorOf(tester).problem.length, 8);
      expect(editorOf(tester).problem.hasBeam, isTrue);
    });

    testWidgets('analysis shows the diagrams beside the steps', (tester) async {
      phoneSize(tester, logical: sideways);
      await tester.pumpWidget(
        await app(
          testState(settings: const AppSettings(lang: Lang.en)),
          home: AnalysisScreen(problem: example),
        ),
      );
      await tester.pumpAndSettle();
      final diagrams = tester.getRect(find.byType(LinkedDiagrams));
      expect(diagrams.width, lessThan(892 * 0.6));
      expect(diagrams.height, greaterThan(300));
      expect(find.text('RB = 10.00 kN ↑'), findsWidgets);
    });

    testWidgets('player and practice fit sideways', (tester) async {
      phoneSize(tester, logical: sideways);
      await tester.pumpWidget(
        await app(
          testState(settings: const AppSettings(lang: Lang.en)),
          home: PlayerScreen(problem: example),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Step 1 of 12'), findsOneWidget);
      await tester.pumpWidget(
        await app(
          testState(settings: const AppSettings(lang: Lang.en)),
          home: Scaffold(body: PracticeView(problem: example)),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('practice-check')), findsOneWidget);
    });

    testWidgets('the orientation setting is kept', (tester) async {
      phoneSize(tester);
      final state = testState(settings: const AppSettings(lang: Lang.en));
      await tester.pumpWidget(await app(state));
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.settings_outlined));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Landscape'));
      await tester.pumpAndSettle();
      expect(state.settings.orientation, OrientationPref.landscape);
      expect(
        AppSettings.fromJson(state.settings.toJson()).orientation,
        OrientationPref.landscape,
      );
    });
  });
}
