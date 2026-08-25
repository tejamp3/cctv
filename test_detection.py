import cv2
import sys
from ultralytics import YOLO

# Load a small pretrained YOLOv8 model (downloads automatically first run, ~6MB)
model = YOLO("yolov8n.pt")

# Video file to test — change this to "foot2.mp4" if needed
video_path = "foot1.mp4"

# Frame number to test — pass as command line arg, e.g. "python test_detection.py 150"
# If no argument given, defaults to 1/3 into the video
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print(f"ERROR: Could not open {video_path}")
    sys.exit()

total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

if len(sys.argv) > 1:
    target_frame = int(sys.argv[1])
else:
    target_frame = total_frames // 3

target_frame = max(0, min(target_frame, total_frames - 1))  # clamp to valid range

cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
ret, frame = cap.read()
cap.release()

if not ret:
    print("ERROR: Could not read frame")
    sys.exit()

print(f"Testing frame {target_frame} of {total_frames} from {video_path}")
print(f"Frame shape: {frame.shape}")

# Run YOLOv8 detection, filtering for 'person' class only (class 0 in COCO)
results = model(frame, classes=[0])

# Draw boxes on the frame
annotated_frame = results[0].plot()

# Save with the frame number in the filename so you don't overwrite previous tests
output_name = f"test_detection_frame{target_frame}.jpg"
cv2.imwrite(output_name, annotated_frame)

num_people = len(results[0].boxes)
print(f"Number of people detected: {num_people}")
print(f"Saved annotated image as {output_name}")