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

# A whole video's program (plan/snapshot-led-beats-plan.md): every snapshot names the part of the video it belongs
# to, and each gets its own line. A raw string here, so the TeX's backslashes reach the program as written.
GEOMETRIC = r'''
a = axes('a', x=(0, 5), y=(0, 2.4), title='partial sums')
f = formula('f')
f.add(r'S = 1 + \frac{1}{2} + \frac{1}{4} + \cdots')
snap('the endless sum S = 1 + 1/2 + 1/4 + ...', name='sum', part='prepare')
sums = []
s = Fraction(0)
for k in range(4):
    s += Fraction(1, 2 ** k)
    sums.append(s)
names = ['S1', 'S2', 'S3', 'S4']
a.bars('s', [float(x) for x in sums[:2]], labels=names[:2])
snap('the first two partial sums, 1 and 1.5', name='first', part='prepare')
a.line('two', (0, 2), (5, 2), style='grey', label='2')
snap('a line at height 2: where the sums are heading', name='goal', part='initiate')
a.bars('s', [float(x) for x in sums], labels=names)
snap('four partial sums: 1, 1.5, 1.75, 1.875', name='four', part='deliver_1')
a.line('wrong', (0.5, 1.2), (4.5, 2.4), style='red', label='forever')
snap('the wrong idea: the sums keep growing, past 2', name='wrong', part='deliver_1', wrong=True)
a.remove('wrong')
f.add(r'2 - S_n = \frac{1}{2^{n-1}}')
snap('each gap to 2 is half the one before: 1, 1/2, 1/4, 1/8', name='gap', part='deliver_1')
a.mark('s', 'found')
snap('so every partial sum stays under 2', name='under', part='deliver_1')
f.set(0, r'S = 1 + \frac{1}{2} S')
snap('the trick: S is 1 plus half of S itself', name='trick', part='deliver_2')
f.set(1, r'S - \frac{1}{2} S = 1')
snap('take half of S from both sides: S - S/2 = 1', name='half', part='deliver_2')
f.add('S = ' + str(1 / (1 - Fraction(1, 2))))
f.box(2)
snap('so S = 2, the line the bars approach', name='total', part='deliver_2')
a.mark('two', 'found')
snap('an endless sum with a finite value: 2', name='idea', part='end')
'''

DIAGRAM_PROGRAMS = {"lcs": LCS, "matmul": MATMUL, "process": PROCESS_STATES, "web": WEB_REQUEST, "dfa": DFA, "rr": ROUND_ROBIN, "tcp": TCP_HANDSHAKE, "adder": FULL_ADDER, "linked": LINKED_LIST, "eigen": EIGENVECTOR, "polar": POLAR, "geometric": GEOMETRIC}


# ---- coverage (plan/visual-coverage-plan.md): the views and calls added for the rest of CS and Math

MATCH = '''
text = 'abababacaba'
pat = 'ababaca'
t = tape('t', text, title='naive matching', index=True)
t.row('p', pat, at=0, label='P')
snap('the pattern starts under the text', name='start', part='prepare')
for s in range(len(text) - len(pat) + 1):
    t.unmark(); t.row('p', pat, at=s, label='P')
    j = 0
    while j < len(pat) and text[s + j] == pat[j]:
        t.mark(s + j, 'found'); t.mark_row('p', j, 'found'); j += 1
    if j == len(pat):
        snap('a match at shift ' + str(s), name='hit', part='deliver_2')
        break
    t.mark(s + j, 'red'); t.mark_row('p', j, 'red')
    snap('shift ' + str(s) + ': ' + str(j) + ' match, then a mismatch', name='s' + str(s), part='deliver_1')
'''

