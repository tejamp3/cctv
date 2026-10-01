"""WRN-16-8 face gender/age model from "Deep Learning based approach to detect
Customer Age, Gender and Expression in Surveillance Video" (Ijjina et al., ICCCNT 2020).

Pipeline in the paper: Haar cascade face detection -> 64x64 RGB face crop -> WRN-16-8
(depth 16, widening factor 8) -> gender (2 classes) + age (101 classes, 0-100).

Usage:
    # train (face crops in <data>/train|val/<male|female>/*.jpg)
    python wrn_gender.py train --data gender_dataset/faces --epochs 30 --device cuda
    # detect faces + predict gender on an image
    python wrn_gender.py predict --weights gender_models/wrn16_8_gender.pt --image test.jpg
"""

import argparse
from pathlib import Path

import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F

IMG_SIZE = 64
CLASSES = ["female", "male"]  # alphabetical, matches ImageFolder ordering


class BasicBlock(nn.Module):
    """Pre-activation wide residual block (BN-ReLU-Conv3x3 x2)."""

    def __init__(self, in_ch, out_ch, stride):
        super().__init__()
        self.bn1 = nn.BatchNorm2d(in_ch)
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, stride, 1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, 1, 1, bias=False)
        self.shortcut = None
        if stride != 1 or in_ch != out_ch:
            self.shortcut = nn.Conv2d(in_ch, out_ch, 1, stride, bias=False)

    def forward(self, x):
        o = F.relu(self.bn1(x))
        sc = self.shortcut(o) if self.shortcut is not None else x
        o = self.conv1(o)
        o = self.conv2(F.relu(self.bn2(o)))
        return o + sc


class WideResNet(nn.Module):
    """WRN-depth-k with two heads: gender (2) and age (101)."""

    def __init__(self, depth=16, k=8, num_ages=101):
        super().__init__()
        assert (depth - 4) % 6 == 0
        n = (depth - 4) // 6
        widths = [16, 16 * k, 32 * k, 64 * k]
        self.conv1 = nn.Conv2d(3, widths[0], 3, 1, 1, bias=False)
        layers, in_ch = [], widths[0]
        for i, w in enumerate(widths[1:]):
            for j in range(n):
                layers.append(BasicBlock(in_ch, w, 2 if (j == 0 and i > 0) else 1))
                in_ch = w
        self.blocks = nn.Sequential(*layers)
        self.bn = nn.BatchNorm2d(in_ch)
        self.gender = nn.Linear(in_ch, 2)
        self.age = nn.Linear(in_ch, num_ages)

    def forward(self, x):
        x = self.blocks(self.conv1(x))
        x = F.adaptive_avg_pool2d(F.relu(self.bn(x)), 1).flatten(1)
        return self.gender(x), self.age(x)


def preprocess(bgr_face):
    img = cv2.resize(bgr_face, (IMG_SIZE, IMG_SIZE))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return torch.from_numpy(img).permute(2, 0, 1).float().div(255.0)


def load_model(weights, device="cpu"):
    model = WideResNet().to(device)
    model.load_state_dict(torch.load(weights, map_location=device))
    return model.eval()


def haar_detector():
    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


@torch.no_grad()
def predict_faces(model, frame, detector, device="cpu", margin=0.4):
    """Returns [(x, y, w, h, gender, prob_male, age)] for each Haar-detected face."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    out = []
    for x, y, w, h in detector.detectMultiScale(gray, 1.1, 5, minSize=(24, 24)):
        m = int(margin * w)
        x0, y0 = max(x - m, 0), max(y - m, 0)
        x1, y1 = min(x + w + m, frame.shape[1]), min(y + h + m, frame.shape[0])
        t = preprocess(frame[y0:y1, x0:x1]).unsqueeze(0).to(device)
        g, a = model(t)
        p = F.softmax(g, 1)[0]
        ages = torch.arange(101, device=a.device).float()
        age = float((F.softmax(a, 1)[0] * ages).sum())  # expected age
        out.append((x, y, w, h, CLASSES[int(p.argmax())], float(p[1]), age))
    return out


def train(args):
    from torchvision import datasets, transforms

    tf_train = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.3, 0.3, 0.3),
        transforms.ToTensor(),
    ])
    tf_val = transforms.Compose([transforms.Resize((IMG_SIZE, IMG_SIZE)), transforms.ToTensor()])
    root = Path(args.data)
    tr = datasets.ImageFolder(root / "train", tf_train)
    va = datasets.ImageFolder(root / "val", tf_val)
    assert tr.classes == CLASSES, f"expected {CLASSES}, got {tr.classes}"
    dl_tr = torch.utils.data.DataLoader(tr, args.batch, shuffle=True, num_workers=args.workers)
    dl_va = torch.utils.data.DataLoader(va, args.batch, num_workers=args.workers)

    dev = args.device
    model = WideResNet().to(dev)
    # Paper trains with SGD-style WRN recipe; SGD + cosine LR + weight decay (Zagoruyko & Komodakis)
    opt = torch.optim.SGD(model.parameters(), lr=0.1, momentum=0.9, weight_decay=5e-4, nesterov=True)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.epochs)
    best = 0.0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for ep in range(args.epochs):
        model.train()
        for x, y in dl_tr:
            x, y = x.to(dev), y.to(dev)
            loss = F.cross_entropy(model(x)[0], y)
            opt.zero_grad()
            loss.backward()
            opt.step()
        sched.step()
        model.eval()
        conf = torch.zeros(2, 2, dtype=torch.long)  # rows=true, cols=pred
        with torch.no_grad():
            for x, y in dl_va:
                pred = model(x.to(dev))[0].argmax(1).cpu()
                for t, p in zip(y, pred):
                    conf[t, p] += 1
        acc = conf.diag().sum().item() / conf.sum().item()
        print(f"epoch {ep + 1}/{args.epochs} val_acc={acc:.4f} confusion(true x pred [female,male])={conf.tolist()}")
        if acc > best:
            best = acc
            torch.save(model.state_dict(), out)
    print(f"best val acc {best:.4f} -> {out}")


def predict(args):
    model = load_model(args.weights, args.device)
    frame = cv2.imread(args.image)
    for x, y, w, h, g, pm, age in predict_faces(model, frame, haar_detector(), args.device):
        print(f"face@({x},{y},{w},{h}) {g} (p_male={pm:.2f}) age~{age:.0f}")
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
        cv2.putText(frame, f"{g[0].upper()},{age:.0f}", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
    cv2.imwrite(args.output, frame)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--data", default="gender_dataset/faces")
    t.add_argument("--epochs", type=int, default=30)
    t.add_argument("--batch", type=int, default=128)
    t.add_argument("--workers", type=int, default=4)
    t.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    t.add_argument("--out", default="gender_models/wrn16_8_gender.pt")
    t.set_defaults(fn=train)
    q = sub.add_parser("predict")
    q.add_argument("--weights", default="gender_models/wrn16_8_gender.pt")
    q.add_argument("--image", required=True)
    q.add_argument("--output", default="wrn_out.jpg")
    q.add_argument("--device", default="cpu")
    q.set_defaults(fn=predict)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
