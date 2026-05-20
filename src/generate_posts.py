import argparse
import csv
import json
import os
from collections import deque
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple

import requests
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None
try:
    import cv2
except Exception:
    cv2 = None


def load_config(config_path: Path) -> Dict:
    with config_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def get_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    if font_path.exists():
        return ImageFont.truetype(str(font_path), size=size)
    try:
        # Use a scalable fallback on Linux/HF so text size still respects `size`.
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def make_default_template(path: Path, occasion: str, canvas: Dict) -> None:
    ensure_dir(path.parent)
    img = Image.new("RGB", (canvas["width"], canvas["height"]), canvas.get("background_color", "#ffffff"))
    draw = ImageDraw.Draw(img)

    # Simple fallback visual so the pipeline works before final branded templates are added.
    header_color = "#ff8a65" if occasion == "birthday" else "#4fc3f7"
    draw.rectangle([(0, 0), (canvas["width"], 200)], fill=header_color)
    draw.text((40, 60), f"{occasion.upper()} POST TEMPLATE", fill="white", font=ImageFont.load_default())

    draw.rectangle([(340, 230), (740, 630)], outline="#777777", width=6)
    draw.text((460, 420), "PHOTO", fill="#777777", font=ImageFont.load_default())

    draw.rectangle([(120, 860), (960, 980)], outline="#777777", width=4)
    draw.text((430, 910), "NAME", fill="#777777", font=ImageFont.load_default())

    img.save(path)


def load_photo(photo_ref: str) -> Image.Image:
    photo_ref = (photo_ref or "").strip().strip('"').strip("'")
    if photo_ref.lower().startswith(("http://", "https://")):
        response = requests.get(photo_ref, timeout=20)
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGBA")

    local_path = Path(photo_ref)
    if not local_path.is_absolute():
        local_path = Path.cwd() / local_path

    if not local_path.exists():
        raise FileNotFoundError(f"Photo not found: {local_path}")

    return Image.open(local_path).convert("RGBA")


def cover_resize(
    image: Image.Image,
    target_w: int,
    target_h: int,
    focus_x: float = 0.5,
    focus_y: float = 0.5,
) -> Image.Image:
    src_w, src_h = image.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        # Crop width with configurable focal point.
        new_w = int(src_h * target_ratio)
        free_x = max(0, src_w - new_w)
        left = int(round(free_x * max(0.0, min(1.0, focus_x))))
        image = image.crop((left, 0, left + new_w, src_h))
    else:
        # Crop height with configurable focal point.
        new_h = int(src_w / target_ratio)
        free_y = max(0, src_h - new_h)
        top = int(round(free_y * max(0.0, min(1.0, focus_y))))
        image = image.crop((0, top, src_w, top + new_h))

    return image.resize((target_w, target_h), Image.Resampling.LANCZOS)


def contain_resize(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = image.size
    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))
    return image.resize((new_w, new_h), Image.Resampling.LANCZOS)