FLOAT32 = '''
x = -6.25
sign = '1' if x < 0 else '0'
m = abs(x); e = 0
while m >= 2:
    m /= 2; e += 1
frac = ''
f = m - 1
for k in range(23):
    f *= 2
    frac += '1' if f >= 1 else '0'
    f -= int(f)
exp = format(e + 127, '08b')
bits = sign + exp + frac
t = tape('t', bits, title='-6.25 as float32', group=4)
snap('32 bits', name='bits', part='prepare')
t.field('s', 0, 1, 'sign', 'red')
snap('the sign bit is 1: negative', name='sign', part='deliver_1')
t.field('e', 1, 9, 'exponent', 'compare')
snap('exponent ' + exp + ' = ' + str(e + 127) + ', so 2 to the ' + str(e), name='exp', part='deliver_1')
t.field('f', 9, 32, 'fraction', 'visited')
snap('fraction: 1.5625 = 1.1001 in binary', name='frac', part='deliver_2')
'''

BSEARCH_CODE = '''
a = [2, 5, 8, 12, 16, 23, 38, 56]
c = code('c', ['def find(a, x):', '  l, h = 0, n-1', '  while l <= h:', '    m = (l+h)//2', '    if a[m] == x:', '      return m', '    if a[m] < x:', '      l = m + 1', '    else:', '      h = m - 1', '  return -1'])
x = 23
lo, hi = 0, len(a) - 1
c.line(1); c.watch('l', lo); c.watch('h', hi)
snap('l and h start at the two ends', name='start', part='prepare')
k = 0
while lo <= hi:
    mid = (lo + hi) // 2
    c.line(3); c.watch('m', mid); c.watch('a[m]', a[mid])
    snap('m = ' + str(mid) + ', a[m] = ' + str(a[mid]), name='mid' + str(k), part='deliver_1')
    if a[mid] == x:
        c.line(5); c.mark(5, 'found')
        snap('found ' + str(x) + ' at ' + str(mid), name='found', part='deliver_2')
        break
    if a[mid] < x:
        lo = mid + 1; c.line(7)
    else:
        hi = mid - 1; c.line(9)
    c.watch('l', lo); c.watch('h', hi)
    snap('now l = ' + str(lo) + ', h = ' + str(hi), name='move' + str(k), part='deliver_1')
    k += 1
'''

FIB_TREE = '''
t = nodes('t', title='calls of fib(4)')
def call(n, parent, path):
    key = path
    t.add(key, 'f(' + str(n) + ')', 'current')
    if parent is not None: t.link(parent, key)
    if n < 2:
        t.mark(key, 'found'); return n
    r = call(n - 1, key, path + 'L') + call(n - 2, key, path + 'R')
    t.mark(key, 'visited')
    return r
r = call(4, None, 'r')
snap('fib(4) makes ' + str(9) + ' calls; fib(2) is computed twice', name='all', part='deliver_1')
for k in ('rLL', 'rR'):
    t.mark(k, 'red')
snap('the two fib(2) calls repeat the same work', name='dup', part='deliver_2', wrong=False)
'''

BTREE = '''
t = nodes('t', title='B-tree, 3 keys max')
t.add('r', keys=[10, 20, 30])
snap('a full node: 10, 20, 30', name='full', part='prepare')
t.set_keys('r', [10, 20, 30])
t.mark('r', 'red')
snap('inserting 25 would make 4 keys: too many', name='over', part='deliver_1', wrong=True)
t.unmark()
t.set_keys('r', [20])
t.add('a', keys=[10]); t.add('b', keys=[25, 30])
t.link('r', 'a', slot=0); t.link('r', 'b', slot=1)
t.mark('r', 'new')
snap('split: 20 moves up, 10 left, 25 and 30 right', name='split', part='deliver_2')
'''

UML = '''
f = flow('f', title='classes')
f.box('acct', 'Account', fields=['id: int', 'bal: float', 'deposit(x)'])
f.box('sav', 'Savings', fields=['rate', 'interest()'])
f.box('chk', 'Checking', fields=['fee'])
f.arrow('sav', 'acct', kind='inherit'); f.arrow('chk', 'acct', kind='inherit')
snap('Savings and Checking are Accounts', name='isa', part='deliver_1')
f.mark('sav', 'current')
snap('Savings adds a rate and interest()', name='sav', part='deliver_1')
'''

