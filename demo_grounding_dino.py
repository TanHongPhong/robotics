import os
import torch
import numpy as np
from PIL import Image
from groundingdino.util.inference import load_model, load_image, predict, annotate

def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))

    config_path = os.path.join(current_dir, "groundingdino", "config", "GroundingDINO_SwinT_OGC.py")
    weights_path = os.path.join(current_dir, "weights", "groundingdino_swint_ogc.pth")
    image_path = os.path.join(current_dir, "input.jpg")

    if not os.path.exists(image_path):
        raise FileNotFoundError("Không tìm thấy input.jpg!")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Device đang dùng:", device)

    model = load_model(config_path, weights_path, device=device)
    image_source, image = load_image(image_path)

    text_prompt = "carton box"
    box_threshold = 0.3
    text_threshold = 0.25

    boxes, logits, phrases = predict(
        model=model,
        image=image,
        caption=text_prompt,
        box_threshold=box_threshold,
        text_threshold=text_threshold,
        device=device,
    )

    print("Số box detect được:", len(boxes))
    for p, l in zip(phrases, logits):
        print(p, float(l))

    annotated = annotate(
        image_source=np.asarray(image_source),
        boxes=boxes,
        logits=logits,
        phrases=phrases,
    )

    save_path = os.path.join(current_dir, "result.jpg")
    Image.fromarray(annotated).save(save_path)
    print("Đã lưu:", save_path)

if __name__ == "__main__":
    main()
