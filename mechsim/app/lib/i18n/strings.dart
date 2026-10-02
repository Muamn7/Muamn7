import 'package:mechsim_core/mechsim_core.dart';

/// Interface strings. Technical names (Beam, Pin, SFD, ANALYZE…) stay in
/// English in both languages, the way they are used in engineering classes;
/// the Arabic interface adds Arabic around them.
abstract class S {
  const S();

  static S of(Lang lang) => lang == Lang.ar ? const _Ar() : const _En();

  String get appName => 'MechSim 2D';
  String get appTagline;

  // navigation
  String get navHome;
  String get navPractice;
  String get navSaved;
  String get navLearn;
  String get navSettings;

  // home
  String get newProblem;
  String get newProblemSub;
  String get practice;
  String get practiceSub;
  String get mechanics;
  String get mechanicsSub;
  String get strength;
  String get strengthSub;
  String get savedProblems;
  String get savedSub;
  String get tutorials;
  String get tutorialsSub;
  String get comingSoon;
  String get learningPath;

  // editor
  String get untitled;
  String get toolSelect => 'Select';
  String get toolBeam => 'Beam';
  String get toolPin => 'Pin';
  String get toolRoller => 'Roller';
  String get toolFixed => 'Fixed';
  String get toolPointLoad => 'Point Load';
  String get toolUdl => 'UDL';
  String get toolUvl => 'UVL';
  String get toolMoment => 'Moment';
  String get toolDimension => 'Dimension';
  String get toolDelete => 'Delete';
  String get undo => 'Undo';
  String get redo => 'Redo';
  String get analyze => 'ANALYZE';
  String hintFor(String tool);
  String get hintEmpty;
  String get drawBeamFirst;
  String get tapOnBeam;
  String get notInMvp;
  String get save;
  String get saved;
  String get nameProblem;
  String get cancel;
  String get ok;
  String get delete;
  String get edit;
  String get clearAll;
  String get fitView;
  String get rename;
  String get flip;

  // properties
  String get beamProps;
  String get supportProps;
  String get loadProps;
  String get udlProps;
  String get uvlProps;
  String get momentProps;
  String get startX;
  String get endX;
  String get intensity;
  String get intensityStart;
  String get intensityEnd;
  String get uniformToggle;
  String get loadDown;
  String get loadUp;
  String get ccw;
  String get cw;
  String get length => 'Length';
  String get position => 'Position';
  String get magnitude => 'Magnitude';
  String get direction => 'Direction';
  String get angle;
  String get angleHelp;
  String get supportType;
  String get invalidNumber;
  String get mustBePositive;

  // analysis
  String get analysis;
  String get fbd => 'FBD';
  String get sfd => 'SFD';
  String get bmd => 'BMD';
  String get afd => 'AFD';
  String get reactions;
  String get keyResults;
  String get steps;
  String get explanation;
  String get explain;
  String get hideExplain;
  String get verification;
  String get allChecksPassed;
  String get someChecksFailed;
  String get playSteps;
  String get quizMe;
  String get copyText;
  String get copied;
  String get tapDiagramHint;
  String get backToEdit;
  String get diagramsWillAppear;
  String step(int n, int total);

  // player
  String get start;
  String get pause;
  String get next;
  String get previous;

  // practice
  String get level;
  String levelName(PracticeLevel l);
  String get newPracticeProblem;
  String question(int n, int total);
  String get yourAnswer;
  String get check;
  String get showSolution;
  String get nextQuestion;
  String get openFullSolution;
  String get practiceDone;
  String score(int correct, int total);
  String get practiceThisProblem;
  String get enterNumber;

  // saved
  String get noSaved;
  String savedSummary(String length, int supports, int loads);
  String get deleted;

  // learn
  String get examples;

