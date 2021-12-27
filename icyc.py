from collections import defaultdict
from difflib import ndiff
from itertools import islice
from pathlib import Path

from model import full_line_comment_pat, lonely_closing_brace_pat, lonely_template_pat, skip_join_next_pat, preprocessor_pat, IndentData, State, IndentTracker, ParenLineNums, NextLineData, Result, CurLineData, Scope, ScopeKind, enum_pat, preprocessor_if_else_pat, lonely_opening_brace_pat, preprocessor_end_pat, if_pat, do_pat, try_pat, value_opening_brace_pat
from strip import strip_string_comment

CONTINUATION_CHARS = {';', ':', '{', '(', '[', '::', '=', '/', '<', ','}

preserve_line_num: bool = True
indent_with_tabs = False


def scope_kind(lines: list[str])->ScopeKind:
    effective_line = ''.join(lines)
    pat_types = (
        (preprocessor_if_else_pat, ScopeKind.IF_ELSE_DIRECTIVE),
        (value_opening_brace_pat, ScopeKind.VALUE),
        (enum_pat, ScopeKind.ENUM),
        (if_pat, ScopeKind.IF),
        (do_pat, ScopeKind.DO),
        (try_pat, ScopeKind.TRY),
        (lonely_opening_brace_pat, ScopeKind.LONELY)
     )
    for pat, pat_type in pat_types:
        if pat.search(effective_line):
            return pat_type
    return ScopeKind.OTHER


def main(in_lines: list[str]) -> Result:
    paren_line_nums = ParenLineNums([], [])
    scope_stack: list[Scope] = []

    effective_state = last_state = State(None, [], False, IndentData(0, ''), False, 0)

    result = Result([], defaultdict(list))

    for _cur_line_num, _cur_line in enumerate(in_lines, 1):
        _cur_line.rstrip()
        if specifier_or_comment_or_empty(_cur_line):
            result.output.append(_cur_line)
            pass#continue
        cur_line_end_slash = _cur_line.endswith('\\')
        if cur_line_end_slash:
            _cur_line = _cur_line[:-1]
        cur_line_data = CurLineData([], _cur_line, [], _cur_line_num)

        cur_line_errors = result.errors[_cur_line_num] = []


        cur_preprocessor = False
        if effective_state.multiline_end_marker is None:
            cur_preprocessor = last_state.preprocessor if last_state.join_next else bool(preprocessor_pat.search(cur_line_data.line))
        else:
            if not strip_till_mutiline_end_marker(cur_line_data, effective_state):
                result.output.append(cur_line_data.line)
                continue

        _cur_line_effective_indent = last_state.indent_data if last_state.join_next else line_indentation(cur_line_data.line)

        _next_line = next_code_line(cur_line_data.line_num, in_lines)
        _next_line_indent = line_indentation(_next_line).indent

        if not cur_preprocessor:
            comment_end_backslash = strip_string_comment(cur_line_data, cur_line_errors, effective_state)

        cur_join_next = cur_line_end_slash or effective_state.multiline_end_marker is not None or (
                not cur_preprocessor
                and (value_opening_brace_pat.search(cur_line_data.line) or not (cur_line_data.line and cur_line_data.line[-1] in ('{', ';')))
                and _next_line_indent > _cur_line_effective_indent.indent
        )

        process_cur_line = not (cur_join_next or cur_preprocessor)

        next_line_data = NextLineData(_next_line, _cur_line_effective_indent if cur_join_next else _next_line_indent)
        effective_state = get_cur_state(_cur_line_effective_indent, cur_join_next, cur_line_data, cur_preprocessor, last_state)

        if process_cur_line:
            if paren_line_nums.close and lonely_closing_brace_pat.search(cur_line_data.line):
                if paren_line_nums.open and line_indentation(cur_line_data.line).indent == paren_line_nums.open[-1].indent:
                    paren_line_nums.open.pop()
                else:
                    cur_line_errors[cur_line_data.line_num] = f"Could not find opening parenthesis for:\n{' ' * 6 + in_lines[cur_line_data.line_num - 1]}"
                paren_line_nums.close.pop()
            elif cur_line_data.line.endswith('{'):
                paren_line_nums.open.append(IndentTracker(effective_state.indent_data.indent, cur_line_data.line_num))
                if next_line_data.effective_indent > effective_state.indent_data.indent or lonely_closing_brace_pat.search(next_line_data.line):
                    scope_stack.append(Scope(effective_state.indent_data, scope_kind(effective_state.lines)))

            if next_line_data.effective_indent <= effective_state.indent_data.indent and add_semicolon(cur_line_data.line, effective_state.lines) and (not scope_stack or scope_stack[-1].kind not in (ScopeKind.ENUM, ScopeKind.VALUE)):
                cur_line_data.right_end.append(';')

        result.output.append(''.join(cur_line_data.left_end) + cur_line_data.line + ''.join(reversed(cur_line_data.right_end)))

        if process_cur_line:
            add_closing_brackets(cur_line_data.line_num, effective_state, scope_stack, next_line_data, paren_line_nums, result)

        last_state = effective_state

    if effective_state.multiline_end_marker not in (None, '*/'):
        result.errors[effective_state.line_num_1idx].append("Raw string literal's terminating delimiter not found.")

    for ln in paren_line_nums.open:
        result.errors[ln.line_num_1idx].append(f"Could not find closing parenthesis for:\n{' ' * 6 + in_lines[ln.line_num_1idx - 1]}")

    return result