def trim_transparent_bounds(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        return image
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return image
    return image.crop(bbox)



def remove_background_from_borders(photo: Image.Image, tolerance: int = 42) -> Image.Image:
    arr = np.array(photo.convert("RGBA"))
    h, w, _ = arr.shape
    rgb = arr[:, :, :3]
    hsv = np.array(Image.fromarray(rgb, mode="RGB").convert("HSV"))
    hch = hsv[:, :, 0].astype(np.int16)
    sch = hsv[:, :, 1].astype(np.int16)
    vch = hsv[:, :, 2].astype(np.int16)

    # Red-wall background key (tight range to avoid removing skin tones).
    red_hue = (hch <= 12) | (hch >= 245)
    strong_sat = sch >= 95
    bright_enough = vch >= 45
    similar = red_hue & strong_sat & bright_enough

    visited = np.zeros((h, w), dtype=np.uint8)
    q = deque()
    for x in range(w):
        if similar[0, x]:
            q.append((0, x))
        if similar[h - 1, x]:
            q.append((h - 1, x))
    for y in range(h):
        if similar[y, 0]:
            q.append((y, 0))
        if similar[y, w - 1]:
            q.append((y, w - 1))

    while q:
        y, x = q.popleft()
        if visited[y, x] or (not similar[y, x]):
            continue
        visited[y, x] = 1
        if y > 0 and not visited[y - 1, x]:
            q.append((y - 1, x))
        if y < h - 1 and not visited[y + 1, x]:
            q.append((y + 1, x))
        if x > 0 and not visited[y, x - 1]:
            q.append((y, x - 1))
        if x < w - 1 and not visited[y, x + 1]:
            q.append((y, x + 1))

    alpha = arr[:, :, 3].copy()
    alpha[visited == 1] = 0
    out = Image.fromarray(np.dstack([arr[:, :, :3], alpha]).astype(np.uint8), mode="RGBA")
    out.putalpha(out.split()[3].filter(ImageFilter.GaussianBlur(radius=0.8)))
    return out


def remove_background_grabcut(photo: Image.Image) -> Image.Image:
    if cv2 is None:
        return photo
    rgb = np.array(photo.convert("RGB"))
    h, w = rgb.shape[:2]
    if h < 8 or w < 8:
        return photo
    mask = np.zeros((h, w), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    rect = (max(1, int(w * 0.03)), max(1, int(h * 0.03)), max(2, int(w * 0.94)), max(2, int(h * 0.94)))
    cv2.grabCut(rgb, mask, rect, bgd_model, fgd_model, 6, cv2.GC_INIT_WITH_RECT)
    alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.2)
    rgba = np.dstack([rgb, alpha])
    return Image.fromarray(rgba, mode="RGBA")


def remove_background_rembg(photo: Image.Image) -> Image.Image:
    if rembg_remove is None:
        return photo
    out = rembg_remove(photo.convert("RGBA")).convert("RGBA")
    if cv2 is None:
        return out

    arr = np.array(out)
    alpha = arr[:, :, 3]
    # Binarize alpha and keep only the largest connected foreground region.
    _, bin_alpha = cv2.threshold(alpha, 16, 255, cv2.THRESH_BINARY)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats((bin_alpha > 0).astype(np.uint8), 8)
    if num_labels > 1:
        # Skip background label 0.
        largest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        clean = np.where(labels == largest, 255, 0).astype(np.uint8)
    else:
        clean = bin_alpha

    # Smooth edge and close pinholes.
    kernel = np.ones((3, 3), np.uint8)
    clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, kernel, iterations=1)
    clean = cv2.GaussianBlur(clean, (0, 0), 0.8)
    arr[:, :, 3] = clean
    return Image.fromarray(arr, mode="RGBA")


def maybe_extract_subject(photo: Image.Image, template_size: Tuple[int, int], tcfg: Dict) -> Image.Image:
    mode = tcfg.get("source_mode", "auto")
    if mode in ("auto", "full_post"):
        pw, ph = photo.size
        tw, th = template_size
        same_ratio = abs((pw / ph) - (tw / th)) < 0.01
        similar_size = abs(pw - tw) <= max(10, int(tw * 0.05)) and abs(ph - th) <= max(10, int(th * 0.05))
        if mode == "full_post" or (mode == "auto" and same_ratio and similar_size):
            # For full composed poster inputs, extract the lower-left subject zone.
            box = tcfg.get("source_crop_box", {"x": 80, "y": 580, "width": 970, "height": 1260})
            x1 = max(0, int(box["x"]))
            y1 = max(0, int(box["y"]))
            x2 = min(pw, x1 + int(box["width"]))
            y2 = min(ph, y1 + int(box["height"]))
            photo = photo.crop((x1, y1, x2, y2))

    if tcfg.get("remove_background", False):
        method = tcfg.get("bg_method", "rembg")
        if method == "rembg":
            photo = remove_background_rembg(photo)
        elif method == "grabcut":
            photo = remove_background_grabcut(photo)
        else:
            photo = remove_background_from_borders(photo, int(tcfg.get("bg_tolerance", 45)))

    return photo


