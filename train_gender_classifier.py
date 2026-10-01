"""Train a YOLOv8 image classifier on a prepared two-class image dataset."""

import argparse

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="gender_dataset/pa100k")
    parser.add_argument("--model", default="yolov8n-cls.pt")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--fraction", type=float, default=1.0, help="Fraction of each split to use")
    parser.add_argument("--device", default=None, help="Set to 0 for CUDA or cpu explicitly")
    parser.add_argument("--resume", action="store_true", help="Resume from runs/gender/pa100k_yolov8n_cls/weights/last.pt")
    args = parser.parse_args()
    if args.resume:
        YOLO("runs/gender/pa100k_yolov8n_cls/weights/last.pt").train(resume=True)
        return
    model = YOLO(args.model)
    train_args = {
        "data": args.data,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "fraction": args.fraction,
        "project": "runs/gender",
        "name": "pa100k_yolov8n_cls",
    }
    if args.device:
        train_args["device"] = args.device
    model.train(**train_args)


if __name__ == "__main__":
    main()