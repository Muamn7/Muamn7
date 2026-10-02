import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

DiagramTour tourOf(String exampleId, {Lang lang = Lang.en}) =>
    DiagramTour.of(SolutionBuilder(lang: lang)
        .build(ExampleLibrary.byId(exampleId).problem))!;

void main() {
  test('central load: stops at the ends and under the load', () {
    final tour = tourOf('central-load');
    expect(tour.stops.map((s) => s.x), [0, 3, 6]);
    expect(tour.stops.map((s) => s.kind),
        [TourStopKind.start, TourStopKind.point, TourStopKind.end]);
    // At the load: the jump in V and M from the SFD's area.
    final at3 = tour.stops[1].lines.map((l) => l.plain).join('\n');
    expect(at3, contains('P1 = 20 kN'));
    expect(at3, contains('M(3)'));
    // Each segment has its own V(x) and M(x).
    expect(tour.segments.length, 2);
    final first = tour.segmentAt(1.5);
    expect(first.shear.single.plain, contains('V = RA'));
    expect(first.moment.first.plain, contains('M = RA·x'));
    expect(first.shearRule.single.plain, contains('V = 10'));
    expect(first.momentRule.single.plain, startsWith('M(3)'));
    expect(tour.segmentAt(3).x0, 3); // the one starting at the load
    expect(tour.segmentAt(6).x1, 6);
    expect(tour.shearAt(1), closeTo(10000, 1e-9));
    expect(tour.momentAt(3), closeTo(30000, 1e-6));
    expect(tour.shearAt(6), closeTo(-10000, 1e-9));
  });

  test('UDL: a stop where V = 0, with the maximum moment', () {
    final tour = tourOf('udl');
    final zero =
        tour.stops.where((s) => s.kind == TourStopKind.zeroShear).single;
    expect(zero.x, closeTo(3, 1e-9));
    expect(zero.lines.map((l) => l.plain).join(' '), contains('22.5'));
    // One segment: the cut stays in it all the way.
    expect(tour.segments.length, 1);
    expect(tour.segmentAt(4).moment.first.plain, contains('x²'));
  });

  test('every example: stops cover the beam, every segment is explained', () {
    for (final e in ExampleLibrary.all) {
      for (final lang in Lang.values) {
        final tour = tourOf(e.id, lang: lang);
        expect(tour.stops.first.x, 0, reason: e.id);
        expect(tour.stops.last.x, e.problem.length, reason: e.id);
        for (final seg in tour.segments) {
          expect(seg.shear, isNotEmpty, reason: '${e.id} V on ${seg.x0}');
          expect(seg.moment, isNotEmpty, reason: '${e.id} M on ${seg.x0}');
        }
        for (final stop in tour.stops.skip(1)) {
          expect(stop.lines, isNotEmpty, reason: '${e.id} at ${stop.x}');
        }
      }
    }
  });

  test('no tour for a beam that cannot be solved', () {
    const p = BeamProblem(length: 6);
    expect(DiagramTour.of(SolutionBuilder().build(p)), isNull);
  });
}
