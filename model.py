import re
from dataclasses import dataclass
from enum import Enum, auto, unique
from typing import Optional, DefaultDict

raw_str_start_pat = re.compile(r'R"(.*)\(')
single_line_str_end_pat = re.compile(r'[^\\]"')
char_end_pat = re.compile(r"[^\\]'")

full_line_comment_pat = re.compile(r'^\s*//.*$')
single_line_c_comment_pat = re.compile(r'/\*.*/\*')
single_line_new_comment_pat = re.compile(r'\s*?//.*')  # blah //     // laskjf

lonely_template_pat = re.compile(r'^\s*template\s*<.*>\s*')
skip_join_next_pat = re.compile(r'.*(public|private|protected|(case[^:]*)|default)\s*:\s*$')

lonely_opening_brace_pat = re.compile(r'^\s*{\s*$')
lonely_closing_brace_pat = re.compile(r'^\s*}.*$')

preprocessor_pat = re.compile(r'^\s*#.*')
preprocessor_if_else_pat = re.compile(r'^\s&#((if|ifdef|ifndef)\s.+|((elif|elifdef|elifndef)\s.+)|else\s*)')
preprocessor_end_pat = re.compile(r'^\s&#endif\s*')

enum_pat = re.compile(r'^\s*enum\s.*{$')
if_pat = re.compile(r'^(.*\s)?if\s*(!?\s*consteval|constexpr)?\s*\(.+\)\s*{$')
do_pat = re.compile(r'^(.*\s)?do\s*{$')
try_pat = re.compile(r'^\s*try\s*{$')

value_opening_brace_pat = re.compile(r'.*\([^)]\s{\s*$')


@dataclass
class IndentData:
    indent: int
    whitespace: str


@dataclass
class State:
    multiline_end_marker: Optional[str]
    lines: list[str]
    join_next: bool
    indent_data: IndentData
    preprocessor: bool
    line_num_1idx: int


@dataclass
class IndentTracker:
    indent: int
    line_num_1idx: int


@dataclass
class Match:
    start: int
    end: int
    end_marker: Optional[str]


@dataclass
class ParenLineNums:
    open: list[IndentTracker]
    close: list[int]


@unique
class ScopeKind(Enum):
    ENUM = auto()
    IF_ELSE_DIRECTIVE = auto()
    IF = auto()
    DO = auto()
    TRY = auto()
    LONELY = auto()
    VALUE = auto()
    OTHER = auto()


@dataclass
class Scope:
    indent_data: IndentData
    kind: ScopeKind


@dataclass
class NextLineData:
    line: str
    effective_indent: int


@dataclass
class Result:
    output: list[str]
    errors: DefaultDict[int, list[str]]


@dataclass
class CurLineData:
    left_end: list[str]
    line: str
    right_end: list[str]
    line_num: int