def paste_photo(
    base: Image.Image,
    person: Image.Image,
    photo_box: Dict,
    shape: str = "rectangle",
    fit_mode: str = "cover",
    anchor: str = "center",
) -> None:
    person = trim_transparent_bounds(person)
    top_pct = float(photo_box.get("photo_top_percent", 1.0))
    if top_pct < 1.0:
        pw, ph = person.size
        person = person.crop((0, 0, pw, max(1, int(ph * top_pct))))
    bw = int(photo_box["width"])
    bh = int(photo_box["height"])
    scale = float(photo_box.get("photo_scale", 1.0))
    scale = max(0.1, min(scale, 5.0))
    target_w = max(1, int(round(bw * scale)))
    target_h = max(1, int(round(bh * scale)))
    focus_x = float(photo_box.get("focus_x", 0.5))
    focus_y = float(photo_box.get("focus_y", 0.5))

    resized = (
        contain_resize(person, target_w, target_h)
        if fit_mode == "contain"
        else cover_resize(person, target_w, target_h, focus_x=focus_x, focus_y=focus_y)
    )

    x, y = int(photo_box["x"]), int(photo_box["y"])
    if anchor == "bottom_center":
        x = int(photo_box["x"]) + (bw - resized.width) // 2
        y = int(photo_box["y"]) + (bh - resized.height)
    elif anchor == "center":
        x = int(photo_box["x"]) + (bw - resized.width) // 2
        y = int(photo_box["y"]) + (bh - resized.height) // 2
    elif anchor == "top":
        x = int(photo_box["x"]) + (bw - resized.width) // 2
        y = int(photo_box["y"])

    x += int(photo_box.get("photo_offset_x", 0))
    y += int(photo_box.get("photo_offset_y", 0))

    # Compose into an explicit box layer so the result always matches the exact box size.
    bg_hex = photo_box.get("photo_bg_color", "")
    if bg_hex:
        from PIL import ImageColor
        r, g, b = ImageColor.getrgb(bg_hex)
        box_layer = Image.new("RGBA", (bw, bh), (r, g, b, 255))
    else:
        box_layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    local_x = x - int(photo_box["x"])
    local_y = y - int(photo_box["y"])
    box_layer.paste(resized, (local_x, local_y), resized if resized.mode == "RGBA" else None)

    if shape == "circle":
        # Keep existing transparency from pasted portrait and only clip to circle.
        circle_mask = Image.new("L", (bw, bh), 0)
        mdraw = ImageDraw.Draw(circle_mask)
        mdraw.ellipse((0, 0, bw - 1, bh - 1), fill=255)
        existing_alpha = box_layer.getchannel("A")
        clipped_alpha = ImageChops.multiply(existing_alpha, circle_mask)
        box_layer.putalpha(clipped_alpha)

    base.paste(box_layer, (int(photo_box["x"]), int(photo_box["y"])), box_layer)


