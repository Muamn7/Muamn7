/// The words of the Educational Explanation Engine, in Arabic and English.
///
/// Arabic prose keeps the English technical names students use in class
/// (Pin, Roller, SFD, Sagging…). Mathematical fragments inside Arabic text
/// are wrapped in Unicode directional isolates so that "−10 kN" or
/// "ΣM_A = 0" never gets reordered by the right-to-left paragraph around it.
library;

import '../model/beam_problem.dart';
import '../model/sign_convention.dart';
import '../statics/equilibrium.dart';
import '../validation/validator.dart';

enum Lang { ar, en }

abstract class Texts {
  const Texts();

  static Texts of(Lang lang) => switch (lang) {
        Lang.ar => const ArabicTexts(),
        Lang.en => const EnglishTexts(),
      };

  /// Wraps a left-to-right fragment so it survives inside right-to-left text.
  String m(String s) => s;

  // given
  String get givenTitle;
  String get givenGoal;
  String supportName(SupportType type) => switch (type) {
        SupportType.pin => 'Pin',
        SupportType.roller => 'Roller',
        SupportType.fixed => 'Fixed',
      };
  String supportBehaviour(SupportType type);
  String loadDescription({
    required String name,
    required String value,
    required String point,
    required String x,
    required String direction,
  });
  String givenExplanation({
    required String length,
    required List<(String, String)> supports,
    required int loadCount,
  });
  String get downward;
  String get upward;
  String get rightward;
  String get leftward;
  String inclined(String angle, String arrow);

  // unsolvable
  String unsolvableTitle(Determinacy status);
  String get unsolvableGoal;
  String stabilityMessage(StabilityReason reason, int unknowns, int degree);
  String stabilityAdvice(StabilityReason reason);

  // free body diagram
  String get fbdTitle;
  String get fbdGoal;
  String get fbdExplanation;
  String get fbdDetail;
  String reactionMeaning(
      ReactionKind kind, String symbol, String point, SupportType type);
  String unknownsCount(int n);
  String equationsCount(int n);
  String get threeEquations;
  String get assumedDirections;

  // components
  String get componentsTitle;
  String get componentsGoal;
  String get componentsExplanation;
  String cosExplanation(String name, String angle);
  String sinExplanation(String name, String angle);

  // equilibrium
  String findGoal(String symbol);
  String get momentEquilibriumMeaning;
  String forceEquilibriumMeaning(bool horizontal);
  String conventionMeaning(EquationKind kind, SignConvention c);
  String termCouple(String symbol, String point, bool positive);
  String termReactionMoment({
    required String symbol,
    required String point,
    required String about,
    required String arm,
    required bool counterClockwise,
    required bool positive,
  });
  String termReactionForce(
      String symbol, String point, String arrow, bool positive);
  String termLoadMoment({
    required String name,
    required String value,
    required String about,
    required String arm,
    required bool isComponent,
    required String loadName,
    required bool counterClockwise,
    required bool positive,
  });
  String termLoadForce({
    required String name,
    required String value,
    required String direction,
    required bool isComponent,
    required String loadName,
    required bool positive,
  });
  String termKnownReaction(String symbol, String value);
  String negativeMeaning(String symbol, String arrow);
  String noHorizontalLoads(String symbol);
  String whySumFxWithLoads(String target);
  String whySumFxNoLoads(String target);
  String whySumFy(String target, List<String> known);
  String whySumMoment({
    required String about,
    required String target,
    required List<String> through,
    required bool isCouple,
  });

  // check and reactions
  String get checkWord;
  String get checkGoal;
  String checkExplanation(String point);
  String get reactionsTitle;
  String get reactionsGoal;
  String get sumOfVerticalReactions;
  String totalDownwardLoad(String value);
  String get verticalBalanceMeaning;
  String get reactionsExplanation;
  String reactionsExplanationWithNegative(List<(String, String)> negatives);

  // shear
  String get shearTitle;
  String get shearGoal;
  String get shearExplanation;
  String get shearDetail;
  String shearTermReaction(String symbol, String value, bool up);
  String shearTermLoad(String symbol, String value, bool down);
  String shearSignNote(int sign, String up, String down);
  String get sfdTitle;
  String get sfdGoal;
  String get sfdExplanation;
  String get sfdDetail;
  String jumpMeaning(String symbol, String value, bool up);
  String get shearClosesNote;
  String get noLoadBetween;
  String get constantShearMeaning;

  // moment
  String get momentTitle;
  String get momentGoal;
  String get momentExplanation;
  String get momentDetail;
  String momentTermForce(String name, String value, String arm, bool sagging);
  String momentTermCouple(String name, String value, bool counterClockwise);
  String get momentStartsAtZero;
  String momentStartsWithCouple(String symbol);
  String areaMeaning(String x0, String x1, String area, bool positive);
  String get bmdTitle;
  String get bmdGoal;
  String get bmdExplanation;
  String get bmdDetail;
  String get slopeZero;
  String get slopeUp;
  String get slopeDown;
  String shearChangesSignAt(String x);
  String get whyZeroShearMeansPeak;
  String get saggingMeaning;
  String get hoggingMeaning;
  String get maxMomentTitle;
  String get maxMomentGoal;
  String maxMomentExplanation({
    required String x,
    required String value,
    required bool atZeroShear,
    required bool sagging,
    required bool atSupport,
  });

  // axial
  String get axialTitle;
  String get axialGoal;
  String get axialExplanation;
  String get tensionNote;
  String get compressionNote;

  // validation
  String checkName(CheckKind kind);
}

class ArabicTexts extends Texts {
  const ArabicTexts();

  @override
  String m(String s) => '\u2066$s\u2069';

  String _list(List<String> items) {
    final wrapped = items.map(m).toList();
    if (wrapped.length <= 1) return wrapped.join();
    return '${wrapped.sublist(0, wrapped.length - 1).join('، ')} و${wrapped.last}';
  }

  String _sign(bool positive) => positive ? 'موجبة' : 'سالبة';

  @override
  String get givenTitle => 'المسألة';
  @override
  String get givenGoal => 'ماذا لدينا؟';

  @override
  String supportBehaviour(SupportType type) => switch (type) {
        SupportType.pin =>
          'مسند مفصلي (Pin): يمنع الحركة الأفقية والرأسية ويسمح بالدوران، فله رد فعلين: أفقي ورأسي.',
        SupportType.roller =>
          'مسند متدحرج (Roller): يتدحرج على سطحه، فيمنع الحركة العمودية على السطح فقط. له رد فعل واحد رأسي ولا يقاوم أي قوة أفقية.',
        SupportType.fixed =>
          'مسند مثبّت (Fixed): الكمرة مدفونة فيه، فلا تتحرك ولا تدور. له ثلاثة ردود أفعال: أفقي ورأسي وعزم.',
      };

