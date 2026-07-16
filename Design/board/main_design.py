import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from game_controller import ChessGameController

def main():
    try:
        controller = ChessGameController()
        controller.run()
    except Exception as e:
        print(f"Critical error running the game: {e}")

if __name__ == "__main__":
    main()