def strip_till_mutiline_end_marker(cur_line_data, cur_state):
    cur_line_data.line, left_end, end_marker_found = split_if_end_marker(cur_line_data.line, cur_state.multiline_end_marker)
    if end_marker_found:
        cur_line_data.left_end.append(left_end)
        cur_state.multiline_end_marker = None
    return end_marker_found


def get_cur_state(cur_line_effective_indent: IndentData, cur_join_next: bool, cur_line_data: CurLineData, cur_preprocessor: bool, last_state: State)->State:
    if last_state.join_next:
        cur_state = last_state
        cur_state.lines.append(cur_line_data.line)
        cur_state.join_next = cur_join_next
    else:
        cur_state = State(None, [cur_line_data.line], cur_join_next, cur_line_effective_indent, cur_preprocessor, cur_line_data.line_num)
    return cur_state


def add_closing_brackets(cur_line_num: int, cur_state: State, scope_stack: list[Scope], next_line_data: NextLineData, paren_line_nums: ParenLineNums, result: Result)->None:
    cur_upper_bound = cur_state.indent_data.indent
    while scope_stack:
        if next_line_data.effective_indent <= scope_stack[-1].indent_data.indent:
            parent_scope = scope_stack.pop()
            append = True
            if lonely_closing_brace_pat.search(next_line_data.line):
                if next_line_data.effective_indent == parent_scope.indent_data.indent:
                    append = False
                else:
                    paren_line_nums.close.append(cur_line_num + 1)
            if append:
                bracket_string = '}' if parent_scope.kind in {ScopeKind.TRY, ScopeKind.IF, ScopeKind.DO, ScopeKind.LONELY, ScopeKind.VALUE} else '};'
                if preserve_line_num:
                    result.output[-1] += bracket_string
                else:
                    result.output.append(parent_scope.indent_data.whitespace + bracket_string)
            paren_line_nums.open.pop()
            cur_upper_bound = parent_scope.indent_data.indent
        else:
            if scope_stack[-1].indent_data.indent < next_line_data.effective_indent < cur_upper_bound:
                result.errors[cur_line_num].append(f"Expected indentation to be either {scope_stack[-1].indent_data.indent} or {cur_upper_bound} spaces equivalent.")
            break


def lonely_closing_brace(indent: int, line: str) -> bool:
    return lonely_closing_brace_pat.search(line) and line_indentation(line) == indent


def add_semicolon(cur_line: str, lines: list[str]) -> bool:
    _add = False
    if cur_line and cur_line[-1] not in CONTINUATION_CHARS:
        _add = lonely_template_declaration(lines)
    return _add


def lonely_template_declaration(lines: list[str])->bool:
    effective_line = ''.join(lines)
    if lonely_template_pat.search(effective_line):
        open_idx = effective_line.find('<')
        assert open_idx != -1
        unbalanced = 1
        for c in islice(effective_line, open_idx + 1):
            if c == '<':
                unbalanced += 1
            elif c == '>':
                unbalanced -= 1
        if unbalanced != 0:
            return False
    return True


def split_if_end_marker(cur_line: str, multiline_end_marker: str) -> tuple[str, str, bool]:
    left_end = ''
    end_marker_found = True
    term_str_idx = cur_line.find(multiline_end_marker)
    if term_str_idx == -1:
        end_marker_found = False
    else:
        str_end_idx = term_str_idx + len(multiline_end_marker)
        left_end = cur_line[:str_end_idx]
        cur_line = cur_line[str_end_idx:]
    return cur_line, left_end, end_marker_found


def next_code_line(cur_line_num: int, in_lines: list[str]) -> str:
    next_line = ''
    for j in range(cur_line_num, len(in_lines)):
        line = in_lines[j]
        if not empty_or_comment(line):
            next_line = line
            break
    return next_line


def empty_or_comment(cur_line: str) -> bool:
    return bool(not cur_line.rstrip() or full_line_comment_pat.search(cur_line))


def specifier_or_comment_or_empty(cur_line: str) -> bool:
    return bool(empty_or_comment(cur_line) or skip_join_next_pat.search(cur_line))


def line_indentation(cur_line: str) -> IndentData:
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
    res = main(orig)
    with open('out.txt', 'w') as f:
        errors = ''.join(f"{_l:>6}: {_e}\n" for _l, _el in sorted(res.errors.items()) for _e in _el)
        f.write(errors)
        f.write('\n')
        if not errors:
            f.write('\n'.join(res.output))
            f.write('\n')
    print('\n'.join((f"{i}: {x}" for i, x in enumerate(ndiff(orig, res.output)) if x[0] != ' ')))