  @override
  String loadDescription({
    required String name,
    required String value,
    required String point,
    required String x,
    required String direction,
  }) =>
      'الحمل ${m(name)} قوة مركزة قيمتها ${m(value)}، تؤثر $direction عند النقطة ${m(point)} على بعد ${m(x)} من الطرف الأيسر.';

  @override
  String givenExplanation({
    required String length,
    required List<(String, String)> supports,
    required int loadCount,
  }) {
    final s = supports.map((e) => '${e.$1} عند ${m(e.$2)}').join(' و');
    final loads = switch (loadCount) {
      0 => 'لا توجد عليها أحمال',
      1 => 'وعليها حمل مركّز واحد',
      2 => 'وعليها حملان مركّزان',
      _ => 'وعليها ${m('$loadCount')} أحمال مركّزة',
    };
    return 'كمرة طولها ${m(length)}، مرتكزة على $s، $loads. '
        'المطلوب: ردود الأفعال، ثم مخطط قوة القص (SFD) ومخطط عزم الانحناء (BMD).';
  }

  @override
  String get downward => 'للأسفل ↓';
  @override
  String get upward => 'للأعلى ↑';
  @override
  String get rightward => 'لليمين →';
  @override
  String get leftward => 'لليسار ←';
  @override
  String inclined(String angle, String arrow) =>
      'مائلة $arrow بزاوية ${m('$angle°')} مع الأفقي';

  @override
  String unsolvableTitle(Determinacy status) => switch (status) {
        Determinacy.unstable => 'الكمرة غير مستقرة',
        Determinacy.indeterminate => 'الكمرة غير محددة استاتيكيًا',
        Determinacy.invalid => 'المسألة غير مكتملة',
        Determinacy.determinate => 'جاهزة للحل',
      };
  @override
  String get unsolvableGoal => 'لماذا لا يمكن الحل؟';

  @override
  String stabilityMessage(StabilityReason reason, int unknowns, int degree) =>
      switch (reason) {
        StabilityReason.noBeam => 'ارسم الكمرة أولًا: اختر Beam ثم اسحب إصبعك على الورقة.',
        StabilityReason.noSupports =>
          'لا توجد مساند، فالكمرة ستسقط. أضف مساند حتى تتزن.',
        StabilityReason.elementOffBeam =>
          'يوجد مسند أو حمل خارج الكمرة. حرّكه ليكون بين بداية الكمرة ونهايتها.',
        StabilityReason.noHorizontalRestraint =>
          'لا يوجد مسند يمنع الكمرة من الانزلاق أفقيًا (لا يوجد Pin أو Fixed). أي قوة أفقية مهما صغرت ستحرّكها.',
        StabilityReason.concurrentReactions =>
          'كل ردود الأفعال تمر بنقطة واحدة، فلا شيء يمنع الكمرة من الدوران حول هذه النقطة.',
        StabilityReason.tooFewReactions =>
          'عدد ردود الأفعال (${m('$unknowns')}) أقل من عدد معادلات الاتزان (3)، فالكمرة يمكن أن تتحرك.',
        StabilityReason.tooManyReactions =>
          'عدد المجاهيل (${m('$unknowns')}) أكبر من عدد معادلات الاتزان (3)، فالكمرة غير محددة استاتيكيًا من الدرجة ${m('$degree')}. '
              'حلها يحتاج معادلات التشوّه (Compatibility)، وهذا خارج نطاق الإصدار الحالي.',
        StabilityReason.ok => '',
      };

  @override
  String stabilityAdvice(StabilityReason reason) => switch (reason) {
        StabilityReason.noHorizontalRestraint => 'الحل: استبدل أحد الـ Rollers بـ Pin.',
        StabilityReason.concurrentReactions => 'الحل: ضع المسندين في نقطتين مختلفتين.',
        StabilityReason.tooFewReactions || StabilityReason.noSupports =>
          'الترتيب المعتاد: Pin في طرف وRoller في الطرف الآخر، أو Fixed في طرف واحد (كمرة كابولية).',
        StabilityReason.tooManyReactions =>
          'لتحصل على كمرة محددة استاتيكيًا: Pin مع Roller، أو Fixed وحده.',
        _ => '',
      };

  @override
  String get fbdTitle => 'مخطط الجسم الحر (FBD)';
  @override
  String get fbdGoal => 'استبدل المساند بردود أفعالها';
  @override
  String get fbdExplanation =>
      'مخطط الجسم الحر يرسم الكمرة وحدها مع كل القوى المؤثرة عليها: الأحمال المعروفة وردود الأفعال المجهولة. '
      'نزيل كل مسند ونضع مكانه القوى التي يستطيع أن يؤثر بها: كل حركة يمنعها المسند تقابلها قوة رد فعل.';
  @override
  String get fbdDetail =>
      'Pin يمنع الحركة الأفقية والرأسية ⇐ رد فعلين (H وR). '
      'Roller يمنع الحركة العمودية على سطحه فقط ⇐ رد فعل واحد (R). '
      'Fixed يمنع الحركتين والدوران ⇐ ثلاثة (H وR وM). '
      'في المستوى لدينا ثلاث معادلات اتزان، فإذا كان عدد المجاهيل ثلاثة بالضبط فالمسألة محددة استاتيكيًا (Statically Determinate) ونحلها بالاتزان وحده.';

  @override
  String reactionMeaning(
          ReactionKind kind, String symbol, String point, SupportType type) =>
      switch (kind) {
        ReactionKind.horizontal =>
          '${m(symbol)}: رد الفعل الأفقي عند ${m(point)}. المسند ${supportName(type)} يمنع الكمرة من الانزلاق أفقيًا، فيستطيع أن يدفعها أو يسحبها في اتجاه x.',
        ReactionKind.vertical => type == SupportType.roller
            ? '${m(symbol)}: رد الفعل الرأسي عند ${m(point)}. الـ Roller يمنع الحركة العمودية على سطحه فقط، لذلك له رد فعل رأسي واحد ولا يقاوم أي قوة أفقية.'
            : '${m(symbol)}: رد الفعل الرأسي عند ${m(point)}. المسند يمنع الكمرة من الحركة للأعلى أو للأسفل.',
        ReactionKind.moment =>
          '${m(symbol)}: عزم رد الفعل عند ${m(point)}. المسند Fixed يمنع الكمرة من الدوران، لذلك يؤثر عليها بعزم.',
      };

  @override
  String unknownsCount(int n) => '${m('$n')} مجاهيل';
  @override
  String equationsCount(int n) => '${m('$n')} معادلات اتزان';
  @override
  String get threeEquations =>
      'في المستوى (2D) لدينا ثلاث معادلات اتزان مستقلة: ${m('ΣFx = 0')} و${m('ΣFy = 0')} و${m('ΣM = 0')}.';
  @override
  String get assumedDirections =>
      'نفترض أن كل رد فعل يعمل في الاتجاه الموجب: H →، R ↑، M ↺. إذا خرجت النتيجة سالبة فالاتجاه الحقيقي عكس ما افترضنا، ولا نعيد الحل.';

