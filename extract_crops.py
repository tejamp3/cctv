import cv2
import os
from ultralytics import YOLO

video_path = "foot1.mp4"
output_dir = "crops"
sample_every_n_frames = 2      # was 5 — now catches brief/edge appearances
confidence_threshold = 0.15    # was default ~0.25 — catches partial/distant people

os.makedirs(output_dir, exist_ok=True)

model = YOLO("yolov8s.pt")     # was yolov8n.pt — better at small/partial detections

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print(f"ERROR: Could not open {video_path}")
    exit()

fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Video: {video_path} | FPS: {fps:.1f} | Total frames: {total_frames}")

frame_idx = 0
saved_count = 0
track_frame_counts = {}

while True:
    ret, frame = cap.read()
    if not ret:
        break

    if frame_idx % sample_every_n_frames == 0:
        results = model.track(
            frame, classes=[0], persist=True, verbose=False,
            conf=confidence_threshold
        )

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = map(int, box)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)

                if x2 <= x1 or y2 <= y1:
                    continue

                # Skip tiny detections (likely noise, not real people)
                if (x2 - x1) < 20 or (y2 - y1) < 40:
                    continue

                crop = frame[y1:y2, x1:x2].copy()

                track_dir = os.path.join(output_dir, f"person_{track_id}")
                os.makedirs(track_dir, exist_ok=True)

                count = track_frame_counts.get(track_id, 0)
                crop_filename = os.path.join(track_dir, f"frame{frame_idx}_{count}.jpg")
                cv2.imwrite(crop_filename, crop)

                track_frame_counts[track_id] = count + 1
                saved_count += 1

    frame_idx += 1
    if frame_idx % 500 == 0:
        print(f"Processed {frame_idx}/{total_frames} frames...")

cap.release()

print(f"\nDone. Saved {saved_count} crops across {len(track_frame_counts)} tracked people.")
print(f"Crops saved in: {output_dir}/")
for track_id, count in sorted(track_frame_counts.items()):
    print(f"  person_{track_id}: {count} crops")