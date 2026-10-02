/// Educational Explanation Engine: turns a solved beam into the steps a
/// student follows — the FBD, each equilibrium equation in the order a
/// textbook takes them, the check, the method of sections for V and M, the
/// diagrams, and where the maximum moment is and why.
///
/// Every number shown is computed from the problem; nothing is canned. The
/// equations come from the same [EquilibriumEquation] objects the solver
/// uses, and the step order is chosen by [planEquations] for whatever supports the
/// student drew.
library;

import 'dart:math' as math;

import '../diagrams/internal_forces.dart';
import '../diagrams/polynomial.dart';
import '../model/beam_problem.dart';
import '../model/labels.dart';
import '../model/sign_convention.dart';
import '../statics/actions.dart';
import '../statics/equilibrium.dart';
import '../units/format.dart';
import '../units/unit.dart';
import '../validation/validator.dart';
import 'highlight.dart';
import 'lang.dart';
import 'solution.dart';

class SolutionBuilder {
  const SolutionBuilder({
    this.lang = Lang.ar,
    this.units = UnitSystem.knM,
    this.convention = SignConvention.standard,
  });

  final Lang lang;
  final UnitSystem units;
  final SignConvention convention;

  Solution build(BeamProblem problem) {
    final statics = StaticsSolver.solve(problem);
    final w = _Writer(statics, Texts.of(lang), units, convention);
    if (!statics.isSolved) {
      return Solution(
        problem: problem,
        statics: statics,
        lang: lang,
        units: units,
        convention: convention,
        steps: [if (problem.hasBeam) w.given(), w.unsolvable()],
      );
    }
    final forces = InternalForceAnalyzer.analyze(statics);
    final validation = SolutionValidator.validate(statics, forces);
    return Solution(
      problem: problem,
      statics: statics,
      lang: lang,
      units: units,
      convention: convention,
      forces: forces,
      validation: validation,
      steps: w.steps(forces),
      results: w.keyResults(forces),
    );
  }
}

/// One equation in the solving order, and what it solves for.
class PlannedEquation {
  const PlannedEquation(this.equation, this.solves, this.label);

  final EquilibriumEquation equation;
  final Reaction solves;

  /// The letter of the moment centre, for a moment equation.
  final String? label;
}

/// The order a textbook solves the reactions in, for any determinate set of
/// supports: at each stage take an equation with exactly one unknown left,
/// preferring ΣFx first, then moments about the support that carries the
/// most unknowns (so they drop out), then ΣFy. A cantilever is done in the
/// order ΣFx, ΣFy, ΣM about the fixed end.
List<PlannedEquation> planEquations(StaticsSolution s) {
  final builder = s.equations;
  final supports = [...s.problem.supports]..sort((a, b) {
      final byCount = reactionKindsOf(b.type).length
          .compareTo(reactionKindsOf(a.type).length);
      return byCount != 0 ? byCount : a.x.compareTo(b.x);
    });
  final hasFixed = s.reactions.any((r) => r.kind == ReactionKind.moment);

  final moments = [
    for (final sup in supports)
      (builder.sumMoment(sup.x), s.labels.pointOf(sup.id)),
  ];
  // Pin + roller: ΣFx, ΣM about the pin (two unknowns drop out), ΣFy.
  // Cantilever: ΣFx, ΣFy, ΣM about the fixed end. The other moment
  // equations stay as fall-backs and as the independent check.
  final candidates = <(EquilibriumEquation, String?)>[
    (builder.sumFx(), null),
    if (hasFixed) (builder.sumFy(), null),
    if (moments.isNotEmpty) moments.first,
    if (!hasFixed) (builder.sumFy(), null),
    ...moments.skip(1),
  ];

  final known = <String>{};
  final plan = <PlannedEquation>[];
  final used = <int>{};
  while (known.length < s.reactions.length) {
    var progressed = false;
    for (var i = 0; i < candidates.length; i++) {
      if (used.contains(i)) continue;
      final (eq, label) = candidates[i];
      final left = eq.unknownIds.toSet().difference(known);
      if (left.length != 1) continue;
      used.add(i);
      known.add(left.single);
      plan.add(PlannedEquation(eq, s.reaction(left.single), label));
      progressed = true;
      break;
    }
    if (!progressed) break;
  }
  return plan;
}

class _Writer {
  _Writer(this.s, this.t, this.units, this.conv)
      : problem = s.problem,
        labels = s.labels;

  final StaticsSolution s;
  final BeamProblem problem;
  final ProblemLabels labels;
  final Texts t;
  final UnitSystem units;
  final SignConvention conv;

  // ---- units -------------------------------------------------------------

  String get fu => units.force.symbol;
  String get lu => units.length.symbol;
  String get mu => units.moment.symbol;

  /// The unit a force times a length comes out in. Derivations are written
  /// in it so that "20 × 3" really is 60 of something; results are then
  /// converted to the chosen moment unit if that differs.
  String get flu => '$fu·$lu';
  double get _fl => units.force.toSi * units.length.toSi;
  bool get _consistent => (_fl - units.moment.toSi).abs() <= 1e-12 * _fl;

  double fd(double si) => units.toDisplay(si, Dimension.force);
  double ld(double si) => units.toDisplay(si, Dimension.length);
  double fld(double si) => si / _fl;

  String f(double si) => Num.compact(fd(si));
  String l(double si) => Num.compact(ld(si));
  String fl(double si) => Num.compact(fld(si));

  String fU(double si) => '${f(si)} $fu';
  String lU(double si) => '${l(si)} $lu';
  String xAt(double x) => 'x = ${lU(x)}';

  /// A moment from a derivation: "60 kN·m", or "60000 kN·mm = 60 kN·m"
  /// when the chosen moment unit is not force × length.
  String mDerived(double si) => _consistent
      ? '${fl(si)} $flu'
      : '${fl(si)} $flu = ${Num.compact(units.toDisplay(si, Dimension.moment))} $mu';

  String readout(double si, Dimension d) =>
      '${Num.fixed(units.toDisplay(si, d))} ${units.unitFor(d).symbol}';

  // ---- names -------------------------------------------------------------

  String point(double x) => labels.pointAt(x) ?? xAt(x);

  String loadName(PointLoad load) => labels.loadName(load.id);

  /// The symbol of the component of a load that enters an equation.
  String componentName(PointLoad load, {required bool vertical}) {
    final name = loadName(load);
    if (!load.isInclined) return name;
    return vertical ? '${name}y' : '${name}x';
  }

  String arrowX(double v) => v >= 0 ? '→' : '←';
  String arrowY(double v) => v >= 0 ? '↑' : '↓';
  String arrowM(double v) => v >= 0 ? '↺' : '↻';

  String reactionArrow(Reaction r, double v) => switch (r.kind) {
        ReactionKind.horizontal => arrowX(v),
        ReactionKind.vertical => arrowY(v),
        ReactionKind.moment => arrowM(v),
      };

