from transformers import pipeline
from pathlib import Path

print("Loading model...")
gender_classifier = pipeline("image-classification", model="NTQAI/pedestrian_gender_recognition")

crops_root = Path("crops_filtered")
image_files = sorted(crops_root.glob("*.jpg")) + sorted(crops_root.glob("*.png"))
test_images = image_files[:5]  # test on first 5 people

for img_path in test_images:
    result = gender_classifier(str(img_path))
    print(f"{img_path.name}:")
    for r in result:
        print(f"    {r['label']}: {r['score']:.3f}")
    print()