import cv2
import os
import numpy as np
import glob

crops_dir = "crops"
output_file = "contact_sheet.jpg"
thumb_size = 120  # each thumbnail will be 120x120

person_folders = sorted(
    [d for d in os.listdir(crops_dir) if os.path.isdir(os.path.join(crops_dir, d))],
    key=lambda x: int(x.split('_')[1])
)

thumbnails = []
labels = []

for folder in person_folders:
    folder_path = os.path.join(crops_dir, folder)
    images = glob.glob(os.path.join(folder_path, "*.jpg"))
    if not images:
        continue
    # Pick the middle image (often clearer than first frame)
    img_path = images[len(images) // 2]
    img = cv2.imread(img_path)
    if img is None:
        continue

    # Resize keeping aspect ratio, pad to square
    h, w = img.shape[:2]
    scale = thumb_size / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h))

    canvas = np.zeros((thumb_size, thumb_size, 3), dtype=np.uint8)
    y_off = (thumb_size - new_h) // 2
    x_off = (thumb_size - new_w) // 2
    canvas[y_off:y_off+new_h, x_off:x_off+new_w] = resized

    # Add label text (person ID + crop count) below thumbnail
    label_height = 25
    labeled_canvas = np.zeros((thumb_size + label_height, thumb_size, 3), dtype=np.uint8)
    labeled_canvas[0:thumb_size] = canvas
    label_text = f"{folder} ({len(images)})"
    cv2.putText(labeled_canvas, label_text, (2, thumb_size + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

    thumbnails.append(labeled_canvas)
    labels.append(folder)

print(f"Building contact sheet for {len(thumbnails)} people...")

cols = 10
rows = (len(thumbnails) + cols - 1) // cols
cell_h, cell_w = thumb_size + 25, thumb_size

sheet = np.zeros((rows * cell_h, cols * cell_w, 3), dtype=np.uint8)

for i, thumb in enumerate(thumbnails):
    r, c = i // cols, i % cols
    sheet[r*cell_h:(r+1)*cell_h, c*cell_w:(c+1)*cell_w] = thumb

cv2.imwrite(output_file, sheet)
print(f"Saved contact sheet as {output_file}")
print(f"Grid: {cols} columns x {rows} rows")