MOD12 = '''
c = nodes('c', layout='circle', directed=True, title='adding 5 mod 12')
for k in range(12):
    c.add(k)
x = 0
c.mark(0, 'current')
snap('start at 0', name='s0', part='prepare')
for step in range(1, 5):
    y = (x + 5) % 12
    c.link(x, y, style='current')
    c.mark(x, 'visited'); c.mark(y, 'current')
    snap(str(x) + ' + 5 = ' + str(y) + ' (mod 12)', name='s' + str(step), part='deliver_1')
    x = y
'''

NEURAL = '''
n = nodes('n', layout='layered', directed=True, title='a 3-4-2 network')
for i in range(3): n.add('x' + str(i), layer=0)
for j in range(4): n.add('h' + str(j), layer=1)
for k in range(2): n.add('y' + str(k), layer=2)
for i in range(3):
    for j in range(4): n.link('x' + str(i), 'h' + str(j))
for j in range(4):
    for k in range(2): n.link('h' + str(j), 'y' + str(k))
snap('inputs, a hidden layer of 4, two outputs', name='net', part='prepare')
for i in range(3): n.restyle_link('x' + str(i), 'h1', 'current')
n.mark('h1', 'current')
snap('h1 sums all three inputs', name='h1', part='deliver_1')
'''

MATCHING = '''
g = nodes('g', layout='bipartite', title='jobs to workers')
for w in ['A', 'B', 'C', 'D']: g.add(w, layer=0)
for j in ['1', '2', '3', '4']: g.add('j' + j, label=j, layer=1)
edges = [('A', 'j1'), ('A', 'j2'), ('B', 'j1'), ('C', 'j2'), ('C', 'j3'), ('D', 'j3'), ('D', 'j4')]
for a, b in edges: g.link(a, b, style='grey')
snap('who can do which job', name='all', part='prepare')
for a, b in [('A', 'j2'), ('B', 'j1'), ('C', 'j3'), ('D', 'j4')]:
    g.restyle_link(a, b, 'found'); g.mark(a, 'found'); g.mark(b, 'found')
snap('a perfect matching: everyone gets a job', name='match', part='deliver_2')
'''

PETERSEN = '''
g = nodes('g', layout='fixed', title='Petersen graph')
for i in range(5):
    a = pi / 2 + 2 * pi * i / 5
    g.add('o' + str(i), str(i), at=(2 * cos(a), 2 * sin(a)))
    g.add('i' + str(i), str(i + 5), at=(0.9 * cos(a), 0.9 * sin(a)))
for i in range(5):
    g.link('o' + str(i), 'o' + str((i + 1) % 5)); g.link('o' + str(i), 'i' + str(i)); g.link('i' + str(i), 'i' + str((i + 2) % 5))
snap('10 vertices, each of degree 3', name='g', part='prepare')
'''

Z_SQUARED = '''
a = axes('a', x=(-1.5, 1.5), y=(-1.5, 1.5), equal=True, title='w = z squared')
sq = (0, 1, 0, 1)
a.grid('g', step=0.25, over=sq, f=lambda x, y: (x, y))
snap('the unit square in the z-plane', name='before', part='prepare')
a.grid('g', step=0.25, over=sq, f=lambda x, y: complex(x, y) ** 2)
snap('after z squared: the square opens into a half-disc', name='after', part='deliver_1')
'''

HEAT_MAP = '''
a = axes('a', x=(-2, 2), y=(-2, 2), equal=True, title='f = x^2 + 2y^2')
F = lambda x, y: x * x + 2 * y * y
a.heat('h', F, n=20)
snap('dark is low, bright is high', name='heat', part='prepare')
for level in (1, 4):
    a.contour('c' + str(level), F, level, style='current', label=str(level))
snap('level curves 1 and 4 on top', name='levels', part='deliver_1')
x, y = 1.8, 1.0
for k in range(5):
    a.point('p' + str(k), x, y, style='red')
    x, y = x - 0.2 * 2 * x, y - 0.2 * 4 * y
snap('gradient descent walks downhill', name='gd', part='deliver_2')
'''

ATTENTION = '''
words = ['I', 'saw', 'a', 'cat']
w = [[70, 10, 10, 10], [20, 60, 10, 10], [10, 50, 30, 10], [10, 20, 40, 30]]
g = grid('g', w, row_names=words, col_names=words, title='attention, %')
g.heat(lo=0, hi=100)
snap('each row sums to 100: who each word attends to', name='w', part='prepare')
g.mark_row(2, 'current')
snap('a looks mostly at cat', name='sat', part='deliver_1')
'''

