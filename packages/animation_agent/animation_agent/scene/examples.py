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