  // settings
  String get settings;
  String get language;
  String get units;
  String get force;
  String get lengthUnit;
  String get momentUnit;
  String get signConvention;
  String get signConventionHelp;
  String get positiveY;
  String get positiveX;
  String get positiveMoment;
  String get beamConventionTitle;
  String get beamConvention;
  String get theme;
  String get themeSystem;
  String get themeLight;
  String get themeDark;
  String get orientation;
  String get orientationAuto;
  String get orientationLandscape;
  String get orientationPortrait;
  String get orientationHelp;
  String get about;
  String get aboutText;

  // strength of materials
  String get somTitle;
  String get somIntro;
  List<(String, String)> get somPlanned;
}

class _Ar extends S {
  const _Ar();

  @override
  String get appTagline => 'ارسم ← افهم ← احسب ← اشرح ← تخيّل ← تدرّب';

  @override
  String get navHome => 'الرئيسية';
  @override
  String get navPractice => 'تدريب';
  @override
  String get navSaved => 'المحفوظة';
  @override
  String get navLearn => 'تعلّم';
  @override
  String get navSettings => 'الإعدادات';

  @override
  String get newProblem => 'New Problem';
  @override
  String get newProblemSub => 'ارسم مسألتك وحلّها خطوة بخطوة';
  @override
  String get practice => 'Practice';
  @override
  String get practiceSub => 'مسائل جديدة في كل مرة مع تلميحات';
  @override
  String get mechanics => 'Mechanics';
  @override
  String get mechanicsSub => 'أمثلة كلاسيكية جاهزة للتجربة';
  @override
  String get strength => 'Strength of Materials';
  @override
  String get strengthSub => 'الإجهاد والانفعال — قريبًا';
  @override
  String get savedProblems => 'Saved Problems';
  @override
  String get savedSub => 'مسائلك المحفوظة';
  @override
  String get tutorials => 'Tutorials';
  @override
  String get tutorialsSub => 'المساند، الاتزان، SFD وBMD';
  @override
  String get comingSoon => 'قريبًا';
  @override
  String get learningPath => 'ارسم ← افهم ← احسب ← تخيّل ← تدرّب';

  @override
  String get untitled => 'مسألة جديدة';
  @override
  String hintFor(String tool) => switch (tool) {
    'beam' => 'اسحب إصبعك أفقيًا لرسم الكمرة',
    'pin' => 'اضغط على الكمرة لوضع Pin',
    'roller' => 'اضغط على الكمرة لوضع Roller',
    'fixed' => 'اضغط على طرف الكمرة لوضع Fixed',
    'pointLoad' => 'اضغط على الكمرة لوضع حمل مركّز',
    'udl' =>
      'اسحب على الكمرة من بداية الحمل إلى نهايته، أو اضغط لوضع حمل طوله 2 m',
    'uvl' => 'اسحب على الكمرة من بداية الحمل إلى نهايته (يبدأ من الصفر ويزداد)',
    'moment' => 'اضغط على الكمرة لوضع عزم مركّز',
    'delete' => 'اضغط على عنصر لحذفه',
    _ => 'اضغط على عنصر لتعديله، واسحبه لتحريكه. ضغطة مطوّلة للخيارات',
  };
  @override
  String get hintEmpty => 'ابدأ برسم الكمرة: اختر Beam واسحب إصبعك على الورقة';
  @override
  String get drawBeamFirst => 'ارسم الكمرة أولًا';
  @override
  String get tapOnBeam => 'اضغط على الكمرة نفسها';
  @override
  String get notInMvp => 'قريبًا: نضيفه بعد اختبار الأحمال المركّزة بالكامل';
  @override
  String get save => 'حفظ';
  @override
  String get saved => 'تم الحفظ';
  @override
  String get nameProblem => 'اسم المسألة';
  @override
  String get cancel => 'إلغاء';
  @override
  String get ok => 'موافق';
  @override
  String get delete => 'حذف';
  @override
  String get edit => 'تعديل';
  @override
  String get clearAll => 'مسح الكل';
  @override
  String get fitView => 'ملاءمة العرض';
  @override
  String get rename => 'إعادة التسمية';
  @override
  String get flip => 'عكس الاتجاه';