SPAN = '''
s = space('s', x=(-2, 2), y=(-2, 2), z=(-2, 2), title='span of u and v')
u, v = (1, 0, 1), (0, 1, 1)
s.vector('u', *u, style='current', label='u'); s.vector('v', *v, style='compare', label='v')
snap('two vectors in R3', name='uv', part='prepare')
n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
s.plane('P', n, 0)
snap('their span is a plane through 0', name='plane', part='deliver_1')
s.vector('n', *n, style='red', label='u x v')
snap('u x v is normal to it', name='normal', part='deliver_1')
s.turn(20, 10)
snap('turned: the plane edge-on', name='turned', part='deliver_2')
'''

SADDLE = '''
s = space('s', x=(-1.5, 1.5), y=(-1.5, 1.5), z=(-1.5, 1.5), title='z = x^2 - y^2')
s.surface('f', lambda x, y: x * x - y * y, n=12)
s.point('o', 0, 0, 0, label='saddle', style='red')
snap('a saddle at the origin', name='saddle', part='deliver_1')
s.plane('t', (0, 0, 1), 0, style='visited')
snap('its tangent plane is z = 0', name='tan', part='deliver_2')
'''

TORUS = '''
s = space('s', x=(-3, 3), y=(-3, 3), z=(-1.5, 1.5), title='a torus')
R, r = 2, 0.7
s.param('T', lambda u, v: (R + r * cos(v)) * cos(u), lambda u, v: (R + r * cos(v)) * sin(u), lambda u, v: r * sin(v), u=(0, 2 * pi), v=(0, 2 * pi), n=16)
snap('a torus: a circle swept round a circle', name='t', part='prepare')
s.curve('c', lambda t: (R + r) * cos(t), lambda t: (R + r) * sin(t), lambda t: 0 * t, t=(0, 2 * pi), style='current')
snap('one loop round the hole', name='loop', part='deliver_1')
'''

COUNTER = '''
c = circuit('c', title='2-bit counter')
c.block('f0', 'DFF', ['n0'])
c.block('f1', 'DFF', ['n1'])
c.gate('n0', 'NOT', ['f0'])
c.gate('n1', 'XOR', ['f1', 'f0'])
c.output('q1', 'f1', 'Q1'); c.output('q0', 'f0', 'Q0')
snap('the count is ' + str(c.value('q1')) + str(c.value('q0')), name='c0', part='prepare')
for k in range(1, 4):
    c.tick()
    snap('after tick ' + str(k) + ': ' + str(c.value('q1')) + str(c.value('q0')), name='c' + str(k), part='deliver_1')
'''

MUX = '''
c = circuit('c', title='a 2-to-1 MUX')
c.input('a', 1, 'd0'); c.input('b', 0, 'd1'); c.input('s', 0, 's')
c.block('m', 'MUX', ['a', 'b', 's'])
c.output('y', 'm', 'y')
snap('s = 0 picks d0: y = ' + str(c.value('y')), name='s0', part='deliver_1')
c.set('s', 1)
snap('s = 1 picks d1: y = ' + str(c.value('y')), name='s1', part='deliver_1')
'''

TIMING = '''
tl = timeline('tl', ['clk', 'D', 'Q'], t=(0, 8), step=1, title='a D flip-flop')
clk = [1, 0] * 4
d = [0, 0, 1, 1, 1, 0, 0, 0]
q, cur = [], 0
for k in range(8):
    if k % 2 == 0: cur = d[k]
    q.append(cur)
tl.signal('c', 'clk', clk); tl.signal('d', 'D', d)
snap('the clock and the input D', name='in', part='prepare')
tl.signal('q', 'Q', q, style='current')
snap('Q copies D at each rising edge', name='q', part='deliver_1')
'''