  @override
  String get componentsTitle => 'تحليل الأحمال المائلة';
  @override
  String get componentsGoal => 'إلى مركبتين x وy';
  @override
  String get componentsExplanation =>
      'الكمرة أفقية، لذلك نحلل كل حمل مائل إلى مركبة على امتداد الكمرة (x) ومركبة عمودية عليها (y). '
      'المركبات x تدخل في ${m('ΣFx')}، والمركبات y تدخل في ${m('ΣFy')} و${m('ΣM')}.';
  @override
  String cosExplanation(String name, String angle) =>
      'المركبة الأفقية لـ ${m(name)} = قيمته × cos الزاوية بينه وبين الأفقي (${m('$angle°')}).';
  @override
  String sinExplanation(String name, String angle) =>
      'المركبة الرأسية لـ ${m(name)} = قيمته × sin الزاوية بينه وبين الأفقي (${m('$angle°')}).';

  @override
  String findGoal(String symbol) => 'إيجاد ${m(symbol)}';
  @override
  String get momentEquilibriumMeaning =>
      'الجسم في حالة اتزان، لذلك مجموع العزوم حول أي نقطة يساوي صفر. '
      'نحن أحرار في اختيار النقطة، واختيار نقطة تمر بها قوى مجهولة يحذفها من المعادلة لأن ذراع عزمها صفر.';
  @override
  String forceEquilibriumMeaning(bool horizontal) =>
      'الجسم في حالة اتزان (لا يتحرك ولا يتسارع)، لذلك مجموع القوى ${horizontal ? 'الأفقية' : 'الرأسية'} عليه يساوي صفرًا.';

  @override
  String conventionMeaning(EquationKind kind, SignConvention c) {
    final rule = switch (kind) {
      EquationKind.sumFx => c.rightPositive ? 'القوة لليمين → موجبة' : 'القوة لليسار ← موجبة',
      EquationKind.sumFy => c.upPositive ? 'القوة للأعلى ↑ موجبة' : 'القوة للأسفل ↓ موجبة',
      EquationKind.sumMoment => c.counterClockwisePositive
          ? 'العزم عكس عقارب الساعة ↺ موجب'
          : 'العزم مع عقارب الساعة ↻ موجب',
    };
    return 'اصطلاح الإشارات: $rule. يمكنك تغييره من الإعدادات؛ تتغير إشارات الحدود لكن النتائج لا تتغير.';
  }

  @override
  String termCouple(String symbol, String point, bool positive) =>
      '${m(symbol)} عزم رد الفعل عند ${m(point)}. العزم المزدوج (Couple) ليس له ذراع: قيمته واحدة حول أي نقطة، لذلك يُكتب كما هو. '
      'افترضناه ↺ فإشارته ${_sign(positive)}.';

  @override
  String termReactionMoment({
    required String symbol,
    required String point,
    required String about,
    required String arm,
    required bool counterClockwise,
    required bool positive,
  }) =>
      '${m(symbol)} هي قوة رد الفعل عند المسند ${m(point)}، و${m(arm)} هي المسافة بين ${m(about)} و${m(point)} (ذراع العزم). '
      '${m(symbol)} للأعلى على ${counterClockwise ? 'يمين' : 'يسار'} ${m(about)} فتدير الكمرة حوله '
      '${counterClockwise ? 'عكس عقارب الساعة ↺' : 'مع عقارب الساعة ↻'}، لذلك إشارتها ${_sign(positive)}.';

  @override
  String termReactionForce(
          String symbol, String point, String arrow, bool positive) =>
      '${m(symbol)} رد الفعل عند ${m(point)}، افترضنا اتجاهه $arrow، لذلك إشارته ${_sign(positive)} في هذه المعادلة.';

  @override
  String termLoadMoment({
    required String name,
    required String value,
    required String about,
    required String arm,
    required bool isComponent,
    required String loadName,
    required bool counterClockwise,
    required bool positive,
  }) {
    final what = isComponent
        ? '${m(value)} هي المركبة الرأسية ${m(name)} للحمل ${m(loadName)}'
        : '${m(value)} هي قيمة الحمل ${m(name)}';
    final note = isComponent
        ? ' (المركبة الأفقية تعمل على محور الكمرة فتمر بالنقطة ${m(about)} ولا عزم لها حولها.)'
        : '';
    return '$what و${m(arm)} هي المسافة من ${m(about)} إلى الحمل. '
        'الحمل يدير الكمرة حول ${m(about)} ${counterClockwise ? 'عكس عقارب الساعة ↺' : 'مع عقارب الساعة ↻'}، '
        'لذلك إشارته ${_sign(positive)}.$note';
  }

  @override
  String termLoadForce({
    required String name,
    required String value,
    required String direction,
    required bool isComponent,
    required String loadName,
    required bool positive,
  }) {
    final what = isComponent
        ? '${m(value)} هي المركبة ${m(name)} للحمل ${m(loadName)}'
        : '${m(value)} هي قيمة الحمل ${m(name)}';
    return '$what، اتجاهها $direction، لذلك إشارتها ${_sign(positive)}.';
  }

  @override
  String termKnownReaction(String symbol, String value) =>
      '${m('$symbol = $value')} وجدناها في خطوة سابقة، فنعوّض بقيمتها.';
  @override
  String negativeMeaning(String symbol, String arrow) =>
      'الإشارة السالبة تعني أن ${m(symbol)} تعمل فعليًا في الاتجاه $arrow، أي عكس الاتجاه الذي افترضناه. الحل صحيح، والاتجاه فقط هو المعكوس.';
  @override
  String noHorizontalLoads(String symbol) =>
      'لا توجد أحمال أفقية، فلا شيء يحتاج ${m(symbol)} أن تقاومه.';
  @override
  String whySumFxWithLoads(String target) =>
      'المعادلة ${m('ΣFx = 0')} فيها مجهول واحد فقط هو ${m(target)}، لأنه رد الفعل الوحيد الذي يقاوم الحركة الأفقية. لذلك نحلها أولًا.';
  @override
  String whySumFxNoLoads(String target) =>
      'لا توجد أحمال أفقية على الكمرة، فالقوة الأفقية الوحيدة هي ${m(target)}، ويجب أن تساوي صفرًا حتى لا تتحرك الكمرة أفقيًا.';
  @override
  String whySumFy(String target, List<String> known) => known.isEmpty
      ? 'المجهول الرأسي الوحيد هو ${m(target)}، فاتزان القوى الرأسية يعطيه مباشرة.'
      : 'بعد معرفة ${_list(known)} نستطيع إيجاد ${m(target)} باستخدام اتزان القوى الرأسية.';
  @override
  String whySumMoment({
    required String about,
    required String target,
    required List<String> through,
    required bool isCouple,
  }) {
    final passes = through.isEmpty
        ? ''
        : '، و${_list(through)} ${through.length == 1 ? 'يمر خط عملها' : 'تمر خطوط عملها'} بالنقطة ${m(about)} لذلك عزمها حول ${m(about)} يساوي صفر';
    return 'استخدمنا العزوم حول ${m(about)} لأننا نريد إيجاد ${m(target)}$passes. '
        'هكذا يبقى في المعادلة مجهول واحد فقط${isCouple ? ' هو ${m(target)}' : ''}.';
  }

