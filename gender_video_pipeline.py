"""
gender_video_pipeline.py

Runs the full pipeline on a video and writes an annotated ("boxed") output video:
  1. YOLOv8 detects + tracks people frame-by-frame (persistent IDs).
  2. Every N frames, each tracked person's current crop is classified by the
     local gender classifier (see --gender-model, default
     gender_models/pa100k_yolov8n_cls.pt — a YOLOv8-nano classifier trained
     on PA-100K; see train_gender_classifier.py).
  3. Predictions per track are averaged over time so the label doesn't flicker.
  4. Every frame gets boxes drawn + label (Male/Female + confidence) for each
     currently-tracked person, and is written to an output video file.

Usage:
    python gender_video_pipeline.py --video path/to/video.mp4 --output out.mp4

Dependencies are listed in requirements.txt (install with
`pip install -r requirements.txt`).
"""

import argparse
import collections
import json
import sys

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    print("ERROR: ultralytics not installed. Run: pip install ultralytics")
    sys.exit(1)

from PIL import Image


def parse_args():
    p = argparse.ArgumentParser(description="Detect, track, classify gender, and box people in a video.")
    p.add_argument("--video", default="foot1.mp4", help="Path to input video")
    p.add_argument("--output", default="output_boxed.mp4", help="Path to write annotated output video")
    p.add_argument("--yolo-model", default="yolov8s.pt", help="YOLO weights (yolov8n.pt or yolov8s.pt)")
    p.add_argument("--gender-model", default="gender_models/pa100k_yolov8n_cls.pt", help="YOLO classification checkpoint for gender")
    p.add_argument("--conf", type=float, default=0.28, help="YOLO detection confidence threshold")
    p.add_argument("--imgsz", type=int, default=960, help="YOLO inference resolution for small and edge detections")
    p.add_argument("--classify-every", type=int, default=10,
                   help="Run gender classifier on each track once every N frames it's seen")
    p.add_argument("--min-w", type=int, default=12, help="Skip boxes narrower than this (pixels)")
    p.add_argument("--min-h", type=int, default=24, help="Skip boxes shorter than this (pixels)")
    p.add_argument("--line-y", type=int, default=None,
                   help="Horizontal footfall line y-coordinate; defaults to 40%% of frame height")
    p.add_argument("--entry-direction", choices=("negative-to-positive", "positive-to-negative"),
                   default="negative-to-positive",
                   help="Only count crossings in this signed line direction")
    p.add_argument("--line-margin", type=float, default=6.0,
                   help="Minimum signed distance on each side before a crossing counts")
    p.add_argument("--summary", default=None, help="Optional JSON summary output path")
    return p.parse_args()


def line_points(normal, offset, width, height):
    normal = np.asarray(normal, dtype=float)
    center = np.array([width / 2, height / 2], dtype=float)
    center = center + normal * (offset - np.dot(normal, center))
    direction = np.array([-normal[1], normal[0]], dtype=float)
    distance = np.hypot(width, height)
    first = center + direction * distance
    second = center - direction * distance
    return tuple(int(value) for value in np.round(first)), tuple(int(value) for value in np.round(second))


def line_side(point, normal, offset):
    return float(np.dot(normal, point) - offset)


