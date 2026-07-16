from __future__ import annotations

import pathlib

import cv2
import numpy as np

class Img:
    def __init__(self):
        self.img = None

    def read(self, path: str | pathlib.Path,
             size: tuple[int, int] | None = None,
             keep_aspect: bool = False,
             interpolation: int = cv2.INTER_AREA) -> "Img":
        """
        Load `path` into self.img and **optionally resize**.
        """
        path = str(path)
        
        try:
            self.img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        except Exception:
            self.img = None

        if self.img is None:
            raise FileNotFoundError(f"Cannot load image: {path}")

        if size is not None:
            target_w, target_h = size
            h, w = self.img.shape[:2]
            if keep_aspect:
                scale = min(target_w / w, target_h / h)
                new_w, new_h = int(w * scale), int(h * scale)
            else:
                new_w, new_h = target_w, target_h

            self.img = cv2.resize(self.img, (new_w, new_h), interpolation=interpolation)

        return self

    def draw_on(self, other_img, x, y):
        if self.img is None or other_img.img is None:
            raise ValueError("Both images must be loaded before drawing.")

        if self.img.shape[2] != other_img.img.shape[2]:
            if self.img.shape[2] == 3 and other_img.img.shape[2] == 4:
                self.img = cv2.cvtColor(self.img, cv2.COLOR_BGR2BGRA)
            elif self.img.shape[2] == 4 and other_img.img.shape[2] == 3:
                self.img = cv2.cvtColor(self.img, cv2.COLOR_BGRA2BGR)

        h, w = self.img.shape[:2]
        H, W = other_img.img.shape[:2]

        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(W, x + w)
        y1 = min(H, y + h)
        if x0 >= x1 or y0 >= y1:
            return

        src = self.img[(y0 - y):(y1 - y), (x0 - x):(x1 - x)]
        roi = other_img.img[y0:y1, x0:x1]

        if self.img.shape[2] == 4:
            mask = src[..., 3] / 255.0
            for c in range(3):
                roi[..., c] = (1 - mask) * roi[..., c] + mask * src[..., c]
        else:
            roi[:] = src

    def put_text(self, txt, x, y, font_size, color=(255, 255, 255, 255), thickness=1):
        if self.img is None:
            raise ValueError("Image not loaded.")
        cv2.putText(self.img, txt, (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, font_size,
                    color, thickness, cv2.LINE_AA)

    def show(self):
        if self.img is None:
            raise ValueError("Image not loaded.")
        cv2.imshow("Image", self.img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()