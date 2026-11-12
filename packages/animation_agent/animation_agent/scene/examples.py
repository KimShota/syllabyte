"""Picture programs written by hand for topics no template draws (plan/scene-grammar-plan.md, P0). They test that
the grammar can say them, and later serve as the writer's worked examples."""

UNION_FIND = '''
n = 8
id = cells('id', list(range(n)), title='id[]')
f = nodes('f', range(n), layout='tree')
c = code('code', ['i = root(p)', 'j = root(q)', 'id[i] = j'])

def root(p):
    while p != id[p]:
        f.mark(p, 'visited')
        p = id[p]
    f.mark(p, 'current')
    return p

def union(p, q):
    f.unmark(); id.unmark()
    c.line(None); id.mark(p, 'compare'); id.mark(q, 'compare')
    snap(f'union({p}, {q})')
    c.line(0); i = root(p)
    snap(f'the root of {p} is {i}')
    f.unmark(); c.line(1); j = root(q)
    snap(f'the root of {q} is {j}')
    if i != j:
        c.line(2); id.unmark(); id[i] = j; id.mark(i, 'current'); f.link(j, i)
        f.unmark(); f.mark(i, 'new')
        snap(f'{i} goes under {j}: id[{i}] = {j}')

snap('every item starts as its own root')
union(4, 3)
union(3, 7)
union(6, 5)
union(4, 6)
f.unmark(); id.unmark(); c.line(None)
snap('one tree: 4, 3, 7, 6 and 5 are connected')
'''

LLRB = '''
class Node:
    def __init__(self, key):
        self.key, self.left, self.right, self.red = key, None, None, True

t = nodes('t', layout='binary', title='red-black BST')
root = None

def red(h):
    return h is not None and h.red

def rotate_left(h):
    x = h.right; h.right = x.left; x.left = h
    x.red = h.red; h.red = True
    fixes.append(f'rotate {h.key} left')
    return x

def rotate_right(h):
    x = h.left; h.left = x.right; x.right = h
    x.red = h.red; h.red = True
    fixes.append(f'rotate {h.key} right')
    return x

def flip(h):
    h.red = True; h.left.red = False; h.right.red = False
    fixes.append(f'flip colours at {h.key}')

def put(h, key):
    if h is None:
        return Node(key)
    if key < h.key:
        h.left = put(h.left, key)
    elif key > h.key:
        h.right = put(h.right, key)
    if red(h.right) and not red(h.left):
        h = rotate_left(h)
    if red(h.left) and red(h.left.left):
        h = rotate_right(h)
    if red(h.left) and red(h.right):
        flip(h)
    return h

def show(h, parent=None, slot=None):
    if h is None:
        return
    if parent is None:
        p = t.parent(h.key)
        if p is not None:
            t.unlink(p, h.key)
    else:
        t.link(parent.key, h.key, style='red' if h.red else None, slot=slot)
    show(h.left, h, 0)
    show(h.right, h, 1)

def plain_insert(h, key):
    # the BST insert alone, before any fix, to show where the new red link lands
    if h is None:
        return Node(key)
    if key < h.key:
        h.left = plain_insert(h.left, key)
    else:
        h.right = plain_insert(h.right, key)
    return h

def copy(h):
    if h is None:
        return None
    c = Node(h.key); c.red = h.red; c.left = copy(h.left); c.right = copy(h.right)
    return c

for key in 'SEARCHXM':
    fixes = []
    before = plain_insert(copy(root), key)
    t.add(key); t.unmark(); show(before); t.mark(key, 'new')
    snap(f'insert {key}: a new red link')
    root = put(root, key); root.red = False
    if fixes:
        t.unmark(); show(root); t.mark(key, 'new')
        snap(', then '.join(fixes))
t.unmark()
snap('balanced: every path has the same number of black links')
'''

WATER_JUGS = '''
a = container('a', 3, title='3 gallons')
b = container('b', 5, title='5 gallons')
snap('measure exactly 4 gallons with a 3 and a 5')

def fill(j):
    j.level = j.capacity
    snap(f'fill the {j.title}')

def empty(j):
    j.level = 0
    snap(f'empty the {j.title}')

def pour(x, y):
    moved = x.pour_into(y)
    snap(f'pour {moved} from the {x.title} into the {y.title}')

fill(b); pour(b, a); empty(a); pour(b, a); fill(b); pour(b, a)
b.style = 'found'
snap('4 gallons left in the 5-gallon jug')
'''

PROGRAMS = {"union_find": UNION_FIND, "llrb": LLRB, "water_jugs": WATER_JUGS}

# ---- math (P2) ---------------------------------------------------------------------------------------------

