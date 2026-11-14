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

BAR_CHART = '''
pop = [30, 2450, 80, 50, 720]
names = ['Arch', 'Engin', 'HSS', 'Mgmt', 'Sci']
a = axes('a', title='majors by school', xlabel='', ylabel='students')
a.bars('pop', pop, labels=names, values=True)
snap('students per school: Engineering dwarfs Architecture', name='pop')
b = axes('b', title='stratified sample', xlabel='', ylabel='picked')
picked = [max(1, round(v * 100 / sum(pop))) for v in pop]
b.bars('s', picked, labels=names, values=True, style='found')
snap('100 picked in proportion, at least one per school: ' + ', '.join(str(v) for v in picked), name='sample')
'''

DIVISION = '''
n = numberline('n', -21, 21, step=7, title='multiples of 7')
for k in range(-3, 4):
    n.point('m' + str(k), 7 * k, style='grey')
snap('the multiples of 7', name='mult')
n.point('x', 17, label='17')
n.jump('j', 14, 17, label='+3')
snap('17 = 2 x 7 + 3: the remainder is 3', name='div')
n.interval('r', 14, 21, closed=(True, False), label='[14,21)')
snap('every number in [14, 21) has quotient 2', name='range')
'''

VOLUME = '''
f = lambda x, y: 1 - x * x - y * y / 2 + 1
s = surface('s', x=(0, 1), y=(0, 1), title='volume under f')
s.plot('f', f, n=10)
snap('the surface z = 2 - x^2 - y^2/2 over the unit square', name='surface')
for n in (2, 4):
    v = s.columns('cols', f, n)
    snap(f'{n * n} columns: volume about {v:.3f}', name='n' + str(n))
s.remove('f')
v = s.columns('cols', f, 8)
snap(f'64 columns: {v:.3f}; the exact volume is {2 - 1/3 - 1/6:.3f}', name='n8')
'''

MATH_PROGRAMS = {"bar_chart": BAR_CHART, "division": DIVISION, "volume": VOLUME, "riemann": RIEMANN, "tangent": TANGENT, "level_curves": LEVEL_CURVES, "venn3": VENN3,
                 "triangle": TRIANGLE, "probability_tree": PROBABILITY_TREE}


# ---- diagrams (P5): tables, boxes and arrows, timelines, messages, circuits, memory; vectors and maps ----

LCS = '''
a, b = 'ABCB', 'BDCB'
t = grid('t', [[0] * (len(b) + 1) for r in range(len(a) + 1)], row_names=[''] + list(a), col_names=[''] + list(b),
         title='LCS table')
for i in range(1, len(a) + 1):
    for j in range(1, len(b) + 1):
        t[i][j] = None
snap('row 0 and column 0 are 0', name='start')
for i in range(1, len(a) + 1):
    for j in range(1, len(b) + 1):
        t.unmark()
        if a[i - 1] == b[j - 1]:
            t[i][j] = t[i - 1][j - 1] + 1
            t.mark(i - 1, j - 1, 'compare')
            why = f'{a[i - 1]} = {b[j - 1]}: diagonal + 1 = {t[i][j]}'
        else:
            t[i][j] = max(t[i - 1][j], t[i][j - 1])
            t.mark(i - 1, j, 'compare'); t.mark(i, j - 1, 'compare')
            why = f'{a[i - 1]} != {b[j - 1]}: max(up, left) = {t[i][j]}'
        t.mark(i, j, 'current')
        if j == len(b) or a[i - 1] == b[j - 1]:
            snap(why, name=f'c{i}{j}')
t.unmark(); t.mark(len(a), len(b), 'found')
snap(f'the LCS has length {t[len(a)][len(b)]}', name='done')
'''