  @override
  String get beamProps => 'Beam — الكمرة';
  @override
  String get supportProps => 'Support — المسند';
  @override
  String get loadProps => 'Point Load — حمل مركّز';
  @override
  String get udlProps => 'UDL — حمل موزّع منتظم';
  @override
  String get uvlProps => 'UVL — حمل موزّع متغير';
  @override
  String get momentProps => 'Moment — عزم مركّز';
  @override
  String get startX => 'من x';
  @override
  String get endX => 'إلى x';
  @override
  String get intensity => 'الشدة w';
  @override
  String get intensityStart => 'w البداية';
  @override
  String get intensityEnd => 'w النهاية';
  @override
  String get uniformToggle => 'منتظم (UDL)';
  @override
  String get loadDown => '↓ للأسفل';
  @override
  String get loadUp => '↑ للأعلى';
  @override
  String get ccw => '↺ عكس عقارب الساعة';
  @override
  String get cw => '↻ مع عقارب الساعة';
  @override
  String get angle => 'θ';
  @override
  String get angleHelp => 'من محور x الموجب عكس عقارب الساعة: −90° = ↓';
  @override
  String get supportType => 'النوع';
  @override
  String get invalidNumber => 'رقم غير صالح';
  @override
  String get mustBePositive => 'يجب أن يكون أكبر من صفر';

  @override
  String get analysis => 'التحليل';
  @override
  String get reactions => 'Reactions — ردود الأفعال';
  @override
  String get keyResults => 'أهم النتائج';
  @override
  String get steps => 'الحل خطوة بخطوة';
  @override
  String get explanation => 'الشرح';
  @override
  String get explain => 'Explain';
  @override
  String get hideExplain => 'إخفاء';
  @override
  String get verification => 'التحقق';
  @override
  String get allChecksPassed => 'كل الفحوص ناجحة ✓';
  @override
  String get someChecksFailed => 'بعض الفحوص فشلت ✗';
  @override
  String get playSteps => 'تشغيل الحل';
  @override
  String get quizMe => 'اختبرني';
  @override
  String get copyText => 'نسخ الحل';
  @override
  String get copied => 'تم نسخ الحل';
  @override
  String get tapDiagramHint => 'المس أي نقطة على المخططات لقراءة القيم';
  @override
  String get backToEdit => 'عودة للتعديل';
  @override
  String get diagramsWillAppear => 'يظهر هنا في خطوة لاحقة';
  @override
  String step(int n, int total) => 'الخطوة $n من $total';

  @override
  String get start => 'ابدأ';
  @override
  String get pause => 'إيقاف';
  @override
  String get next => 'التالي';
  @override
  String get previous => 'السابق';

  @override
  String get level => 'المستوى';
  @override
  String levelName(PracticeLevel l) => switch (l) {
    PracticeLevel.basic => 'أساسي',
    PracticeLevel.intermediate => 'متوسط',
    PracticeLevel.advanced => 'متقدم',
  };
  @override
  String get newPracticeProblem => 'مسألة جديدة';
  @override
  String question(int n, int total) => 'السؤال $n من $total';
  @override
  String get yourAnswer => 'إجابتك';
  @override
  String get check => 'Check';
  @override
  String get showSolution => 'Show Solution';
  @override
  String get nextQuestion => 'السؤال التالي';
  @override
  String get openFullSolution => 'افتح الحل الكامل';
  @override
  String get practiceDone => 'أنهيت أسئلة هذه المسألة';
  @override
  String score(int correct, int total) =>
      'صحيح من المحاولة الأولى: $correct من $total';
  @override
  String get practiceThisProblem => 'تدرّب على هذه المسألة';
  @override
  String get enterNumber => 'اكتب رقمًا';