BOXPLOT = '''
a = axes('a', title='two classes')
A = [52, 55, 58, 60, 61, 63, 64, 66, 70, 90]
B = [40, 45, 47, 50, 52, 53, 55, 58, 60]
a.boxplot('A', A, x=1, style='visited', name='A'); a.boxplot('B', B, x=2, style='compare', name='B')
snap('class A: median ' + str(a.boxplot('A', A, x=1, style='visited', name='A')[1]) + '; 90 is an outlier', name='box', part='deliver_1')
'''

STACKED = '''
a = axes('a', title='sales by quarter')
x = [10, 12, 9]; y = [4, 6, 8]
a.bars('x', x, labels=['Q1', 'Q2', 'Q3'], style='visited')
snap('product X', name='x', part='prepare')
a.bars('y', y, labels=['Q1', 'Q2', 'Q3'], style='compare', base=x)
snap('product Y stacked on top', name='y', part='deliver_1')
'''

TCP_FULL = '''
s = sequence('s', ['client', 'server'], title='TCP: open, send, close')
msgs = [('client', 'server', 'SYN seq=100', False), ('server', 'client', 'SYN-ACK 300', True), ('client', 'server', 'ACK 301', False),
        ('client', 'server', 'GET / (40 B)', False), ('server', 'client', 'ACK 141', True), ('server', 'client', '200 OK (1 KB)', True),
        ('client', 'server', 'ACK 1325', False), ('client', 'server', 'FIN', False), ('server', 'client', 'ACK', True), ('server', 'client', 'FIN', True)]
for k, (a, b, label, d) in enumerate(msgs):
    s.message('m' + str(k), a, b, label, style='current', dashed=d)
    if k > 0: s.mark('m' + str(k - 1), None)
    snap(label, name='m' + str(k), part='deliver_1' if k < 5 else 'deliver_2')
'''

LONG_ARRAY = '''
a = cells('a', [2, 4, 7, 9, 13, 15, 18, 21, 24, 29, 33, 36, 40, 45, 51, 56, 60, 64, 71, 77], title='20 sorted keys')
lo, hi, x = 0, 19, 64
a.point('lo', lo); a.point('hi', hi)
snap('search for 64 in 20 keys', name='start', part='prepare')
while lo <= hi:
    mid = (lo + hi) // 2
    a.unmark(); a.mark(mid, 'compare')
    snap('mid ' + str(mid) + ' holds ' + str(a[mid]), name='m' + str(mid), part='deliver_1')
    if a[mid] == x:
        a.mark(mid, 'found'); snap('found', name='found', part='deliver_2'); break
    if a[mid] < x: lo = mid + 1
    else: hi = mid - 1
    a.point('lo', lo); a.point('hi', hi)
'''

BINARY_ADD = '''
a, b = '01101101', '00111011'
t = tape('t', a, title='binary addition', group=4)
t.row('b', b, label='+')
snap('two 8-bit numbers', name='start', part='prepare')
carry = 0
s = ['_'] * 8
cs = ['0'] * 9
for i in range(7, -1, -1):
    total = int(a[i]) + int(b[i]) + carry
    s[i] = str(total % 2); carry = total // 2; cs[i] = str(carry)
    t.row('c', ''.join(cs[:8]), label='c')
    t.row('s', ''.join(x if x != '_' else ' ' for x in s), label='=')
    t.unmark(); t.mark(i, 'current')
    if i in (7, 6, 3, 0):
        snap('bit ' + str(7 - i) + ': sum ' + s[i] + ', carry ' + str(carry), name='b' + str(i), part='deliver_1')
'''

COVERAGE_PROGRAMS = {"match": MATCH, "float32": FLOAT32, "bsearch_code": BSEARCH_CODE, "fib_tree": FIB_TREE, "btree": BTREE, "uml": UML, "mod12": MOD12, "neural": NEURAL, "matching": MATCHING, "petersen": PETERSEN, "z_squared": Z_SQUARED, "heat_map": HEAT_MAP, "attention": ATTENTION, "span": SPAN, "saddle": SADDLE, "torus": TORUS, "counter": COUNTER, "mux": MUX, "timing": TIMING, "boxplot": BOXPLOT, "stacked": STACKED, "tcp_full": TCP_FULL, "long_array": LONG_ARRAY, "binary_add": BINARY_ADD}
