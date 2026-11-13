import re
TOK = re.compile(r'"[^"]*"|[{}=]|[^\s{}="]+')

class Block:
    __slots__ = ("items", "vals")
    def __init__(self):
        self.items = []   # (key, value) pairs, order and repeats preserved
        self.vals = []    # bare values, e.g. { 1 2 3 }
    def get(self, key, default=None):
        for k, v in self.items:
            if k == key:
                return v
        return default
    def getall(self, key):
        return [v for k, v in self.items if k == key]
    def keys(self):
        return [k for k, _ in self.items]

def _scalar(t):
    if t[0] == '"':
        return t[1:-1]
    try:
        return int(t)
    except ValueError:
        try:
            return float(t)
        except ValueError:
            return t

def parse(text):
    it = TOK.finditer(text)
    nxt = lambda: (m.group(0) if (m := next(it, None)) else None)
    root = Block()
    stack = [(root, None)]          # (block, key it will be stored under)
    t = nxt()
    while t is not None:
        if t == '}':
            if len(stack) == 1:      # stray closing brace (this save has one at EOF)
                t = nxt(); continue
            blk, key = stack.pop()
            parent = stack[-1][0]
            if key is None: parent.vals.append(blk)
            else: parent.items.append((key, blk))
            t = nxt()
        elif t == '{':
            stack.append((Block(), None))
            t = nxt()
        else:
            n = nxt()
            if n == '=':
                v = nxt()
                if v == '{':
                    stack.append((Block(), t))
                    t = nxt()
                else:
                    stack[-1][0].items.append((t, _scalar(v)))
                    t = nxt()
            else:
                stack[-1][0].vals.append(_scalar(t))
                t = n
    return root
