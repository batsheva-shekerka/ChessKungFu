import os
import sys
import cv2
import time
from typing import List, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chessRender import ChessRenderer
from network_client import NetworkClient

try:
    from chess_io.board_parser import BoardParser
    from model.board import Board
    from model.piece import Piece, PieceStatus
    from model.position import Position
    from controller.board_mapper import BoardMapper
    from realtime.motion import Motion

    HAS_REAL_MODEL = True
except ImportError:
    HAS_REAL_MODEL = False
    Motion = None  # type: ignore

MS_PER_CELL = 1000


SCREEN_LOGIN = "login"
SCREEN_LOBBY = "lobby"
SCREEN_JOIN = "join"
SCREEN_GAME = "game"

# Lobby / join button rectangles (x1, y1, x2, y2)
BTN_PLAY = (60, 220, 320, 290)
BTN_CREATE = (60, 320, 320, 390)
BTN_JOIN = (60, 420, 320, 490)
BTN_CANCEL = (360, 220, 620, 290)
BTN_BACK = (60, 520, 320, 590)
BTN_LOGIN = (60, 380, 280, 450)


def _point_in_rect(x: int, y: int, rect) -> bool:
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


class ChessGameController:
    """
    מחברת את הגרפיקה לשרת:
    Login / Lobby ב-UI, ואז מהלכים בלחיצות על הלוח שנשלחות ב-WebSocket.
    """

    def __init__(self, server_uri: str = "ws://localhost:8765"):
        self.input_txt_path = os.path.join(ROOT_DIR, "input.txt")
        self.renderer = ChessRenderer()
        self.net = NetworkClient(uri=server_uri)

        self.screen = SCREEN_LOGIN
        self.username = ""
        self.password = ""
        self.join_room_id = ""
        self.login_focus = "username"  # username | password
        self.status_text = "Connecting to server..."

        self.board: Optional[Board] = None
        self.mapper: Optional[BoardMapper] = None
        self.selected: Optional[tuple[int, int]] = None
        self.score = {"w": 0, "b": 0}
        self.game_over = False
        self.winner = None
        self.my_color: Optional[str] = None
        self.active_motions: List = []
        self._motion_counter = 0

    def load_board_from_file(self) -> Optional[Board]:
        if not HAS_REAL_MODEL:
            return None
        if not os.path.exists(self.input_txt_path):
            print(f"Warning: input.txt not found at {self.input_txt_path}.")
            return None

        try:
            with open(self.input_txt_path, "r", encoding="utf-8") as f:
                raw_lines = f.readlines()

            board_lines = []
            in_board_section = False
            for line in raw_lines:
                cleaned = line.strip()
                if cleaned == "Board:":
                    in_board_section = True
                    continue
                if cleaned.startswith("Commands:"):
                    break
                if in_board_section and cleaned:
                    board_lines.append(line)

            return BoardParser.parse_initial_board(board_lines)
        except Exception as e:
            print(f"Failed to parse input.txt: {e}")
            return None

    @staticmethod
    def board_from_state(pieces) -> Optional[Board]:
        if not HAS_REAL_MODEL:
            return None
        board = Board()
        for raw in pieces or []:
            if isinstance(raw, dict):
                row = int(raw["row"])
                col = int(raw["col"])
                color = str(raw["color"])
                piece_type = str(raw["type"])
                status_name = str(raw.get("status", "IDLE"))
            else:
                row = int(raw.row)
                col = int(raw.col)
                color = str(raw.color)
                piece_type = str(raw.type)
                status_name = str(getattr(raw, "status", "IDLE"))

            try:
                status = PieceStatus[status_name]
            except KeyError:
                status = PieceStatus.IDLE

            # Server snapshots may still say MOVING; local motions drive animation.
            if status in (PieceStatus.MOVING, PieceStatus.JUMPING):
                status = PieceStatus.IDLE

            piece = Piece(
                piece_id=f"{color}{piece_type}{row}{col}",
                color=color,
                piece_type=piece_type,
                status=status,
            )
            board.set_piece(Position(row, col), piece)
        return board

    def _enter_game(self) -> None:
        self.screen = SCREEN_GAME
        self.selected = None
        self.game_over = False
        self.winner = None
        self.score = {"w": 0, "b": 0}
        self.my_color = self.net.color
        self.active_motions = []
        self._motion_counter = 0
        self.board = self.load_board_from_file()
        if self.board is not None:
            self.mapper = BoardMapper(self.board)
        self.status_text = self.net.status

    def _back_to_lobby(self) -> None:
        self.net.reset_game_session()
        self.screen = SCREEN_LOBBY
        self.selected = None
        self.board = None
        self.mapper = None
        self.active_motions = []
        self.game_over = False
        self.winner = None
        self.status_text = self.net.status or "Lobby"

    @staticmethod
    def _move_duration_ms(start: Position, end: Position) -> int:
        dr = abs(end.row - start.row)
        dc = abs(end.col - start.col)
        return max(1, max(dr, dc)) * MS_PER_CELL

    def _apply_state(self, data: dict) -> None:
        # Authoritative sync from server — drop local animations.
        self.active_motions = []
        pieces = data.get("pieces") or []
        new_board = self.board_from_state(pieces)
        if new_board is not None:
            self.board = new_board
            self.mapper = BoardMapper(self.board)
        score = data.get("score") or {}
        self.score = {
            "w": int(score.get("w", 0) or 0),
            "b": int(score.get("b", 0) or 0),
        }
        self.game_over = bool(data.get("game_over", False))
        self.winner = data.get("winner")

    def _apply_ack(self, data: dict) -> None:
        """Start a local fly animation for an accepted move (own or opponent)."""
        if self.board is None or not HAS_REAL_MODEL or Motion is None:
            return
        start = data.get("start")
        end = data.get("end")
        if not start or not end:
            return
        start_pos = Position(int(start[0]), int(start[1]))
        end_pos = Position(int(end[0]), int(end[1]))
        piece = self.board.get_piece(start_pos)
        if piece is None:
            return
        if piece.status in (PieceStatus.MOVING, PieceStatus.JUMPING):
            return

        duration = self._move_duration_ms(start_pos, end_pos)
        piece.status = PieceStatus.MOVING
        self._motion_counter += 1
        self.active_motions.append(
            Motion(
                motion_id=self._motion_counter,
                piece=piece,
                start=start_pos,
                end=end_pos,
                remaining_time=duration,
                original_duration=duration,
                is_jump=False,
            )
        )

    def _update_motions(self, dt_ms: int) -> None:
        if not self.active_motions or self.board is None or not HAS_REAL_MODEL:
            return

        finished = []
        for motion in self.active_motions:
            motion.remaining_time -= dt_ms
            if motion.remaining_time <= 0:
                finished.append(motion)

        for motion in finished:
            self.active_motions.remove(motion)
            piece_at_start = self.board.get_piece(motion.start)
            if piece_at_start is motion.piece:
                self.board.set_piece(motion.start, None)
            motion.piece.status = PieceStatus.IDLE
            self.board.set_piece(motion.end, motion.piece)

    def _process_network_events(self) -> None:
        while True:
            event = self.net.poll_event()
            if event is None:
                break
            name, data = event
            self.status_text = self.net.status

            if name == "login_ok":
                self.screen = SCREEN_LOBBY
            elif name == "enter_game":
                self._enter_game()
            elif name == "state":
                self._apply_state(data)
            elif name == "ack":
                self._apply_ack(data)
            elif name == "game_over":
                self.game_over = True
                self.winner = data.get("winner")
                self.status_text = self.net.status
            elif name == "error":
                self.status_text = self.net.status
            elif name == "match_timeout":
                self.status_text = self.net.status
            elif name == "connected":
                self.status_text = self.net.status

    def on_mouse_click(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        if self.screen == SCREEN_LOGIN:
            if _point_in_rect(x, y, BTN_LOGIN):
                self._try_login()
            elif 60 <= x <= 520 and 200 <= y <= 254:
                self.login_focus = "username"
            elif 60 <= x <= 520 and 270 <= y <= 324:
                self.login_focus = "password"
            return

        if self.screen == SCREEN_LOBBY:
            if _point_in_rect(x, y, BTN_PLAY):
                self.net.play()
                self.status_text = "Searching for opponent..."
            elif _point_in_rect(x, y, BTN_CANCEL):
                self.net.cancel_play()
                self.status_text = "Cancelled matchmaking"
            elif _point_in_rect(x, y, BTN_CREATE):
                self.net.create_room()
                self.status_text = "Creating room..."
            elif _point_in_rect(x, y, BTN_JOIN):
                self.join_room_id = ""
                self.screen = SCREEN_JOIN
                self.status_text = "Type room id and press Enter"
            return

        if self.screen == SCREEN_JOIN:
            if _point_in_rect(x, y, BTN_BACK):
                self.screen = SCREEN_LOBBY
                self.status_text = "Lobby"
            return

        if self.screen == SCREEN_GAME:
            if self.game_over:
                if _point_in_rect(x, y, BTN_BACK):
                    self._back_to_lobby()
                return
            if x >= self.renderer.board_width:
                return
            if self.mapper is None or self.board is None:
                return
            if self.net.role == "viewer":
                self.status_text = "Spectating — cannot move"
                return

            position = self.mapper.to_position(x, y)
            if position is None:
                return
            self._handle_board_click(position)

    def _handle_board_click(self, position: Position) -> None:
        row, col = position.row, position.col
        piece = self.board.get_piece(position)

        if self.selected is None:
            if piece is None:
                return
            if piece.status in (PieceStatus.MOVING, PieceStatus.JUMPING):
                self.status_text = "Piece is still moving"
                return
            if self.my_color and piece.color != self.my_color:
                self.status_text = "Not your piece"
                return
            self.selected = (row, col)
            return

        sel_row, sel_col = self.selected
        if (row, col) == (sel_row, sel_col):
            self.selected = None
            return

        if (
            piece is not None
            and self.my_color
            and piece.color == self.my_color
            and piece.status not in (PieceStatus.MOVING, PieceStatus.JUMPING)
        ):
            self.selected = (row, col)
            return

        start = (sel_row, sel_col)
        end = (row, col)
        self.net.send_move(start, end)
        self.status_text = f"Sent move {start} -> {end}"
        self.selected = None

    def _try_login(self) -> None:
        user = self.username.strip()
        if not user or not self.password:
            self.status_text = "Username and password required"
            return
        if not self.net.connected:
            self.status_text = "Not connected to server"
            return
        self.net.login(user, self.password)
        self.status_text = "Logging in..."

    def _handle_key(self, key: int) -> bool:
        """Returns True if the app should exit."""
        if key == 27:  # ESC
            return True

        if self.screen == SCREEN_GAME and self.game_over and key in (ord("b"), ord("B")):
            self._back_to_lobby()
            return False

        if self.screen == SCREEN_LOGIN:
            return self._handle_login_key(key)

        if self.screen == SCREEN_JOIN:
            return self._handle_join_key(key)

        return False

    def _handle_login_key(self, key: int) -> bool:
        if key in (13, 10):  # Enter
            if self.login_focus == "username":
                self.login_focus = "password"
            else:
                self._try_login()
            return False
        if key in (9,):  # Tab
            self.login_focus = (
                "password" if self.login_focus == "username" else "username"
            )
            return False
        if key in (8, 127):  # Backspace
            if self.login_focus == "username":
                self.username = self.username[:-1]
            else:
                self.password = self.password[:-1]
            return False
        if 32 <= key <= 126:
            ch = chr(key)
            if self.login_focus == "username":
                if len(self.username) < 24:
                    self.username += ch
            else:
                if len(self.password) < 32:
                    self.password += ch
        return False

    def _handle_join_key(self, key: int) -> bool:
        if key in (13, 10):
            room_id = self.join_room_id.strip()
            if not room_id:
                self.status_text = "Enter a room id"
                return False
            self.net.join_room(room_id)
            self.status_text = f"Joining room {room_id}..."
            return False
        if key in (8, 127):
            self.join_room_id = self.join_room_id[:-1]
            return False
        if 32 <= key <= 126:
            if len(self.join_room_id) < 16:
                self.join_room_id += chr(key)
        return False

    def _draw_frame(self):
        if self.screen == SCREEN_LOGIN:
            return self.renderer.render_menu(
                title="KungFu Chess",
                subtitle="Login to server",
                buttons=[(BTN_LOGIN, "Login")],
                status=self.status_text,
                fields=[
                    ("Username", self.username, self.login_focus == "username"),
                    ("Password", self.password, self.login_focus == "password"),
                ],
            )

        if self.screen == SCREEN_LOBBY:
            name = self.net.username or "?"
            elo = self.net.elo if self.net.elo is not None else "?"
            return self.renderer.render_menu(
                title="Lobby",
                subtitle=f"{name}  |  ELO {elo}",
                buttons=[
                    (BTN_PLAY, "Play (matchmaking)"),
                    (BTN_CANCEL, "Cancel queue"),
                    (BTN_CREATE, "Create room"),
                    (BTN_JOIN, "Join room"),
                ],
                status=self.status_text,
            )

        if self.screen == SCREEN_JOIN:
            return self.renderer.render_menu(
                title="Join Room",
                subtitle="Type room id, then Enter",
                buttons=[(BTN_BACK, "Back to lobby")],
                status=self.status_text,
                fields=[("Room ID", self.join_room_id, True)],
            )

        color = self.my_color or "?"
        room = self.net.room_id or "?"
        panel_lines = [
            f"You: {color}",
            f"Room: {room}",
            self.status_text[:24],
        ]
        if self.game_over:
            panel_lines.append("Click BACK / press B")

        canvas = self.renderer.render(
            self.board,
            motions=list(self.active_motions),
            selected_square=self.selected,
            scoreboard=self.score,
            game_over=self.game_over,
            winner=self.winner,
            panel_lines=panel_lines,
        )
        if self.game_over:
            self.renderer._draw_button(canvas, BTN_BACK, "Back to lobby")
        return canvas

    def run(self):
        window_name = "KungFu Chess Online"
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, self.on_mouse_click)

        print("\n" + "=" * 50)
        print("Online chess UI — make sure the server is running.")
        print("Login in the window, then use lobby buttons / board clicks.")
        print("Press ESC to exit.")
        print("=" * 50 + "\n")

        self.net.start()
        last_time = time.perf_counter()
        try:
            while True:
                now = time.perf_counter()
                dt_ms = int((now - last_time) * 1000)
                last_time = now

                self._process_network_events()
                if self.screen == SCREEN_GAME:
                    self._update_motions(dt_ms)

                canvas = self._draw_frame()
                cv2.imshow(window_name, canvas.img)

                key = cv2.waitKey(30) & 0xFF
                if key != 255 and self._handle_key(key):
                    break
        finally:
            self.net.stop()
            cv2.destroyAllWindows()
            print("Chess window closed successfully.")