RIEMANN = '''
f = lambda x: x * x / 2 + 1
a = axes('a', x=(0, 4), title='area under f')
a.plot('f', f, label='f(x)')
exact = integral(f, 0, 4)
snap('f(x) = x^2/2 + 1, from 0 to 4', name='curve')
for n in (2, 4, 8, 16):
    total = a.riemann('rects', f, 0, 4, n, rule='left')
    snap(f'{n} left rectangles: {total:.2f} in all', name='n' + str(n))
a.remove('rects')
a.area('exact', f, 0, 4, label=f'{exact:.2f}')
snap(f'the exact area is {exact:.2f}: the sums climb toward it', name='exact')
'''

TANGENT = '''
f = lambda x: x * x
a = axes('a', x=(-1, 3), title='slope of x^2 at 1')
a.plot('f', f, label='x^2')
a.point('p', 1, f(1), label='P')
snap('the point P = (1, 1) on y = x^2', name='p')
for k, h in enumerate((1.5, 0.8, 0.3)):
    m = (f(1 + h) - f(1)) / h
    a.point('q', 1 + h, f(1 + h), label='Q', style='compare')
    a.line('sec', (0, f(1) - m), (1 + h + 0.3, f(1) + m * (h + 0.3)), style='compare')
    snap(f'Q is {h} to the right: the secant PQ has slope {m:.2f}', name='h' + str(k))
a.remove('q')
a.remove('sec')
m = a.tangent('tan', f, 1, half=1.0, label='slope ' + str(round(m)))
snap(f'as Q reaches P the slope settles at {m:.0f}: the tangent', name='tangent')
'''

LEVEL_CURVES = '''
F = lambda x, y: x * x + 2 * y * y
a = axes('a', x=(-4, 4), y=(-3, 3), equal=True, title='levels of F')
for c in (1, 4, 9):
    a.contour('c' + str(c), F, c, label=str(c))
    snap(f'every point where x^2 + 2y^2 = {c}', name='level' + str(c))
a.field('grad', lambda x, y: (2 * x, 4 * y), n=6)
snap('the gradient (2x, 4y) crosses every level curve at a right angle', name='grad')
'''

VENN3 = '''
v = venn('v', {'A': {1, 2, 3, 4}, 'B': {3, 4, 5, 6}, 'C': {4, 6, 7}}, universe={8})
v.show_elements()
snap('A, B and C; 8 is in none of them', name='sets')
v.shade('A&B')
snap('A and B share ' + str(sorted(v.region('A&B'))), name='and')
v.unshade()
v.shade('(A|B)-C')
snap('in A or B but not C: ' + str(sorted(v.region('(A|B)-C'))), name='minus')
v.unshade()
v.shade('~(A|B|C)', 'grey')
snap('outside all three: ' + str(sorted(v.region('~(A|B|C)'))), name='none')
'''

TRIANGLE = '''
g = geometry('g', title='a triangle')
g.point('A', 0, 0)
g.point('B', 4, 0)
g.point('C', 1.3, 2.6)
g.polygon('t', ['A', 'B', 'C'])
snap('triangle ABC', name='tri')
a = g.angle('a', 'B', 'A', 'C')
g.angle('a', 'B', 'A', 'C', label=f'{a:.0f}°')
snap(f'the angle at A is {a:.0f} degrees', name='a')
b = g.angle('b', 'C', 'B', 'A', style='compare')
g.angle('b', 'C', 'B', 'A', label=f'{b:.0f}°', style='compare')
snap(f'the angle at B is {b:.0f} degrees', name='b')
c = g.angle('c', 'A', 'C', 'B', style='visited')
g.angle('c', 'A', 'C', 'B', label=f'{c:.0f}°', style='visited')
snap(f'{a:.0f} + {b:.0f} + {c:.0f} = {a + b + c:.0f} degrees', name='sum')
'''

PROBABILITY_TREE = '''
red, blue = 3, 2
t = nodes('t', ['S'], title='two draws')
first = {'R': Fraction(red, red + blue), 'B': Fraction(blue, red + blue)}
for c, p in first.items():
    t.add(c)
    t.link('S', c, label=str(p))
snap('3 red and 2 blue balls: the first draw is red 3/5 of the time', name='first')
both = {}
for c, p in first.items():
    r, b = red - (c == 'R'), blue - (c == 'B')
    for d, q in (('R', Fraction(r, r + b)), ('B', Fraction(b, r + b))):
        t.add(c + d)
        t.link(c, c + d, label=str(q))
        both[c + d] = p * q
snap('the second draw: one ball fewer in the bag', name='second')
t.mark('R', 'found')
t.mark('RR', 'found')
rr = both['RR']
snap(f'two reds: 3/5 times 2/4 = {rr}', name='rr')
'''

MATH_PROGRAMS = {"riemann": RIEMANN, "tangent": TANGENT, "level_curves": LEVEL_CURVES, "venn3": VENN3,
                 "triangle": TRIANGLE, "probability_tree": PROBABILITY_TREE}
