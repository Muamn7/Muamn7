// Trusses: drawing one joint by joint, the method of joints and the method
// of sections.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mechsim/drawing/truss_scene.dart';
import 'package:mechsim/state/app_state.dart';
import 'package:mechsim/ui/analysis/step_card.dart';
import 'package:mechsim/ui/truss/truss_analysis_screen.dart';
import 'package:mechsim/ui/truss/truss_editor_screen.dart';
import 'package:mechsim_core/mechsim_core.dart';

import 'support/harness.dart';

const kN = 1000.0;

void main() {
  Future<void> open(
    WidgetTester tester,
    Widget home, {
    Size size = const Size(412, 892),
    Lang lang = Lang.en,
  }) async {
    phoneSize(tester, logical: size);
    await tester.pumpWidget(
      await app(testState(settings: AppSettings(lang: lang)), home: home),
    );
    await tester.pumpAndSettle();
  }

  /// Where the sheet's origin is on the screen: an empty sheet starts
  /// 40 px to the metre with the origin low on the left.
  Offset origin(WidgetTester tester) {
    final rect = tester.getRect(find.byKey(const ValueKey('truss-canvas')));
    return rect.topLeft + Offset(56, rect.height * 0.7);
  }

  Offset onResult(WidgetTester tester, TrussProblem p, double x, double y) {
    final rect = tester.getRect(find.byKey(const ValueKey('truss-result')));
    return rect.topLeft + fitTruss(p, rect.size, margin: 64).toScreen(x, y);
  }

  List<String> chips(WidgetTester tester) => [
    for (final c in tester.widgetList<ResultChip>(find.byType(ResultChip)))
      c.result.text,
  ];

  Future<void> tool(WidgetTester tester, String name) async {
    await tester.tap(find.byKey(ValueKey('truss-tool-$name')));
    await tester.pump();
  }

  testWidgets('draw a triangle, support it, load it and solve it', (
    tester,
  ) async {
    await open(tester, const TrussEditorScreen());
    final o = origin(tester);
    Offset onEditor(WidgetTester tester, double x, double y) =>
        o + Offset(x * 40, -y * 40);
    // Joints at A(0, 0), B(6, 0), C(3, 4): sides 6, 5 and 5.
    for (final (x, y) in [(0.0, 0.0), (6.0, 0.0), (3.0, 4.0)]) {
      await tester.tapAt(onEditor(tester, x, y));
      await tester.pump(const Duration(milliseconds: 400));
    }
    await tool(tester, 'member');
    for (final (x, y) in [(0.0, 0.0), (6.0, 0.0), (3.0, 4.0), (0.0, 0.0)]) {
      await tester.tapAt(onEditor(tester, x, y));
      await tester.pump(const Duration(milliseconds: 400));
    }
    await tool(tester, 'pin');
    await tester.tapAt(onEditor(tester, 0, 0));
    await tester.pump(const Duration(milliseconds: 400));
    await tool(tester, 'roller');
    await tester.tapAt(onEditor(tester, 6, 0));
    await tester.pump(const Duration(milliseconds: 400));
    await tool(tester, 'load');
    await tester.tapAt(onEditor(tester, 3, 4));
    await tester.pumpAndSettle();
    // The new load is selected: 10 kN straight down.
    expect(find.text('Load @ C'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('truss-analyze')));
    await tester.pumpAndSettle();
    expect(find.text('Truss analysis'), findsOneWidget);
    final results = chips(tester);
    // Each support takes half; the sloping sides push (C), the base pulls (T).
    expect(results, contains('F_AB = 3.75 kN (T)'));
    expect(results, contains('F_AC = −6.25 kN ⇒ 6.25 kN (C)'));
    expect(results, contains('F_BC = −6.25 kN ⇒ 6.25 kN (C)'));
    expect(results.where((r) => r.contains('= 5.00 kN ↑')).toSet().length, 2);
  });

  testWidgets('a template, then the method of joints step by step', (
    tester,
  ) async {
    await open(tester, const TrussEditorScreen());
    await tester.tap(find.byKey(const ValueKey('truss-templates')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('template-pratt')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('truss-analyze')));
    await tester.pumpAndSettle();
    final results = chips(tester);
    expect(results, containsAll(['Ay = 15.00 kN ↑', 'Ey = 15.00 kN ↑']));
    expect(results, contains('F_AB = 15.00 kN (T)'));
    expect(results, contains('F_AF = −21.21 kN ⇒ 21.21 kN (C)'));
    expect(find.byType(StepCard), findsWidgets);

    // Tapping a joint in the drawing opens its step.
    final p = TrussTemplates.build('pratt');
    await tester.tapAt(onResult(tester, p, 0, 0));
    // The drawing keeps pulsing, so step through the scroll by hand.
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 60));
    }
    expect(
      find.textContaining('Joint A', findRichText: true).hitTestable(),
      findsWidgets,
    );
  });

  testWidgets('method of sections: cut three members by tapping them', (
    tester,
  ) async {
    final p = TrussTemplates.build('pratt');
    await open(tester, TrussAnalysisScreen(problem: p));
    await tester.tap(find.byKey(const ValueKey('tab-sections')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Tap the members the section cuts'), findsOne);

    // The second panel: bottom chord BC, top chord FG and diagonal CF.
    for (final (x, y) in [(4.5, 0.0), (4.5, 3.0), (4.5, 1.5)]) {
      await tester.tapAt(onResult(tester, p, x, y));
      await tester.pumpAndSettle();
    }
    expect(find.byType(InputChip), findsNWidgets(3));
    expect(find.byKey(const ValueKey('cut-error')), findsNothing);
    expect(find.byType(StepCard), findsNWidgets(5));
    // Each force comes out of one equation, and agrees with the joints.
    const forces = [
      'F_FG = −20.00 kN ⇒ 20.00 kN (C)',
      'F_BC = 15.00 kN (T)',
      'F_CF = 7.07 kN (T)',
    ];
    expect(chips(tester), containsAll(forces));

    // The other part gives the same forces.
    await tester.tap(find.byKey(const ValueKey('other-side')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('cut-error')), findsNothing);
    expect(chips(tester), containsAll(forces));

    // Clearing starts again.
    await tester.tap(find.byKey(const ValueKey('clear-cut')));
    await tester.pumpAndSettle();
    expect(find.byType(InputChip), findsNothing);
    expect(find.byType(StepCard), findsNothing);
  });

  testWidgets('a cut that does not split the truss says so', (tester) async {
    final p = TrussTemplates.build('pratt');
    await open(tester, TrussAnalysisScreen(problem: p));
    await tester.tap(find.byKey(const ValueKey('tab-sections')));
    await tester.pumpAndSettle();
    await tester.tapAt(onResult(tester, p, 4.5, 0));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('cut-error')), findsOneWidget);
  });

  testWidgets('a truss that cannot stand explains why', (tester) async {
    final p = TrussTemplates.build('triangle').remove('s2');
    await open(tester, TrussAnalysisScreen(problem: p));
    expect(find.byType(ResultChip), findsNothing);
    expect(find.text('Back to editing'), findsOneWidget);
  });

  testWidgets('sideways: the drawing beside the steps, no overflow', (
    tester,
  ) async {
    final p = TrussTemplates.build('warren');
    await open(
      tester,
      TrussEditorScreen(problem: p),
      size: const Size(892, 412),
    );
    expect(find.byKey(const ValueKey('truss-tool-joint')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('truss-analyze')));
    await tester.pumpAndSettle();
    final drawing = tester.getRect(find.byKey(const ValueKey('truss-result')));
    expect(drawing.height, greaterThan(300));
    expect(drawing.right, lessThan(892 * 0.6));
    expect(tester.takeException(), isNull);
  });

  testWidgets('Arabic: the editor and both methods', (tester) async {
    final p = TrussTemplates.build('howe');
    await open(tester, TrussEditorScreen(problem: p), lang: Lang.ar);
    expect(find.text('جملون جديد'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('truss-analyze')));
    await tester.pumpAndSettle();
    expect(find.text('طريقة الوصلات'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('tab-sections')));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
