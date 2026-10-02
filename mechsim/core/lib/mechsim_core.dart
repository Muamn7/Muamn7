/// MechSim 2D engine.
///
/// The layers, from the bottom up:
/// * units — the Unit Conversion Engine;
/// * model — the beam, its supports and loads, labels and sign conventions;
/// * statics — the Physics Engine (actions) and the reactions solver;
/// * diagrams — internal forces by the method of sections and the Graph
///   Engine that turns them into drawable outlines;
/// * validation — equilibrium and diagram self-checks;
/// * explain — the Educational Explanation Engine;
/// * practice — the Problem Generator and answer checking;
/// * storage — saving and loading problems;
/// * content — the example library and the tutorials.
library;

export 'src/content/examples.dart';
export 'src/content/tutorials.dart';
export 'src/diagrams/graph.dart';
export 'src/diagrams/internal_forces.dart';
export 'src/diagrams/polynomial.dart';
export 'src/explain/highlight.dart';
export 'src/explain/lang.dart';
export 'src/explain/solution.dart';
export 'src/explain/solution_builder.dart';
export 'src/explain/text_renderer.dart';
export 'src/explain/tour.dart';
export 'src/model/beam_problem.dart';
export 'src/model/labels.dart';
export 'src/model/sign_convention.dart';
export 'src/practice/generator.dart';
export 'src/practice/practice.dart';
export 'src/statics/actions.dart';
export 'src/statics/equilibrium.dart';
export 'src/storage/storage.dart';
export 'src/units/format.dart';
export 'src/units/unit.dart';
export 'src/validation/validator.dart';