  @override
  String get checkWord => 'تحقق';
  @override
  String get checkGoal => 'هل الحل صحيح؟';
  @override
  String checkExplanation(String point) =>
      'لم نستخدم العزوم حول ${m(point)} في إيجاد ردود الأفعال، فإذا أعطت صفرًا أيضًا فالقيم صحيحة. '
      'هذه طريقة سريعة لاكتشاف الأخطاء في الامتحان.';
  @override
  String get reactionsTitle => 'ردود الأفعال';
  @override
  String get reactionsGoal => 'النتائج واتجاهاتها الحقيقية';
  @override
  String get sumOfVerticalReactions => 'ΣR';
  @override
  String totalDownwardLoad(String value) => '${m(value)} (صافي الأحمال للأسفل)';
  @override
  String get verticalBalanceMeaning =>
      'ما ترفعه المساند للأعلى يساوي ما تدفعه الأحمال للأسفل؛ هذا معنى ${m('ΣFy = 0')}.';
  @override
  String get reactionsExplanation =>
      'كل ردود الأفعال غير السالبة تعمل في الاتجاهات التي افترضناها.';
  @override
  String reactionsExplanationWithNegative(List<(String, String)> negatives) {
    final list = negatives.map((e) => '${m(e.$1)} ${e.$2}').join('، ');
    return 'خرجت إشارة $list سالبة، أي أنها تعمل عكس الاتجاه الذي افترضناه. '
        'يحدث هذا عادة عندما يبرز جزء من الكمرة خارج المساند (Overhang): الحمل على الطرف البارز يرفع الطرف الآخر، فيشدّه المسند للأسفل.';
  }

  @override
  String get shearTitle => 'حساب قوة القص V(x)';
  @override
  String get shearGoal => 'طريقة المقاطع (Method of Sections)';
  @override
  String get shearExplanation =>
      'نقطع الكمرة عند مقطع x داخل كل جزء ونأخذ الجزء الأيسر. قوة القص V تساوي مجموع القوى الرأسية على يسار المقطع: '
      'القوة للأعلى ↑ موجبة، والقوة للأسفل ↓ سالبة.';
  @override
  String get shearDetail =>
      'اصطلاح الإشارة: V موجبة إذا كانت القوى على يسار المقطع تدفعه للأعلى (وعلى يمينه للأسفل). '
      'لماذا الجزء الأيسر؟ الجزءان يعطيان نفس V، والأيسر أسهل لأننا نقرأ الكمرة من اليسار لليمين. '
      'المقطع يقع بين حملين، لذلك نكتب المدى بإشارة < : القوة الواقعة على المقطع نفسه هي سبب القفزة في المخطط.';
  @override
  String shearTermReaction(String symbol, String value, bool up) => up
      ? '${m(symbol)} رد فعل على يسار المقطع، قيمته ${m(value)} للأعلى ↑ فيُضاف بإشارة موجبة.'
      : '${m(symbol)} = ${m(value)}: افترضناه ↑ لكنه خرج سالبًا، فنعوّض بقيمته السالبة.';
  @override
  String shearTermLoad(String symbol, String value, bool down) => down
      ? '${m(symbol)} حمل على يسار المقطع، ${m(value)} للأسفل ↓ فيُطرح.'
      : '${m(symbol)} حمل على يسار المقطع، ${m(value)} للأعلى ↑ فيُضاف.';
  @override
  String shearSignNote(int sign, String up, String down) => switch (sign) {
        < 0 =>
          'V سالبة هنا لأن القوى للأسفل على يسار المقطع (${m(down)}) أكبر من القوى للأعلى (${m(up)}).',
        > 0 =>
          'V موجبة لأن القوى للأعلى على يسار المقطع (${m(up)}) أكبر من القوى للأسفل (${m(down)}).',
        _ => 'V = 0: القوى على يسار المقطع متوازنة.',
      };
  @override
  String get sfdTitle => 'رسم مخطط قوة القص (SFD)';
  @override
  String get sfdGoal => 'من الأحمال إلى SFD';
  @override
  String get sfdExplanation =>
      'نرسم SFD مباشرة من الأحمال ونحن نتحرك من اليسار إلى اليمين: القوة للأعلى تجعل المخطط يقفز للأعلى بمقدارها، '
      'والقوة للأسفل تجعله يقفز للأسفل. وبين الأحمال يبقى المخطط أفقيًا لأنه لا يوجد حمل.';
  @override
  String get sfdDetail =>
      'لماذا يعود المخطط إلى الصفر في النهاية؟ لأن مجموع كل القفزات هو مجموع كل القوى الرأسية، وهو صفر بسبب ${m('ΣFy = 0')}. '
      'إذا لم يعد إلى الصفر فهناك خطأ في ردود الأفعال.';
  @override
  String jumpMeaning(String symbol, String value, bool up) =>
      'عند قوة مركّزة يقفز مخطط القص بمقدار القوة نفسها وفي اتجاهها: ${m(symbol)} = ${m(value)} ${up ? 'للأعلى ⇐ يقفز المخطط للأعلى' : 'للأسفل ⇐ يقفز المخطط للأسفل'}.';
  @override
  String get shearClosesNote =>
      'يعود المخطط إلى الصفر عند نهاية الكمرة ✓ — وهذا تحقق تلقائي من ${m('ΣFy = 0')}.';
  @override
  String get noLoadBetween => 'لا يوجد حمل';
  @override
  String get constantShearMeaning =>
      'بين الأحمال المركّزة لا يوجد حمل موزّع، فقوة القص ثابتة (خط أفقي): ${m('dV/dx = −w = 0')}.';