  Dimension dimOf(Reaction r) =>
      r.kind == ReactionKind.moment ? Dimension.moment : Dimension.force;

  String loadArrow(PointLoad load) {
    if (load.isVertical) return arrowY(load.fy);
    if (load.isHorizontal) return arrowX(load.fx);
    if (load.fx > 0) return load.fy > 0 ? '↗' : '↘';
    return load.fy > 0 ? '↖' : '↙';
  }

  /// The acute angle between a load and the beam axis.
  double acuteAngle(PointLoad load) {
    final a = normaliseAngle(load.angleDeg).abs();
    return a > 90 ? 180 - a : a;
  }

  List<PointLoad> get loads =>
      [...problem.pointLoads]..sort((a, b) => a.x.compareTo(b.x));

  Iterable<Reaction> get reactions => s.reactions;

  Reveal get _allSolved => Reveal(
        reactions: true,
        solved: {for (final r in reactions) r.id},
      );

  // ---- steps -------------------------------------------------------------

  List<SolutionStep> steps(InternalForces forces) {
    final list = <SolutionStep>[given(), freeBody()];
    final inclined = loads.where((l) => l.isInclined).toList();
    if (inclined.isNotEmpty) list.add(components(inclined));

    final plan = planEquations(s);
    final known = <String, double>{};
    for (final p in plan) {
      list.add(equilibrium(p, Map.of(known)));
      known[p.solves.id] = s.valueOf(p.solves.id);
    }
    final check = checkStep(plan);
    if (check != null) list.add(check);
    list
      ..add(reactionSummary())
      ..add(shear(forces))
      ..add(shearDiagram(forces))
      ..add(moment(forces))
      ..add(momentDiagram(forces))
      ..add(maxMoment(forces));
    if (forces.hasAxial) list.add(axial(forces));
    return list;
  }

  SolutionStep given() {
    final supports = [...problem.supports]..sort((a, b) => a.x.compareTo(b.x));
    return SolutionStep(
      kind: StepKind.given,
      title: t.givenTitle,
      goal: t.givenGoal,
      lines: [
        MathLine([
          const MathToken('L', role: TokenRole.symbol),
          const MathToken('=', role: TokenRole.equals),
          MathToken(lU(problem.length), role: TokenRole.value),
        ]),
        for (final sup in supports)
          MathLine([
            MathToken('${labels.pointOf(sup.id)}:', role: TokenRole.symbol),
            MathToken(t.supportName(sup.type),
                role: TokenRole.term,
                explanation: t.supportBehaviour(sup.type),
                highlights: [SupportHighlight(sup.id)]),
            MathToken('(${xAt(sup.x)})', role: TokenRole.value),
          ], highlights: [SupportHighlight(sup.id)]),
        for (final load in loads)
          MathLine([
            MathToken('${loadName(load)} = ${fU(load.magnitude)} ${loadArrow(load)}',
                role: TokenRole.term,
                explanation: t.loadDescription(
                  name: loadName(load),
                  value: fU(load.magnitude),
                  point: labels.pointOf(load.id),
                  x: lU(load.x),
                  direction: _directionWords(load),
                ),
                highlights: [LoadHighlight(load.id)]),
            MathToken('@ ${labels.pointOf(load.id)} (${xAt(load.x)})',
                role: TokenRole.value),
          ], highlights: [LoadHighlight(load.id)]),
      ],
      explanation: t.givenExplanation(
        length: lU(problem.length),
        supports: [
          for (final sup in supports)
            (t.supportName(sup.type), labels.pointOf(sup.id)),
        ],
        loadCount: loads.length,
      ),
      reveal: Reveal.nothing,
    );
  }

  String _directionWords(PointLoad load) {
    if (load.isVertical) return load.fy < 0 ? t.downward : t.upward;
    if (load.isHorizontal) return load.fx > 0 ? t.rightward : t.leftward;
    return t.inclined(Num.compact(acuteAngle(load)), loadArrow(load));
  }

  SolutionStep unsolvable() {
    final st = s.stability;
    return SolutionStep(
      kind: StepKind.unsolvable,
      title: t.unsolvableTitle(st.status),
      goal: t.unsolvableGoal,
      lines: const [],
      explanation: t.stabilityMessage(st.reason, st.unknowns, st.degree),
      detail: t.stabilityAdvice(st.reason),
    );
  }

  SolutionStep freeBody() {
    final supports = [...problem.supports]..sort((a, b) => a.x.compareTo(b.x));
    final lines = <MathLine>[];
    for (final sup in supports) {
      final letter = labels.pointOf(sup.id);
      final rs = reactions.where((r) => r.supportId == sup.id).toList();
      lines.add(MathLine([
        MathToken('$letter (${t.supportName(sup.type)})',
            role: TokenRole.symbol,
            explanation: t.supportBehaviour(sup.type),
            highlights: [SupportHighlight(sup.id)]),
        const MathToken('⇒', role: TokenRole.operator),
        for (var i = 0; i < rs.length; i++) ...[
          if (i > 0) const MathToken(',', role: TokenRole.operator, spaceBefore: false),
          MathToken('${rs[i].symbol} ${reactionArrow(rs[i], 1)}',
              role: TokenRole.term,
              explanation: t.reactionMeaning(rs[i].kind, rs[i].symbol, letter, sup.type),
              highlights: [ReactionHighlight(rs[i].id)]),
        ],
      ], highlights: [SupportHighlight(sup.id)]));
    }
    final n = reactions.length;
    lines.add(MathLine([
      MathToken(t.unknownsCount(n), role: TokenRole.text),
      const MathToken('=', role: TokenRole.equals),
      MathToken(t.equationsCount(3),
          role: TokenRole.term, explanation: t.threeEquations),
    ], note: t.assumedDirections));

    return SolutionStep(
      kind: StepKind.freeBody,
      title: t.fbdTitle,
      goal: t.fbdGoal,
      lines: lines,
      explanation: t.fbdExplanation,
      detail: t.fbdDetail,
      highlights: [for (final r in reactions) ReactionHighlight(r.id)],
      reveal: const Reveal(reactions: true),
    );
  }

