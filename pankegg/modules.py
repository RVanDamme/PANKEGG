"""KEGG module completeness from the KOs of a genome (standard library only).

A KEGG module definition is a logical expression over KOs:

* a space separates consecutive steps (all needed); outside parentheses a
  space always starts a new step;
* a comma separates alternatives (one is enough);
* ``+`` joins the subunits of a complex (all needed);
* ``-`` marks an optional subunit (ignored);
* ``--`` is a step without a KO (ignored: it can never be observed);
* ``M00001`` refers to another module.

A KO scores 1 when present. A sequence or complex scores the mean of its
parts and a set of alternatives the best of its parts, so every expression
has a score between 0 and 1. The completeness of a module is the mean score
of its top-level steps, as a percentage, so a step that is only partly
present counts partly. A module is complete at 100%, when every step has one
fully present alternative.
"""

import re

_TOKEN = re.compile(r"K\d{5}|M\d{5}|--|[(),+\- ]")


class DefinitionError(ValueError):
    pass


def tokenize(definition):
    tokens, pos = [], 0
    definition = definition.strip()
    while pos < len(definition):
        m = _TOKEN.match(definition, pos)
        if not m:
            raise DefinitionError(f"unexpected text at {pos}: {definition[pos:pos + 12]!r}")
        tokens.append(m.group(0))
        pos = m.end()
    # collapse runs of spaces
    out = []
    for tok in tokens:
        if tok == " " and (not out or out[-1] == " "):
            continue
        out.append(tok)
    while out and out[-1] == " ":
        out.pop()
    return out


class _Parser:
    """alternatives := sequence (',' sequence)* ; sequence := complex (' ' complex)* ;
    complex := unit (('+' | '-') unit)* ; unit := KO | module | '--' | '(' alternatives ')'"""

    def __init__(self, tokens):
        self.tokens, self.i = tokens, 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def alternatives(self):
        options = [self.sequence()]
        while self.peek() == ",":
            self.take()
            options.append(self.sequence())
        options = [o for o in options if o is not None]
        if not options:
            return None
        return options[0] if len(options) == 1 else ("or", options)

    def sequence(self):
        while self.peek() == " ":
            self.take()
        parts = [self.complex()]
        while self.peek() == " ":
            self.take()
            if self.peek() in (None, ",", ")"):
                break
            parts.append(self.complex())
        parts = [p for p in parts if p is not None]
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else ("seq", parts)

    def complex(self):
        parts, optional = [], False
        if self.peek() == "-":          # leading optional unit, e.g. "-K00242"
            self.take()
            optional = True
        while True:
            unit = self.unit()
            if not optional and unit is not None:
                parts.append(unit)
            nxt = self.peek()
            if nxt == "+":
                self.take()
                optional = False
            elif nxt == "-":
                self.take()
                optional = True
            else:
                break
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else ("all", parts)

    def unit(self):
        tok = self.take()
        if tok is None:
            raise DefinitionError("unexpected end of definition")
        if tok == "--":
            return None
        if tok == "(":
            inner = self.alternatives()
            if self.take() != ")":
                raise DefinitionError("missing ')'")
            return inner
        if tok[0] == "K":
            return ("ko", tok)
        if tok[0] == "M":
            return ("module", tok)
        raise DefinitionError(f"unexpected {tok!r}")


def parse(definition):
    """Parse a definition into its top-level steps (a list of expression trees).

    Outside parentheses a space always starts a new step, so ``(A B),(C D) E`` is two steps
    (the first with two alternative routes). Inside parentheses a comma separates alternatives,
    each of which may be a space-separated sequence.
    """
    chunks, current, depth = [], [], 0
    for tok in tokenize(definition):
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
            if depth < 0:
                raise DefinitionError("unexpected ')'")
        if tok == " " and depth == 0:
            if current:
                chunks.append(current)
            current = []
        else:
            current.append(tok)
    if depth:
        raise DefinitionError("missing ')'")
    if current:
        chunks.append(current)
    steps = []
    for chunk in chunks:
        parser = _Parser(chunk)
        tree = parser.alternatives()
        if parser.peek() is not None:
            raise DefinitionError(f"unexpected {parser.peek()!r}")
        if tree is not None:            # '--' and optional steps carry no requirement
            steps.append(tree)
    return steps


def _score(node, kos, module_score):
    kind, value = node
    if kind == "ko":
        return 1.0 if value in kos else 0.0
    if kind == "module":
        return module_score(value)
    scores = [_score(child, kos, module_score) for child in value]
    return max(scores) if kind == "or" else sum(scores) / len(scores)


def definition_kos(definition):
    return set(re.findall(r"K\d{5}", definition))


class ModuleSet:
    """All KEGG modules: ``ModuleSet(load_modules(path))`` then ``.completeness(kos)``."""

    def __init__(self, modules):
        """modules: {module_number: (name, definition)}"""
        self.names = {m: v[0] for m, v in modules.items()}
        self.definitions = {m: v[1] for m, v in modules.items()}
        self.steps = {}
        for number, definition in self.definitions.items():
            try:
                self.steps[number] = parse(definition)
            except DefinitionError:
                self.steps[number] = []          # unknown syntax: the module is never reported
        self.kos = {m: definition_kos(d) for m, d in self.definitions.items()}

    def step_scores(self, number, kos, _stack=()):
        """Score (0..1) of each top-level step of one module for a set of KOs."""
        if number in _stack:                      # circular reference: cannot be satisfied
            return [0.0 for _ in self.steps.get(number, [])]

        def module_score(other):
            scores = self.step_scores(other, kos, _stack + (number,))
            return sum(scores) / len(scores) if scores else 0.0

        return [_score(step, kos, module_score) for step in self.steps.get(number, [])]

    def completeness(self, kos):
        """{module_number: (steps_complete, steps_total, percent)} for modules with a score above 0."""
        kos = set(kos)
        out = {}
        for number in self.steps:
            scores = self.step_scores(number, kos)
            if scores and any(scores):
                out[number] = (sum(1 for s in scores if s >= 1.0), len(scores),
                               round(100.0 * sum(scores) / len(scores), 2))
        return out


def load_modules(path):
    """{module_number: (name, definition)} from the tab-separated file shipped with PANKEGG."""
    modules = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3 and parts[0].startswith("M"):
                modules[parts[0]] = (parts[1], parts[2])
    return modules