  @override
  String get momentTitle => 'حساب عزم الانحناء M(x)';
  @override
  String get momentGoal => 'عزوم الجزء الأيسر حول المقطع';
  @override
  String get momentExplanation =>
      'نأخذ نفس المقطع ونجمع عزوم القوى الواقعة على يساره حول المقطع. كل قوة تساهم بـ: القوة × بعدها عن المقطع. '
      'القوة للأعلى على يسار المقطع تعطي عزمًا موجبًا (Sagging).';
  @override
  String get momentDetail =>
      'اصطلاح الإشارة: العزم الموجب يحني الكمرة على شكل ابتسامة ∪ (Sagging): الألياف العليا مضغوطة والسفلى مشدودة. '
      'العزم السالب (Hogging) يحنيها على شكل ∩. لاحظ أن M(x) خطي بين الأحمال المركّزة لأن V ثابتة هناك.';
  @override
  String momentTermForce(String name, String value, String arm, bool sagging) =>
      '${m(name)} × (${m(arm)}): عزم القوة حول المقطع = القوة (${m(value)}) × بعدها عن المقطع (${m(arm)}). '
      '${sagging ? 'القوة للأعلى على يسار المقطع تحني الكمرة على شكل ابتسامة (Sagging) فعزمها موجب.' : 'القوة للأسفل على يسار المقطع تحني الكمرة بالعكس (Hogging) فعزمها سالب.'}';
  @override
  String momentTermCouple(String name, String value, bool counterClockwise) =>
      '${m(name)} عزم مركّز على يسار المقطع بقيمة ${m(value)} ${counterClockwise ? '↺' : '↻'}. '
      'نطرحه لأن العزم ↺ على الجزء الأيسر يعاكس الانحناء الموجب (Sagging).';
  @override
  String get momentStartsAtZero =>
      'عند طرف حر أو مسند Pin أو Roller لا يوجد عزم، فالمخطط يبدأ من الصفر.';
  @override
  String momentStartsWithCouple(String symbol) =>
      'يبدأ المخطط بقيمة ${m('−$symbol')} لأن المسند الثابت يؤثر بعزم ${m(symbol)} عند هذا الطرف.';
  @override
  String areaMeaning(String x0, String x1, String area, bool positive) =>
      'التغير في العزم بين ${m('x = $x0')} و${m('x = $x1')} يساوي مساحة مخطط القص بينهما = ${m(area)}. '
      'المساحة ${positive ? 'موجبة فالعزم يزداد' : 'سالبة فالعزم يقل'}.';
  @override
  String get bmdTitle => 'رسم مخطط عزم الانحناء (BMD)';
  @override
  String get bmdGoal => 'من SFD إلى BMD';
  @override
  String get bmdExplanation =>
      'ميل مخطط العزم يساوي قوة القص (${m('dM/dx = V')}). حيث V ثابتة يكون BMD خطًا مستقيمًا: '
      'V موجبة ⇐ العزم يزداد، V سالبة ⇐ العزم يقل. لذلك التغير في العزم بين نقطتين = مساحة SFD بينهما.';
  @override
  String get bmdDetail =>
      'وعند الطرف الأخير يجب أن يعود العزم إلى الصفر (ما لم يكن هناك مسند Fixed) ✓ — هذا تحقق تلقائي من ${m('ΣM = 0')}.';
  @override
  String get slopeZero => 'V = 0 ⇐ العزم ثابت هنا';
  @override
  String get slopeUp => 'V موجبة ⇐ العزم يزداد ↗';
  @override
  String get slopeDown => 'V سالبة ⇐ العزم يقل ↘';
  @override
  String shearChangesSignAt(String x) => 'V تغيّر إشارتها عند ${m(x)}';
  @override
  String get whyZeroShearMeansPeak =>
      'بما أن ${m('dM/dx = V')}، فالعزم يزداد ما دامت V موجبة ويقل عندما تصبح سالبة. '
      'إذن أكبر عزم يكون حيث تغيّر V إشارتها (أو تساوي صفرًا)، أو عند المساند والأطراف.';
  @override
  String get saggingMeaning =>
      'أكبر عزم موجب (Sagging): الكمرة منحنية ∪، الألياف السفلى في شد (Tension) والعليا في ضغط (Compression).';
  @override
  String get hoggingMeaning =>
      'أكبر عزم سالب (Hogging): الكمرة منحنية ∩، الألياف العليا في شد والسفلى في ضغط.';
  @override
  String get maxMomentTitle => 'أقصى عزم Mmax';
  @override
  String get maxMomentGoal => 'أين وكم؟';
  @override
  String maxMomentExplanation({
    required String x,
    required String value,
    required bool atZeroShear,
    required bool sagging,
    required bool atSupport,
  }) {
    if (atZeroShear) {
      return 'أقصى عزم = ${m(value)} عند ${m(x)}: هناك تتغير إشارة قوة القص، فالعزم يتوقف عن الزيادة ويبدأ بالنقصان — هذه قمة المخطط.';
    }
    if (atSupport && !sagging) {
      return 'أكبر قيمة للعزم = ${m(value)} عند المسند (${m(x)}). العزم سالب (Hogging): في الكمرة الكابولية أو فوق مسند يليه جزء بارز يكون أكبر عزم عند المسند.';
    }
    return 'أكبر قيمة للعزم = ${m(value)} عند ${m(x)}.';
  }

  @override
  String get axialTitle => 'القوة المحورية N(x)';
  @override
  String get axialGoal => 'شد أم ضغط؟';
  @override
  String get axialExplanation =>
      'القوة المحورية تساوي سالب مجموع القوى الأفقية على يسار المقطع: ${m('N = −ΣFx')}. '
      'N موجبة تعني شدًا (Tension: المقطع يُسحب)، وسالبة تعني ضغطًا (Compression).';
  @override
  String get tensionNote => 'N موجبة ⇐ شد (Tension)';
  @override
  String get compressionNote => 'N سالبة ⇐ ضغط (Compression)';

  @override
  String checkName(CheckKind kind) => switch (kind) {
        CheckKind.sumFx => 'ΣFx = 0',
        CheckKind.sumFy => 'ΣFy = 0',
        CheckKind.sumMomentLeftEnd => 'ΣM حول الطرف الأيسر = 0',
        CheckKind.sumMomentRightEnd => 'ΣM حول الطرف الأيمن = 0',
        CheckKind.shearClosesAtEnd => 'SFD يعود إلى الصفر عند النهاية',
        CheckKind.momentClosesAtEnd => 'BMD يعود إلى الصفر عند النهاية',
        CheckKind.axialClosesAtEnd => 'N تعود إلى الصفر عند النهاية',
        CheckKind.shearJumpsMatchLoads => 'قفزات SFD = الأحمال المركّزة',
        CheckKind.momentJumpsMatchCouples => 'قفزات BMD = العزوم المركّزة',
        CheckKind.slopeEqualsShear => 'ميل BMD = V  (dM/dx = V)',
        CheckKind.areaRule => 'تغيّر M = مساحة SFD',
      };
}

class EnglishTexts extends Texts {
  const EnglishTexts();