  SolutionStep components(List<PointLoad> inclined) {
    final lines = <MathLine>[];
    for (final load in inclined) {
      final name = loadName(load);
      final angle = Num.compact(acuteAngle(load));
      final hl = [LoadHighlight(load.id)];
      lines.add(MathLine([
        MathToken('${name}x', role: TokenRole.symbol, highlights: hl),
        const MathToken('=', role: TokenRole.equals),
        MathToken('${f(load.magnitude)} × cos $angle°',
            role: TokenRole.term,
            explanation: t.cosExplanation(name, angle),
            highlights: hl),
        const MathToken('=', role: TokenRole.equals),
        MathToken('${fU(load.fx.abs())} ${arrowX(load.fx)}',
            role: TokenRole.result, highlights: hl),
      ]));
      lines.add(MathLine([
        MathToken('${name}y', role: TokenRole.symbol, highlights: hl),
        const MathToken('=', role: TokenRole.equals),
        MathToken('${f(load.magnitude)} × sin $angle°',
            role: TokenRole.term,
            explanation: t.sinExplanation(name, angle),
            highlights: hl),
        const MathToken('=', role: TokenRole.equals),
        MathToken('${fU(load.fy.abs())} ${arrowY(load.fy)}',
            role: TokenRole.result, highlights: hl),
      ]));
    }
    return SolutionStep(
      kind: StepKind.components,
      title: t.componentsTitle,
      goal: t.componentsGoal,
      lines: lines,
      explanation: t.componentsExplanation,
      highlights: [for (final l in inclined) LoadHighlight(l.id)],
      reveal: const Reveal(reactions: true),
    );
  }

  // ---- equilibrium -------------------------------------------------------

  double _convSign(EquationKind kind) => switch (kind) {
        EquationKind.sumFx => conv.xSign,
        EquationKind.sumFy => conv.ySign,
        EquationKind.sumMoment => conv.momentSign,
      };

  String _eqTitle(EquationKind kind, String? label, double? about) =>
      switch (kind) {
        EquationKind.sumFx => 'ΣFx = 0',
        EquationKind.sumFy => 'ΣFy = 0',
        EquationKind.sumMoment => 'ΣM_${label ?? point(about!)} = 0',
      };

  String _convArrow(EquationKind kind) => switch (kind) {
        EquationKind.sumFx => conv.xArrow,
        EquationKind.sumFy => conv.yArrow,
        EquationKind.sumMoment => conv.momentArrow,
      };

  MathLine _header(EquationKind kind, String? label, double? about) {
    final title = _eqTitle(kind, label, about);
    final name = title.substring(0, title.indexOf(' ='));
    return MathLine([
      MathToken(name,
          role: TokenRole.symbol,
          explanation: kind == EquationKind.sumMoment
              ? t.momentEquilibriumMeaning
              : t.forceEquilibriumMeaning(kind == EquationKind.sumFx),
          highlights: [if (about != null) MomentCentreHighlight(about)]),
      const MathToken('=', role: TokenRole.equals),
      const MathToken('0', role: TokenRole.value),
      MathToken('(${_convArrow(kind)} +)',
          role: TokenRole.term, explanation: t.conventionMeaning(kind, conv)),
    ]);
  }

  /// One displayed term: its sign in the written equation, its text, and
  /// what tapping it says and shows.
  ({double sign, String text, String? explanation, List<Highlight> highlights})
      _term(EquilibriumEquation eq, EquationTerm term) {
    final kind = eq.kind;
    final c = _convSign(kind);
    final about = eq.about;
    final aboutName = about == null ? '' : point(about);
    final reaction = s.reactions.where((r) => r.id == term.sourceId).firstOrNull;
    final load = problem.loadById(term.sourceId);
    final hl = <Highlight>[
      if (reaction != null) ReactionHighlight(reaction.id),
      if (load != null) LoadHighlight(load.id),
      if (about != null && term.arm != null) ...[
        MomentCentreHighlight(about),
        ArmHighlight(about, about + term.arm!),
      ],
    ];
    final physical = term.isUnknown ? term.coefficient! : term.knownValue!;
    final sign = c * (physical == 0 ? 1 : physical.sign);
    final positiveInConvention = sign > 0;

    if (term.isUnknown) {
      final r = reaction!;
      final text = term.arm != null ? '${r.symbol} × ${l(term.arm!.abs())}' : r.symbol;
      final explanation = switch (kind) {
        EquationKind.sumMoment when r.kind == ReactionKind.moment =>
          t.termCouple(r.symbol, labels.pointOf(r.supportId), positiveInConvention),
        EquationKind.sumMoment => t.termReactionMoment(
            symbol: r.symbol,
            point: labels.pointOf(r.supportId),
            about: aboutName,
            arm: lU(term.arm!.abs()),
            counterClockwise: term.arm! > 0,
            positive: positiveInConvention),
        _ => t.termReactionForce(r.symbol, labels.pointOf(r.supportId),
            reactionArrow(r, 1), positiveInConvention),
      };
      return (sign: sign, text: text, explanation: explanation, highlights: hl);
    }

    // A known term: a load, or a reaction solved in an earlier step.
    final component = term.component;
    final isMoment = kind == EquationKind.sumMoment;
    final String text;
    if (isMoment && term.arm != null) {
      text = '${f(component!.abs())} × ${l(term.arm!.abs())}';
    } else if (isMoment) {
      text = fl(term.knownValue!.abs());
    } else {
      text = f(term.knownValue!.abs());
    }
    String explanation;
    if (load is PointLoad) {
      final vertical = kind != EquationKind.sumFx;
      final name = componentName(load, vertical: vertical);
      final value = fU(vertical ? load.fy.abs() : load.fx.abs());
      final direction = vertical ? arrowY(load.fy) : arrowX(load.fx);
      explanation = isMoment
          ? t.termLoadMoment(
              name: name,
              value: value,
              about: aboutName,
              arm: lU(term.arm!.abs()),
              isComponent: load.isInclined,
              loadName: loadName(load),
              counterClockwise: term.knownValue! > 0,
              positive: positiveInConvention)
          : t.termLoadForce(
              name: name,
              value: value,
              direction: direction,
              isComponent: load.isInclined,
              loadName: loadName(load),
              positive: positiveInConvention);
    } else {
      final r = reaction!;
      final v = s.valueOf(r.id);
      explanation = t.termKnownReaction(
          r.symbol,
          r.kind == ReactionKind.moment
              ? mDerived(v)
              : fU(v));
    }
    return (sign: sign, text: text, explanation: explanation, highlights: hl);
  }

  List<MathToken> _signedTerms(
      EquilibriumEquation eq, Iterable<EquationTerm> terms) {
    final tokens = <MathToken>[];
    var first = true;
    for (final term in terms) {
      final d = _term(eq, term);
      if (first) {
        if (d.sign < 0) tokens.add(const MathToken(minus, role: TokenRole.operator));
        tokens.add(MathToken(d.text,
            role: TokenRole.term,
            explanation: d.explanation,
            highlights: d.highlights,
            spaceBefore: d.sign >= 0 || tokens.isEmpty ? true : false));
        first = false;
      } else {
        tokens
          ..add(MathToken(d.sign < 0 ? minus : '+', role: TokenRole.operator))
          ..add(MathToken(d.text,
              role: TokenRole.term,
              explanation: d.explanation,
              highlights: d.highlights));
      }
    }
    if (tokens.isEmpty) tokens.add(const MathToken('0', role: TokenRole.value));
    return tokens;
  }

  MathLine _equationLine(EquilibriumEquation eq, {String? note}) => MathLine([
        ..._signedTerms(eq, eq.terms),
        const MathToken('=', role: TokenRole.equals),
        const MathToken('0', role: TokenRole.value),
      ], note: note);

