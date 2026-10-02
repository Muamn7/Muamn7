// The animated walk along the beam that draws the SFD and BMD.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mechsim/state/app_state.dart';
import 'package:mechsim/ui/analysis/analysis_screen.dart';
import 'package:mechsim/ui/tour/tour_screen.dart';
import 'package:mechsim_core/mechsim_core.dart';

import 'support/harness.dart';

void main() {
  final example = ExampleLibrary.byId('central-load').problem;

  Future<void> open(WidgetTester tester, {Size? size}) async {
    phoneSize(tester, logical: size ?? const Size(412, 892));
    await tester.pumpWidget(
      await app(
        testState(settings: const AppSettings(lang: Lang.en)),
        home: TourScreen(problem: example, autoplay: false),
      ),
    );
    await tester.pumpAndSettle();
  }

  /// Lets animations run: many short frames, as on a phone.
  Future<void> run(WidgetTester tester, int ms) async {
    for (var t = 0; t < ms; t += 50) {
      await tester.pump(const Duration(milliseconds: 50));
    }
  }

  double cut(WidgetTester tester) =>
      (tester.state(find.byType(TourScreen)) as dynamic).cut as double;

  testWidgets('starts at the left end with the idea of the cut', (
    tester,
  ) async {
    await open(tester);
    expect(find.textContaining('A cut moves along the beam'), findsOneWidget);
    expect(find.text('0 < x < 3 m      x = 0.00 m'), findsOneWidget);
    expect(find.textContaining('V(0.00) = +10.00 kN'), findsOneWidget);
    expect(find.textContaining('M(0.00) = 0.00 kN·m'), findsOneWidget);
  });

  testWidgets('next point: the jump under the load, explained', (tester) async {
    await open(tester);
    await tester.tap(find.byKey(const ValueKey('tour-next')));
    await run(tester, 600);
    expect(find.byKey(const ValueKey('tour-stop-3.0')), findsOneWidget);
    expect(find.textContaining('P1 = 20 kN', findRichText: true), findsWidgets);
    // Right of the load: V has jumped to −10, M is the peak 30.
    expect(find.textContaining('V(3.00) = −10.00 kN'), findsOneWidget);
    expect(find.textContaining('M(3.00) = +30.00 kN·m'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('tour-prev')));
    await run(tester, 600);
    expect(find.textContaining('V(0.00)'), findsOneWidget);
  });

  testWidgets('play walks to the end, pausing on the way', (tester) async {
    await open(tester);
    await tester.tap(find.byKey(const ValueKey('tour-play')));
    await run(tester, 2000);
    final midway = cut(tester);
    expect(midway, greaterThan(0));
    expect(midway, lessThan(3));
    await run(tester, 16000);
    expect(cut(tester), 6);
    expect(find.byKey(const ValueKey('tour-stop-6.0')), findsOneWidget);
    expect(find.byIcon(Icons.play_arrow_rounded), findsOneWidget);
  });

  testWidgets('touching the drawing moves the cut there', (tester) async {
    await open(tester);
    final canvas = tester.getRect(find.byKey(const ValueKey('tour-canvas')));
    final left = canvas.left + 58, right = canvas.right - 58;
    await tester.tapAt(Offset(left + (right - left) * 0.25, canvas.center.dy));
    await tester.pump();
    expect(cut(tester), closeTo(1.5, 0.05));
    expect(find.textContaining('V(1.50) = +10.00 kN'), findsOneWidget);
    expect(find.textContaining('M(1.50) = +15.00 kN·m'), findsOneWidget);
  });

  testWidgets('sideways it fits, and the analysis opens it', (tester) async {
    await open(tester, size: const Size(800, 360));
    expect(tester.takeException(), isNull);
    phoneSize(tester);
    await tester.pumpWidget(
      await app(
        testState(settings: const AppSettings(lang: Lang.en)),
        home: AnalysisScreen(problem: example),
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const ValueKey('open-tour')));
    await tester.tap(find.byKey(const ValueKey('open-tour')));
    await run(tester, 600);
    expect(find.byType(TourScreen), findsOneWidget);
  });
}