  String _list(List<String> items) {
    if (items.length <= 1) return items.join();
    return '${items.sublist(0, items.length - 1).join(', ')} and ${items.last}';
  }

  String _sign(bool positive) => positive ? 'positive' : 'negative';

  @override
  String get givenTitle => 'The problem';
  @override
  String get givenGoal => 'What is given';

  @override
  String supportBehaviour(SupportType type) => switch (type) {
        SupportType.pin =>
          'Pin: stops the beam moving sideways and up/down but lets it rotate, so it gives two reactions, horizontal and vertical.',
        SupportType.roller =>
          'Roller: rolls along its surface, so it only stops movement perpendicular to that surface. One vertical reaction, no horizontal resistance.',
        SupportType.fixed =>
          'Fixed: the beam is built in, so it can neither move nor rotate. Three reactions: horizontal, vertical and a moment.',
      };

  @override
  String loadDescription({
    required String name,
    required String value,
    required String point,
    required String x,
    required String direction,
  }) =>
      'Load $name is a concentrated force of $value acting $direction at point $point, $x from the left end.';

  @override
  String givenExplanation({
    required String length,
    required List<(String, String)> supports,
    required int loadCount,
  }) {
    final s = _list([for (final e in supports) 'a ${e.$1} at ${e.$2}']);
    final loads = switch (loadCount) {
      0 => 'no loads',
      1 => 'one point load',
      _ => '$loadCount point loads',
    };
    return 'A $length beam on $s, carrying $loads. '
        'Find the reactions, then draw the shear force diagram (SFD) and the bending moment diagram (BMD).';
  }

  @override
  String get downward => 'downward ↓';
  @override
  String get upward => 'upward ↑';
  @override
  String get rightward => 'to the right →';
  @override
  String get leftward => 'to the left ←';
  @override
  String inclined(String angle, String arrow) =>
      'inclined $arrow at $angle° to the horizontal';

  @override
  String unsolvableTitle(Determinacy status) => switch (status) {
        Determinacy.unstable => 'The beam is unstable',
        Determinacy.indeterminate => 'Statically indeterminate',
        Determinacy.invalid => 'The problem is incomplete',
        Determinacy.determinate => 'Ready to solve',
      };
  @override
  String get unsolvableGoal => 'Why it cannot be solved';

  @override
  String stabilityMessage(StabilityReason reason, int unknowns, int degree) =>
      switch (reason) {
        StabilityReason.noBeam => 'Draw a beam first: pick Beam and drag across the sheet.',
        StabilityReason.noSupports =>
          'There are no supports, so the beam would fall. Add supports to hold it.',
        StabilityReason.elementOffBeam =>
          'A support or load is off the beam. Move it between the two ends.',
        StabilityReason.noHorizontalRestraint =>
          'Nothing stops the beam sliding sideways (there is no pin or fixed support). Any horizontal force, however small, would move it.',
        StabilityReason.concurrentReactions =>
          'All the reactions pass through one point, so nothing stops the beam rotating about it.',
        StabilityReason.tooFewReactions =>
          'There are $unknowns reactions but 3 equilibrium equations, so the beam can move.',
        StabilityReason.tooManyReactions =>
          'There are $unknowns unknowns but only 3 equilibrium equations: the beam is statically indeterminate to degree $degree. '
              'Solving it needs compatibility of deformations, which this version does not cover yet.',
        StabilityReason.ok => '',
      };

  @override
  String stabilityAdvice(StabilityReason reason) => switch (reason) {
        StabilityReason.noHorizontalRestraint => 'Fix: replace one roller with a pin.',
        StabilityReason.concurrentReactions => 'Fix: put the two supports at different points.',
        StabilityReason.tooFewReactions || StabilityReason.noSupports =>
          'The usual set-ups: a pin at one end and a roller at the other, or a single fixed support (a cantilever).',
        StabilityReason.tooManyReactions =>
          'For a determinate beam use a pin with a roller, or one fixed support alone.',
        _ => '',
      };

  @override
  String get fbdTitle => 'Free Body Diagram (FBD)';
  @override
  String get fbdGoal => 'Replace each support by its reactions';
  @override
  String get fbdExplanation =>
      'The FBD shows the beam on its own with every force acting on it: the loads we know and the reactions we do not. '
      'Each support is removed and replaced by the forces it can apply: every movement a support prevents has a reaction.';
  @override
  String get fbdDetail =>
      'A pin stops horizontal and vertical movement ⇒ two reactions (H, R). '
      'A roller only stops movement perpendicular to its surface ⇒ one reaction (R). '
      'A fixed support stops both movements and rotation ⇒ three (H, R, M). '
      'In 2D there are three equilibrium equations, so with exactly three unknowns the beam is statically determinate and equilibrium alone solves it.';

  @override
  String reactionMeaning(
          ReactionKind kind, String symbol, String point, SupportType type) =>
      switch (kind) {
        ReactionKind.horizontal =>
          '$symbol: the horizontal reaction at $point. The ${supportName(type).toLowerCase()} stops the beam sliding sideways, so it can push or pull along x.',
        ReactionKind.vertical => type == SupportType.roller
            ? '$symbol: the vertical reaction at $point. A roller only resists movement perpendicular to its surface, so it has one vertical reaction and no horizontal one.'
            : '$symbol: the vertical reaction at $point. The support stops the beam moving up or down.',
        ReactionKind.moment =>
          '$symbol: the reaction moment at $point. A fixed support stops the beam rotating, so it applies a moment.',
      };

  @override
  String unknownsCount(int n) => '$n unknowns';
  @override
  String equationsCount(int n) => '$n equilibrium equations';
  @override
  String get threeEquations =>
      'In 2D there are three independent equilibrium equations: ΣFx = 0, ΣFy = 0 and ΣM = 0.';
  @override
  String get assumedDirections =>
      'Every reaction is assumed to act in the positive direction: H →, R ↑, M ↺. If a result comes out negative, it acts the other way — no need to redo anything.';

  @override
  String get componentsTitle => 'Resolve inclined loads';
  @override
  String get componentsGoal => 'into x and y components';
  @override
  String get componentsExplanation =>
      'The beam is horizontal, so each inclined load is split into a component along the beam (x) and one perpendicular to it (y). '
      'The x components go into ΣFx; the y components go into ΣFy and ΣM.';
  @override
  String cosExplanation(String name, String angle) =>
      'Horizontal component of $name = its value × cos of its angle to the horizontal ($angle°).';
  @override
  String sinExplanation(String name, String angle) =>
      'Vertical component of $name = its value × sin of its angle to the horizontal ($angle°).';