  SolutionStep equilibrium(PlannedEquation p, Map<String, double> known) {
    final eq = p.equation;
    final target = p.solves;
    final value = s.valueOf(target.id);
    final c = _convSign(eq.kind);
    final about = eq.about;
    final title = _eqTitle(eq.kind, p.label, about);
    final lines = <MathLine>[_header(eq.kind, p.label, about)];

    lines.add(_equationLine(eq));
    final usesKnown = eq.unknownIds.any(known.containsKey);
    final substituted = eq.substitute(known);
    if (usesKnown) lines.add(_equationLine(substituted));

    // a·U + Σk = 0, everything in display units and in the written sign.
    final unknownTerm =
        substituted.terms.firstWhere((x) => x.isUnknown && x.sourceId == target.id);
    final knownTerms = substituted.terms.where((x) => !x.isUnknown).toList();
    final isCouple = target.kind == ReactionKind.moment;
    final aSign = c * unknownTerm.coefficient!.sign;
    final aAbs = unknownTerm.arm != null ? ld(unknownTerm.arm!.abs()) : 1.0;
    final arrow = reactionArrow(target, value);
    final valueText = value == 0
        ? '0'
        : '${isCouple ? mDerived(value) : fU(value)}${value > 0 ? ' $arrow' : ''}';
    final unknownHl = [ReactionHighlight(target.id)];
    final resultToken = MathToken(valueText,
        role: TokenRole.result,
        explanation: value < 0 ? t.negativeMeaning(target.symbol, arrow) : null,
        highlights: unknownHl);
    MathToken symbolToken() =>
        MathToken(target.symbol, role: TokenRole.symbol, highlights: unknownHl);
    const eqToken = MathToken('=', role: TokenRole.equals);

    if (knownTerms.isEmpty) {
      // Nothing to move across: the equation already reads "HA = 0".
      lines
        ..removeLast()
        ..add(MathLine([symbolToken(), eqToken, resultToken],
            note: eq.kind == EquationKind.sumFx
                ? t.noHorizontalLoads(target.symbol)
                : null));
    } else {
      // Move the known terms across: their signs flip, and a negative
      // coefficient on the unknown flips them back.
      final moved = <MathToken>[];
      var total = 0.0;
      // Positive terms first, as a student writes "RA = 20 − 10".
      final ordered = [
        for (final k in knownTerms)
          (term: k, d: _term(substituted, k), sign: -_term(substituted, k).sign * aSign),
      ]..sort((p, q) => q.sign.compareTo(p.sign));
      for (var i = 0; i < ordered.length; i++) {
        final d = ordered[i].d;
        final sign = ordered[i].sign;
        total += sign * _displayMagnitude(substituted, ordered[i].term);
        if (i > 0 || sign < 0) {
          moved.add(MathToken(sign < 0 ? minus : '+', role: TokenRole.operator));
        }
        moved.add(MathToken(d.text,
            role: TokenRole.term,
            explanation: d.explanation,
            highlights: d.highlights,
            spaceBefore: i > 0 || sign >= 0));
      }
      final singleNumber = knownTerms.length == 1 && !moved.last.text.contains('×');
      if (aAbs != 1) {
        lines.add(MathLine([
          MathToken('${target.symbol} × ${Num.compact(aAbs)}',
              role: TokenRole.term, highlights: unknownHl),
          eqToken,
          ...moved,
        ]));
        lines.add(MathLine([
          symbolToken(),
          eqToken,
          MathToken('${Num.compact(total)} ÷ ${Num.compact(aAbs)}',
              role: TokenRole.value),
          eqToken,
          resultToken,
        ]));
      } else {
        lines.add(MathLine([
          symbolToken(),
          eqToken,
          if (!singleNumber) ...[...moved, eqToken],
          resultToken,
        ]));
      }
    }

    final results = [_reactionResult(target)];
    return SolutionStep(
      kind: StepKind.equilibrium,
      title: title,
      goal: t.findGoal(target.symbol),
      lines: [
        ...lines.take(lines.length - 1),
        MathLine(lines.last.tokens,
            note: [
              if (lines.last.note != null) lines.last.note!,
              if (value < 0) t.negativeMeaning(target.symbol, arrow),
            ].join('\n').ifEmptyNull),
      ],
      explanation: _whyThisEquation(p, known),
      detail: eq.kind == EquationKind.sumMoment
          ? t.momentEquilibriumMeaning
          : t.forceEquilibriumMeaning(eq.kind == EquationKind.sumFx),
      highlights: [
        ...unknownHl,
        if (about != null) MomentCentreHighlight(about),
      ],
      reveal: Reveal(
          reactions: true, solved: {...known.keys, target.id}),
      results: results,
    );
  }

  /// The size of a known term in display units (force, or force × length).
  double _displayMagnitude(EquilibriumEquation eq, EquationTerm term) {
    if (eq.kind == EquationKind.sumMoment) return fld(term.knownValue!.abs());
    return fd(term.knownValue!.abs());
  }

  String _whyThisEquation(PlannedEquation p, Map<String, double> known) {
    final eq = p.equation;
    final target = p.solves.symbol;
    switch (eq.kind) {
      case EquationKind.sumFx:
        final hasHorizontalLoad = loads.any((l) => l.fx != 0);
        return hasHorizontalLoad
            ? t.whySumFxWithLoads(target)
            : t.whySumFxNoLoads(target);
      case EquationKind.sumFy:
        final knownSymbols = [
          for (final r in reactions)
            if (r.kind == ReactionKind.vertical && known.containsKey(r.id)) r.symbol,
        ];
        return t.whySumFy(target, knownSymbols);
      case EquationKind.sumMoment:
        final about = eq.about!;
        final through = [
          for (final r in reactions)
            if (r.kind == ReactionKind.horizontal ||
                (r.kind == ReactionKind.vertical && (r.x - about).abs() < 1e-9))
              r.symbol,
        ];
        return t.whySumMoment(
            about: p.label ?? point(about), target: target, through: through,
            isCouple: p.solves.kind == ReactionKind.moment);
    }
  }

  ResultValue _reactionResult(Reaction r) {
    final v = s.valueOf(r.id);
    final dim = dimOf(r);
    final arrow = reactionArrow(r, v);
    final text = v == 0
        ? '${r.symbol} = 0'
        : v > 0
            ? '${r.symbol} = ${readout(v, dim)} $arrow'
            : '${r.symbol} = ${readout(v, dim)} ⇒ ${readout(-v, dim)} $arrow';
    return ResultValue(
      symbol: r.symbol,
      si: v,
      dimension: dim,
      text: text,
      direction: v == 0 ? null : arrow,
      x: r.x,
      highlights: [ReactionHighlight(r.id)],
    );
  }