def fit_name_font(draw: ImageDraw.ImageDraw, name: str, box: Dict, font_path: Path, max_size: int, min_size: int):
    for size in range(max_size, min_size - 1, -2):
        font = get_font(font_path, size)
        bbox = draw.textbbox((0, 0), name, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        if text_w <= box["width"] and text_h <= box["height"]:
            return font, text_w, text_h

    font = get_font(font_path, min_size)
    bbox = draw.textbbox((0, 0), name, font=font)
    return font, bbox[2] - bbox[0], bbox[3] - bbox[1]


def paste_logo(base: Image.Image, tcfg: Dict) -> None:
    logo_path_raw = (tcfg.get("logo_path") or "").strip()
    logo_box = tcfg.get("logo_box")
    if not logo_path_raw or not logo_box:
        return

    logo_path = Path(logo_path_raw)
    if not logo_path.is_absolute():
        logo_path = Path.cwd() / logo_path
    if not logo_path.exists():
        return

    logo = Image.open(logo_path).convert("RGBA")
    bw = max(1, int(logo_box["width"]))
    bh = max(1, int(logo_box["height"]))
    fitted = contain_resize(logo, bw, bh)

    layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    ox = (bw - fitted.width) // 2
    oy = (bh - fitted.height) // 2
    layer.paste(fitted, (ox, oy), fitted)
    base.paste(layer, (int(logo_box["x"]), int(logo_box["y"])), layer)


def sanitize_filename(value: str) -> str:
    keep = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        elif ch.isspace():
            keep.append("_")
    cleaned = "".join(keep).strip("_")
    return cleaned or "post"


def generate_one_post(row: Dict, config: Dict, output_root: Path) -> Tuple[bool, str]:
    occasion = (row.get("occasion") or "").strip().lower()
    name = (row.get("employee_name") or "").strip()
    photo_ref = (row.get("photo_path") or "").strip()
    date_str = (row.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()

    if occasion not in config["templates"]:
        return False, f"Invalid occasion '{occasion}'"
    if not name:
        return False, "Missing employee_name"
    if not photo_ref:
        return False, f"Missing photo_path for '{name}'"

    tcfg = config["templates"][occasion]
    template_path = Path(tcfg["path"])
    if not template_path.is_absolute():
        template_path = Path.cwd() / template_path

    if not template_path.exists():
        make_default_template(template_path, occasion, config["canvas"])

    base = Image.open(template_path).convert("RGBA")
    paste_logo(base, tcfg)

    photo_box = dict(tcfg["photo_box"])  # shallow copy so row override doesn't mutate config
    row_top_pct = (row.get("photo_top_percent") or "").strip()
    if row_top_pct:
        photo_box["photo_top_percent"] = float(row_top_pct)
    person = load_photo(photo_ref)
    person = maybe_extract_subject(person, base.size, tcfg)
    paste_photo(
        base,
        person,
        photo_box,
        tcfg.get("photo_shape", "rectangle"),
        tcfg.get("photo_fit", "cover"),
        tcfg.get("photo_anchor", "center"),
    )

    draw = ImageDraw.Draw(base)
    font_path = Path(tcfg.get("name_font_path", config.get("default_font_path", "")))
    if not font_path.is_absolute():
        font_path = Path.cwd() / font_path

    name_box = tcfg["name_box"]
    render_name = name.upper() if tcfg.get("name_uppercase", False) else name
    font, text_w, text_h = fit_name_font(
        draw,
        render_name,
        name_box,
        font_path,
        int(tcfg.get("max_font_size", 72)),
        int(tcfg.get("min_font_size", 32)),
    )

    align = tcfg.get("text_align", "center")
    if align == "left":
        tx = name_box["x"]
    elif align == "right":
        tx = name_box["x"] + name_box["width"] - text_w
    else:
        tx = name_box["x"] + (name_box["width"] - text_w) // 2

    ty = name_box["y"] + (name_box["height"] - text_h) // 2
    draw.text((tx, ty), render_name, fill=tcfg.get("name_color", "#111111"), font=font)

    out_dir = output_root / date_str
    ensure_dir(out_dir)

    safe_name = sanitize_filename(name)
    out_file = out_dir / f"{occasion}_{safe_name}.png"
    base.save(out_file, format=config["output"].get("image_format", "PNG"))
    return True, str(out_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate birthday/welcome posts from CSV input.")
    parser.add_argument("--config", default="config.json", help="Path to config JSON")
    parser.add_argument("--input", default="input/posts.csv", help="Path to CSV input")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    output_dir = Path(config["output"].get("directory", "output"))
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    ensure_dir(output_dir)

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path

    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    success = 0
    failed = 0
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            try:
                ok, message = generate_one_post(row, config, output_dir)
                if ok:
                    success += 1
                    print(f"[OK][line {i}] {message}")
                else:
                    failed += 1
                    print(f"[FAIL][line {i}] {message}")
            except Exception as exc:
                failed += 1
                print(f"[ERROR][line {i}] {exc}")

    print("-" * 50)
    print(f"Completed. Success: {success}, Failed: {failed}")


if __name__ == "__main__":
    main()