MATMUL = '''
A = grid('A', [[1, 2], [3, 4]], matrix=True, title='A')
B = grid('B', [[5, 6], [7, 8]], matrix=True, title='B')
C = grid('C', [[None, None], [None, None]], matrix=True, title='C = AB')
snap('A times B', name='start')
for i in range(2):
    for j in range(2):
        A.unmark(); B.unmark(); C.unmark()
        A.mark_row(i, 'compare'); B.mark_col(j, 'compare')
        C[i][j] = sum(A[i][k] * B[k][j] for k in range(2))
        C.mark(i, j, 'current')
        snap(f'row {i + 1} of A times column {j + 1} of B: {A[i][0]}*{B[0][j]} + {A[i][1]}*{B[1][j]} = {C[i][j]}', name=f'c{i}{j}')
A.unmark(); B.unmark(); C.unmark()
snap('C = AB', name='done')
'''

PROCESS_STATES = '''
f = flow('f', title='process states')
for k in ('new', 'ready', 'running', 'waiting', 'done'):
    f.box(k, k, shape='round')
f.arrow('new', 'ready', 'admit')
f.arrow('ready', 'running', 'dispatch')
f.arrow('running', 'ready', 'timeout')
f.arrow('running', 'waiting', 'I/O')
f.arrow('waiting', 'ready', 'I/O done')
f.arrow('running', 'done', 'exit')
snap('five states a process moves through', name='all')
path = [('new', 'ready'), ('ready', 'running'), ('running', 'waiting'), ('waiting', 'ready'), ('ready', 'running'), ('running', 'done')]
for n, (a, b) in enumerate(path):
    f.unmark(); f.mark(b, 'current'); f.restyle(a, b, 'current')
    snap(f'{a} -> {b}', name=f's{n}')
'''

WEB_REQUEST = '''
f = flow('f', title='loading a page')
f.box('u', 'you', shape='person')
f.box('b', 'browser', shape='monitor')
f.box('d', 'DNS')
f.box('s', 'server', shape='server')
f.box('db', 'database', shape='cylinder')
f.arrow('u', 'b', 'URL')
f.arrow('b', 'd', 'name?')
f.arrow('b', 's', 'GET')
f.arrow('s', 'db', 'query')
snap('the parts', name='all')
for k in ('u', 'b', 'd', 's', 'db'):
    f.unmark(); f.mark(k, 'current')
    snap(k, name=k)
'''

DFA = '''
f = flow('f', direction='right', title='multiples of 3')
for k in range(3):
    f.box(f'q{k}', f'q{k}', shape='double' if k == 0 else 'circle')
for k in range(3):
    for bit in (0, 1):
        f.arrow(f'q{k}', f'q{(2 * k + bit) % 3}', str(bit))
snap('remainder mod 3 after each bit', name='all')
state = 0
for n, bit in enumerate('110'):
    nxt = (2 * state + int(bit)) % 3
    f.unmark(); f.mark(f'q{nxt}', 'current'); f.restyle(f'q{state}', f'q{nxt}', 'current')
    snap(f'read {bit}: q{state} -> q{nxt}', name=f'b{n}')
    state = nxt
f.unmark(); f.mark(f'q{state}', 'found' if state == 0 else 'red')
snap('110 is 6: accepted' if state == 0 else 'rejected', name='end')
'''

ROUND_ROBIN = '''
burst = {'P1': 5, 'P2': 3, 'P3': 1}
q = 2
tl = timeline('tl', list(burst), title='round robin, q = 2')
left = dict(burst)
queue = list(burst)
t = 0
n = 0
while queue:
    p = queue.pop(0)
    run = min(q, left[p])
    tl.block(f'b{n}', p, t, t + run, style='current')
    for k in range(n):
        tl.mark(f'b{k}', 'visited')
    t += run
    left[p] -= run
    if left[p]:
        queue.append(p)
        snap(f'{p} runs {run} until t = {t}; {left[p]} left', name=f'r{n}')
    else:
        tl.marker(f'm{p}', t, label=f't={t}')
        snap(f'{p} finishes at t = {t}', name=f'r{n}')
    n += 1
'''

