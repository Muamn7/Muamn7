// Renders the main screens to PNG files for a visual check.
//
//   MECHSIM_SHOTS=/some/dir flutter test test/screenshots_test.dart
//
// Skipped unless MECHSIM_SHOTS is set: it needs real fonts from the Flutter
// SDK and the system, which CI does not promise.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mechsim/state/app_state.dart';
import 'package:mechsim/ui/analysis/analysis_screen.dart';
import 'package:mechsim/ui/editor/editor_screen.dart';
import 'package:mechsim/ui/player/player_screen.dart';
import 'package:mechsim_core/mechsim_core.dart';

import 'support/harness.dart';

void main() {
  final dir = Platform.environment['MECHSIM_SHOTS'];
  final skip = dir == null ? 'set MECHSIM_SHOTS to render screenshots' : null;
  final example = ExampleLibrary.byId('central-load').problem;

  setUpAll(() async {
    if (dir != null) expect(await loadRealFonts(), isTrue);
  });

  // Real shadows instead of the test framework's black outlines, switched
  // back on before the test ends so the framework's invariants hold.
  void shot(String name, Future<void> Function(WidgetTester tester) body) {
    testWidgets(name, (tester) async {
      debugDisableShadows = false;
      try {
        await body(tester);
      } finally {
        debugDisableShadows = true;
      }
    }, skip: skip != null);
  }

  Future<void> settle(WidgetTester tester) async {
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 120));
    }
  }

  /// Scrolls the step list until [finder] is on screen, below the diagrams.
  Future<void> scrollTo(WidgetTester tester, Finder finder) async {
    final list = find.byType(Scrollable).last;
    for (var i = 0; i < 60 && finder.evaluate().isEmpty; i++) {
      await tester.drag(list, const Offset(0, -250));
      await tester.pump(const Duration(milliseconds: 50));
    }
    await tester.ensureVisible(finder.first);
    await tester.drag(list, const Offset(0, 120));
    await settle(tester);
  }

  shot('home', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(await app(testState()));
    await settle(tester);
    await shoot(tester, dir!, '01_home_ar');
  });

  shot('editor', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(
        testState(),
        home: EditorScreen(problem: example, name: 'Beam 6 m'),
      ),
    );
    await settle(tester);
    await shoot(tester, dir!, '02_editor_ar');
    // Select the load to show its properties.
    final state = tester.state<State<EditorScreen>>(find.byType(EditorScreen));
    (state as dynamic).controller.select('p1');
    await settle(tester);
    await shoot(tester, dir, '03_editor_load_selected');
  });

  shot('analysis', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(testState(), home: AnalysisScreen(problem: example)),
    );
    await settle(tester);
    await shoot(tester, dir!, '04_analysis_ar');

    await tester.tap(find.textContaining('RB = 10.00 kN').first);
    await settle(tester);
    await shoot(tester, dir, '05_analysis_rb_tapped');

    final term = find.text('RB × 6', findRichText: true);
    await scrollTo(tester, term);
    await tester.tap(term.first);
    await settle(tester);
    await shoot(tester, dir, '06_analysis_term_tapped');

    final mmax = find.textContaining('M+max', findRichText: true);
    await scrollTo(tester, mmax);
    await tester.tap(mmax.first);
    await settle(tester);
    await shoot(tester, dir, '07_analysis_mmax');
  });

  shot('analysis in English, overhang', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(
        testState(settings: const AppSettings(lang: Lang.en)),
        home: AnalysisScreen(problem: ExampleLibrary.byId('overhang').problem),
      ),
    );
    await settle(tester);
    await tester.tapAt(const Offset(206 + 70, 330));
    await settle(tester);
    await shoot(tester, dir!, '08_overhang_en');
  });

  shot('inclined load, dark', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(
        testState(
          settings: const AppSettings(lang: Lang.en, theme: ThemePref.dark),
        ),
        home: AnalysisScreen(
          problem: ExampleLibrary.byId('inclined-load').problem,
        ),
      ),
    );
    await settle(tester);
    await shoot(tester, dir!, '09_inclined_dark');
  });

  shot('player', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(testState(), home: PlayerScreen(problem: example)),
    );
    await settle(tester);
    await shoot(tester, dir!, '10_player_step1');
    for (var i = 0; i < 3; i++) {
      await tester.tap(find.byIcon(Icons.skip_next));
      await settle(tester);
    }
    await shoot(tester, dir, '11_player_sum_ma');
    for (var i = 0; i < 5; i++) {
      await tester.tap(find.byIcon(Icons.skip_next));
      await settle(tester);
    }
    await shoot(tester, dir, '12_player_sfd');
  });

  shot('practice', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(await app(testState()));
    await settle(tester);
    await tester.tap(find.byIcon(Icons.quiz_outlined).last);
    await settle(tester);
    await tester.enterText(find.byKey(const ValueKey('practice-answer')), '3');
    await tester.tap(find.byKey(const ValueKey('practice-check')));
    await settle(tester);
    await shoot(tester, dir!, '13_practice_hint');
  });

  shot('settings and learn', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(await app(testState()));
    await settle(tester);
    await tester.tap(find.byIcon(Icons.settings_outlined));
    await settle(tester);
    await shoot(tester, dir!, '14_settings');
    await tester.tap(find.byIcon(Icons.school_outlined));
    await settle(tester);
    await tester.tap(find.byType(ListTile).at(4));
    await settle(tester);
    await shoot(tester, dir, '15_tutorial_sfd');
  });

  const sideways = Size(892, 412);

  shot('landscape: home', (tester) async {
    phoneSize(tester, logical: sideways);
    await tester.pumpWidget(await app(testState()));
    await settle(tester);
    await shoot(tester, dir!, '20_land_home');
  });

  shot('landscape: editor', (tester) async {
    phoneSize(tester, logical: sideways);
    await tester.pumpWidget(
      await app(
        testState(),
        home: EditorScreen(problem: example, name: 'Beam 6 m'),
      ),
    );
    await settle(tester);
    await shoot(tester, dir!, '21_land_editor');
    final state = tester.state<State<EditorScreen>>(find.byType(EditorScreen));
    (state as dynamic).controller.select('p1');
    await settle(tester);
    await shoot(tester, dir, '22_land_editor_selected');
  });

  shot('landscape: analysis', (tester) async {
    phoneSize(tester, logical: sideways);
    await tester.pumpWidget(
      await app(testState(), home: AnalysisScreen(problem: example)),
    );
    await settle(tester);
    final term = find.text('RB × 6', findRichText: true);
    await scrollTo(tester, term);
    await tester.tap(term.first);
    await settle(tester);
    await shoot(tester, dir!, '23_land_analysis');
  });

  shot('landscape: player', (tester) async {
    phoneSize(tester, logical: sideways);
    await tester.pumpWidget(
      await app(testState(), home: PlayerScreen(problem: example)),
    );
    await settle(tester);
    for (var i = 0; i < 8; i++) {
      await tester.tap(find.byIcon(Icons.skip_next));
      await settle(tester);
    }
    await settle(tester);
    await shoot(tester, dir!, '24_land_player');
  });

  shot('landscape: practice', (tester) async {
    phoneSize(tester, logical: sideways);
    await tester.pumpWidget(await app(testState()));
    await settle(tester);
    await tester.tap(find.byIcon(Icons.quiz_outlined).last);
    await settle(tester);
    await tester.enterText(find.byKey(const ValueKey('practice-answer')), '3');
    await tester.tap(find.byKey(const ValueKey('practice-check')));
    await settle(tester);
    await shoot(tester, dir!, '25_land_practice');
  });

  const mixed = BeamProblem(
    length: 8,
    supports: [
      Support(id: 's1', type: SupportType.pin, x: 0),
      Support(id: 's2', type: SupportType.roller, x: 6),
    ],
    loads: [
      DistributedLoad(id: 'w1', x: 0, x2: 4, w1: 5000, w2: 5000),
      DistributedLoad(id: 'w2', x: 6, x2: 8, w1: 0, w2: 6000),
      PointLoad(id: 'p1', x: 5, magnitude: 10000),
      PointMoment(id: 'c1', x: 4.5, magnitude: 8000),
    ],
  );

  shot('loads: editor', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(testState(), home: const EditorScreen(problem: mixed)),
    );
    await settle(tester);
    await shoot(tester, dir!, '30_loads_editor');
    final state = tester.state<State<EditorScreen>>(find.byType(EditorScreen));
    (state as dynamic).controller.select('w1');
    await settle(tester);
    await shoot(tester, dir, '31_loads_udl_selected');
    (state as dynamic).controller.select('w2');
    await settle(tester);
    await shoot(tester, dir, '32_loads_uvl_selected');
    (state as dynamic).controller.select('c1');
    await settle(tester);
    await shoot(tester, dir, '33_loads_moment_selected');
  });

  shot('loads: analysis', (tester) async {
    phoneSize(tester);
    await tester.pumpWidget(
      await app(testState(), home: const AnalysisScreen(problem: mixed)),
    );
    await settle(tester);
    await shoot(tester, dir!, '34_loads_analysis');
    final term = find.text('x̄(W1)', findRichText: true);
    await scrollTo(tester, term);
    await tester.tap(term.first);
    await settle(tester);
    await shoot(tester, dir, '35_loads_resultant');
  });

  shot('loads: landscape editor', (tester) async {
    phoneSize(tester, logical: const Size(892, 412));
    await tester.pumpWidget(
      await app(testState(), home: const EditorScreen(problem: mixed)),
    );
    await settle(tester);
    await shoot(tester, dir!, '36_loads_land_editor');
  });

  shot('loads: small phone', (tester) async {
    phoneSize(tester, logical: const Size(360, 740));
    await tester.pumpWidget(
      await app(testState(), home: const EditorScreen(problem: mixed)),
    );
    await settle(tester);
    await shoot(tester, dir!, '37_loads_small_phone');
  });

  shot('loads: phone sideways, dark', (tester) async {
    // The size of a typical phone turned sideways, in the dark theme.
    phoneSize(tester, logical: const Size(800, 360));
    await tester.pumpWidget(
      await app(
        testState(settings: const AppSettings(theme: ThemePref.dark)),
        home: const EditorScreen(problem: mixed),
      ),
    );
    await settle(tester);
    await shoot(tester, dir!, '38_land_dark_editor');
    final state = tester.state<State<EditorScreen>>(find.byType(EditorScreen));
    (state as dynamic).controller.select('w2');
    await settle(tester);
    await shoot(tester, dir, '39_land_dark_uvl_selected');
    (state as dynamic).controller.select('p1');
    await settle(tester);
    await shoot(tester, dir, '40_land_dark_load_selected');
  });
}
