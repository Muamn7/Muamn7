"""Five role stands (Roamer, Jungler, Mid, Exp, Gold) on the yellow stand design. One shared base."""
import stand1
from logos import ROLES
from manifold3d import Manifold

REST = stand1.REST
F = stand1.F

# group layout for the combined render: back row of 3, front row of 2 (like the logo sheet)
LAYOUT = {
    'Roamer': (-175.0, 95.0), 'Jungler': (0.0, 95.0), 'Mid_Laner': (175.0, 95.0),
    'Exp_Laner': (-88.0, -95.0), 'Gold_Laner': (88.0, -95.0),
}


def build():
    bb, by = stand1.base()
    M, _ = stand1.plate_matrix()
    parts = {'Base': {'black': bb, 'accent': by, 'accent2': Manifold(), 'assembly': None, 'show': False}}
    for role in ROLES:
        pb, py, pw = stand1.plate(role)
        parts['Plate_' + role] = {'black': pb, 'accent': py, 'accent2': pw, 'assembly': M, 'show': False}
    return {'name': 'Role_Stands', 'parts': parts, 'accent_name': 'yellow', 'accent2_name': 'white'}


if __name__ == '__main__':
    d = build()
    for k, v in d['parts'].items():
        print(k, ['%s %.2f cm3' % (c, v[c].volume() / 1000) for c in ('black', 'accent', 'accent2')])