  SolutionStep? checkStep(List<PlannedEquation> plan) {
    final usedCentres = [
      for (final p in plan)
        if (p.equation.kind == EquationKind.sumMoment) p.equation.about!,
    ];
    double? centre;
    // Prefer another support, then the load point farthest from the
    // centres already used, then a free end.
    final supports = [...problem.supports]..sort((a, b) => a.x.compareTo(b.x));
    for (final sup in supports) {
      if (usedCentres.every((c) => (c - sup.x).abs() > 1e-9)) {
        centre = sup.x;
        break;
      }
    }
    if (centre == null) {
      final options = [
        ...loads.map((l) => l.x),
        0.0,
        problem.length,
      ].where((x) => usedCentres.every((c) => (c - x).abs() > 1e-9)).toList();
      if (options.isEmpty) return null;
      double distance(double x) =>
          usedCentres.map((c) => (c - x).abs()).fold(0.0, math.max);
      options.sort((a, b) => distance(b).compareTo(distance(a)));
      centre = options.first;
    }

    final eq = s.equations.sumMoment(centre).substitute(s.values);
    final label = labels.pointAt(centre);
    final title = _eqTitle(EquationKind.sumMoment, label, centre);
    var sum = 0.0;
    for (final term in eq.terms) {
      sum += _convSign(eq.kind) * fld(term.knownValue!);
    }
    final values = <MathToken>[];
    var first = true;
    for (final term in eq.terms) {
      final v = _convSign(eq.kind) * fld(term.knownValue!);
      if (first) {
        values.add(MathToken(Num.compact(v), role: TokenRole.value));
        first = false;
      } else {
        values
          ..add(MathToken(v < 0 ? minus : '+', role: TokenRole.operator))
          ..add(MathToken(Num.compact(v.abs()), role: TokenRole.value));
      }
    }
    final ok = Num.isZeroAt(sum, 3);
    return SolutionStep(
      kind: StepKind.check,
      title: '${t.checkWord}: $title',
      goal: t.checkGoal,
      lines: [
        _header(EquationKind.sumMoment, label, centre),
        _equationLine(eq),
        MathLine([
          ...values,
          const MathToken('=', role: TokenRole.equals),
          MathToken('${Num.compact(sum)} ${ok ? '✓' : '✗'}',
              role: TokenRole.result),
        ]),
      ],
      explanation: t.checkExplanation(label ?? xAt(centre)),
      highlights: [MomentCentreHighlight(centre)],
      reveal: _allSolved,
    );
  }

  SolutionStep reactionSummary() {
    final results = [for (final r in reactions) _reactionResult(r)];
    final negatives = [
      for (final r in reactions)
        if (s.valueOf(r.id) < 0) r,
    ];
    final up = reactions
        .where((r) => r.kind == ReactionKind.vertical)
        .fold(0.0, (sum, r) => sum + s.valueOf(r.id));
    final down = -loads.fold(0.0, (sum, l) => sum + l.fy);
    return SolutionStep(
      kind: StepKind.reactions,
      title: t.reactionsTitle,
      goal: t.reactionsGoal,
      lines: [
        for (final r in results)
          MathLine([
            MathToken(r.text, role: TokenRole.result, highlights: r.highlights),
          ]),
        MathLine([
          MathToken(t.sumOfVerticalReactions, role: TokenRole.text),
          const MathToken('=', role: TokenRole.equals),
          MathToken(fU(up), role: TokenRole.value),
          const MathToken('=', role: TokenRole.equals),
          MathToken(t.totalDownwardLoad(fU(down)),
              role: TokenRole.term, explanation: t.verticalBalanceMeaning),
        ]),
      ],
      explanation: negatives.isEmpty
          ? t.reactionsExplanation
          : t.reactionsExplanationWithNegative(
              [for (final r in negatives) (r.symbol, reactionArrow(r, s.valueOf(r.id)))]),
      highlights: [for (final r in reactions) ReactionHighlight(r.id)],
      reveal: _allSolved,
      results: results,
    );
  }

  // ---- internal forces ---------------------------------------------------

  String _range(double a, double b, {bool closed = false}) {
    final op = closed ? '≤' : '<';
    return '${l(a)} $op x $op ${l(b)} $lu';
  }

  String _actionSymbol(Action a, {required bool vertical}) {
    final load = problem.loadById(a.sourceId);
    if (load is PointLoad) return componentName(load, vertical: vertical);
    return s.reactions.firstWhere((r) => r.id == a.sourceId).symbol;
  }

  bool _isReaction(Action a) => s.reactions.any((r) => r.id == a.sourceId);

  /// The actions left of a cut, left to right, reactions before loads at
  /// the same point: the order a student writes them in.
  List<Action> _leftOf(InternalForces forces, double a) {
    final list = forces.actionsLeftOf(a);
    final order = {for (var i = 0; i < list.length; i++) list[i]: i};
    list.sort((p, q) {
      final byX = p.x.compareTo(q.x);
      if (byX != 0) return byX;
      final byKind = (_isReaction(p) ? 0 : 1).compareTo(_isReaction(q) ? 0 : 1);
      return byKind != 0 ? byKind : order[p]!.compareTo(order[q]!);
    });
    return list;
  }

  List<Highlight> _actionHighlights(Action a) => _isReaction(a)
      ? [ReactionHighlight(a.sourceId)]
      : [LoadHighlight(a.sourceId)];

