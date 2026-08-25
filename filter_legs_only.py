import cv2
import os
import glob
import shutil
import mediapipe as mp

crops_dir = "crops"
legs_only_dir = "legs_only_excluded"   # rejected folders get copied here (originals untouched)
good_dir = "crops_filtered"            # best crop of each "good" person copied here for next step

os.makedirs(legs_only_dir, exist_ok=True)
os.makedirs(good_dir, exist_ok=True)

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.4)

# Keypoints that indicate upper body is visible
UPPER_BODY_LANDMARKS = [
    mp_pose.PoseLandmark.LEFT_SHOULDER,
    mp_pose.PoseLandmark.RIGHT_SHOULDER,
    mp_pose.PoseLandmark.LEFT_HIP,
    mp_pose.PoseLandmark.RIGHT_HIP,
]
VISIBILITY_THRESHOLD = 0.5  # mediapipe visibility score per landmark


def pick_best_crop(folder_path):
    images = glob.glob(os.path.join(folder_path, "*.jpg"))
    if not images:
        return None
    best_path, best_area = None, 0
    for img_path in images:
        img = cv2.imread(img_path)
        if img is None:
            continue
        h, w = img.shape[:2]
        area = h * w
        if area > best_area:
            best_area = area
            best_path = img_path
    return best_path


def has_upper_body(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return False, 0
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = pose.process(img_rgb)
    if not results.pose_landmarks:
        return False, 0

    visible_count = 0
    for lm_id in UPPER_BODY_LANDMARKS:
        lm = results.pose_landmarks.landmark[lm_id]
        if lm.visibility >= VISIBILITY_THRESHOLD:
            visible_count += 1

    # Require at least 2 of the 4 upper-body points (e.g. both shoulders, or a shoulder+hip)
    return visible_count >= 2, visible_count


person_folders = sorted(
    [d for d in os.listdir(crops_dir) if os.path.isdir(os.path.join(crops_dir, d))],
    key=lambda x: int(x.split('_')[1])
)

good_count = 0
legs_only_count = 0
no_detection_count = 0

for folder in person_folders:
    folder_path = os.path.join(crops_dir, folder)
    best_crop = pick_best_crop(folder_path)

    if best_crop is None:
        print(f"{folder}: no images, skipping")
        continue

    is_good, visible_count = has_upper_body(best_crop)

    if is_good:
        shutil.copy2(best_crop, os.path.join(good_dir, f"{folder}.jpg"))
        good_count += 1
    else:
        shutil.copy2(best_crop, os.path.join(legs_only_dir, f"{folder}.jpg"))
        if visible_count == 0:
            no_detection_count += 1
        legs_only_count += 1

    print(f"{folder}: upper-body keypoints visible = {visible_count}/4 -> {'KEEP' if is_good else 'LEGS-ONLY'}")

pose.close()

print("\n--- Summary ---")
print(f"Total folders scanned: {len(person_folders)}")
print(f"Kept (upper body visible): {good_count}  -> saved in '{good_dir}'")
print(f"Excluded (legs-only / no upper body): {legs_only_count}  -> saved in '{legs_only_dir}'")
print(f"  (of which no pose detected at all: {no_detection_count})")
print(f"\nNext: review '{good_dir}' - these are your candidates for male/female labeling.")