"""Curses prompt helpers."""

from __future__ import annotations

import curses


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

        key = stdscr.getch()
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
    line = message[: max(0, width - 1)]
    y = max(0, height // 2)
    x = max(0, (width - len(line)) // 2)
    safe_addstr(stdscr, y, x, line)
    safe_addstr(stdscr, y + 1, x, "Press any key to return"[: max(0, width - x - 1)])
    stdscr.refresh()
    stdscr.timeout(-1)
    stdscr.getch()