  SolutionStep shear(InternalForces forces) {
    final lines = <MathLine>[];
    final results = <ResultValue>[];
    for (final piece in forces.shear.pieces) {
      final a = piece.x0, b = piece.x1;
      final left = [
        for (final act in _leftOf(forces, a))
          if (act is PointForce && act.fy != 0) act,
      ];
      final v = piece.start;
      final range = [
        DiagramRangeHighlight(DiagramKind.shear, a, b),
        SectionHighlight((a + b) / 2),
      ];
      final tokens = <MathToken>[
        MathToken('${_range(a, b)}:', role: TokenRole.symbol, highlights: range),
        const MathToken('V', role: TokenRole.symbol),
        const MathToken('=', role: TokenRole.equals),
      ];
      if (left.isEmpty) {
        tokens.add(const MathToken('0', role: TokenRole.result));
      } else {
        // Symbols: a reaction is assumed upward (+), a load carries its own
        // direction.
        for (var i = 0; i < left.length; i++) {
          final act = left[i];
          final reaction = _isReaction(act);
          final plus = reaction || act.fy > 0;
          if (i > 0 || !plus) {
            tokens.add(MathToken(plus ? '+' : minus,
                role: TokenRole.operator));
          }
          tokens.add(MathToken(_actionSymbol(act, vertical: true),
              role: TokenRole.term,
              spaceBefore: i > 0 || plus,
              explanation: reaction
                  ? t.shearTermReaction(_actionSymbol(act, vertical: true),
                      fU(act.fy), act.fy >= 0)
                  : t.shearTermLoad(_actionSymbol(act, vertical: true),
                      fU(act.fy.abs()), act.fy < 0),
              highlights: _actionHighlights(act)));
        }
        if (left.length > 1) {
          tokens.add(const MathToken('=', role: TokenRole.equals));
          tokens.addAll(_signedNumbers([for (final act in left) fd(act.fy)]));
        }
        tokens
          ..add(const MathToken('=', role: TokenRole.equals))
          ..add(MathToken(fU(v),
              role: TokenRole.result,
              highlights: [DiagramRangeHighlight(DiagramKind.shear, a, b)]));
      }
      final up = left.where((x) => x.fy > 0).fold(0.0, (s2, x) => s2 + x.fy);
      final down = -left.where((x) => x.fy < 0).fold(0.0, (s2, x) => s2 + x.fy);
      lines.add(MathLine(tokens,
          note: t.shearSignNote(Num.isZeroAt(fd(v), 6) ? 0 : v.sign.toInt(), fU(up), fU(down)),
          highlights: range));
      results.add(ResultValue(
        symbol: 'V',
        si: v,
        dimension: Dimension.force,
        text: 'V = ${readout(v, Dimension.force)}  (${_range(a, b)})',
        x: (a + b) / 2,
        highlights: [DiagramRangeHighlight(DiagramKind.shear, a, b)],
      ));
    }
    return SolutionStep(
      kind: StepKind.shear,
      title: t.shearTitle,
      goal: t.shearGoal,
      lines: lines,
      explanation: t.shearExplanation,
      detail: t.shearDetail,
      reveal: _allSolved,
      results: results,
    );
  }

  List<MathToken> _signedNumbers(List<double> values) {
    final tokens = <MathToken>[];
    for (var i = 0; i < values.length; i++) {
      final v = values[i];
      if (i == 0) {
        tokens.add(MathToken(Num.compact(v), role: TokenRole.value));
      } else {
        tokens
          ..add(MathToken(v < 0 ? minus : '+', role: TokenRole.operator))
          ..add(MathToken(Num.compact(v.abs()), role: TokenRole.value));
      }
    }
    return tokens;
  }

  SolutionStep shearDiagram(InternalForces forces) {
    final lines = <MathLine>[];
    final bps = forces.breakpoints;
    for (var i = 0; i < bps.length; i++) {
      final x = bps[i];
      final here = [
        for (final a in forces.actionsAt(x))
          if (a is PointForce && a.fy != 0) a,
      ];
      final before = forces.shear.leftLimit(x);
      final isEnd = i == bps.length - 1;
      final after = isEnd
          ? before + here.fold(0.0, (s2, a) => s2 + a.fy)
          : forces.shear.rightLimit(x);
      if (here.isNotEmpty) {
        final tokens = <MathToken>[
          MathToken('${xAt(x)}:', role: TokenRole.symbol, highlights: [
            DiagramPointHighlight(DiagramKind.shear, x, Side.right),
          ]),
        ];
        for (var k = 0; k < here.length; k++) {
          final a = here[k];
          if (k > 0) {
            tokens.add(const MathToken(',', role: TokenRole.operator, spaceBefore: false));
          }
          tokens.add(MathToken(
              '${arrowY(a.fy)} ${_actionSymbol(a, vertical: true)} = ${fU(a.fy.abs())}',
              role: TokenRole.term,
              explanation: t.jumpMeaning(_actionSymbol(a, vertical: true),
                  fU(a.fy.abs()), a.fy > 0),
              highlights: _actionHighlights(a)));
        }
        tokens
          ..add(const MathToken('⇒', role: TokenRole.operator))
          ..add(const MathToken('V:', role: TokenRole.symbol))
          ..add(MathToken(f(before), role: TokenRole.value, highlights: [
            DiagramPointHighlight(DiagramKind.shear, x, Side.left),
          ]))
          ..add(const MathToken('→', role: TokenRole.operator))
          ..add(MathToken(isEnd ? '${f(after)} ✓' : f(after),
              role: TokenRole.result,
              highlights: [
                DiagramPointHighlight(DiagramKind.shear, x, isEnd ? Side.left : Side.right),
              ]));
        lines.add(MathLine(tokens,
            note: isEnd ? t.shearClosesNote : null,
            highlights: [DiagramPointHighlight(DiagramKind.shear, x)]));
      }
      if (!isEnd) {
        final piece = forces.shear.pieces[i];
        lines.add(MathLine([
          MathToken('${_range(piece.x0, piece.x1)}:',
              role: TokenRole.symbol,
              highlights: [
                DiagramRangeHighlight(DiagramKind.shear, piece.x0, piece.x1),
              ]),
          MathToken(t.noLoadBetween, role: TokenRole.text),
          const MathToken('⇒', role: TokenRole.operator),
          MathToken('V = ${fU(piece.start)}',
              role: TokenRole.result,
              explanation: t.constantShearMeaning,
              highlights: [
                DiagramRangeHighlight(DiagramKind.shear, piece.x0, piece.x1),
              ]),
        ]));
      }
    }
    return SolutionStep(
      kind: StepKind.shearDiagram,
      title: t.sfdTitle,
      goal: t.sfdGoal,
      lines: lines,
      explanation: t.sfdExplanation,
      detail: t.sfdDetail,
      reveal: _allSolved.copyWith(shear: true),
    );
  }

  /// One part of a sum: "10x" first, "−20(x − 3)" first and negative,
  /// "+ 10x" or "− 20(x − 3)" after the first.
  String _signedPart(double value, bool first, String magnitude) {
    if (first) return value < 0 ? '$minus$magnitude' : magnitude;
    return '${value < 0 ? minus : '+'} $magnitude';
  }

  /// Formats a·x + b, as a student would write it: "−10x + 60".
  String _linear(double a, double b) {
    final parts = <String>[];
    if (!Num.isZeroAt(a, 6)) {
      final coeff = Num.compact(a.abs());
      parts.add('${a < 0 ? minus : ''}${coeff == '1' ? '' : coeff}x');
    }
    if (!Num.isZeroAt(b, 6) || parts.isEmpty) {
      final value = Num.compact(b.abs());
      if (parts.isEmpty) {
        parts.add('${b < 0 ? minus : ''}$value');
      } else {
        parts.add('${b < 0 ? minus : '+'} $value');
      }
    }
    return parts.join(' ');
  }