  @override
  String findGoal(String symbol) => 'Find $symbol';
  @override
  String get momentEquilibriumMeaning =>
      'The body is in equilibrium, so the sum of moments about any point is zero. '
      'We may choose the point freely, and choosing one that unknown forces pass through removes them from the equation: their moment arm is zero.';
  @override
  String forceEquilibriumMeaning(bool horizontal) =>
      'The body is in equilibrium (it does not move or accelerate), so the ${horizontal ? 'horizontal' : 'vertical'} forces on it add up to zero.';

  @override
  String conventionMeaning(EquationKind kind, SignConvention c) {
    final rule = switch (kind) {
      EquationKind.sumFx => c.rightPositive ? 'forces to the right → are positive' : 'forces to the left ← are positive',
      EquationKind.sumFy => c.upPositive ? 'upward forces ↑ are positive' : 'downward forces ↓ are positive',
      EquationKind.sumMoment => c.counterClockwisePositive
          ? 'counter-clockwise moments ↺ are positive'
          : 'clockwise moments ↻ are positive',
    };
    return 'Sign convention: $rule. You can change it in Settings; the signs of the terms change but the results do not.';
  }

  @override
  String termCouple(String symbol, String point, bool positive) =>
      '$symbol is the reaction moment at $point. A couple has no arm: its moment is the same about every point, so it is written as it is. '
      'It was assumed ↺, so it is ${_sign(positive)}.';

  @override
  String termReactionMoment({
    required String symbol,
    required String point,
    required String about,
    required String arm,
    required bool counterClockwise,
    required bool positive,
  }) =>
      '$symbol is the reaction force at support $point, and $arm is the distance between $about and $point (the moment arm). '
      '$symbol pushes up to the ${counterClockwise ? 'right' : 'left'} of $about, so it turns the beam '
      '${counterClockwise ? 'counter-clockwise ↺' : 'clockwise ↻'} about it: ${_sign(positive)}.';

  @override
  String termReactionForce(
          String symbol, String point, String arrow, bool positive) =>
      '$symbol is the reaction at $point, assumed $arrow, so it is ${_sign(positive)} in this equation.';

  @override
  String termLoadMoment({
    required String name,
    required String value,
    required String about,
    required String arm,
    required bool isComponent,
    required String loadName,
    required bool counterClockwise,
    required bool positive,
  }) {
    final what = isComponent
        ? '$value is $name, the vertical component of load $loadName,'
        : '$value is the value of load $name';
    final note = isComponent
        ? ' (The horizontal component acts along the beam axis, through $about, so it has no moment about it.)'
        : '';
    return '$what and $arm is the distance from $about to the load. '
        'It turns the beam ${counterClockwise ? 'counter-clockwise ↺' : 'clockwise ↻'} about $about, so it is ${_sign(positive)}.$note';
  }

  @override
  String termLoadForce({
    required String name,
    required String value,
    required String direction,
    required bool isComponent,
    required String loadName,
    required bool positive,
  }) {
    final what = isComponent
        ? '$value is component $name of load $loadName'
        : '$value is the value of load $name';
    return '$what, acting $direction, so it is ${_sign(positive)}.';
  }

  @override
  String termKnownReaction(String symbol, String value) =>
      '$symbol = $value was found in an earlier step, so its value is substituted.';
  @override
  String negativeMeaning(String symbol, String arrow) =>
      'The minus sign means $symbol actually acts $arrow, opposite to the direction we assumed. The answer is right; only the direction is reversed.';
  @override
  String noHorizontalLoads(String symbol) =>
      'There are no horizontal loads, so there is nothing for $symbol to resist.';
  @override
  String whySumFxWithLoads(String target) =>
      'ΣFx = 0 has only one unknown, $target, because it is the only reaction that resists horizontal movement. So we solve it first.';
  @override
  String whySumFxNoLoads(String target) =>
      'There are no horizontal loads on the beam, so the only horizontal force is $target, and it must be zero or the beam would slide.';
  @override
  String whySumFy(String target, List<String> known) => known.isEmpty
      ? '$target is the only vertical unknown, so vertical equilibrium gives it directly.'
      : 'Now that ${_list(known)} ${known.length == 1 ? 'is' : 'are'} known, vertical force equilibrium gives $target.';
  @override
  String whySumMoment({
    required String about,
    required String target,
    required List<String> through,
    required bool isCouple,
  }) {
    final passes = through.isEmpty
        ? ''
        : ', and the line${through.length == 1 ? '' : 's'} of action of ${_list(through)} pass${through.length == 1 ? 'es' : ''} through $about, so their moment about $about is zero';
    return 'We take moments about $about because we want $target$passes. '
        'That leaves a single unknown in the equation.';
  }

  @override
  String get checkWord => 'Check';
  @override
  String get checkGoal => 'Is the answer right?';
  @override
  String checkExplanation(String point) =>
      'We did not use moments about $point to find the reactions, so if this also comes out zero the values are right. '
      'It is a quick way to catch mistakes in an exam.';
  @override
  String get reactionsTitle => 'Reactions';
  @override
  String get reactionsGoal => 'The results and their real directions';
  @override
  String get sumOfVerticalReactions => 'ΣR';
  @override
  String totalDownwardLoad(String value) => '$value (net downward load)';
  @override
  String get verticalBalanceMeaning =>
      'What the supports push up equals what the loads push down; that is what ΣFy = 0 means.';
  @override
  String get reactionsExplanation =>
      'Every non-negative reaction acts in the direction we assumed.';
  @override
  String reactionsExplanationWithNegative(List<(String, String)> negatives) {
    final list = negatives.map((e) => '${e.$1} ${e.$2}').join(', ');
    return '$list came out negative, so it acts opposite to the assumed direction. '
        'This usually happens with an overhang: a load on the overhanging end lifts the other end, and that support has to pull it down.';
  }

