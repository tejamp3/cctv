"""Export the gender attribute from PA-100K into a YOLO ImageFolder dataset."""

import argparse
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.io import loadmat
from datasets import load_dataset


def first_value(annotation, names):
    for name in names:
        if name in annotation:
            return annotation[name]
    raise KeyError(f"Could not find any of {names} in annotation.mat")


def flatten_names(values):
    names = []
    for value in np.asarray(values).reshape(-1):
        if isinstance(value, np.ndarray):
            value = value.reshape(-1)[0]
        if isinstance(value, bytes):
            value = value.decode()
        names.append(str(value))
    return names


def export_split(image_root, output_root, split, image_names, labels, gender_index):
    split_output = output_root / split
    counts = {"male": 0, "female": 0}
    for image_name, row in zip(image_names, np.asarray(labels)):
        image_path = image_root / image_name
        if not image_path.is_file():
            raise FileNotFoundError(f"Missing PA-100K image: {image_path}")
        gender_value = int(np.asarray(row).reshape(-1)[gender_index])
        label = "female" if gender_value else "male"
        destination = split_output / label
        destination.mkdir(parents=True, exist_ok=True)
        with Image.open(image_path) as image:
            image.convert("RGB").save(destination / Path(image_name).name, quality=95)
        counts[label] += 1
    print(f"{split}: {counts}")


def export_huggingface(repo, output_root):
    for split in ("train", "val"):
        dataset = load_dataset(repo, split=split)
        split_output = output_root / split
        counts = {"male": 0, "female": 0}
        for row in dataset:
            label = "female" if int(row["Female"]) else "male"
            destination = split_output / label
            destination.mkdir(parents=True, exist_ok=True)
            image_name = Path(row["image_name"]).name
            row["image"].convert("RGB").save(destination / image_name, quality=95)
            counts[label] += 1
        print(f"{split}: {counts}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="gender_dataset/pa100k_raw", help="Extracted PA-100K directory")
    parser.add_argument("--output", default="gender_dataset/pa100k")
    parser.add_argument("--annotation", default=None, help="Path to annotation.mat; defaults to source/annotation.mat")
    parser.add_argument("--gender-index", type=int, default=0, help="PA-100K gender attribute column")
    parser.add_argument("--hf-repo", default=None, help="Hugging Face PA-100K repository, for example tuandunghcmut/PA-100K")
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    if output.exists():
        shutil.rmtree(output)

    if args.hf_repo:
        export_huggingface(args.hf_repo, output)
        print(f"Prepared PA-100K at {output}")
        return

    annotation_path = Path(args.annotation) if args.annotation else source / "annotation.mat"
    annotation = loadmat(annotation_path)
    image_root = source / "data"
    if not image_root.is_dir():
        image_root = source

    for split, image_keys, label_keys in (
        ("train", ("train_images_name", "train_im_names"), ("train_label", "train_labels")),
        ("val", ("val_images_name", "val_im_names"), ("val_label", "val_labels")),
    ):
        names = flatten_names(first_value(annotation, image_keys))
        labels = first_value(annotation, label_keys)
        export_split(image_root, output, split, names, labels, args.gender_index)
    print(f"Prepared PA-100K at {output}")


if __name__ == "__main__":
    main()