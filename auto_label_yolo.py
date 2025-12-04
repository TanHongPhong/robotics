import os
import torch
import glob
import numpy as np
from PIL import Image

from groundingdino.util.inference import load_model, load_image, predict

ROOT = os.path.dirname(os.path.abspath(__file__))
DINO_DIR = os.path.join(ROOT, "GroundingDINO")
IMG_DIR = os.path.join(ROOT, "images")
LABEL_DIR = os.path.join(ROOT, "labels")
WEIGHTS = os.path.join(DINO_DIR, "weights", "groundingdino_swint_ogc.pth")
CONFIG = os.path.join(DINO_DIR, "groundingdino", "config", "GroundingDINO_SwinT_OGC.py")

os.makedirs(LABEL_DIR, exist_ok=True)

# ==== 12 CLASSES ====
CLASS_PROMPTS = {
    0: "blue crate with mini pepsi bottles . blue drink crate . blue beverage crate",
    1: "red coca cola crate with bottles . red drink crate . red beverage crate",

    2: "white noodle carton box pho tron acecook . pho tron box",
    3: "brown sukay carton box . sukay snack carton",
    4: "white blue pho xua nay carton . acecook pho xua nay box",

    5: "small kumquat bonsai tree with orange fruits . mini kumquat plant",
    6: "yellow apricot blossom bonsai tree . small mai flower plant",

    7: "black and red omachi noodle cup . omachi instant cup",
    8: "pink hao hao noodle cup . haohao instant noodle cup",

    9: "mini shopping cart . small supermarket trolley . metal shopping cart",

    10: "red snack gift pack . cosy pocky snack gift set . wrapped snack pack",
    11: "red snack gift bundle with choco pie . snack gift bag",
}

BOX_THR = 0.25
TEXT_THR = 0.25


def save_yolo_label(path, boxes, cls_id, w, h):
    with open(path, "a") as f:  # append for multiple classes
        for x1, y1, x2, y2 in boxes:
            xc = (x1 + x2) / 2 / w
            yc = (y1 + y2) / 2 / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            f.write(f"{cls_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Using:", device)

    model = load_model(CONFIG, WEIGHTS, device=device)

    images = sorted(glob.glob(os.path.join(IMG_DIR, "*.jpg")) +
                    glob.glob(os.path.join(IMG_DIR, "*.png")))

    print(f"Found {len(images)} images")

    for img_path in images:
        print("\nProcessing:", img_path)

        image_source, img_tensor = load_image(img_path)
        w, h = image_source.size

        base = os.path.splitext(os.path.basename(img_path))[0]
        label_path = os.path.join(LABEL_DIR, base + ".txt")

        # clear old label
        open(label_path, "w").close()

        # run each class separately
        for cls_id, prompt in CLASS_PROMPTS.items():
            boxes, logits, phrases = predict(
                model=model,
                image=img_tensor,
                caption=prompt,
                box_threshold=BOX_THR,
                text_threshold=TEXT_THR,
                device=device
            )

            boxes = boxes.numpy()
            if len(boxes) > 0:
                print(f"  -> Class {cls_id}: {len(boxes)} boxes")
                save_yolo_label(label_path, boxes, cls_id, w, h)

    print("\n===== AUTO LABEL DONE (12 classes) =====")


if __name__ == "__main__":
    main()