  @override
  String get shearTitle => 'Shear force V(x)';
  @override
  String get shearGoal => 'Method of sections';
  @override
  String get shearExplanation =>
      'Cut the beam at a section x inside each segment and keep the left part. The shear V is the sum of the vertical forces left of the cut: '
      'upward ↑ positive, downward ↓ negative.';
  @override
  String get shearDetail =>
      'Sign convention: V is positive when the forces left of the cut push it up (and those to the right push it down). '
      'Why the left part? Both parts give the same V; the left is simpler because we read the beam left to right. '
      'The cut is between two loads, hence the strict < in the range: a force exactly at the cut is what makes the diagram jump.';
  @override
  String shearTermReaction(String symbol, String value, bool up) => up
      ? '$symbol is a reaction left of the cut, $value upward ↑, so it is added.'
      : '$symbol = $value: assumed ↑ but it came out negative, so its negative value is substituted.';
  @override
  String shearTermLoad(String symbol, String value, bool down) => down
      ? '$symbol is a load left of the cut, $value downward ↓, so it is subtracted.'
      : '$symbol is a load left of the cut, $value upward ↑, so it is added.';
  @override
  String shearSignNote(int sign, String up, String down) => switch (sign) {
        < 0 =>
          'V is negative here because the downward forces left of the cut ($down) outweigh the upward ones ($up).',
        > 0 =>
          'V is positive because the upward forces left of the cut ($up) outweigh the downward ones ($down).',
        _ => 'V = 0: the forces left of the cut balance.',
      };
  @override
  String get sfdTitle => 'Shear Force Diagram (SFD)';
  @override
  String get sfdGoal => 'From the loads to the SFD';
  @override
  String get sfdExplanation =>
      'The SFD can be drawn straight from the loads, walking left to right: an upward force makes the diagram jump up by its value, '
      'a downward force makes it jump down. Between loads it stays level because there is no load there.';
  @override
  String get sfdDetail =>
      'Why does the diagram end at zero? Because all the jumps add up to the sum of all vertical forces, which is zero by ΣFy = 0. '
      'If it does not close, a reaction is wrong.';
  @override
  String jumpMeaning(String symbol, String value, bool up) =>
      'At a point force the shear jumps by that force, in its direction: $symbol = $value ${up ? 'upward ⇒ the diagram jumps up' : 'downward ⇒ the diagram jumps down'}.';
  @override
  String get shearClosesNote =>
      'The diagram returns to zero at the end of the beam ✓ — a built-in check of ΣFy = 0.';
  @override
  String get noLoadBetween => 'no load';
  @override
  String get constantShearMeaning =>
      'Between point loads there is no distributed load, so the shear is constant (a level line): dV/dx = −w = 0.';

  @override
  String get momentTitle => 'Bending moment M(x)';
  @override
  String get momentGoal => 'Moments of the left part about the cut';
  @override
  String get momentExplanation =>
      'Take the same cut and add up the moments of the forces left of it about the cut. Each force contributes force × its distance to the cut. '
      'An upward force on the left gives a positive (sagging) moment.';
  @override
  String get momentDetail =>
      'Sign convention: a positive moment bends the beam into a smile ∪ (sagging): top fibres in compression, bottom fibres in tension. '
      'A negative (hogging) moment bends it ∩. M(x) is linear between point loads because V is constant there.';
  @override
  String momentTermForce(String name, String value, String arm, bool sagging) =>
      '$name × ($arm): the moment of a force about the cut = the force ($value) × its distance to the cut ($arm). '
      '${sagging ? 'An upward force left of the cut bends the beam into a smile (sagging): positive.' : 'A downward force left of the cut bends the beam the other way (hogging): negative.'}';
  @override
  String momentTermCouple(String name, String value, bool counterClockwise) =>
      '$name is a couple of $value ${counterClockwise ? '↺' : '↻'} left of the cut. '
      'It is subtracted because a ↺ couple on the left part opposes sagging.';
  @override
  String get momentStartsAtZero =>
      'A free end, a pin or a roller cannot carry moment, so the diagram starts at zero.';
  @override
  String momentStartsWithCouple(String symbol) =>
      'The diagram starts at −$symbol because the fixed support applies the moment $symbol at this end.';
  @override
  String areaMeaning(String x0, String x1, String area, bool positive) =>
      'The change in moment between x = $x0 and x = $x1 equals the area of the SFD between them = $area. '
      'The area is ${positive ? 'positive, so M increases' : 'negative, so M decreases'}.';
  @override
  String get bmdTitle => 'Bending Moment Diagram (BMD)';
  @override
  String get bmdGoal => 'From the SFD to the BMD';
  @override
  String get bmdExplanation =>
      'The slope of the BMD equals the shear (dM/dx = V). Where V is constant the BMD is a straight line: '
      'positive V ⇒ M rises, negative V ⇒ M falls. So the change in M between two points is the area of the SFD between them.';
  @override
  String get bmdDetail =>
      'At the far end the moment must come back to zero (unless that end is fixed) ✓ — a built-in check of ΣM = 0.';
  @override
  String get slopeZero => 'V = 0 ⇒ M is constant here';
  @override
  String get slopeUp => 'V positive ⇒ M rises ↗';
  @override
  String get slopeDown => 'V negative ⇒ M falls ↘';
  @override
  String shearChangesSignAt(String x) => 'V changes sign at $x';
  @override
  String get whyZeroShearMeansPeak =>
      'Since dM/dx = V, the moment rises while V is positive and falls once V turns negative. '
      'So the largest moment is where V changes sign (or is zero), or at a support or an end.';
  @override
  String get saggingMeaning =>
      'Largest positive (sagging) moment: the beam bends ∪, bottom fibres in tension, top fibres in compression.';
  @override
  String get hoggingMeaning =>
      'Largest negative (hogging) moment: the beam bends ∩, top fibres in tension, bottom fibres in compression.';
  @override
  String get maxMomentTitle => 'Maximum moment Mmax';
  @override
  String get maxMomentGoal => 'Where, and how big?';
  @override
  String maxMomentExplanation({
    required String x,
    required String value,
    required bool atZeroShear,
    required bool sagging,
    required bool atSupport,
  }) {
    if (atZeroShear) {
      return 'Mmax = $value at $x: that is where the shear changes sign, so the moment stops rising and starts to fall — the peak of the diagram.';
    }
    if (atSupport && !sagging) {
      return 'The largest moment is $value at the support ($x). It is hogging: in a cantilever, or over a support next to an overhang, the largest moment is at the support.';
    }
    return 'The largest moment is $value at $x.';
  }

  @override
  String get axialTitle => 'Axial force N(x)';
  @override
  String get axialGoal => 'Tension or compression?';
  @override
  String get axialExplanation =>
      'The axial force is minus the sum of the horizontal forces left of the cut: N = −ΣFx. '
      'Positive N is tension (the cut is pulled), negative is compression.';
  @override
  String get tensionNote => 'N positive ⇒ tension';
  @override
  String get compressionNote => 'N negative ⇒ compression';

  @override
  String checkName(CheckKind kind) => switch (kind) {
        CheckKind.sumFx => 'ΣFx = 0',
        CheckKind.sumFy => 'ΣFy = 0',
        CheckKind.sumMomentLeftEnd => 'ΣM about the left end = 0',
        CheckKind.sumMomentRightEnd => 'ΣM about the right end = 0',
        CheckKind.shearClosesAtEnd => 'SFD closes to zero at the end',
        CheckKind.momentClosesAtEnd => 'BMD closes to zero at the end',
        CheckKind.axialClosesAtEnd => 'N closes to zero at the end',
        CheckKind.shearJumpsMatchLoads => 'SFD jumps = point loads',
        CheckKind.momentJumpsMatchCouples => 'BMD jumps = point couples',
        CheckKind.slopeEqualsShear => 'BMD slope = V  (dM/dx = V)',
        CheckKind.areaRule => 'Change in M = area of SFD',
      };
}
