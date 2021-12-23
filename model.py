import re
from dataclasses import dataclass
from typing import Optional, DefaultDict

raw_str_start_pat = re.compile(r'R"(.*)\(')
single_line_str_end_pat = re.compile(r'[^\\]"')
char_end_pat = re.compile(r"[^\\]'")
full_line_comment_pat = re.compile(r'^\s*//')
single_line_c_comment_pat = re.compile(r'/\*.*/\*')
single_line_new_comment_pat = re.compile(r'\s*//.*')
lonely_closing_brace_pat = re.compile(r'^\s*}.*;?\s*$')
lonely_template_pat = re.compile(r'^\s*template\s*<.*>\s*$')
skip_join_next_pat = re.compile(r'.*(public|private|protected|(case[^:]*)|default)\s*:\s*$')
preprocessor_pat = re.compile(r'^\s*#')


@dataclass
class IndentData:
    indent: int
    indent_whitespace: str


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