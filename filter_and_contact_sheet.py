import cv2
import os
import numpy as np
import glob

crops_dir = "."
output_file = "contact_sheet_filtered.jpg"
rejected_log = "rejected_folders.txt"
thumb_size = 120

# Aspect ratio bounds for a plausible upper/full body crop (height / width)
MIN_RATIO = 1.3   # below this -> too square/wide, likely junk box
MAX_RATIO = 3.0   # above this -> likely legs-only / too tall & narrow
MIN_AREA = 40 * 100  # discard tiny crops (width*height) - adjust if needed

def is_plausible_body(img):
    h, w = img.shape[:2]
    if w == 0 or h == 0:
        return False
    ratio = h / w
    area = h * w
    if area < MIN_AREA:
        return False
    return MIN_RATIO <= ratio <= MAX_RATIO

person_folders = sorted(
    [d for d in os.listdir(crops_dir) if os.path.isdir(os.path.join(crops_dir, d))],
    key=lambda x: int(x.split('_')[1])
)

thumbnails = []
rejected = []
kept_count = 0

for folder in person_folders:
    folder_path = os.path.join(crops_dir, folder)
    images = glob.glob(os.path.join(folder_path, "*.jpg"))
    if not images:
        rejected.append((folder, "no images found"))
        continue

    best_img = None
    best_area = 0

    for img_path in images:
        img = cv2.imread(img_path)
        if img is None:
            continue
        if not is_plausible_body(img):
            continue
        h, w = img.shape[:2]
        area = h * w
        if area > best_area:
            best_area = area
            best_img = img

    if best_img is None:
        rejected.append((folder, f"no plausible body crop among {len(images)} images"))
        continue

    kept_count += 1

    # Resize keeping aspect ratio, pad to square thumbnail
    h, w = best_img.shape[:2]
    scale = thumb_size / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(best_img, (new_w, new_h))

    canvas = np.zeros((thumb_size, thumb_size, 3), dtype=np.uint8)
    y_off = (thumb_size - new_h) // 2
    x_off = (thumb_size - new_w) // 2
    canvas[y_off:y_off+new_h, x_off:x_off+new_w] = resized

    label_height = 25
    labeled_canvas = np.zeros((thumb_size + label_height, thumb_size, 3), dtype=np.uint8)
    labeled_canvas[0:thumb_size] = canvas
    label_text = f"{folder} ({len(images)})"
    cv2.putText(labeled_canvas, label_text, (2, thumb_size + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

    thumbnails.append(labeled_canvas)

print(f"Total folders scanned: {len(person_folders)}")
print(f"Folders with a usable body crop: {kept_count}")
print(f"Folders rejected (no usable crop): {len(rejected)}")

# Write rejected log
with open(rejected_log, "w") as f:
    for folder, reason in rejected:
        f.write(f"{folder}: {reason}\n")
print(f"Rejected folder list saved to {rejected_log}")

if not thumbnails:
    print("No usable crops found at all — check MIN_RATIO/MAX_RATIO/MIN_AREA settings or your crop pipeline.")
else:
    cols = 10
    rows = (len(thumbnails) + cols - 1) // cols
    cell_h, cell_w = thumb_size + 25, thumb_size

    sheet = np.zeros((rows * cell_h, cols * cell_w, 3), dtype=np.uint8)

    for i, thumb in enumerate(thumbnails):
        r, c = i // cols, i % cols
        sheet[r*cell_h:(r+1)*cell_h, c*cell_w:(c+1)*cell_w] = thumb

    cv2.imwrite(output_file, sheet)
    print(f"Saved filtered contact sheet as {output_file}")
    print(f"Grid: {cols} columns x {rows} rows")