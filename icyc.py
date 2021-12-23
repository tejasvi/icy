import re
from dataclasses import dataclass
from difflib import ndiff
from itertools import islice
from pathlib import Path
from typing import Optional

CONTINUATION_CHARS = {';', ':', '{', '(', '[', '::', '=', '/', '<', ','}

raw_str_start_pat = re.compile(r'R"(.*)\(')
single_line_str_end_pat = re.compile(r'[^\\]"')
char_end_pat = re.compile(r"[^\\]'")

full_line_comment_pat = re.compile(r'^\s*//')
single_line_c_comment_pat = re.compile(r'/\*.*/\*')
single_line_new_comment_pat = re.compile(r'\s*//.*')

lonely_closing_brace_pat = re.compile(r'^\s*};?\s*$')
lonely_template_pat = re.compile(r'^\s*template\s*<.*>\s*$')

skip_join_next_pat = re.compile(r'.*(public|private|protected|(case[^:]*)|default)\s*:\s*$')

preprocessor_pat = re.compile(r'^\s*#')


@dataclass
class IndentData:
    indent: int
    indent_whitespace: str


@dataclass
class State:
    effective_lines: list[str]
    join_next: bool
    effective_indent_data: IndentData
    preprocessor: bool
    line_num_1idx: int


@dataclass
class IndentTracker:
    indent: int
    line_num_1idx: int


preserve_line_num: bool = True
indent_with_tabs = False


def lonely_closing_brace(indent: int, line: str) -> bool:
    return lonely_closing_brace_pat.match(line) and line_indentation(line) == indent