  @override
  String get noSaved => 'لا توجد مسائل محفوظة بعد. احفظ مسألة من شاشة الرسم.';
  @override
  String savedSummary(String length, int supports, int loads) =>
      'L = $length · $supports مساند · $loads أحمال';
  @override
  String get deleted => 'تم الحذف';

  @override
  String get examples => 'أمثلة Mechanics';

  @override
  String get settings => 'الإعدادات';
  @override
  String get language => 'اللغة';
  @override
  String get units => 'الوحدات';
  @override
  String get force => 'القوة';
  @override
  String get lengthUnit => 'الطول';
  @override
  String get momentUnit => 'العزم';
  @override
  String get signConvention => 'اصطلاح الإشارات';
  @override
  String get signConventionHelp =>
      'يغيّر طريقة كتابة معادلات الاتزان فقط؛ ردود الأفعال نفسها لا تتغير.';
  @override
  String get positiveY => 'الاتجاه الرأسي الموجب';
  @override
  String get positiveX => 'الاتجاه الأفقي الموجب';
  @override
  String get positiveMoment => 'العزم الموجب';
  @override
  String get beamConventionTitle => 'إشارات المخططات (ثابتة)';
  @override
  String get beamConvention =>
      'V موجبة: مجموع القوى للأعلى على يسار المقطع.\nM موجب: Sagging ∪ (الألياف السفلى في شد).\nN موجبة: شد (Tension).';
  @override
  String get theme => 'المظهر';
  @override
  String get themeSystem => 'حسب النظام';
  @override
  String get themeLight => 'فاتح';
  @override
  String get themeDark => 'داكن';
  @override
  String get orientation => 'اتجاه الشاشة';
  @override
  String get orientationAuto => 'تلقائي';
  @override
  String get orientationLandscape => 'بالعرض';
  @override
  String get orientationPortrait => 'بالطول';
  @override
  String get orientationHelp =>
      '«بالعرض» يُبقي التطبيق أفقيًا حتى لو كان تدوير الهاتف مقفلًا. «تلقائي» يتبع الهاتف.';
  @override
  String get about => 'عن التطبيق';
  @override
  String get aboutText =>
      'MechSim 2D — الإصدار الأول (MVP): كمرة، Pin وRoller وFixed، أحمال مركّزة، ردود الأفعال، FBD وSFD وBMD مع الشرح خطوة بخطوة ووضع التدريب. '
      'المحرك الحسابي مستقل عن الواجهة ويتحقق من كل حل تلقائيًا.';

  @override
  String get somTitle => 'Strength of Materials';
  @override
  String get somIntro =>
      'هذا القسم قادم بعد اكتمال اختبار قسم الكمرات. المخطط له:';
  @override
  List<(String, String)> get somPlanned => const [
    ('Tension', 'σ = F/A مع اتجاه القوة'),
    ('Compression', 'σ = −F/A'),
    ('Shear Stress', 'τ = V/A والفرق بين القوة العمودية وقوة القص'),
    ('Bending Stress', 'σ = My/I مع المحور المحايد ومنطقتي الشد والضغط'),
    ('Torsion', 'τ = Tr/J على عمود دائري'),
  ];
}

class _En extends S {
  const _En();

  @override
  String get appTagline =>
      'Draw → Understand → Calculate → Explain → Visualize → Practice';

  @override
  String get navHome => 'Home';
  @override
  String get navPractice => 'Practice';
  @override
  String get navSaved => 'Saved';
  @override
  String get navLearn => 'Learn';
  @override
  String get navSettings => 'Settings';

  @override
  String get newProblem => 'New Problem';
  @override
  String get newProblemSub => 'Draw your own problem and solve it step by step';
  @override
  String get practice => 'Practice';
  @override
  String get practiceSub => 'A fresh problem every time, with hints';
  @override
  String get mechanics => 'Mechanics';
  @override
  String get mechanicsSub => 'Classic examples, ready to explore';
  @override
  String get strength => 'Strength of Materials';
  @override
  String get strengthSub => 'Stress and strain — coming soon';
  @override
  String get savedProblems => 'Saved Problems';
  @override
  String get savedSub => 'Your saved problems';
  @override
  String get tutorials => 'Tutorials';
  @override
  String get tutorialsSub => 'Supports, equilibrium, SFD and BMD';
  @override
  String get comingSoon => 'Coming soon';
  @override
  String get learningPath =>
      'Draw → Understand → Calculate → Visualize → Practice';

