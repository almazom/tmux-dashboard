"""Curses prompt helpers."""

from __future__ import annotations

import curses
import textwrap


def safe_addstr(
    stdscr: curses._CursesWindow,
    y: int,
    x: int,
    text: str,
    attr: int = 0,
) -> None:
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= width:
        return
    if x + len(text) >= width:
        text = text[: max(0, width - x - 1)]
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def prompt_input_popup(
    stdscr: curses._CursesWindow,
    title: str,
    default: str = "",
    prompt: str = "Enter session name:",
    help_text: str = "Enter=confirm  Esc=cancel",
    max_len: int = 50,
    allow_empty: bool = False,
) -> str | None:
    height, width = stdscr.getmaxyx()
    try:
        curses.curs_set(1)
    except curses.error:
        pass
    stdscr.nodelay(False)

    buffer: list[str] = list(default)

    while True:
        center_y = height // 2
        for row in range(center_y - 2, center_y + 3):
            safe_addstr(stdscr, row, 0, " " * width)

        title_x = max(0, (width - len(title)) // 2)
        prompt_x = max(0, (width - len(prompt)) // 2)
        help_x = max(0, (width - len(help_text)) // 2)

        safe_addstr(stdscr, center_y - 1, title_x, title)
        safe_addstr(stdscr, center_y, prompt_x, prompt)

        input_display = "".join(buffer)
        max_input_width = width - 4
        if len(input_display) > max_input_width:
            input_display = "~" + input_display[-(max_input_width - 1):]
        input_x = max(2, (width - len(input_display)) // 2)
        safe_addstr(stdscr, center_y + 1, input_x, input_display)
        try:
            stdscr.move(center_y + 1, input_x + min(len(input_display), max_input_width))
        except curses.error:
            pass

        safe_addstr(stdscr, center_y + 2, help_x, help_text)
        stdscr.refresh()

        try:
            key = stdscr.get_wch()
        except curses.error:
            continue
        if isinstance(key, str):
            if key in ("\n", "\r"):
                break
            if key == "\x1b":
                try:
                    curses.curs_set(0)
                except curses.error:
                    pass
                return None
            if key in ("\x7f", "\b"):
                if buffer:
                    buffer.pop()
                continue
            if key.isprintable():
                if len(buffer) < max_len:
                    buffer.append(key)
            continue

        if key in (10, 13):
            break
        if key == 27:
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            return None
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if buffer:
                buffer.pop()
            continue
        if 32 <= key <= 126:
            if len(buffer) < max_len:
                buffer.append(chr(key))

    try:
        curses.curs_set(0)
    except curses.error:
        pass
    value = "".join(buffer).strip()
    if value:
        return value
    return "" if allow_empty else None


def confirm_dialog(
    stdscr: curses._CursesWindow,
    title: str,
    lines: list[str],
) -> bool:
    height, width = stdscr.getmaxyx()
    content_width = max([len(title), *[len(line) for line in lines]])
    box_width = min(width - 4, content_width + 4)
    box_height = min(height - 2, len(lines) + 4)
    top = max(1, (height - box_height) // 2)
    left = max(1, (width - box_width) // 2)

    for row in range(box_height):
        safe_addstr(stdscr, top + row, left, " " * box_width)

    safe_addstr(stdscr, top + 1, left + 2, title[: box_width - 4])
    for idx, line in enumerate(lines, start=2):
        if idx >= box_height - 1:
            break
        safe_addstr(stdscr, top + idx, left + 2, line[: box_width - 4])

    stdscr.refresh()

    while True:
        key = stdscr.getch()
        if key in (10, 13):
            return True
        if key == 27:
            return False


def draw_center_box(
    stdscr: curses._CursesWindow,
    title: str,
    lines: list[str],
    width: int,
    height: int,
) -> None:
    content_width = max([len(title), *[len(line) for line in lines]])
    box_width = min(width - 4, content_width + 4)
    box_height = min(height - 2, len(lines) + 4)
    top = max(1, (height - box_height) // 2)
    left = max(1, (width - box_width) // 2)

    for row in range(box_height):
        safe_addstr(stdscr, top + row, left, " " * box_width)

    safe_addstr(stdscr, top + 1, left + 2, title[: box_width - 4])
    for idx, line in enumerate(lines, start=2):
        if idx >= box_height - 1:
            break
        safe_addstr(stdscr, top + idx, left + 2, line[: box_width - 4])

    stdscr.refresh()


def show_message(stdscr: curses._CursesWindow, message: str) -> None:
    height, width = stdscr.getmaxyx()
    stdscr.erase()

    if width < 20 or height < 7:
        line = message[: max(0, width - 1)]
        y = max(0, height // 2)
        x = max(0, (width - len(line)) // 2)
        safe_addstr(stdscr, y, x, line)
        stdscr.refresh()
        stdscr.getch()
        return

    title = "ALERT"
    footer = "Enter=ok  Esc=close"
    raw_lines = message.splitlines() if message else [""]
    max_line = max([len(title), len(footer), *[len(line) for line in raw_lines]])
    inner_width = min(width - 6, max(16, max_line))
    inner_width = max(10, inner_width)
    box_width = inner_width + 2

    body_lines: list[str] = []
    for line in raw_lines:
        if not line:
            body_lines.append("")
            continue
        body_lines.extend(textwrap.wrap(line, width=inner_width, break_long_words=True))
    if not body_lines:
        body_lines = [""]

    max_body = max(1, height - 6)
    if len(body_lines) > max_body:
        body_lines = body_lines[:max_body]

    box_height = 6 + len(body_lines)
    top = max(0, (height - box_height) // 2)
    left = max(0, (width - box_width) // 2)

    border_attr = curses.A_DIM
    title_bar_attr = curses.A_BOLD
    footer_attr = curses.A_REVERSE
    if curses.has_colors():
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(6, curses.COLOR_RED, -1)
            curses.init_pair(10, curses.COLOR_WHITE, curses.COLOR_RED)
            border_attr |= curses.color_pair(6)
            title_bar_attr |= curses.color_pair(10)
            footer_attr |= curses.color_pair(5)
        except curses.error:
            pass

    safe_addstr(stdscr, top, left, "+" + "=" * max(0, box_width - 2) + "+", border_attr)
    safe_addstr(stdscr, top + 1, left, "|", border_attr)
    safe_addstr(stdscr, top + 1, left + 1, " " * max(0, box_width - 2), title_bar_attr)
    safe_addstr(stdscr, top + 1, left + box_width - 1, "|", border_attr)
    safe_addstr(stdscr, top + 1, left + 2, title[:inner_width], title_bar_attr)
    safe_addstr(stdscr, top + 2, left, "+" + "-" * max(0, box_width - 2) + "+", border_attr)

    row = top + 3
    for line in body_lines:
        safe_addstr(stdscr, row, left, "|", border_attr)
        safe_addstr(stdscr, row, left + 1, " " * max(0, box_width - 2))
        safe_addstr(stdscr, row, left + 2, line[:inner_width])
        safe_addstr(stdscr, row, left + box_width - 1, "|", border_attr)
        row += 1

    safe_addstr(stdscr, row, left, "+" + "-" * max(0, box_width - 2) + "+", border_attr)
    row += 1
    safe_addstr(stdscr, row, left, "|", border_attr)
    safe_addstr(stdscr, row, left + 1, " " * max(0, box_width - 2), footer_attr)
    safe_addstr(stdscr, row, left + box_width - 1, "|", border_attr)
    footer_x = left + 2 + max(0, (inner_width - len(footer)) // 2)
    safe_addstr(stdscr, row, footer_x, footer[:inner_width], footer_attr)
    row += 1
    safe_addstr(stdscr, row, left, "+" + "=" * max(0, box_width - 2) + "+", border_attr)

    stdscr.refresh()
    stdscr.timeout(-1)
    stdscr.getch()