  SolutionStep moment(InternalForces forces) {
    final lines = <MathLine>[];
    for (final piece in forces.moment.pieces) {
      final a = piece.x0, b = piece.x1;
      final left = [
        for (final act in _leftOf(forces, a))
          if ((act is PointForce && act.fy != 0) || act is PointCouple) act,
      ];
      final range = [
        DiagramRangeHighlight(DiagramKind.moment, a, b),
        SectionHighlight((a + b) / 2),
      ];
      final tokens = <MathToken>[
        MathToken('${_range(a, b, closed: true)}:',
            role: TokenRole.symbol, highlights: range),
        const MathToken('M', role: TokenRole.symbol),
        const MathToken('=', role: TokenRole.equals),
      ];
      if (left.isEmpty) {
        tokens.add(const MathToken('0', role: TokenRole.result));
      } else {
        final symbolic = <MathToken>[];
        final numeric = <String>[];
        var slope = 0.0, intercept = 0.0;
        for (var i = 0; i < left.length; i++) {
          final act = left[i];
          final reaction = _isReaction(act);
          switch (act) {
            case PointForce(:final fy, :final x):
              final arm = x == 0 ? 'x' : '(x $minus ${l(x)})';
              final plus = reaction || fy > 0;
              final name = _actionSymbol(act, vertical: true);
              if (i > 0 || !plus) {
                symbolic.add(MathToken(plus ? '+' : minus, role: TokenRole.operator));
              }
              symbolic.add(MathToken('$name·$arm',
                  role: TokenRole.term,
                  spaceBefore: i > 0 || plus,
                  explanation: t.momentTermForce(
                      name, fU(fy.abs()), x == 0 ? 'x' : 'x $minus ${l(x)}',
                      fy > 0),
                  highlights: [
                    ..._actionHighlights(act),
                    ArmHighlight(x, (a + b) / 2),
                  ]));
              final coeff = fd(fy);
              final size = Num.compact(coeff.abs());
              numeric.add(_signedPart(coeff, numeric.isEmpty,
                  '${size == '1' ? '' : size}${x == 0 ? 'x' : '(x $minus ${l(x)})'}'));
              slope += coeff;
              intercept -= coeff * ld(x);
            case PointCouple(moment: final cpl):
              final name = _actionSymbol(act, vertical: true);
              // The left part's couple enters with a minus (sagging +).
              symbolic.add(MathToken(minus, role: TokenRole.operator));
              symbolic.add(MathToken(name,
                  role: TokenRole.term,
                  spaceBefore: i > 0,
                  explanation: t.momentTermCouple(name, mDerived(cpl.abs()), cpl > 0),
                  highlights: _actionHighlights(act)));
              final v = -fld(cpl);
              numeric.add(_signedPart(v, numeric.isEmpty, Num.compact(v.abs())));
              intercept += v;
          }
        }
        tokens.addAll(symbolic);
        tokens
          ..add(const MathToken('=', role: TokenRole.equals))
          ..add(MathToken(numeric.join(' '), role: TokenRole.value));
        final simplified = _linear(slope, intercept);
        if (left.length > 1 && simplified != numeric.join(' ')) {
          tokens
            ..add(const MathToken('=', role: TokenRole.equals))
            ..add(MathToken(simplified,
                role: TokenRole.result,
                highlights: [DiagramRangeHighlight(DiagramKind.moment, a, b)]));
        }
      }
      lines.add(MathLine(tokens, highlights: range));
    }

    // The values the BMD is drawn through.
    final values = <MathToken>[];
    for (final x in forces.breakpoints) {
      final leftV = forces.moment.leftLimit(x);
      final rightV = forces.moment.rightLimit(x);
      final atStart = (x - forces.breakpoints.first).abs() < 1e-9;
      final atEnd = (x - forces.breakpoints.last).abs() < 1e-9;
      final v = atStart ? rightV : leftV;
      if (values.isNotEmpty) {
        values.add(const MathToken(',', role: TokenRole.operator, spaceBefore: false));
      }
      values.add(MathToken('M(${l(x)}) = ${fl(v)}',
          role: TokenRole.value,
          highlights: [
            DiagramPointHighlight(DiagramKind.moment, x, atStart ? Side.right : Side.left),
          ]));
      if (!atStart && !atEnd && (leftV - rightV).abs() > 1e-9) {
        values.add(MathToken('→ ${fl(rightV)}',
            role: TokenRole.value,
            highlights: [DiagramPointHighlight(DiagramKind.moment, x, Side.right)]));
      }
    }
    lines.add(MathLine([
      ...values,
      MathToken('($flu)', role: TokenRole.text),
    ]));

    return SolutionStep(
      kind: StepKind.moment,
      title: t.momentTitle,
      goal: t.momentGoal,
      lines: lines,
      explanation: t.momentExplanation,
      detail: t.momentDetail,
      reveal: _allSolved.copyWith(shear: true),
    );
  }

  SolutionStep momentDiagram(InternalForces forces) {
    final lines = <MathLine>[];
    final bps = forces.breakpoints;
    final m0 = forces.moment.rightLimit(bps.first);
    final c0 = forces.actionsAt(bps.first).whereType<PointCouple>().toList();
    lines.add(MathLine([
      MathToken('M(${l(bps.first)})', role: TokenRole.symbol),
      const MathToken('=', role: TokenRole.equals),
      MathToken(fl(m0),
          role: TokenRole.result,
          explanation: c0.isEmpty ? t.momentStartsAtZero : t.momentStartsWithCouple(
              _actionSymbol(c0.first, vertical: false)),
          highlights: [DiagramPointHighlight(DiagramKind.moment, bps.first, Side.right)]),
    ]));
    var current = m0;
    for (var i = 0; i < forces.shear.pieces.length; i++) {
      final v = forces.shear.pieces[i];
      final area = v.p.integrate(v.x0, v.x1);
      final next = current + area;
      final dx = v.x1 - v.x0;
      final isLast = i == forces.shear.pieces.length - 1;
      final areaText = v.p.degree == 0
          ? '(${f(v.start)} × ${l(dx)})'
          : '(∫V dx = ${fl(area)})';
      lines.add(MathLine([
        MathToken('M(${l(v.x1)})', role: TokenRole.symbol),
        const MathToken('=', role: TokenRole.equals),
        MathToken('M(${l(v.x0)})', role: TokenRole.symbol),
        const MathToken('+', role: TokenRole.operator),
        MathToken(areaText,
            role: TokenRole.term,
            explanation: t.areaMeaning(l(v.x0), l(v.x1), fl(area), area >= 0),
            highlights: [DiagramRangeHighlight(DiagramKind.shear, v.x0, v.x1)]),
        const MathToken('=', role: TokenRole.equals),
        MathToken(fl(current), role: TokenRole.value),
        MathToken(area < 0 ? minus : '+', role: TokenRole.operator),
        MathToken(fl(area.abs()), role: TokenRole.value),
        const MathToken('=', role: TokenRole.equals),
        MathToken(isLast && Num.isZeroAt(fld(next), 6) ? '${fl(next)} ✓' : fl(next),
            role: TokenRole.result,
            highlights: [DiagramPointHighlight(DiagramKind.moment, v.x1, Side.left)]),
      ], note: isLast ? null : _slopeNote(v.start)));
      current = next;
      // A couple applied at the end of this piece makes M jump.
      if (!isLast) {
        final couples = forces.actionsAt(v.x1).whereType<PointCouple>().toList();
        for (final cpl in couples) {
          current -= cpl.moment;
          lines.add(MathLine([
            MathToken(xAt(v.x1), role: TokenRole.symbol),
            MathToken('${_actionSymbol(cpl, vertical: false)} ⇒ ΔM = ${fl(-cpl.moment)}',
                role: TokenRole.term, highlights: _actionHighlights(cpl)),
          ]));
        }
      }
    }
    return SolutionStep(
      kind: StepKind.momentDiagram,
      title: t.bmdTitle,
      goal: t.bmdGoal,
      lines: lines,
      explanation: t.bmdExplanation,
      detail: t.bmdDetail,
      reveal: _allSolved.copyWith(shear: true, moment: true),
    );
  }

