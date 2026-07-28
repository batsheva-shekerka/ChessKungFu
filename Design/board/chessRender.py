import os
import sys
import cv2
import time
import numpy as np

WHITE = (255, 255, 255, 255)
YELLOW = (0, 220, 255, 255)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from img import Img

try:
    from model.position import Position
    from model.piece import PieceStatus
    HAS_REAL_MODEL = True
except ImportError:
    HAS_REAL_MODEL = False
    PieceStatus = None

    class Position:
        def __init__(self, row: int, col: int):
            self.row = row
            self.col = col


class ChessRenderer:
    """
    מחלקה האחראית אך ורק על הציור והגרפיקה של המשחק (View).
    היא טוענת את קובצי הגרפיקה פעם אחת לזיכרון (Caching) ומציירת פריימים נקיים.
    """

    def __init__(self):
        self.pictures_dir = os.path.abspath(os.path.join(CURRENT_DIR, "..", "pictures"))

        background_path = os.path.join(self.pictures_dir, "board.png")
        if not os.path.exists(background_path):
            raise FileNotFoundError(
                f"Error: Board background image not found at: {background_path}"
            )

        self.background = Img().read(background_path, size=(800, 800), keep_aspect=False)
        h, w = self.background.img.shape[:2]

        self.board_width = w
        self.panel_width = 220
        self.square_size = w // 8

        self.pieces_dir = os.path.join(
            self.pictures_dir, "assets", "assets", "pieces_mine"
        )
        print(f"Renderer using asset folder: {self.pieces_dir}")

        self.cached_sprites = {}
        self.cache_all_sprites()

    def cache_all_sprites(self):
        piece_types = ["P", "R", "N", "B", "Q", "K"]
        colors = ["w", "b"]
        states = ["idle", "move", "jump"]

        for p_type in piece_types:
            for col in colors:
                abbrev = f"{col}{p_type}"

                for state in states:
                    frames = []
                    frame_num = 1
                    while True:
                        path = os.path.join(
                            self.pieces_dir,
                            abbrev,
                            "states",
                            state,
                            "sprites",
                            f"{frame_num}.png",
                        )
                        if not os.path.exists(path):
                            break
                        frames.append(
                            Img().read(path, size=(self.square_size, self.square_size))
                        )
                        frame_num += 1
                    if frames:
                        self.cached_sprites[(abbrev, state)] = frames

    def pick_frame(self, abbrev, state, elapsed_sec, fps=6, loop=True):
        frames = self.cached_sprites.get((abbrev, state))
        if not frames:
            frames = self.cached_sprites.get((abbrev, "idle"))
        if not frames:
            return None
        idx = int(elapsed_sec * fps)
        if loop:
            idx = idx % len(frames)
        else:
            idx = min(idx, len(frames) - 1)
        return frames[idx]

    def _create_canvas(self) -> Img:
        """בונה קנבס רחב: לוח משמאל + פאנל מידע מימין."""
        canvas = Img()
        board_img = self.background.img.copy()
        h, w = board_img.shape[:2]
        channels = board_img.shape[2] if len(board_img.shape) == 3 else 1
        total_w = w + self.panel_width

        wide = np.zeros((h, total_w, channels), dtype=np.uint8)
        wide[:, :w] = board_img

        if channels == 4:
            wide[:, w:, 0] = 32
            wide[:, w:, 1] = 32
            wide[:, w:, 2] = 38
            wide[:, w:, 3] = 255
        else:
            wide[:, w:] = (38, 32, 32)

        canvas.img = wide
        return canvas

    @staticmethod
    def _score_values(scoreboard):
        """Accepts Scoreboard object or dict like {'w': n, 'b': n}."""
        if scoreboard is None:
            return 0, 0, [], []
        if isinstance(scoreboard, dict):
            return (
                int(scoreboard.get("w", 0) or 0),
                int(scoreboard.get("b", 0) or 0),
                list(scoreboard.get("w_moves", []) or []),
                list(scoreboard.get("b_moves", []) or []),
            )
        return (
            getattr(scoreboard, "plaier1_score", 0),
            getattr(scoreboard, "plaier2_score", 0),
            list(getattr(scoreboard, "plaier1_moves", []) or []),
            list(getattr(scoreboard, "plaier2_moves", []) or []),
        )

    def _draw_panel(self, canvas: Img, scoreboard, extra_lines=None) -> None:
        x = self.board_width + 10
        y = 35
        line_h = 22
        white_score, black_score, white_moves, black_moves = self._score_values(
            scoreboard
        )

        canvas.put_text(
            "SCORE", x, y, 0.55, color=(100, 220, 255, 255), thickness=2
        )
        y += 28
        canvas.put_text(
            f"White: {white_score}", x, y, 0.5, color=WHITE, thickness=2
        )
        y += 28
        canvas.put_text(
            f"Black: {black_score}", x, y, 0.5, color=WHITE, thickness=2
        )

        y += 40
        canvas.put_text(
            "WHITE MOVES", x, y, 0.45, color=(180, 180, 180, 255), thickness=1
        )
        y += line_h
        for move in white_moves[-8:]:
            text = move if len(move) <= 22 else move[:19] + "..."
            canvas.put_text(
                text, x, y, 0.38, color=(210, 210, 210, 255), thickness=1
            )
            y += line_h

        y += 16
        canvas.put_text(
            "BLACK MOVES", x, y, 0.45, color=(180, 180, 180, 255), thickness=1
        )
        y += line_h
        for move in black_moves[-8:]:
            text = move if len(move) <= 22 else move[:19] + "..."
            canvas.put_text(
                text, x, y, 0.38, color=(210, 210, 210, 255), thickness=1
            )
            y += line_h

        if extra_lines:
            y += 24
            for line in extra_lines:
                text = line if len(line) <= 24 else line[:21] + "..."
                canvas.put_text(
                    text, x, y, 0.38, color=(180, 220, 180, 255), thickness=1
                )
                y += line_h

    def _draw_game_over(self, canvas: Img, winner: str) -> None:
        cv2.rectangle(
            canvas.img,
            (40, 280),
            (self.board_width - 40, 560),
            (28, 25, 22, 255) if canvas.img.shape[2] == 4 else (22, 25, 28),
            -1,
        )

        if winner == "w":
            msg, sub = "White Wins!", "Congratulations White"
            sub_color = WHITE
        else:
            msg, sub = "Black Wins!", "Congratulations Black"
            sub_color = (210, 210, 210, 255)

        canvas.put_text(msg, 200, 360, 2.2, color=YELLOW, thickness=4)
        canvas.put_text(sub, 215, 430, 0.9, color=sub_color, thickness=2)
        canvas.put_text("Game Over", 280, 500, 1.0, color=WHITE, thickness=2)

    def render(
        self,
        board,
        motions=None,
        selected_square=None,
        scoreboard=None,
        game_over=False,
        winner=None,
        panel_lines=None,
    ) -> Img:
        """
        יוצרת קנבס חדש לגמרי בכל פריים, שואבת נתונים מהמודל ומציירת עליו את כל הכלים.
        """
        now = time.time()
        if motions is None:
            motions = []
        canvas = self._create_canvas()

        if board is None:
            canvas.put_text(
                "Error: Board Not Loaded",
                50,
                100,
                1.5,
                color=(0, 0, 255, 255),
                thickness=3,
            )
            return canvas

        num_rows = getattr(board, "num_rows", 8)
        num_cols = getattr(board, "num_cols", 8)

        for row in range(num_rows):
            for col in range(num_cols):
                try:
                    pos = Position(row, col)
                    piece = board.get_piece(pos)

                    if piece is not None:
                        # Skip animating pieces only when motion list drives draw.
                        if (
                            motions
                            and PieceStatus is not None
                            and piece.status
                            in (
                                PieceStatus.MOVING,
                                PieceStatus.JUMPING,
                                PieceStatus.CAPTURED,
                            )
                        ):
                            continue
                        abbrev = (
                            str(piece.color).lower() + str(piece.piece_type).upper()
                        )

                        sprite = self.pick_frame(abbrev, "idle", now)
                        if sprite is not None:
                            pixel_x = col * self.square_size
                            pixel_y = row * self.square_size
                            sprite.draw_on(canvas, pixel_x, pixel_y)
                except Exception:
                    pass

        for motion in motions:
            duration = motion.original_duration
            if duration <= 0:
                progress = 1.0
            else:
                progress = 1 - motion.remaining_time / duration
            progress = max(0.0, min(1.0, progress))

            abbrev = (
                str(motion.piece.color).lower()
                + str(motion.piece.piece_type).upper()
            )
            elapsed_sec = (motion.original_duration - motion.remaining_time) / 1000.0

            if motion.is_jump or (
                motion.start.row == motion.end.row
                and motion.start.col == motion.end.col
            ):
                pixel_x = int(motion.start.col * self.square_size)
                lift = int(20 * (1 - abs(2 * progress - 1)))
                lift = min(lift, motion.start.row * self.square_size)
                pixel_y = int(motion.start.row * self.square_size) - lift
                sprite = self.pick_frame(
                    abbrev, "jump", elapsed_sec, fps=10, loop=False
                )
            else:
                cur_row = motion.start.row + (
                    motion.end.row - motion.start.row
                ) * progress
                cur_col = motion.start.col + (
                    motion.end.col - motion.start.col
                ) * progress
                pixel_x = int(cur_col * self.square_size)
                pixel_y = int(cur_row * self.square_size)
                sprite = self.pick_frame(
                    abbrev, "move", elapsed_sec, fps=8, loop=True
                )

            if sprite is not None:
                sprite.draw_on(canvas, pixel_x, pixel_y)

        if selected_square is not None:
            sel_row, sel_col = selected_square
            pixel_x = sel_col * self.square_size
            pixel_y = sel_row * self.square_size
            cv2.rectangle(
                canvas.img,
                (pixel_x, pixel_y),
                (pixel_x + self.square_size, pixel_y + self.square_size),
                (0, 255, 0, 255),
                4,
            )

        if scoreboard is not None or panel_lines:
            self._draw_panel(canvas, scoreboard or {}, extra_lines=panel_lines)

        if game_over and winner is not None:
            self._draw_game_over(canvas, winner)
        else:
            canvas.put_text(
                "KungFu Chess",
                280,
                self.board_width - 15,
                0.7,
                color=(120, 255, 120, 255),
                thickness=2,
            )

        return canvas

    def _draw_button(self, canvas: Img, rect, label: str) -> None:
        x1, y1, x2, y2 = rect
        fill = (48, 48, 58, 255)
        if canvas.img.shape[2] == 3:
            fill = fill[:3]
        cv2.rectangle(canvas.img, (x1, y1), (x2, y2), fill, -1)
        cv2.rectangle(canvas.img, (x1, y1), (x2, y2), (180, 220, 180, 255), 2)
        text_x = x1 + 18
        text_y = y1 + ((y2 - y1) // 2) + 8
        canvas.put_text(label, text_x, text_y, 0.7, color=WHITE, thickness=2)

    def render_menu(
        self,
        title: str,
        subtitle: str,
        buttons: list,
        status: str = "",
        fields=None,
    ) -> Img:
        """Full-screen menu (login / lobby) drawn over the board background."""
        canvas = self._create_canvas()
        overlay = canvas.img
        dim = (18, 18, 22, 220) if overlay.shape[2] == 4 else (22, 18, 18)
        cv2.rectangle(
            overlay, (0, 0), (self.board_width + self.panel_width, 800), dim, -1
        )

        canvas.put_text(title, 60, 90, 1.4, color=YELLOW, thickness=3)
        canvas.put_text(subtitle, 60, 140, 0.7, color=WHITE, thickness=2)

        y = 200
        if fields:
            for label, value, focused in fields:
                x1, y1, x2, y2 = (60, y, 520, y + 54)
                border = (0, 220, 255, 255) if focused else (140, 140, 140, 255)
                fill = (40, 40, 48, 255)
                if overlay.shape[2] == 3:
                    fill = fill[:3]
                    border = border[:3]
                cv2.rectangle(overlay, (x1, y1), (x2, y2), fill, -1)
                cv2.rectangle(overlay, (x1, y1), (x2, y2), border, 2)
                shown = (
                    value
                    if (label != "Password" or not value)
                    else ("*" * len(value))
                )
                canvas.put_text(
                    f"{label}: {shown}",
                    x1 + 14,
                    y1 + 36,
                    0.65,
                    color=WHITE,
                    thickness=2,
                )
                y += 70

        for rect, label in buttons:
            self._draw_button(canvas, rect, label)

        if status:
            canvas.put_text(
                status[:70],
                60,
                760,
                0.55,
                color=(180, 220, 180, 255),
                thickness=1,
            )
        return canvas
