// Solves a beam from the command line and prints the full explanation.
//
//   dart run mechsim_core:mechsim --length 6 --pin 0 --roller 6 --load 20@3
//   dart run mechsim_core:mechsim --length 4 --fixed 0 --load 10@4 --lang en
//   dart run mechsim_core:mechsim --json problem.json
//
// Lengths in metres and forces in kN unless --units says otherwise
// (kN-m, N-m or N-mm). A load is MAGNITUDE@X or MAGNITUDE@X@ANGLE, the angle
// in degrees counter-clockwise from +x (−90, the default, points down).
// Distributed loads: --udl W@FROM:TO, --uvl W1:W2@FROM:TO (downward);
// couples: --couple M@X (counter-clockwise positive).
// ignore_for_file: avoid_print

import 'dart:convert';
import 'dart:io';

import 'package:mechsim_core/mechsim_core.dart';

void main(List<String> args) {
  var lang = Lang.ar;
  var units = UnitSystem.knM;
  var problem = const BeamProblem();
  var detail = false;

  double len(String v) => units.fromDisplay(_number(v), Dimension.length);
  double force(String v) => units.fromDisplay(_number(v), Dimension.force);

  for (var i = 0; i < args.length; i++) {
    final arg = args[i];
    String next() {
      if (i + 1 >= args.length) _fail('$arg needs a value');
      return args[++i];
    }

    switch (arg) {
      case '--lang':
        lang = Lang.values.byName(next());
      case '--units':
        units = switch (next()) {
          'kN-m' => UnitSystem.knM,
          'N-m' => UnitSystem.nM,
          'N-mm' => UnitSystem.nMm,
          final other => _fail('unknown units "$other"'),
        };
      case '--length':
        problem = problem.copyWith(length: len(next()));
      case '--pin' || '--roller' || '--fixed':
        final type = SupportType.values.byName(arg.substring(2));
        problem = problem.withSupport(Support(
            id: problem.nextId('s'), type: type, x: len(next())));
      case '--load':
        final parts = next().split('@');
        if (parts.length < 2) _fail('a load is MAGNITUDE@X[@ANGLE]');
        problem = problem.withLoad(PointLoad(
          id: problem.nextId('p'),
          magnitude: force(parts[0]),
          x: len(parts[1]),
          angleDeg: parts.length > 2 ? _number(parts[2]) : -90,
        ));
      case '--udl' || '--uvl':
        // --udl W@FROM:TO  or  --uvl W1:W2@FROM:TO   (kN/m, downward)
        final parts = next().split('@');
        final w = parts[0].split(':');
        final span = parts[1].split(':');
        final unit = units.force.toSi / units.length.toSi;
        problem = problem.withLoad(DistributedLoad(
          id: problem.nextId('w'),
          x: len(span[0]),
          x2: len(span[1]),
          w1: _number(w[0]) * unit,
          w2: _number(w.length > 1 ? w[1] : w[0]) * unit,
        ));
      case '--couple':
        // --couple M@X   (positive counter-clockwise)
        final parts = next().split('@');
        final value = units.fromDisplay(_number(parts[0]), Dimension.moment);
        problem = problem.withLoad(PointMoment(
          id: problem.nextId('c'),
          x: len(parts[1]),
          magnitude: value.abs(),
          counterClockwise: value >= 0,
        ));
      case '--json':
        final json = jsonDecode(File(next()).readAsStringSync());
        problem = BeamProblem.fromJson(json as Map<String, Object?>);
      case '--detail':
        detail = true;
      case '--help' || '-h':
        print(File.fromUri(Platform.script).readAsLinesSync()
            .takeWhile((l) => l.startsWith('//'))
            .map((l) => l.replaceFirst(RegExp('^// ?'), ''))
            .join('\n'));
        return;
      default:
        _fail('unknown argument "$arg" (try --help)');
    }
  }

  final solution =
      SolutionBuilder(lang: lang, units: units).build(problem);
  print(TextRenderer.render(solution, withDetail: detail));
  if (solution.validation != null && !solution.validation!.allPassed) {
    exitCode = 1;
  }
}

double _number(String text) => Num.parse(text) ?? _fail('not a number: "$text"');

Never _fail(String message) {
  stderr.writeln('mechsim: $message');
  exit(64);
}
