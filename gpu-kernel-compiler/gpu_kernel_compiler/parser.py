"""AST nodes and a recursive-descent parser for the GPU kernel DSL.

Grammar (EBNF-ish):

    kernel_def  := "kernel" IDENT "(" params ")" "->" IDENT ":" type "{" stmts "}"
    params      := param ("," param)* | <empty>
    param       := IDENT ":" "f32" ("[" "N" "]")?
    type        := "f32" ("[" "N" "]")?
    stmts       := stmt*
    stmt        := "let" IDENT "=" expr ";"
                 | IDENT "[" expr "]" "=" expr ";"
                 | IDENT "=" expr ";"                      (scalar assignment)
                 | "for" IDENT "in" NUM ".." NUM "{" stmts "}"
    expr        := term (("+" | "-") term)*
    term        := factor (("*" | "/" | "%") factor)*
    factor      := NUM | IDENT ("[" expr "]")? | "(" expr ")" | "-" factor

`i` is the implicit work-item index; loop variables come from `for` stmts.
"""

from dataclasses import dataclass, field

from .lexer import tokenize, LexError


class ParseError(Exception):
    pass


@dataclass(frozen=True)
class Num:
    value: object  # int or float


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Index:
    name: str
    index: object  # expr


@dataclass(frozen=True)
class BinOp:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class Unary:
    op: str
    operand: object


@dataclass(frozen=True)
class Param:
    name: str
    is_array: bool


@dataclass(frozen=True)
class Let:
    name: str
    expr: object


@dataclass(frozen=True)
class Assign:
    name: str
    index: object  # expr, or None for a scalar assignment
    expr: object


@dataclass(frozen=True)
class For:
    var: str
    start: int
    end: int  # exclusive
    body: tuple


@dataclass(frozen=True)
class Kernel:
    name: str
    params: tuple
    ret_name: str
    ret_is_array: bool
    body: tuple


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self):
        tok = self.peek()
        if tok is None:
            raise ParseError("unexpected end of input")
        self.pos += 1
        return tok

    def expect_sym(self, sym):
        tok = self.next()
        if tok.kind != "sym" or tok.value != sym:
            raise ParseError(f"expected {sym!r}, got {tok.value!r} at offset {tok.pos}")
        return tok

    def expect_keyword(self, kw):
        tok = self.next()
        if tok.kind != "keyword" or tok.value != kw:
            raise ParseError(f"expected keyword {kw!r}, got {tok.value!r} at offset {tok.pos}")
        return tok

    def expect_ident(self):
        tok = self.next()
        if tok.kind != "ident":
            raise ParseError(f"expected identifier, got {tok.value!r} at offset {tok.pos}")
        return tok.value

    def parse_kernel(self):
        self.expect_keyword("kernel")
        name = self.expect_ident()
        self.expect_sym("(")
        params = []
        if not (self.peek().kind == "sym" and self.peek().value == ")"):
            params.append(self.parse_param())
            while self.peek().kind == "sym" and self.peek().value == ",":
                self.next()
                params.append(self.parse_param())
        self.expect_sym(")")
        self.expect_sym("->")
        ret_name = self.expect_ident()
        self.expect_sym(":")
        ret_is_array = self.parse_type()
        self.expect_sym("{")
        body = self.parse_stmts()
        self.expect_sym("}")
        if self.pos != len(self.tokens):
            extra = self.peek()
            raise ParseError(f"trailing tokens after kernel, starting at {extra.value!r}")
        return Kernel(name, tuple(params), ret_name, ret_is_array, tuple(body))

    def parse_param(self):
        name = self.expect_ident()
        self.expect_sym(":")
        is_array = self.parse_type()
        return Param(name, is_array)

    def parse_type(self):
        tok = self.next()
        if tok.kind != "keyword" or tok.value != "f32":
            raise ParseError(f"expected type f32, got {tok.value!r} at offset {tok.pos}")
        is_array = False
        if self.peek().kind == "sym" and self.peek().value == "[":
            self.next()
            n = self.next()
            if n.kind != "ident" or n.value != "N":
                raise ParseError("array size must be N")
            self.expect_sym("]")
            is_array = True
        return is_array

    def parse_stmts(self):
        stmts = []
        while True:
            tok = self.peek()
            if tok is None or (tok.kind == "sym" and tok.value == "}"):
                return stmts
            stmts.append(self.parse_stmt())

    def parse_stmt(self):
        tok = self.peek()
        if tok.kind == "keyword" and tok.value == "let":
            self.next()
            name = self.expect_ident()
            self.expect_sym("=")
            expr = self.parse_expr()
            self.expect_sym(";")
            return Let(name, expr)
        if tok.kind == "keyword" and tok.value == "for":
            self.next()
            var = self.expect_ident()
            self.expect_keyword("in")
            start = self.next()
            if start.kind != "num":
                raise ParseError("for-loop start must be a number")
            rng = self.next()
            if rng.kind != "sym" or rng.value != "..":
                raise ParseError("for-loop needs '..' range")
            end = self.next()
            if end.kind != "num":
                raise ParseError("for-loop end must be a number")
            self.expect_sym("{")
            body = self.parse_stmts()
            self.expect_sym("}")
            return For(var, int(start.value), int(end.value), tuple(body))
        if tok.kind == "ident":
            name = self.next().value
            if self.peek().kind == "sym" and self.peek().value == "=":
                self.next()
                expr = self.parse_expr()
                self.expect_sym(";")
                return Assign(name, None, expr)
            self.expect_sym("[")
            index = self.parse_expr()
            self.expect_sym("]")
            self.expect_sym("=")
            expr = self.parse_expr()
            self.expect_sym(";")
            return Assign(name, index, expr)
        raise ParseError(f"unexpected token {tok.value!r} at offset {tok.pos}")

    def parse_expr(self):
        node = self.parse_term()
        while self.peek() is not None and self.peek().kind == "sym" and self.peek().value in ("+", "-"):
            op = self.next().value
            node = BinOp(op, node, self.parse_term())
        return node

    def parse_term(self):
        node = self.parse_factor()
        while self.peek() is not None and self.peek().kind == "sym" and self.peek().value in ("*", "/", "%"):
            op = self.next().value
            node = BinOp(op, node, self.parse_factor())
        return node

    def parse_factor(self):
        tok = self.next()
        if tok.kind == "num":
            return Num(tok.value)
        if tok.kind == "sym" and tok.value == "-":
            return Unary("-", self.parse_factor())
        if tok.kind == "sym" and tok.value == "(":
            node = self.parse_expr()
            self.expect_sym(")")
            return node
        if tok.kind == "ident":
            if self.peek() is not None and self.peek().kind == "sym" and self.peek().value == "[":
                self.next()
                index = self.parse_expr()
                self.expect_sym("]")
                return Index(tok.value, index)
            return Var(tok.value)
        raise ParseError(f"unexpected token {tok.value!r} at offset {tok.pos}")


def parse(source):
    """Parse DSL source text into a Kernel AST node."""
    try:
        tokens = tokenize(source)
    except LexError as exc:
        raise ParseError(str(exc)) from exc
    return Parser(tokens).parse_kernel()
