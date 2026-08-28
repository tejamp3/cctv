"""
gender_video_pipeline.py

Runs the full pipeline on a video and writes an annotated ("boxed") output video:
  1. YOLOv8 detects + tracks people frame-by-frame (persistent IDs, same as extract_crops.py)
  2. Every N frames, each tracked person's current crop is classified by the
     HF gender model (NTQAI/pedestrian_gender_recognition)
  3. Predictions per track are averaged over time so the label doesn't flicker
  4. Every frame gets boxes drawn + label (Male/Female + confidence) for each
     currently-tracked person, and is written to an output video file.

Usage:
    python gender_video_pipeline.py --video foot1.mp4 --output foot1_boxed.mp4

Drop this file in the same folder as extract_crops.py / yolov8s.pt in your repo
and run it in your existing `gender-classifier` conda env (it already has
ultralytics-compatible deps: torch, transformers, opencv-python-headless).

If `ultralytics` isn't installed yet:
    pip install ultralytics
"""

import argparse
import collections
import sys

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    print("ERROR: ultralytics not installed. Run: pip install ultralytics")
    sys.exit(1)

try:
    from transformers import pipeline
except ImportError:
    print("ERROR: transformers not installed. Run: pip install transformers")
    sys.exit(1)

from PIL import Image


def parse_args():
    p = argparse.ArgumentParser(description="Detect, track, classify gender, and box people in a video.")
    p.add_argument("--video", default="foot1.mp4", help="Path to input video")
    p.add_argument("--output", default="output_boxed.mp4", help="Path to write annotated output video")
    p.add_argument("--yolo-model", default="yolov8s.pt", help="YOLO weights (yolov8n.pt or yolov8s.pt)")
    p.add_argument("--conf", type=float, default=0.15, help="YOLO detection confidence threshold")
    p.add_argument("--classify-every", type=int, default=10,
                   help="Run gender classifier on each track once every N frames it's seen")
    p.add_argument("--min-w", type=int, default=20, help="Skip boxes narrower than this (pixels)")
    p.add_argument("--min-h", type=int, default=40, help="Skip boxes shorter than this (pixels)")
    p.add_argument("--line-y", type=int, default=None,
                   help="Horizontal footfall line y-coordinate; defaults to 40%% of frame height")
    return p.parse_args()


def main():
    args = parse_args()

    print("Loading YOLO model...")
    yolo = YOLO(args.yolo_model)

    print("Loading gender classifier (NTQAI/pedestrian_gender_recognition)...")
    gender_classifier = pipeline("image-classification", model="NTQAI/pedestrian_gender_recognition")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: could not open video {args.video}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {args.video} | {width}x{height} | {fps:.1f} fps | {total_frames} frames")

    line_y = args.line_y if args.line_y is not None else int(height * 0.4)
    if not 0 < line_y < height:
        print(f"ERROR: --line-y must be between 0 and {height}")
        sys.exit(1)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(args.output, fourcc, fps, (width, height))

    # Per-track running state
    frames_seen = collections.defaultdict(int)          # track_id -> total frames seen
    female_prob_sum = collections.defaultdict(float)    # track_id -> sum of female probability
    votes_count = collections.defaultdict(int)          # track_id -> number of classifier calls made
    current_label = {}                                  # track_id -> ("Female"/"Male", avg_conf)
    previous_side = {}
    counted_ids = set()
    crossed_down = 0
    male_count = 0
    female_count = 0

    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = yolo.track(frame, classes=[0], persist=True, verbose=False, conf=args.conf)

        cv2.line(frame, (0, line_y), (width, line_y), (0, 255, 255), 3)

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = map(int, box)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(width, x2), min(height, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                if (x2 - x1) < args.min_w or (y2 - y1) < args.min_h:
                    continue

                frames_seen[track_id] += 1

                current_side = ((y1 + y2) // 2) >= line_y
                if track_id in previous_side and track_id not in counted_ids:
                    if previous_side[track_id] != current_side:
                        if current_side:
                            counted_ids.add(track_id)
                            crossed_down += 1
                            label = current_label.get(track_id, ("?", 0.0))[0]
                            if label == "Male":
                                male_count += 1
                            elif label == "Female":
                                female_count += 1
                previous_side[track_id] = current_side

                # Periodically (re)classify this track's current crop
                if frames_seen[track_id] % args.classify_every == 1:
                    crop = frame[y1:y2, x1:x2]
                    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(crop_rgb)
                    try:
                        result = gender_classifier(pil_img)
                        scores = {r["label"]: r["score"] for r in result}
                        female_p = scores.get("Female", 0.0)
                        female_prob_sum[track_id] += female_p
                        votes_count[track_id] += 1

                        avg_female_p = female_prob_sum[track_id] / votes_count[track_id]
                        if avg_female_p >= 0.5:
                            current_label[track_id] = ("Female", avg_female_p)
                        else:
                            current_label[track_id] = ("Male", 1 - avg_female_p)
                    except Exception as e:
                        print(f"Warning: classification failed for track {track_id}: {e}")

                label, conf = current_label.get(track_id, ("?", 0.0))
                color = (203, 92, 232) if label == "Female" else (255, 140, 0)  # BGR: pink / orange-blue
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                text = f"ID{track_id} {label} {conf:.2f}"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 4, y1), color, -1)
                cv2.putText(frame, text, (x1 + 2, max(12, y1 - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        cv2.putText(frame,
                    f"Footfall: {crossed_down}  Male: {male_count}  Female: {female_count}",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

        writer.write(frame)
        frame_idx += 1
        if frame_idx % 200 == 0:
            print(f"Processed {frame_idx}/{total_frames} frames...")

    cap.release()
    writer.release()

    print(f"\nDone. Wrote annotated video to: {args.output}")
    print(f"Tracked {len(frames_seen)} people total.")
    print(f"Total footfall: {crossed_down}")
    print(f"Male: {male_count}")
    print(f"Female: {female_count}")
    for track_id in sorted(frames_seen):
        label, conf = current_label.get(track_id, ("?", 0.0))
        print(f"  person_{track_id}: {frames_seen[track_id]} frames, final label = {label} ({conf:.2f})")


if __name__ == "__main__":
    main()