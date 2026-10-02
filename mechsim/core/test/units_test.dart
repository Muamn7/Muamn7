import 'package:mechsim_core/mechsim_core.dart';
import 'package:test/test.dart';

void main() {
  group('Units.convert', () {
    test('force', () {
      expect(Units.convert(20, Units.kilonewton, Units.newton), 20000);
      expect(Units.convert(2500, Units.newton, Units.kilonewton), 2.5);
    });

    test('length', () {
      expect(Units.convert(6, Units.metre, Units.millimetre), closeTo(6000, 1e-9));
      expect(Units.convert(250, Units.centimetre, Units.metre), closeTo(2.5, 1e-12));
      expect(Units.convert(35, Units.millimetre, Units.centimetre), closeTo(3.5, 1e-12));
    });

    test('moment', () {
      expect(Units.convert(30, Units.kilonewtonMetre, Units.newtonMetre), 30000);
      expect(Units.convert(30, Units.kilonewtonMetre, Units.newtonMillimetre),
          closeTo(3e7, 1e-3));
      expect(Units.convert(1, Units.newtonMetre, Units.newtonMillimetre),
          closeTo(1000, 1e-9));
    });

    test('1 MPa is 1 N/mm²', () {
      final pa = 1 / Units.squareMillimetre.toSi; // 1 N over 1 mm², in Pa
      expect(Units.convert(pa, Units.pascal, Units.megapascal), closeTo(1, 1e-12));
    });

    test('refuses to mix dimensions', () {
      expect(() => Units.convert(1, Units.newton, Units.metre), throwsArgumentError);
    });

    test('round trip through every unit of a dimension', () {
      for (final d in Dimension.values) {
        for (final a in Units.of(d)) {
          for (final b in Units.of(d)) {
            final there = Units.convert(123.456, a, b);
            expect(Units.convert(there, b, a), closeTo(123.456, 1e-9));
          }
        }
      }
    });
  });

  group('UnitSystem', () {
    test('display conversion', () {
      const u = UnitSystem.nMm;
      expect(u.toDisplay(20 * 1000, Dimension.force), 20000);
      expect(u.toDisplay(3, Dimension.length), closeTo(3000, 1e-9));
      expect(u.toDisplay(30000, Dimension.moment), closeTo(3e7, 1e-3));
      expect(u.fromDisplay(6000, Dimension.length), closeTo(6, 1e-12));
    });

    test('JSON round trip', () {
      final u = UnitSystem.knM.copyWith(length: Units.centimetre);
      expect(UnitSystem.fromJson(u.toJson()), u);
    });
  });

  group('Num', () {
    test('compact trims zeros and never prints minus zero', () {
      expect(Num.compact(10), '10');
      expect(Num.compact(2.5), '2.5');
      expect(Num.compact(1 / 3), '0.333');
      expect(Num.compact(-1e-12), '0');
      expect(Num.compact(9.9999999999), '10');
      expect(Num.compact(-10), '${minus}10');
    });

    test('fixed and signed', () {
      expect(Num.fixed(-10), '${minus}10.00');
      expect(Num.fixed(-0.001), '0.00');
      expect(Num.signed(10), '+10.00');
      expect(Num.signed(0), '0.00');
    });

    test('parses Arabic-Indic digits, Arabic decimal separator and minus', () {
      expect(Num.parse('٢٠'), 20);
      expect(Num.parse('٢٫٥'), 2.5);
      expect(Num.parse('−10'), -10);
      expect(Num.parse('-10,5'), -10.5);
      expect(Num.parse('۱۲'), 12);
      expect(Num.parse(''), isNull);
      expect(Num.parse('abc'), isNull);
    });
  });
}