TCP_HANDSHAKE = '''
s = sequence('s', ['client', 'server'], title='TCP handshake')
snap('two hosts', name='start')
s.message('syn', 'client', 'server', 'SYN seq=100')
snap('SYN', name='syn')
s.message('synack', 'server', 'client', 'SYN-ACK 300', dashed=True)
snap('SYN-ACK', name='synack')
s.message('ack', 'client', 'server', 'ACK 301')
snap('ACK: connected', name='ack')
s.message('get', 'client', 'server', 'GET /')
s.message('ok', 'server', 'client', '200 OK', dashed=True)
snap('data flows', name='data')
'''

FULL_ADDER = '''
c = circuit('c', title='full adder')
c.input('A'); c.input('B'); c.input('Ci', label='Cin')
c.gate('x1', 'XOR', ['A', 'B'])
c.gate('a1', 'AND', ['A', 'B'])
c.gate('s', 'XOR', ['x1', 'Ci'])
c.gate('a2', 'AND', ['x1', 'Ci'])
c.gate('co', 'OR', ['a1', 'a2'])
c.output('S', 's')
c.output('Co', 'co', label='Cout')
for bits in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 1)):
    c.set('A', bits[0]); c.set('B', bits[1]); c.set('Ci', bits[2])
    hi, lo = c.value('Co'), c.value('S')
    snap(f'{bits[0]} + {bits[1]} + {bits[2]} = {hi}{lo} in binary', name='r' + ''.join(str(b) for b in bits))
'''

LINKED_LIST = '''
m = memory('m', title='a linked list')
m.frame('main', 'main()')
for k, v in enumerate((5, 8)):
    m.obj(f'n{k}', 'Node')
    m.set(f'n{k}', 'val', v)
    m.set(f'n{k}', 'next', None)
m.set('n0', 'next', m.ref('n1'))
m.set('main', 'head', m.ref('n0'))
snap('head points to the first node', name='list')
m.frame('f', 'push(1)')
m.obj('n2', 'Node')
m.set('n2', 'val', 1)
m.set('n2', 'next', m.ref('n0'))
m.set('f', 'x', m.ref('n2'))
snap('push makes a node pointing at the old head', name='new')
m.set('main', 'head', m.ref('n2'))
m.remove('f')
snap('head now points to it', name='done')
'''

EIGENVECTOR = '''
M = [[2, 1], [1, 2]]
a = axes('a', x=(-4, 4), y=(-4, 4), equal=True, title='A = [[2,1],[1,2]]')
a.grid('g')
a.vector('v', 1, 1, style='found', label='v')
a.vector('w', 1, 0, style='compare', label='w')
snap('the plane before', name='before')
a.grid('g', matrix=M)
a.vector('v', M[0][0] + M[0][1], M[1][0] + M[1][1], style='found', label='Av')
a.vector('w', M[0][0], M[1][0], style='compare', label='Aw')
snap('Av = 3v stays on its line; Aw turns', name='after')
'''

POLAR = '''
a = axes('a', x=(-1.5, 1.5), y=(-1.5, 1.5), equal=True)
a.polar('r', lambda t: cos(2 * t))
a.curve('c', lambda t: cos(t), lambda t: sin(t), t=(0, 2 * pi), style='grey')
a.polygon('p', [(0, 0), (1, 0), (0.5, 0.8)], style='visited', label='T')
snap('a rose, a circle and a triangle', name='all')
'''

DIAGRAM_PROGRAMS = {"lcs": LCS, "matmul": MATMUL, "process": PROCESS_STATES, "web": WEB_REQUEST, "dfa": DFA, "rr": ROUND_ROBIN, "tcp": TCP_HANDSHAKE, "adder": FULL_ADDER, "linked": LINKED_LIST, "eigen": EIGENVECTOR, "polar": POLAR}
