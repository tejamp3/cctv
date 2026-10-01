import argparse
import sys

import cv2
from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(
        description="Count people crossing a horizontal line in a video."
    )
    parser.add_argument("--video", default="foot1.mp4", help="Input video path")
    parser.add_argument(
        "--output",
        default="foot1_footfall.mp4",
        help="Output annotated video path",
    )
    parser.add_argument(
        "--yolo-model",
        default="yolov8s.pt",
        help="YOLO weights, for example yolov8n.pt or yolov8s.pt",
    )
    parser.add_argument(
        "--line-y",
        type=int,
        default=None,
        help="Horizontal line y-coordinate in pixels; defaults to 40% of the frame height",
    )
    parser.add_argument(
        "--conf", type=float, default=0.30, help="Person detection confidence threshold"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    model = YOLO(args.yolo_model)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: could not open video {args.video}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    line_y = args.line_y if args.line_y is not None else int(height * 0.4)
    if not 0 < line_y < height:
        print(f"ERROR: --line-y must be between 0 and {height}")
        sys.exit(1)

    writer = cv2.VideoWriter(
        args.output,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )

    previous_side = {}
    counted_ids = set()
    crossed_down = 0
    crossed_up = 0
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model.track(
            frame,
            classes=[0],
            persist=True,
            verbose=False,
            conf=args.conf,
        )

        cv2.line(frame, (0, line_y), (width, line_y), (0, 255, 255), 3)

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = map(int, box)
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                current_side = center_y >= line_y

                if track_id in previous_side and track_id not in counted_ids:
                    if previous_side[track_id] != current_side:
                        counted_ids.add(track_id)
                        if current_side:
                            crossed_down += 1
                        else:
                            crossed_up += 1

                previous_side[track_id] = current_side
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)
                cv2.putText(
                    frame,
                    f"ID {track_id}",
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 200, 0),
                    2,
                )

        total_crossings = crossed_down
        cv2.putText(
            frame,
            f"Footfall: {total_crossings} ",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 255),
            2,
        )
        writer.write(frame)
        frame_idx += 1
        if frame_idx % 200 == 0:
            print(f"Processed {frame_idx}/{total_frames} frames...")

    cap.release()
    writer.release()
    print(f"\nDone. Wrote annotated video to: {args.output}")
    print(f"Total footfall: {crossed_down + crossed_up}")
    print(f"Crossed down: {crossed_down}")
    print(f"Crossed up: {crossed_up}")


if __name__ == "__main__":
    main()