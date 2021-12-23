from typing import Optional

from model import raw_str_start_pat, single_line_str_end_pat, char_end_pat, single_line_new_comment_pat, Match, CurLineData, State


def strip_string_comment(cur_line_data: CurLineData, cur_line_errors: list[str], cur_state: State)->None:
    while cur_line_data.line:
        earliest_match, errors = earliest_non_code_match(cur_line_data.line)
        cur_line_errors.extend(errors)

        cur_line_data.line, comment = split_comment_if_early(cur_line_data.line, earliest_match)
        cur_line_data.right_end.append(comment)

        if not comment:
            cur_line_data.line, left_end, cur_state.multiline_end_marker, processed = split_match_end(cur_line_data.line, earliest_match)
            cur_line_data.left_end.append(left_end)
            if processed:
                break


def earlier_single_line_char(cur_line: str, earliest_match: Match) -> tuple[Match, str]:
    error = ""
    char_start_idx = cur_line.find("'")
    if -1 < char_start_idx < earliest_match.start:
        if match := char_end_pat.search(cur_line, char_start_idx + 1):
            char_end_idx = match.end()
            earliest_match = Match(char_start_idx, char_end_idx, None)
        else:
            error = "End quote of character literal not found."
    return earliest_match, error


def earlier_multiline_comment(cur_line: str, earliest_match: Match) -> Match:
    multiline_comment_start_match = cur_line.find('/*')
    if -1 < multiline_comment_start_match < earliest_match.start:
        multiline_comment_end_match = cur_line.find('*/')
        earliest_match = Match(multiline_comment_start_match, multiline_comment_end_match, '*/')
    return earliest_match


def earlier_single_line_string(cur_line: str, earliest_match: Match) -> tuple[Match, str]:
    error = ""
    single_line_str_start_idx = cur_line.find('"')
    if -1 < single_line_str_start_idx < earliest_match.start:
        if match := single_line_str_end_pat.search(cur_line, single_line_str_start_idx + 1):
            single_line_str_end_idx = match.end()
            earliest_match = Match(single_line_str_start_idx, single_line_str_end_idx, None)
        else:
            error = "End double-quote of string literal not found."
    return earliest_match, error


def earlier_raw_multiline_string(cur_line: str, earliest_match: Match) -> Match:
    raw_str_start_match = raw_str_start_pat.search(cur_line)
    if raw_str_start_match:
        raw_str_start_idx = raw_str_start_match.start()
        if raw_str_start_idx < earliest_match.start:
            raw_str_delimiter = raw_str_start_match.groups()[0]
            raw_str_end_marker = f'){raw_str_delimiter}"'
            raw_str_end_idx = cur_line.find(raw_str_end_marker, raw_str_start_idx)
            if raw_str_end_idx != -1:
                raw_str_end_idx += len(raw_str_end_marker)
            earliest_match = Match(raw_str_start_idx, raw_str_end_idx, raw_str_end_marker)
    return earliest_match


def earliest_non_code_match(cur_line: str)->tuple[Match, list[str]]:
    earliest_match = Match(len(cur_line), len(cur_line), None)
    for f in (earlier_raw_multiline_string, earlier_multiline_comment):
        earliest_match = f(cur_line, earliest_match)
    errors = []
    for f in (earlier_single_line_char, earlier_single_line_string):
        earliest_match, error = f(cur_line, earliest_match)
        if error:
            errors.append(error)
    return earliest_match, errors


def split_match_end(cur_line: str, earliest_match: Match) -> tuple[str, str, Optional[str], bool]:
    left_end = ''
    multiline_end_marker = None
    processed = True
    if earliest_match.start != len(cur_line):
        if earliest_match.end == -1:
            multiline_end_marker = earliest_match.end_marker
            left_end = cur_line
            cur_line = ''
        else:
            left_end = cur_line[:earliest_match.end]
            cur_line = cur_line[earliest_match.end:]
            processed = False
    return cur_line, left_end, multiline_end_marker, processed


def split_comment_if_early(cur_line: str, earliest_match: Match) -> tuple[str, str]:
    comment = ""
    single_line_comment_match = single_line_new_comment_pat.search(cur_line)
    if single_line_comment_match and single_line_comment_match.start() < earliest_match.start:
        comment = single_line_comment_match.string
        cur_line = cur_line.removesuffix(single_line_comment_match.string)
    return cur_line, comment
