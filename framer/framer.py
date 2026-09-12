import cv2
import os

INPUT = "/Users/mass/Desktop/IA_THINKER/insta_scraper/downloads/DU3Rmy5Dvqf/video.mp4"
OUTPUT_DIR = "frames"

# Paramètres
MOTION_THRESHOLD = 0.02   # % de pixels considérés comme mouvement
PIXEL_THRESHOLD = 25      # différence minimale entre deux pixels
MIN_FRAME_GAP = 5         # nombre minimum de frames entre deux frames retenues

os.makedirs(OUTPUT_DIR, exist_ok=True)

cap = cv2.VideoCapture(INPUT)

if not cap.isOpened():
    raise RuntimeError("Impossible d'ouvrir la vidéo")

fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print(f"FPS : {fps}")
print(f"Frames : {total_frames}")

previous_gray = None
last_saved_frame = -MIN_FRAME_GAP

frame_number = 0
saved = 0

while True:

    ret, frame = cap.read()

    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Première frame
    if previous_gray is None:
        previous_gray = gray
        frame_number += 1
        continue

    # Différence entre frames
    diff = cv2.absdiff(previous_gray, gray)

    # Seuillage
    _, threshold = cv2.threshold(
        diff,
        PIXEL_THRESHOLD,
        255,
        cv2.THRESH_BINARY
    )

    # Pourcentage de pixels ayant bougé
    motion_ratio = cv2.countNonZero(threshold) / threshold.size

    # Frame intéressante ?
    if (
        motion_ratio > MOTION_THRESHOLD
        and frame_number - last_saved_frame >= MIN_FRAME_GAP
    ):

        filename = os.path.join(
            OUTPUT_DIR,
            f"frame_{frame_number:06d}.jpg"
        )

        cv2.imwrite(filename, frame)

        print(
            f"Frame {frame_number} | "
            f"temps={frame_number / fps:.2f}s | "
            f"mouvement={motion_ratio:.2%}"
        )

        last_saved_frame = frame_number
        saved += 1

    previous_gray = gray
    frame_number += 1

cap.release()

print()
print(f"Frames conservées : {saved}")