  @override
  String get untitled => 'New problem';
  @override
  String hintFor(String tool) => switch (tool) {
    'beam' => 'Drag across the sheet to draw the beam',
    'pin' => 'Tap the beam to place a pin',
    'roller' => 'Tap the beam to place a roller',
    'fixed' => 'Tap an end of the beam to fix it',
    'pointLoad' => 'Tap the beam to place a point load',
    'udl' =>
      'Drag along the beam from where the load starts to where it ends, or tap for a 2 m load',
    'uvl' => 'Drag along the beam from start to end (it rises from zero)',
    'moment' => 'Tap the beam to place a concentrated moment',
    'delete' => 'Tap an element to delete it',
    _ => 'Tap an element to edit it, drag to move it, long-press for options',
  };
  @override
  String get hintEmpty =>
      'Start with the beam: pick Beam and drag across the sheet';
  @override
  String get drawBeamFirst => 'Draw the beam first';
  @override
  String get tapOnBeam => 'Tap on the beam itself';
  @override
  String get notInMvp => 'Coming soon: added once point loads are fully tested';
  @override
  String get save => 'Save';
  @override
  String get saved => 'Saved';
  @override
  String get nameProblem => 'Problem name';
  @override
  String get cancel => 'Cancel';
  @override
  String get ok => 'OK';
  @override
  String get delete => 'Delete';
  @override
  String get edit => 'Edit';
  @override
  String get clearAll => 'Clear all';
  @override
  String get fitView => 'Fit view';
  @override
  String get rename => 'Rename';
  @override
  String get flip => 'Flip direction';

  @override
  String get beamProps => 'Beam';
  @override
  String get supportProps => 'Support';
  @override
  String get loadProps => 'Point Load';
  @override
  String get udlProps => 'UDL — uniformly distributed load';
  @override
  String get uvlProps => 'UVL — uniformly varying load';
  @override
  String get momentProps => 'Moment — concentrated couple';
  @override
  String get startX => 'From x';
  @override
  String get endX => 'To x';
  @override
  String get intensity => 'Intensity w';
  @override
  String get intensityStart => 'w at start';
  @override
  String get intensityEnd => 'w at end';
  @override
  String get uniformToggle => 'Uniform (UDL)';
  @override
  String get loadDown => '↓ Down';
  @override
  String get loadUp => '↑ Up';
  @override
  String get ccw => '↺ Counter-clockwise';
  @override
  String get cw => '↻ Clockwise';
  @override
  String get angle => 'θ';
  @override
  String get angleHelp => 'From +x, counter-clockwise: −90° = ↓';
  @override
  String get supportType => 'Type';
  @override
  String get invalidNumber => 'Not a number';
  @override
  String get mustBePositive => 'Must be greater than zero';

  @override
  String get analysis => 'Analysis';
  @override
  String get reactions => 'Reactions';
  @override
  String get keyResults => 'Key results';
  @override
  String get steps => 'Step-by-step solution';
  @override
  String get explanation => 'Explanation';
  @override
  String get explain => 'Explain';
  @override
  String get hideExplain => 'Hide';
  @override
  String get verification => 'Verification';
  @override
  String get allChecksPassed => 'All checks passed ✓';
  @override
  String get someChecksFailed => 'Some checks failed ✗';
  @override
  String get playSteps => 'Play solution';
  @override
  String get quizMe => 'Quiz me';
  @override
  String get copyText => 'Copy solution';
  @override
  String get copied => 'Solution copied';
  @override
  String get tapDiagramHint => 'Touch any point of the diagrams to read values';
  @override
  String get backToEdit => 'Back to editing';
  @override
  String get diagramsWillAppear => 'Appears in a later step';
  @override
  String step(int n, int total) => 'Step $n of $total';

