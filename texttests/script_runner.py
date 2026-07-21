from chess_io.board_parser import BoardParser
from chess_io.board_printer import BoardPrinter
from engine.game_engine import GameEngine
from controller.controller import Controller
from controller.board_mapper import BoardMapper
from exceptions import ChessValidationError


class ScriptRunner:
    def __init__(self):
        self.board = None
        self.engine = None
        self.controller = None

    def run_script(self, raw_input: str):
        lines = [line.strip() for line in raw_input.splitlines() if line.strip()]

        board_lines = []
        command_lines = []
        is_commands_section = False

        for line in lines:
            if line == "Board:":
                continue
            if line == "Commands:":
                is_commands_section = True
                continue

            if is_commands_section:
                command_lines.append(line)
            else:
                board_lines.append(line)

        if board_lines:
            try:
                self.board = BoardParser.parse_initial_board(board_lines)
            except ChessValidationError as e:
                print(e)
                return
            self.engine = GameEngine(self.board)
            self.controller = Controller(self.engine)

        for command in command_lines:
            parts = command.split()
            if not parts:
                continue
                
            cmd_type = parts[0]
            
            if cmd_type == "click":
                x = int(parts[1])
                y = int(parts[2])
                if self.controller:
                    self.controller.click(x, y)

            elif cmd_type == "jump":
                x = int(parts[1])
                y = int(parts[2])
                if self.engine and self.board:
                    position = BoardMapper(self.board).to_position(x, y)
                    if position is not None:
                        self.engine.handle_jump_request(position)

            elif cmd_type == "wait":
                ms = int(parts[1])
                if self.engine:
                    self.engine.wait(ms)
                
            elif command == "print board":
                if self.board:
                    BoardPrinter.print_board(self.board)