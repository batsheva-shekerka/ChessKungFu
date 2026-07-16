import os
import sys
import cv2
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from chessRender import ChessRenderer

try:
    from chess_io.board_parser import BoardParser
    HAS_REAL_MODEL = True
except ImportError:
    HAS_REAL_MODEL = False


class ChessGameController:
    """
    אחראית על מחזור החיים של המשחק:
    טוענת את input.txt, מחברת את המנוע והבקר הלוגי הקיימים,
    ומריצה את לולאת התצוגה בזמן-אמת.
    """
    def __init__(self):
        self.input_txt_path = os.path.join(ROOT_DIR, "input.txt")
        self.board = None
        self.engine = None
        self.input_controller = None

        self.load_board_from_file()

        self.renderer = ChessRenderer()

        # חיבור המנוע והבקר הלוגי הקיימים (רק אם נטען לוח אמיתי)
        if self.board is not None:
            from engine.game_engine import GameEngine
            from controller.controller import Controller
            self.engine = GameEngine(self.board)
            self.input_controller = Controller(self.engine)

   
    
    def load_board_from_file(self):
        """טעינת input.txt וסינון שורות הלוח בלבד עבור ה-Parser."""
        if not HAS_REAL_MODEL:
            return

        if not os.path.exists(self.input_txt_path):
            print(f"Warning: input.txt not found at {self.input_txt_path}.")
            return

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

            self.board = BoardParser.parse_initial_board(board_lines)
            print("Successfully loaded board from input.txt!")
        except Exception as e:
            print(f"Failed to parse input.txt: {e}")
            self.board = None

    def on_mouse_click(self, event, x, y, flags, param):
        """קליק שמאלי → העברת קואורדינטת הפיקסל לבקר הלוגי הקיים."""
        if event == cv2.EVENT_LBUTTONDOWN and self.input_controller is not None:
            self.input_controller.click(x, y)

    def run(self):
        """לולאת המשחק המרכזית (33 FPS), יציאה במקש ESC."""
        window_name = "Chess Live Engine"
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, self.on_mouse_click)

        print("\n" + "=" * 50)
        print("Game window running in real-time loop! (33 FPS)")
        print("Press the 'ESC' key inside the chess window to exit safely.")
        print("=" * 50 + "\n")

        last_time = time.perf_counter()
        while True:
            now = time.perf_counter()
            dt_ms = int((now - last_time) * 1000)
            last_time = now

            if self.engine is not None:
                self.engine.update_game_clock(dt_ms)
                current_board = self.engine.board
                motions = self.engine.arbiter.get_active_motions()
            else:
                current_board = self.board
                motions = []
            canvas = self.renderer.render(current_board, motions=motions, selected_square=self.input_controller.selected)
            cv2.imshow(window_name, canvas.img)

            if cv2.waitKey(30) == 27:
                break

        cv2.destroyAllWindows()
        print("Chess window closed successfully.")