def estimate_counting_line(yolo, cap, width, height, conf, total_frames):
    """Choose an angled line crossed by the most distinct tracked people."""
    trajectories = collections.defaultdict(list)
    sample_step = max(1, total_frames // 300)
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample_step == 0:
            results = yolo.track(frame, classes=[0], persist=True, verbose=False, conf=conf, imgsz=1280)
            if results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                track_ids = results[0].boxes.id.cpu().numpy().astype(int)
                for box, track_id in zip(boxes, track_ids):
                    x1, y1, x2, y2 = map(int, box)
                    if x2 - x1 >= 12 and y2 - y1 >= 24:
                        trajectories[track_id].append(((x1 + x2) // 2, (y1 + y2) // 2))
        frame_idx += 1

    diagonal = np.hypot(width, height)
    candidates = []
    for angle in np.arange(0, 180, 10):
        radians = np.deg2rad(angle)
        normal = np.array([np.cos(radians), np.sin(radians)])
        center_offset = np.dot(normal, np.array([width / 2, height / 2]))
        for offset in np.linspace(center_offset - diagonal * 0.35, center_offset + diagonal * 0.35, 25):
            candidates.append((normal, offset))

    best_line = (np.array([0.0, 1.0]), height * 0.4)
    best_score = 0
    for normal, offset in candidates:
        score = sum(
            any(
                (line_side(current, normal, offset) * line_side(previous, normal, offset) < 0)
                for previous, current in zip(positions, positions[1:])
            )
            for positions in trajectories.values()
            if len(positions) >= 3
        )
        if score > best_score:
            best_line, best_score = (normal, offset), score

    normal, offset = best_line
    if normal[1] < 0 or (abs(normal[1]) < 1e-6 and normal[0] < 0):
        best_line = (-normal, -offset)

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    points = line_points(*best_line, width, height)
    print(f"Automatic line calibration: {points[0]} -> {points[1]} with {best_score} crossing candidates")
    return best_line


def main():
    args = parse_args()

    print("Loading YOLO model...")
    yolo = YOLO(args.yolo_model)

    print(f"Loading gender classifier ({args.gender_model})...")
    gender_classifier = YOLO(args.gender_model)

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
    counting_line = (np.array([0.0, 1.0]), float(line_y))
    line_start, line_end = line_points(*counting_line, width, height)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(args.output, fourcc, fps, (width, height))

    # Per-track running state
    frames_seen = collections.defaultdict(int)          # track_id -> total frames seen
    last_seen_frame = {}
    female_prob_sum = collections.defaultdict(float)    # track_id -> accumulated female probability
    votes_count = collections.defaultdict(int)          # track_id -> number of classifier calls made
    current_label = {}                                  # track_id -> ("Female"/"Male", avg_conf)
    stable_side = {}
    counted_ids = set()
    crossed_down = 0
    male_count = 0
    female_count = 0

    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = yolo.track(frame, classes=[0], persist=True, verbose=False, conf=args.conf, imgsz=args.imgsz)

        cv2.line(frame, line_start, line_end, (0, 255, 255), 3)

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
                last_seen_frame[track_id] = frame_idx
                if frames_seen[track_id] < 3:
                    continue

                # Periodically (re)classify this track's current crop
                if frames_seen[track_id] == 3 or (frames_seen[track_id] > 3 and (frames_seen[track_id] - 3) % args.classify_every == 0):
                    padding_x = max(4, int((x2 - x1) * 0.08))
                    padding_y = max(4, int((y2 - y1) * 0.08))
                    crop_x1 = max(0, x1 - padding_x)
                    crop_y1 = max(0, y1 - padding_y)
                    crop_x2 = min(width, x2 + padding_x)
                    crop_y2 = min(height, y2 + padding_y)
                    crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]
                    lab_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
                    lab_l, lab_a, lab_b = cv2.split(lab_crop)
                    lab_l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab_l)
                    crop = cv2.cvtColor(cv2.merge((lab_l, lab_a, lab_b)), cv2.COLOR_LAB2BGR)
                    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(crop_rgb)
                    try:
                        result = gender_classifier(pil_img, verbose=False)[0]
                        scores = {
                            result.names[index].strip().lower(): float(score)
                            for index, score in enumerate(result.probs.data.tolist())
                        }
                        female_p = scores.get("female", 1 - scores.get("male", 0.0))
                        female_prob_sum[track_id] += female_p
                        votes_count[track_id] += 1
                        if votes_count[track_id] >= 1:
                            average_probability = female_prob_sum[track_id] / votes_count[track_id]
                            if average_probability >= 0.60:
                                current_label[track_id] = ("Female", average_probability)
                            elif average_probability <= 0.40:
                                current_label[track_id] = ("Male", 1 - average_probability)
                    except Exception as e:
                        print(f"Warning: classification failed for track {track_id}: {e}")

                center = ((x1 + x2) // 2, (y1 + y2) // 2)
                current_line_value = line_side(center, *counting_line)
                margin = args.line_margin
                current_stable_side = 1 if current_line_value >= margin else -1 if current_line_value <= -margin else None
                if current_stable_side is not None:
                    previous_stable_side = stable_side.get(track_id)
                    if previous_stable_side is not None and previous_stable_side != current_stable_side and track_id not in counted_ids:
                        entered = (
                            args.entry_direction == "negative-to-positive" and previous_stable_side < 0 and current_stable_side > 0
                        ) or (
                            args.entry_direction == "positive-to-negative" and previous_stable_side > 0 and current_stable_side < 0
                        )
                        if entered:
                            counted_ids.add(track_id)
                            crossed_down += 1
                            label = current_label.get(track_id, ("?", 0.0))[0]
                            if label == "Male":
                                male_count += 1
                            elif label == "Female":
                                female_count += 1
                    stable_side[track_id] = current_stable_side

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
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as summary_file:
            json.dump({
                "footfall": crossed_down,
                "male": male_count,
                "female": female_count,
                "tracked_people": len(frames_seen),
                "line_start": line_start,
                "line_end": line_end,
            }, summary_file)
    for track_id in sorted(frames_seen):
        label, conf = current_label.get(track_id, ("?", 0.0))
        print(f"  person_{track_id}: {frames_seen[track_id]} frames, final label = {label} ({conf:.2f})")


if __name__ == "__main__":
    main()