def main(in_lines: list[str]):
    multi_line_end_marker: Optional[str] = None

    out_lines: list[str] = []

    open_paren_line_nums: list[IndentTracker] = []
    close_paren_line_nums: list[int] = []
    cur_state = last_state = State([], False, IndentData(0, ''), False, 0)

    indent_stack: list[IndentData] = []

    error_messages: list[tuple[int, str]] = []

    for cur_line_num, cur_line in enumerate(in_lines, 1):
        cur_line.rstrip()
        if ignore_line(cur_line):
            out_lines.append(cur_line)
            continue

        processed_left: list[str] = []
        processed_right: list[str] = []

        cur_preprocessor = False
        if multi_line_end_marker is None:
            cur_preprocessor = last_state.preprocessor if last_state.join_next else bool(preprocessor_pat.match(cur_line))
        else:
            term_str_idx = cur_line.find(multi_line_end_marker)
            if term_str_idx == -1:
                out_lines.append(cur_line)
                continue
            else:
                str_end_idx = term_str_idx + len(multi_line_end_marker)
                processed_left.append(cur_line[:str_end_idx])
                cur_line = cur_line[str_end_idx:]
                multi_line_end_marker = None

        _cur_line_effective_indent = last_state.effective_indent_data if last_state.join_next else line_indentation(cur_line)

        if not cur_preprocessor:
            while cur_line:
                span: tuple[int, int, Optional[str]] = (len(cur_line), len(cur_line), None)

                char_start_idx = cur_line.find("'")
                if -1 < char_start_idx < span[0]:
                    if match := char_end_pat.search(cur_line, char_start_idx + 1):
                        char_end_idx = match.end()
                        span = char_start_idx, char_end_idx, None
                    else:
                        error_messages.append((cur_line_num, "End quote of character literal not found."))

                raw_str_start_match = raw_str_start_pat.search(cur_line)
                if raw_str_start_match:
                    raw_str_delimiter = raw_str_start_match.groups()[0]

                    raw_str_start_idx = raw_str_start_match.start()
                    if raw_str_start_idx < span[0]:
                        raw_str_end_marker = f'){raw_str_delimiter}"'
                        raw_str_end_idx = cur_line.find(raw_str_end_marker, raw_str_start_idx)
                        if raw_str_end_idx != -1:
                            raw_str_end_idx += len(raw_str_end_marker)
                        span = raw_str_start_idx, raw_str_end_idx, raw_str_end_marker

                single_line_str_start_idx = cur_line.find('"')
                if -1 < single_line_str_start_idx < span[0]:
                    if match := single_line_str_end_pat.search(cur_line, single_line_str_start_idx + 1):
                        single_line_str_end_idx = match.end()
                        span = single_line_str_start_idx, single_line_str_end_idx, None
                    else:
                        error_messages.append((cur_line_num, "End double-quote of string literal not found."))

                multi_line_comment_start_match = cur_line.find('/*')
                if -1 < multi_line_comment_start_match < span[0]:
                    multi_line_comment_end_match = cur_line.find('*/')
                    span = multi_line_comment_start_match, multi_line_comment_end_match, '*/'

                single_line_comment_match = single_line_new_comment_pat.search(cur_line)
                if single_line_comment_match:
                    processed_right.append(single_line_comment_match.string)
                    cur_line = cur_line.removesuffix(single_line_comment_match.string)
                else:
                    start, end, end_marker = span
                    if start == len(cur_line):
                        break

                    if end == -1:
                        multi_line_end_marker = end_marker
                        processed_left.append(cur_line)
                        cur_line = ''
                        break
                    else:
                        processed_left.append(cur_line[:end])
                        cur_line = cur_line[end:]

        next_line = next_non_empty_line(cur_line_num, in_lines)
        _next_line_indent = line_indentation(next_line).indent

        cur_join_next = (not (cur_preprocessor or cur_line.endswith('{') or cur_line.endswith(';')) and _next_line_indent > _cur_line_effective_indent.indent) or cur_line.endswith('\\') or multi_line_end_marker is not None
        if last_state.join_next:
            cur_state = last_state
            cur_state.effective_lines.append(cur_line)
            cur_state.join_next = cur_join_next
        else:
            cur_state = State([cur_line], cur_join_next, _cur_line_effective_indent, cur_preprocessor, cur_line_num)

        next_line_effective_indent = cur_state.effective_indent_data.indent if cur_join_next else _next_line_indent

        if not (cur_join_next or cur_preprocessor):
            if close_paren_line_nums and lonely_closing_brace_pat.match(cur_line):
                if open_paren_line_nums and line_indentation(cur_line).indent == open_paren_line_nums[-1].indent:
                    open_paren_line_nums.pop()
                else:
                    error_messages.append((cur_line_num, f"Could not find opening parenthesis for:\n{' ' * 6 + in_lines[cur_line_num - 1]}"))
                close_paren_line_nums.pop()
            elif cur_line.endswith('{'):
                open_paren_line_nums.append(IndentTracker(cur_state.effective_indent_data.indent, cur_line_num))
                if next_line_effective_indent > cur_state.effective_indent_data.indent or lonely_closing_brace_pat.match(next_line):
                    indent_stack.append(cur_state.effective_indent_data)
            elif next_line_effective_indent <= cur_state.effective_indent_data.indent:
                s_strip = cur_line.rstrip()
                if s_strip and s_strip[-1] not in CONTINUATION_CHARS:
                    add_semicolon = True
                    if lonely_template_pat.match(''.join(cur_state.effective_lines)):
                        open_idx = cur_line.find('<')
                        assert open_idx != -1
                        unbalanced = 1
                        for c in islice(cur_line, open_idx + 1):
                            if c == '<':
                                unbalanced += 1
                            elif c == '>':
                                unbalanced -= 1
                        if unbalanced != 0:
                            add_semicolon = False
                    if add_semicolon:
                        processed_right.append(';')

        out_lines.append(''.join(processed_left) + cur_line + ''.join(reversed(processed_right)))

        if not (cur_join_next or cur_preprocessor):
            cur_upper_bound = cur_state.effective_indent_data.indent
            while indent_stack:
                if next_line_effective_indent <= indent_stack[-1].indent:
                    parent_indent = indent_stack.pop()
                    append = True
                    if lonely_closing_brace_pat.match(next_line):
                        if line_indentation(next_line) == parent_indent.indent:
                            append = False
                        else:
                            close_paren_line_nums.append(cur_line_num + 1)
                    if append:
                        if preserve_line_num:
                            out_lines[-1] += '};'
                        else:
                            out_lines.append(parent_indent.indent_whitespace + '};')
                    open_paren_line_nums.pop()
                    cur_upper_bound = parent_indent.indent
                else:
                    if indent_stack[-1].indent < next_line_effective_indent < cur_upper_bound:
                        error_messages.append((cur_line_num, f"Expected indentation to be either {indent_stack[-1].indent} or {cur_upper_bound} spaces equivalent."))
                    break

        last_state = cur_state

    if multi_line_end_marker not in (None, '*/'):
        error_messages.append((cur_state.line_num_1idx, "Raw string literal's terminating delimiter not found."))

    error_messages.extend((ln.line_num_1idx, f"Could not find closing parenthesis for:\n{' ' * 6 + in_lines[ln.line_num_1idx - 1]}") for ln in open_paren_line_nums)

    return out_lines, error_messages


def next_non_empty_line(line_number, in_lines) -> str:
    next_line = ''
    for j in range(line_number, len(in_lines)):
        line = in_lines[j]
        if not empty_or_comment(line):
            next_line = line
            break
    return next_line


def empty_or_comment(cur_line) -> bool:
    return bool(not cur_line.rstrip() or full_line_comment_pat.match(cur_line))


def ignore_line(cur_line) -> bool:
    return bool(empty_or_comment(cur_line) or skip_join_next_pat.search(cur_line))


def line_indentation(cur_line) -> IndentData:
    indent = 0
    indent_chars = []
    for c in cur_line:
        if c == ' ':
            indent += 1
        elif c == '\t':
            indent += 8
        else:
            break
        indent_chars.append(c)
    return IndentData(indent, ''.join(indent_chars))


if __name__ == "__main__":
    orig = Path("test.icy").read_text().splitlines()
    o, e = main(orig)
    data = ''.join(f"{_l:<6}: {_s}\n" for _l, _s in e) if e else '\n'.join(o) + '\n'
    Path('out.txt').write_text(data)
    print('\n'.join((f"{i}: {x}" for i, x in enumerate(ndiff(orig, o)) if x[0] != ' ')))