  @override
  String get start => 'Start';
  @override
  String get pause => 'Pause';
  @override
  String get next => 'Next';
  @override
  String get previous => 'Previous';

  @override
  String get level => 'Level';
  @override
  String levelName(PracticeLevel l) => switch (l) {
    PracticeLevel.basic => 'Basic',
    PracticeLevel.intermediate => 'Intermediate',
    PracticeLevel.advanced => 'Advanced',
  };
  @override
  String get newPracticeProblem => 'New problem';
  @override
  String question(int n, int total) => 'Question $n of $total';
  @override
  String get yourAnswer => 'Your answer';
  @override
  String get check => 'Check';
  @override
  String get showSolution => 'Show Solution';
  @override
  String get nextQuestion => 'Next question';
  @override
  String get openFullSolution => 'Open full solution';
  @override
  String get practiceDone => 'You have finished this problem';
  @override
  String score(int correct, int total) =>
      'Right first time: $correct of $total';
  @override
  String get practiceThisProblem => 'Practise this problem';
  @override
  String get enterNumber => 'Type a number';

  @override
  String get noSaved =>
      'No saved problems yet. Save one from the drawing screen.';
  @override
  String savedSummary(String length, int supports, int loads) =>
      'L = $length · $supports supports · $loads loads';
  @override
  String get deleted => 'Deleted';

  @override
  String get examples => 'Mechanics examples';

  @override
  String get settings => 'Settings';
  @override
  String get language => 'Language';
  @override
  String get units => 'Units';
  @override
  String get force => 'Force';
  @override
  String get lengthUnit => 'Length';
  @override
  String get momentUnit => 'Moment';
  @override
  String get signConvention => 'Sign convention';
  @override
  String get signConventionHelp =>
      'Changes how the equilibrium equations are written; the reactions themselves never change.';
  @override
  String get positiveY => 'Positive vertical direction';
  @override
  String get positiveX => 'Positive horizontal direction';
  @override
  String get positiveMoment => 'Positive moment';
  @override
  String get beamConventionTitle => 'Diagram signs (fixed)';
  @override
  String get beamConvention =>
      'V positive: upward forces left of the cut.\nM positive: sagging ∪ (bottom fibres in tension).\nN positive: tension.';
  @override
  String get theme => 'Theme';
  @override
  String get themeSystem => 'System';
  @override
  String get themeLight => 'Light';
  @override
  String get themeDark => 'Dark';
  @override
  String get orientation => 'Screen orientation';
  @override
  String get orientationAuto => 'Auto';
  @override
  String get orientationLandscape => 'Landscape';
  @override
  String get orientationPortrait => 'Portrait';
  @override
  String get orientationHelp =>
      'Landscape keeps the app sideways even when the phone\'s rotation is locked. Auto follows the phone.';
  @override
  String get about => 'About';
  @override
  String get aboutText =>
      'MechSim 2D — first version (MVP): beam, pin, roller and fixed supports, point loads, reactions, FBD, SFD and BMD with step-by-step explanations and practice. '
      'The calculation engine is separate from the interface and checks every solution itself.';

  @override
  String get somTitle => 'Strength of Materials';
  @override
  String get somIntro =>
      'This section comes once the beam section is fully tested. Planned:';
  @override
  List<(String, String)> get somPlanned => const [
    ('Tension', 'σ = F/A, with the direction of the force'),
    ('Compression', 'σ = −F/A'),
    ('Shear Stress', 'τ = V/A, normal force versus shear force'),
    (
      'Bending Stress',
      'σ = My/I with the neutral axis, tension and compression zones',
    ),
    ('Torsion', 'τ = Tr/J on a circular shaft'),
  ];
}
