import os
import sys
import cv2
import time
import numpy as np

WHITE=(255,255,255,255)
YELLOW=(0, 220, 255, 255)
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
            raise FileNotFoundError(f"Error: Board background image not found at: {background_path}")
        
        
        self.background = Img().read(background_path, size=(800, 800), keep_aspect=False)
        h, w = self.background.img.shape[:2]

        self.board_width = w
        self.panel_width = 220
        self.square_size = w // 8
        
        
        self.pieces_dir = os.path.join(self.pictures_dir, "assets", "assets", "pieces_mine")
        print(f"Renderer using asset folder: {self.pieces_dir}")
        
        self.cached_sprites = {}
        self.cache_all_sprites()

    def cache_all_sprites(self):
        
        piece_types = ['P', 'R', 'N', 'B', 'Q', 'K']
        colors = ['w', 'b']
        states = ["idle", "move", "jump"]

        for p_type in piece_types:
            for col in colors:
                abbrev = f"{col}{p_type}" 
                
                for state in states:
                    frames = []
                    frame_num = 1
                    while True:
                        path = os.path.join(self.pieces_dir, abbrev, "states",
                                            state, "sprites", f"{frame_num}.png")
                        if not os.path.exists(path):
                            break
                        frames.append(Img().read(path, size=(self.square_size, self.square_size)))
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
            idx = min(idx, len(frames) - 1)   # נעצר בפריים האחרון
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

    def _draw_panel(self, canvas: Img, scoreboard) -> None:
        x = self.board_width + 10
        y = 35
        line_h = 22

        canvas.put_text("SCORE", x, y, 0.55, color=(100, 220, 255, 255), thickness=2)
        y += 28
        canvas.put_text(f"White: {scoreboard.plaier1_score}", x, y, 0.5,
                        color=WHITE, thickness=2)
        y += 28
        canvas.put_text(f"Black: {scoreboard.plaier2_score}", x, y, 0.5,
                        color=WHITE, thickness=2)

        y += 40
        canvas.put_text("WHITE MOVES", x, y, 0.45, color=(180, 180, 180, 255), thickness=1)
        y += line_h
        for move in scoreboard.plaier1_moves[-8:]:
            text = move if len(move) <= 22 else move[:19] + "..."
            canvas.put_text(text, x, y, 0.38, color=(210, 210, 210, 255), thickness=1)
            y += line_h

        y += 16
        canvas.put_text("BLACK MOVES", x, y, 0.45, color=(180, 180, 180, 255), thickness=1)
        y += line_h
        for move in scoreboard.plaier2_moves[-8:]:
            text = move if len(move) <= 22 else move[:19] + "..."
            canvas.put_text(text, x, y, 0.38, color=(210, 210, 210, 255), thickness=1)
            y += line_h

    def _draw_game_over(self, canvas: Img, winner: str) -> None:
        cv2.rectangle(canvas.img, (40, 280), (self.board_width - 40, 560),
                      (28, 25, 22, 255) if canvas.img.shape[2] == 4 else (22, 25, 28), -1)

        if winner == 'w':
            msg, sub = "White Wins!", "Congratulations White"
            sub_color = WHITE
        else:
            msg, sub = "Black Wins!", "Congratulations Black"
            sub_color = (210, 210, 210, 255)

        canvas.put_text(msg, 200, 360, 2.2, color=YELLOW, thickness=4)
        canvas.put_text(sub, 215, 430, 0.9, color=sub_color, thickness=2)
        canvas.put_text("Game Over", 280, 500, 1.0, color=WHITE, thickness=2)

    def render(self, board, motions=None, selected_square=None,
               scoreboard=None, game_over=False, winner=None) -> Img:
        """
        יוצרת קנבס חדש לגמרי בכל פריים, שואבת נתונים מהמודל ומציירת עליו את כל הכלים.
        """
        now = time.time()
        if motions is None:
            motions = []
        canvas = self._create_canvas()
        
        if board is None:
            canvas.put_text("Error: Board Not Loaded", 50, 100, 1.5, color=(0, 0, 255, 255), thickness=3)
            return canvas
            
        num_rows = getattr(board, 'num_rows', 8)
        num_cols = getattr(board, 'num_cols', 8)
        
        for row in range(num_rows):
            for col in range(num_cols):
                try:
                    pos = Position(row, col)
                    piece = board.get_piece(pos)
                    
                    if piece is not None:
                        if PieceStatus is not None and piece.status in (
                                PieceStatus.MOVING, PieceStatus.JUMPING, PieceStatus.CAPTURED):
                            continue
                        abbrev = str(piece.color).lower() + str(piece.piece_type).upper()

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

            abbrev = str(motion.piece.color).lower() + str(motion.piece.piece_type).upper()
            elapsed_sec = (motion.original_duration - motion.remaining_time) / 1000.0

            if motion.is_jump or (motion.start.row == motion.end.row and motion.start.col == motion.end.col):
                pixel_x = int(motion.start.col * self.square_size)
                lift = int(20 * (1 - abs(2 * progress - 1)))
                lift = min(lift, motion.start.row * self.square_size)
                pixel_y = int(motion.start.row * self.square_size) - lift
                sprite = self.pick_frame(abbrev, "jump", elapsed_sec, fps=10, loop=False)
            else:
                cur_row = motion.start.row + (motion.end.row - motion.start.row) * progress
                cur_col = motion.start.col + (motion.end.col - motion.start.col) * progress
                pixel_x = int(cur_col * self.square_size)
                pixel_y = int(cur_row * self.square_size)
                sprite = self.pick_frame(abbrev, "move", elapsed_sec, fps=8, loop=True)

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
                4
            )

        if scoreboard is not None:
            self._draw_panel(canvas, scoreboard)

        if game_over and winner is not None:
            self._draw_game_over(canvas, winner)
        else:
            canvas.put_text("KungFu Chess", 280, self.board_width - 15, 0.7,
                            color=(120, 255, 120, 255), thickness=2)

        return canvas