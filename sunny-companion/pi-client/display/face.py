"""The talking face.

Deliberately geometry rather than sprite art. It has to animate at 30fps
on a Pi 3B while Vosk, Piper and the network compete for the same four
cores, and drawing two ellipses costs effectively nothing.

The states map to what the pipeline is genuinely doing -- idle, thinking,
searching, speaking -- so the face is never a decorative loop. If the
mouth is moving, audio is playing; if the dots are cycling, a request is
actually in flight. A face that animates regardless of state is worse
than no face, because it stops being information.
"""

import math

import pygame

WHITE = (240, 240, 240)
DIM = (120, 120, 120)
BLUE = (37, 150, 190)
YELLOW = (247, 209, 1)
ORANGE = (255, 140, 0)
IDLE_GREY = (60, 60, 60)

STATE_COLORS = {
    "idle": BLUE,
    "thinking": YELLOW,
    "searching": ORANGE,
    "speaking": BLUE,
}

STATE_LABELS = {
    "thinking": "thinking",
    "searching": "searching the web",
    "speaking": "speaking",
}


class Face:
    def __init__(self, display) -> None:
        self.d = display
        self.state = "idle"
        self.t = 0.0

    def set_state(self, state: str) -> None:
        if state != self.state:
            # Reset the clock on every transition so an animation always
            # starts at its beginning rather than mid-cycle.
            self.t = 0.0
            self.state = state

    def draw(self, dt: float) -> None:
        self.t += dt
        d = self.d
        w, h = d.size
        cx, cy = w // 2, int(h * 0.40)
        eye_dx = int(w * 0.16)
        eye_r = int(min(w, h) * 0.075)
        color = STATE_COLORS.get(self.state, BLUE)

        # A slow blink while idle, so a working device never reads as frozen.
        blink = self.state == "idle" and (self.t % 4.2) < 0.16
        squash = 0.12 if blink else 1.0

        for side in (-1, 1):
            rect = pygame.Rect(0, 0, eye_r * 2, max(2, int(eye_r * 2 * squash)))
            rect.center = (cx + side * eye_dx, cy)
            pygame.draw.ellipse(d.screen, color, rect)

        mouth_w = int(w * 0.26)
        mouth_y = cy + int(h * 0.15)

        if self.state == "speaking":
            # Amplitude stands in for speech. The exact shape matters far
            # less than the screen visibly responding while audio plays --
            # without it there is no way to tell playback from a hang.
            amp = (math.sin(self.t * 13) + 1) / 2
            mh = max(4, int(min(w, h) * (0.02 + 0.075 * amp)))
            pygame.draw.ellipse(
                d.screen, color,
                pygame.Rect(cx - mouth_w // 2, mouth_y - mh // 2, mouth_w, mh),
            )
        elif self.state in ("thinking", "searching"):
            lit = int((self.t * 3) % 4)
            for i in range(3):
                pygame.draw.circle(
                    d.screen, color if i < lit else IDLE_GREY,
                    (cx - int(w * 0.07) + i * int(w * 0.07), mouth_y),
                    max(2, int(min(w, h) * 0.018)),
                )
        else:
            pygame.draw.line(
                d.screen, color,
                (cx - mouth_w // 2, mouth_y), (cx + mouth_w // 2, mouth_y),
                max(3, int(min(w, h) * 0.012)),
            )

        label = STATE_LABELS.get(self.state)
        if label:
            d.text(label, d.f_small, DIM, w // 2, int(h * 0.74), center=True)