  String _slopeNote(double v) {
    if (Num.isZeroAt(fd(v), 6)) return t.slopeZero;
    return v > 0 ? t.slopeUp : t.slopeDown;
  }

  SolutionStep maxMoment(InternalForces forces) {
    final m = forces.moment;
    final absMax = m.absMaximum!;
    final positive = m.maximum!;
    final negative = m.minimum!;
    final crossings = forces.shear.signChanges();
    final lines = <MathLine>[];
    for (final x in crossings) {
      lines.add(MathLine([
        MathToken(t.shearChangesSignAt(xAt(x)),
            role: TokenRole.term,
            explanation: t.whyZeroShearMeansPeak,
            highlights: [DiagramPointHighlight(DiagramKind.shear, x)]),
      ]));
    }
    final hasPositive = positive.value > 1e-9;
    final hasNegative = negative.value < -1e-9;
    if (hasPositive) {
      lines.add(MathLine([
        MathToken('M+max = ${mDerived(positive.value)}',
            role: TokenRole.result,
            explanation: t.saggingMeaning,
            highlights: [DiagramPointHighlight(DiagramKind.moment, positive.x, positive.side)]),
        MathToken('@ ${xAt(positive.x)}', role: TokenRole.value),
      ]));
    }
    if (hasNegative) {
      lines.add(MathLine([
        MathToken('M${minus}max = ${mDerived(negative.value)}',
            role: TokenRole.result,
            explanation: t.hoggingMeaning,
            highlights: [DiagramPointHighlight(DiagramKind.moment, negative.x, negative.side)]),
        MathToken('@ ${xAt(negative.x)}', role: TokenRole.value),
      ]));
    }
    final peakAtCrossing = crossings.any((x) => (x - absMax.x).abs() < 1e-9);
    final result = keyResults(forces).maxMoment;
    return SolutionStep(
      kind: StepKind.maxMoment,
      title: t.maxMomentTitle,
      goal: t.maxMomentGoal,
      lines: lines,
      explanation: t.maxMomentExplanation(
        x: xAt(absMax.x),
        value: mDerived(absMax.value),
        atZeroShear: peakAtCrossing,
        sagging: absMax.value > 0,
        atSupport: problem.supports.any((sp) => (sp.x - absMax.x).abs() < 1e-9),
      ),
      detail: t.whyZeroShearMeansPeak,
      highlights: [DiagramPointHighlight(DiagramKind.moment, absMax.x, absMax.side)],
      reveal: _allSolved.copyWith(shear: true, moment: true),
      results: [if (result != null) result],
    );
  }

  SolutionStep axial(InternalForces forces) {
    final lines = <MathLine>[];
    for (final piece in forces.axial.pieces) {
      final a = piece.x0, b = piece.x1;
      final left = [
        for (final act in _leftOf(forces, a))
          if (act is PointForce && act.fx != 0) act,
      ];
      final n = piece.start;
      final range = [DiagramRangeHighlight(DiagramKind.axial, a, b), SectionHighlight((a + b) / 2)];
      final tokens = <MathToken>[
        MathToken('${_range(a, b)}:', role: TokenRole.symbol, highlights: range),
        const MathToken('N', role: TokenRole.symbol),
        const MathToken('=', role: TokenRole.equals),
      ];
      if (left.isEmpty) {
        tokens.add(const MathToken('0', role: TokenRole.result));
      } else {
        tokens.add(MathToken('$minus(', role: TokenRole.operator));
        final nums = _signedNumbers([for (final act in left) fd(act.fx)]);
        for (var i = 0; i < nums.length; i++) {
          tokens.add(MathToken(nums[i].text,
              role: nums[i].role, spaceBefore: i > 0));
        }
        tokens
          ..add(const MathToken(')', role: TokenRole.operator, spaceBefore: false))
          ..add(const MathToken('=', role: TokenRole.equals))
          ..add(MathToken(fU(n),
              role: TokenRole.result,
              highlights: [DiagramRangeHighlight(DiagramKind.axial, a, b)]));
      }
      lines.add(MathLine(tokens,
          note: Num.isZeroAt(fd(n), 6)
              ? null
              : (n > 0 ? t.tensionNote : t.compressionNote),
          highlights: range));
    }
    return SolutionStep(
      kind: StepKind.axial,
      title: t.axialTitle,
      goal: t.axialGoal,
      lines: lines,
      explanation: t.axialExplanation,
      reveal: _allSolved.copyWith(shear: true, moment: true, axial: true),
    );
  }

  KeyResults keyResults(InternalForces forces) {
    ResultValue diagramValue(String symbol, PointValue p, DiagramKind kind, Dimension d) =>
        ResultValue(
          symbol: symbol,
          si: p.value,
          dimension: d,
          text: '$symbol = ${readout(p.value, d)}  @ x = ${Num.fixed(ld(p.x))} $lu',
          x: p.x,
          highlights: [DiagramPointHighlight(kind, p.x, p.side)],
        );

    final m = forces.moment;
    final v = forces.shear;
    final maxPos = m.maximum;
    final maxNeg = m.minimum;
    return KeyResults(
      reactions: [for (final r in reactions) _reactionResult(r)],
      maxShear: v.absMaximum == null
          ? null
          : diagramValue('Vmax', v.absMaximum!, DiagramKind.shear, Dimension.force),
      maxMoment: m.absMaximum == null
          ? null
          : diagramValue('Mmax', m.absMaximum!, DiagramKind.moment, Dimension.moment),
      maxPositiveMoment: maxPos != null && maxPos.value > 1e-9
          ? diagramValue('M+max', maxPos, DiagramKind.moment, Dimension.moment)
          : null,
      maxNegativeMoment: maxNeg != null && maxNeg.value < -1e-9
          ? diagramValue('M${minus}max', maxNeg, DiagramKind.moment, Dimension.moment)
          : null,
      maxAxial: forces.hasAxial && forces.axial.absMaximum != null
          ? diagramValue('Nmax', forces.axial.absMaximum!, DiagramKind.axial, Dimension.force)
          : null,
      zeroShear: v.signChanges(),
    );
  }
}

extension on String {
  String? get ifEmptyNull => isEmpty ? null : this;
}
