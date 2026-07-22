from __future__ import annotations

import os
import sys
from typing import Any

_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ROOT = os.path.abspath(os.path.join(_SERVER_DIR, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from chess_io.board_parser import BoardParser
from model.board import Board


class InputTxtBoardLoader:
    """Loads the initial chess board from project input.txt (infrastructure IO)."""

    def __init__(self, project_root: str):
        self._project_root = project_root

    def load(self) -> Board:
        input_path = os.path.join(self._project_root, "input.txt")
        with open(input_path, encoding="utf-8") as f:
            lines = f.readlines()

        board_lines: list[str] = []
        in_board = False
        for line in lines:
            cleaned = line.strip()
            if cleaned == "Board:":
                in_board = True
                continue
            if cleaned.startswith("Commands:"):
                break
            if in_board and cleaned:
                board_lines.append(line)
        return BoardParser.parse_initial_board(board_lines)
