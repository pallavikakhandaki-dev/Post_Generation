import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from src.generate_posts import fit_name_font, maybe_extract_subject, paste_photo


CONFIG_PATH = Path("config.json")


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_config(config_path: Path, config: dict) -> None:
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_font_safe(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    if font_path.exists():
        return ImageFont.truetype(str(font_path), size=size)
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def ordinal_parts(n: int) -> tuple[str, str]:
    text = ordinal(n)
    if len(text) >= 3:
        return text[:-2], text[-2:]
    return text, ""


def draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, x: int, y: int, max_width: int, fill: str, line_spacing: int = 10) -> int:
    lines = []
    for paragraph in text.splitlines():
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for w in words:
            trial = w if not current else f"{current} {w}"
            bbox = draw.textbbox((0, 0), trial, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)

    line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
    for i, line in enumerate(lines):
        draw.text((x, y + i * (line_h + line_spacing)), line, fill=fill, font=font)
    return y + len(lines) * (line_h + line_spacing)


def paste_logo_preview(base: Image.Image, tcfg: dict) -> None:
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
    logo.thumbnail((bw, bh), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    ox = (bw - logo.width) // 2
    oy = (bh - logo.height) // 2
    layer.paste(logo, (ox, oy), logo)
    base.paste(layer, (int(logo_box["x"]), int(logo_box["y"])), layer)


def render_preview(
    uploaded: BytesIO,
    employee_name: str,
    config: dict,
    occasion: str,
    photo_scale: float,
    photo_offset_x: int,
    photo_offset_y: int,
    photo_top_percent: float,
) -> Image.Image:
    tcfg = config["templates"][occasion]
    template_path = Path(tcfg["path"])
    if not template_path.is_absolute():
        template_path = Path.cwd() / template_path

    base = Image.open(template_path).convert("RGBA")
    paste_logo_preview(base, tcfg)
    person = Image.open(uploaded).convert("RGBA")
    person = maybe_extract_subject(person, base.size, tcfg)

    photo_box = dict(tcfg["photo_box"])
    photo_box["photo_scale"] = photo_scale
    photo_box["photo_offset_x"] = photo_offset_x
    photo_box["photo_offset_y"] = photo_offset_y
    photo_box["photo_top_percent"] = photo_top_percent

    paste_photo(
        base=base,
        person=person,
        photo_box=photo_box,
        shape=tcfg.get("photo_shape", "rectangle"),
        fit_mode=tcfg.get("photo_fit", "cover"),
        anchor=tcfg.get("photo_anchor", "center"),
    )

    draw = ImageDraw.Draw(base)
    font_path = Path(tcfg.get("name_font_path", config.get("default_font_path", "")))
    if not font_path.is_absolute():
        font_path = Path.cwd() / font_path

    name_box = tcfg["name_box"]
    render_name = employee_name.upper() if tcfg.get("name_uppercase", False) else employee_name
    font, text_w, text_h = fit_name_font(
        draw=draw,
        name=render_name,
        box=name_box,
        font_path=font_path,
        max_size=int(tcfg.get("max_font_size", 72)),
        min_size=int(tcfg.get("min_font_size", 32)),
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
    return base


def render_anniversary_preview(
    uploaded: BytesIO,
    employee_name: str,
    designation: str,
    years: int,
    config: dict,
    photo_scale: float,
    photo_offset_x: int,
    photo_offset_y: int,
    photo_top_percent: float,
):
    tcfg = config["templates"]["employee_anniversary"]
    template_path = Path(tcfg["path"])
    if not template_path.is_absolute():
        template_path = Path.cwd() / template_path

    base = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(base)

    person = Image.open(uploaded).convert("RGBA")
    person = maybe_extract_subject(person, base.size, tcfg)

    photo_box = dict(tcfg["photo_box"])
    photo_box["photo_scale"] = photo_scale
    photo_box["photo_offset_x"] = photo_offset_x
    photo_box["photo_offset_y"] = photo_offset_y
    photo_box["photo_top_percent"] = photo_top_percent

    paste_photo(
        base=base,
        person=person,
        photo_box=photo_box,
        shape=tcfg.get("photo_shape", "rectangle"),
        fit_mode=tcfg.get("photo_fit", "cover"),
        anchor=tcfg.get("photo_anchor", "center"),
    )

    font_path = Path(tcfg.get("name_font_path", config.get("default_font_path", "")))
    if not font_path.is_absolute():
        font_path = Path.cwd() / font_path

    # Heading ordinal (1ST, 2ND, ...)
    ord_box = tcfg["ordinal_box"]
    ord_num, ord_suffix = ordinal_parts(years)
    ord_font_size = int(tcfg.get("ordinal_font_size", 64))
    suffix_ratio = float(tcfg.get("ordinal_suffix_scale", 0.62))
    suffix_raise = int(tcfg.get("ordinal_suffix_raise", 12))
    suffix_gap = int(tcfg.get("ordinal_suffix_gap", 6))
    ord_font = get_font_safe(font_path, ord_font_size)
    ord_suffix_font = get_font_safe(font_path, max(10, int(ord_font_size * suffix_ratio)))

    num_bbox = draw.textbbox((0, 0), ord_num, font=ord_font)
    num_w = num_bbox[2] - num_bbox[0]
    num_h = num_bbox[3] - num_bbox[1]
    suf_bbox = draw.textbbox((0, 0), ord_suffix, font=ord_suffix_font)
    suf_w = suf_bbox[2] - suf_bbox[0]
    total_w = num_w + suffix_gap + suf_w
    ord_x = ord_box["x"] + (ord_box["width"] - total_w) // 2
    ord_y = ord_box["y"] + (ord_box["height"] - num_h) // 2

    draw.text((ord_x, ord_y), ord_num, fill=tcfg.get("ordinal_color", "#2f3137"), font=ord_font)
    if ord_suffix:
        draw.text(
            (ord_x + num_w + suffix_gap, ord_y - suffix_raise),
            ord_suffix,
            fill=tcfg.get("ordinal_color", "#2f3137"),
            font=ord_suffix_font,
        )

    # Name
    name_box = tcfg["name_box"]
    display_name = employee_name.upper() if tcfg.get("name_uppercase", False) else employee_name
    name_font, name_w, name_h = fit_name_font(
        draw=draw,
        name=display_name,
        box=name_box,
        font_path=font_path,
        max_size=int(tcfg.get("max_font_size", 68)),
        min_size=int(tcfg.get("min_font_size", 36)),
    )
    name_align = tcfg.get("name_align", "left")
    if name_align == "center":
        name_x = name_box["x"] + (name_box["width"] - name_w) // 2
    elif name_align == "right":
        name_x = name_box["x"] + name_box["width"] - name_w
    else:
        name_x = name_box["x"]
    name_y = name_box["y"] + (name_box["height"] - name_h) // 2
    draw.text((name_x, name_y), display_name, fill=tcfg.get("name_color", "#2f3137"), font=name_font)

    # Designation
    des_box = tcfg["designation_box"]
    des_font_path = Path(tcfg.get("designation_font_path", tcfg.get("name_font_path", config.get("default_font_path", ""))))
    if not des_font_path.is_absolute():
        des_font_path = Path.cwd() / des_font_path
    des_font = get_font_safe(des_font_path, int(tcfg.get("designation_font_size", 36)))
    des_text = designation.upper() if tcfg.get("designation_uppercase", False) else designation
    des_bbox = draw.textbbox((0, 0), des_text, font=des_font)
    des_w = des_bbox[2] - des_bbox[0]
    des_h = des_bbox[3] - des_bbox[1]
    des_align = tcfg.get("designation_align", "left")
    if des_align == "center":
        des_x = des_box["x"] + (des_box["width"] - des_w) // 2
    elif des_align == "right":
        des_x = des_box["x"] + des_box["width"] - des_w
    else:
        des_x = des_box["x"]
    des_y = des_box["y"] + (des_box["height"] - des_h) // 2
    draw.text((des_x, des_y), des_text, fill=tcfg.get("designation_color", "#2f3137"), font=des_font)

    # Description with year/years (optional; keep off when base template already has paragraph text)
    if tcfg.get("draw_description", False):
        first_line = f"Congratulations on completing {years} {'year' if years == 1 else 'years'} with THE STRELEMA..."
        rest_text = "Your commitment, consistency, and professionalism have played a meaningful role in our journey. Thank you for being an integral part of the team."
        desc_box = tcfg["description_box"]
        desc_font_size = int(tcfg.get("description_font_size", 22))
        desc_color = tcfg.get("description_color", "#ffffff")

        bold_font_path = Path(tcfg.get("description_bold_font_path", tcfg.get("description_font_path", tcfg.get("name_font_path", config.get("default_font_path", "")))))
        if not bold_font_path.is_absolute():
            bold_font_path = Path.cwd() / bold_font_path
        bold_font = get_font_safe(bold_font_path, desc_font_size)

        desc_font_path = Path(tcfg.get("description_font_path", tcfg.get("name_font_path", config.get("default_font_path", ""))))
        if not desc_font_path.is_absolute():
            desc_font_path = Path.cwd() / desc_font_path
        desc_font = get_font_safe(desc_font_path, desc_font_size)

        next_y = draw_wrapped_text(draw, first_line, bold_font, int(desc_box["x"]), int(desc_box["y"]), int(desc_box["width"]), desc_color, line_spacing=8)
        draw_wrapped_text(draw, rest_text, desc_font, int(desc_box["x"]), next_y, int(desc_box["width"]), desc_color, line_spacing=8)
    return base


def _make_non_white_overlay(template: Image.Image, threshold: int = 210) -> Image.Image:
    arr = np.array(template.copy().convert("RGBA"), dtype=np.uint8)
    is_white = (arr[:, :, 0] > threshold) & (arr[:, :, 1] > threshold) & (arr[:, :, 2] > threshold)
    arr[is_white, 3] = 0
    return Image.fromarray(arr)


def _cut_rect_hole(template: Image.Image, x: int, y: int, width: int, height: int) -> Image.Image:
    arr = np.array(template.copy().convert("RGBA"), dtype=np.uint8)
    arr[y:y + height, x:x + width, 3] = 0
    return Image.fromarray(arr)


def _cut_ring_hole(template: Image.Image, seed_x: int, seed_y: int, thresh: int = 60, expand_px: int = 0) -> Image.Image:
    """Flood-fill from a seed point inside the gold ring and make those pixels transparent.

    If expand_px > 0, the transparent region is dilated by that many pixels using
    MaxFilter. This fills in the ring border and the rounded corner areas, effectively
    making the frame a sharp rectangle with no curved-corner clipping.
    """
    from PIL import ImageFilter
    temp_rgb = template.copy().convert("RGB")
    marker = (3, 7, 11)
    ImageDraw.floodfill(temp_rgb, (seed_x, seed_y), marker, thresh=thresh)
    arr_temp = np.array(temp_rgb)
    filled = (arr_temp[:, :, 0] == 3) & (arr_temp[:, :, 1] == 7) & (arr_temp[:, :, 2] == 11)

    if expand_px > 0:
        filled_img = Image.fromarray((filled.astype(np.uint8)) * 255, mode="L")
        filled_img = filled_img.filter(ImageFilter.MaxFilter(expand_px * 2 + 1))
        filled = np.array(filled_img) > 127

    arr = np.array(template.copy().convert("RGBA"), dtype=np.uint8)
    arr[filled, 3] = 0
    return Image.fromarray(arr)


@st.cache_resource
def _get_template_overlay(template_key: str) -> Image.Image:
    """Load the template image and compute its transparency overlay once per
    app session.  The result is cached in memory so every subsequent render
    just reads from RAM instead of re-opening and re-processing the file.
    """
    cfg = load_config(CONFIG_PATH)
    tcfg = cfg["templates"][template_key]
    tpl_path = Path(tcfg["path"])
    if not tpl_path.is_absolute():
        tpl_path = Path.cwd() / tpl_path

    out_w = int(tcfg.get("output_width", 1080))
    out_h = int(tcfg.get("output_height", 1080))
    raw = Image.open(tpl_path).convert("RGBA")
    if raw.size != (out_w, out_h):
        raw = raw.resize((out_w, out_h), Image.Resampling.LANCZOS)

    overlay = raw.copy()
    rect_holes = tcfg.get("rect_holes", [])
    ring_seeds = tcfg.get("ring_seeds", [])
    if rect_holes:
        for rh in rect_holes:
            overlay = _cut_rect_hole(overlay, int(rh["x"]), int(rh["y"]), int(rh["width"]), int(rh["height"]))
    elif ring_seeds:
        for seed in ring_seeds:
            overlay = _cut_ring_hole(overlay, int(seed["x"]), int(seed["y"]), expand_px=int(seed.get("expand_px", 0)))
    else:
        overlay = _make_non_white_overlay(overlay)
    return overlay


def render_welcome_preview(
    people: list,
    num_persons: int,
    config: dict,
) -> Image.Image:
    template_key = f"welcome_{num_persons}"
    tcfg = config["templates"][template_key]

    out_w = int(tcfg.get("output_width", 1080))
    out_h = int(tcfg.get("output_height", 1080))

    photo_boxes = tcfg.get("photo_boxes", [])
    name_boxes = tcfg.get("name_boxes", [])
    designation_boxes = tcfg.get("designation_boxes", [])

    name_font_path = Path(tcfg.get("name_font_path", config.get("default_font_path", "")))
    if not name_font_path.is_absolute():
        name_font_path = Path.cwd() / name_font_path

    des_font_path = Path(tcfg.get("designation_font_path", tcfg.get("name_font_path", config.get("default_font_path", ""))))
    if not des_font_path.is_absolute():
        des_font_path = Path.cwd() / des_font_path

    # Overlay retrieved from cache (file load + transparency computation only
    # happens once per template on first use; free on all subsequent renders).
    overlay = _get_template_overlay(template_key)

    # White photo base sits behind the template overlay.
    photo_base = Image.new("RGBA", (out_w, out_h), (255, 255, 255, 255))

    for i, (uploaded, name, designation, scale, offset_x, offset_y, top_pct) in enumerate(people):
        if i >= len(photo_boxes):
            break
        if uploaded is not None:
            photo_box = dict(photo_boxes[i])
            photo_box["photo_scale"] = scale
            photo_box["photo_offset_x"] = offset_x
            photo_box["photo_offset_y"] = offset_y
            photo_box["photo_top_percent"] = top_pct
            person = Image.open(uploaded).convert("RGBA")
            person = maybe_extract_subject(person, photo_base.size, tcfg)
            paste_photo(
                base=photo_base,
                person=person,
                photo_box=photo_box,
                shape=tcfg.get("photo_shape", "rectangle"),
                fit_mode=tcfg.get("photo_fit", "cover"),
                anchor=tcfg.get("photo_anchor", "center"),
            )

    # Template (ring decoration, gold border, chevrons) composited on top of photo.
    base = Image.alpha_composite(photo_base, overlay)
    draw = ImageDraw.Draw(base)

    for i, (uploaded, name, designation, scale, offset_x, offset_y, top_pct) in enumerate(people):
        if i >= len(photo_boxes):
            break

        if name.strip() and i < len(name_boxes):
            name_box = name_boxes[i]
            display_name = name.upper() if tcfg.get("name_uppercase", True) else name
            name_font, name_w, name_h = fit_name_font(
                draw=draw,
                name=display_name,
                box=name_box,
                font_path=name_font_path,
                max_size=int(tcfg.get("max_font_size", 48)),
                min_size=int(tcfg.get("min_font_size", 18)),
            )
            align = tcfg.get("text_align", "center")
            if align == "left":
                nx = name_box["x"]
            elif align == "right":
                nx = name_box["x"] + name_box["width"] - name_w
            else:
                nx = name_box["x"] + (name_box["width"] - name_w) // 2
            ny = name_box["y"]
            draw.text((nx, ny), display_name, fill=tcfg.get("name_color", "#ffffff"), font=name_font)

        if designation.strip() and i < len(designation_boxes):
            des_box = designation_boxes[i]
            des_font = get_font_safe(des_font_path, int(tcfg.get("designation_font_size", 26)))
            des_text = designation.upper() if tcfg.get("designation_uppercase", False) else designation
            des_align = tcfg.get("designation_align", "center")
            box_w = int(des_box["width"])
            box_h = int(des_box["height"])

            des_bbox = draw.textbbox((0, 0), des_text, font=des_font)
            des_w = des_bbox[2] - des_bbox[0]
            des_h = des_bbox[3] - des_bbox[1]

            if des_w <= box_w:
                lines = [des_text]
            else:
                words = des_text.split()
                best_split, best_max = 1, float('inf')
                for j in range(1, len(words)):
                    l1 = ' '.join(words[:j]); l2 = ' '.join(words[j:])
                    w1 = draw.textbbox((0,0), l1, font=des_font)[2]
                    w2 = draw.textbbox((0,0), l2, font=des_font)[2]
                    if max(w1, w2) < best_max:
                        best_max = max(w1, w2); best_split = j
                lines = [' '.join(words[:best_split]), ' '.join(words[best_split:])]

            line_gap = 4
            dy_start = des_box["y"]
            for li, line in enumerate(lines):
                lw = draw.textbbox((0, 0), line, font=des_font)[2]
                if des_align == "left":
                    dx = des_box["x"]
                elif des_align == "right":
                    dx = des_box["x"] + box_w - lw
                else:
                    dx = des_box["x"] + (box_w - lw) // 2
                draw.text((dx, dy_start + li * (des_h + line_gap)), line, fill=tcfg.get("designation_color", "#ffffff"), font=des_font)

    return base


def _preview_jpeg(img: Image.Image, quality: int = 88) -> BytesIO:
    """Convert a PIL image to a JPEG BytesIO for fast st.image() display.
    JPEG is ~10-20x smaller than PNG for preview purposes, so it loads
    much faster over the network on Hugging Face."""
    buf = BytesIO()
    # JPEG doesn't support alpha — flatten onto white background first
    flat = Image.new("RGB", img.size, (255, 255, 255))
    flat.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
    flat.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return buf


st.set_page_config(page_title="Poster Studio", page_icon="🖼️", layout="wide")

# Hide Streamlit's white "re-running" blur overlay that appears on every
# slider/upload interaction — keeps the UI clean during renders.
st.markdown("""
<style>
div[data-testid="stStatusWidget"] { display: none; }
.stApp > header { display: none; }
iframe[title="streamlit_analytics"] { display: none; }
[data-testid="stAppViewBlockContainer"] > div > div[style*="opacity: 0"] { opacity: 1 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("## Poster Studio")

config = load_config(CONFIG_PATH)
birthday_tab, anniversary_tab, welcome_tab = st.tabs(["Birthday", "Anniversary", "Welcome"])

with birthday_tab:
    left, right = st.columns([1, 1.35], gap="large")
    with left:
        uploaded = st.file_uploader("Upload employee photo", type=["png", "jpg", "jpeg", "webp"], key="b_up")
        name = st.text_input("Employee name", value="", placeholder="Enter a name", key="b_name")

        occasion = "employee_birthday"

        tcfg = config["templates"][occasion]
        default_photo_box = tcfg["photo_box"]
        default_name_box = tcfg["name_box"]
        scale = st.slider("Zoom", 0.6, 2.2, float(default_photo_box.get("photo_scale", 1.0)), 0.01, key="b_zoom")
        offset_x = st.slider("Move Left / Right", -700, 700, int(default_photo_box.get("photo_offset_x", 0)), 1, key="b_x")
        offset_y = st.slider("Move Up / Down", -700, 700, int(default_photo_box.get("photo_offset_y", 0)), 1, key="b_y")
        top_pct = st.slider("Visible Body Amount", 0.4, 1.0, float(default_photo_box.get("photo_top_percent", 1.0)), 0.01, key="b_top")
        with st.expander("Advanced: Name Position / Font"):
            n_x = st.slider("Name X", -500, 4000, int(default_name_box.get("x", 0)), 1, key="b_nx")
            n_y = st.slider("Name Y", -500, 4000, int(default_name_box.get("y", 0)), 1, key="b_ny")
            n_w = st.slider("Name Width", 100, 4000, int(default_name_box.get("width", 1000)), 1, key="b_nw")
            n_h = st.slider("Name Height", 50, 2000, int(default_name_box.get("height", 200)), 1, key="b_nh")
            n_max = st.slider("Name Max Font", 20, 300, int(tcfg.get("max_font_size", 72)), 1, key="b_nmax")
            n_min = st.slider("Name Min Font", 10, 220, int(tcfg.get("min_font_size", 32)), 1, key="b_nmin")
            n_color = st.color_picker("Name Color", tcfg.get("name_color", "#111111"), key="b_nc")

        if st.button("Save Current Settings As Template Default", use_container_width=True, key="b_save"):
            config["templates"][occasion]["photo_box"]["photo_scale"] = float(scale)
            config["templates"][occasion]["photo_box"]["photo_offset_x"] = int(offset_x)
            config["templates"][occasion]["photo_box"]["photo_offset_y"] = int(offset_y)
            config["templates"][occasion]["photo_box"]["photo_top_percent"] = float(top_pct)
            config["templates"][occasion]["name_box"]["x"] = int(n_x)
            config["templates"][occasion]["name_box"]["y"] = int(n_y)
            config["templates"][occasion]["name_box"]["width"] = int(n_w)
            config["templates"][occasion]["name_box"]["height"] = int(n_h)
            config["templates"][occasion]["max_font_size"] = int(n_max)
            config["templates"][occasion]["min_font_size"] = int(n_min)
            config["templates"][occasion]["name_color"] = str(n_color)
            save_config(CONFIG_PATH, config)
            st.success(f"Saved defaults for template: {occasion}")
            st.rerun()

    with right:
        if uploaded is None:
            st.info("Upload a photo to preview.")
        elif not name.strip():
            st.warning("Enter employee name.")
        else:
            preview_config = json.loads(json.dumps(config))
            preview_config["templates"][occasion]["name_box"]["x"] = int(n_x)
            preview_config["templates"][occasion]["name_box"]["y"] = int(n_y)
            preview_config["templates"][occasion]["name_box"]["width"] = int(n_w)
            preview_config["templates"][occasion]["name_box"]["height"] = int(n_h)
            preview_config["templates"][occasion]["max_font_size"] = int(n_max)
            preview_config["templates"][occasion]["min_font_size"] = int(n_min)
            preview_config["templates"][occasion]["name_color"] = str(n_color)

            result = render_preview(
                uploaded=uploaded,
                employee_name=name.strip(),
                config=preview_config,
                occasion=occasion,
                photo_scale=scale,
                photo_offset_x=offset_x,
                photo_offset_y=offset_y,
                photo_top_percent=top_pct,
            )
            st.image(_preview_jpeg(result), caption="Live Preview", use_container_width=True)
            png_bytes = BytesIO()
            result.save(png_bytes, format="PNG")
            png_bytes.seek(0)
            file_name = f"Birthday_{name.strip().replace(' ', '_')}.png"
            st.download_button(
                "Download PNG",
                data=png_bytes,
                file_name=file_name,
                mime="image/png",
                use_container_width=True,
                key="b_down",
            )

with anniversary_tab:
    left, right = st.columns([1, 1.35], gap="large")
    with left:
        ann_photo = st.file_uploader("Upload employee photo", type=["png", "jpg", "jpeg", "webp"], key="a_up")
        ann_name = st.text_input("Employee name", value="", placeholder="Enter a name", key="a_name")
        ann_designation = st.text_input("Designation", value="", placeholder="Enter designation", key="a_des")
        ann_year = st.number_input("Anniversary Year", min_value=1, max_value=50, value=1, step=1, key="a_year")

        ann_cfg = config["templates"]["employee_anniversary"]
        ann_photo_box = ann_cfg["photo_box"]
        ann_scale = st.slider("Zoom", 0.6, 2.2, float(ann_photo_box.get("photo_scale", 1.0)), 0.01, key="a_zoom")
        ann_x = st.slider("Move Left / Right", -700, 700, int(ann_photo_box.get("photo_offset_x", 0)), 1, key="a_x")
        ann_y = st.slider("Move Up / Down", -700, 700, int(ann_photo_box.get("photo_offset_y", 0)), 1, key="a_y")
        ann_top = st.slider("Visible Body Amount", 0.4, 1.0, float(ann_photo_box.get("photo_top_percent", 1.0)), 0.01, key="a_top")

    with right:
        if ann_photo is None:
            st.info("Upload a photo to preview anniversary post.")
        elif not ann_name.strip():
            st.warning("Enter employee name.")
        elif not ann_designation.strip():
            st.warning("Enter designation.")
        else:
            ann_result = render_anniversary_preview(
                uploaded=ann_photo,
                employee_name=ann_name.strip(),
                designation=ann_designation.strip(),
                years=int(ann_year),
                config=config,
                photo_scale=ann_scale,
                photo_offset_x=ann_x,
                photo_offset_y=ann_y,
                photo_top_percent=ann_top,
            )
            st.image(_preview_jpeg(ann_result), caption="Live Preview", use_container_width=True)
            ann_bytes = BytesIO()
            ann_result.save(ann_bytes, format="PNG")
            ann_bytes.seek(0)
            ann_file = f"Anniversary_{ann_name.strip().replace(' ', '_')}.png"
            st.download_button(
                "Download Anniversary PNG",
                data=ann_bytes,
                file_name=ann_file,
                mime="image/png",
                use_container_width=True,
                key="a_down",
            )

with welcome_tab:
    WELCOME_COUNTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    left, right = st.columns([1, 1.35], gap="large")

    with left:
        num_persons = st.selectbox("Number of persons", WELCOME_COUNTS, index=0, key="w_count")
        template_key = f"welcome_{num_persons}"

        if template_key not in config.get("templates", {}):
            st.error(f"Template config for {num_persons} person(s) not found in config.json.")
        else:
            w_tcfg = config["templates"][template_key]
            template_path_check = Path(w_tcfg["path"])
            if not template_path_check.is_absolute():
                template_path_check = Path.cwd() / template_path_check
            if not template_path_check.exists():
                st.warning(f"Template image not found: {w_tcfg['path']}. Please add it to the templates/ folder.")

            people_inputs = []
            for i in range(num_persons):
                with st.expander(f"Person {i + 1}", expanded=(i == 0)):
                    up = st.file_uploader(f"Photo", type=["png", "jpg", "jpeg", "webp"], key=f"w_up_{i}")
                    nm = st.text_input("Name", value="", placeholder="Enter name", key=f"w_name_{i}")
                    dg = st.text_input("Designation", value="", placeholder="Enter designation", key=f"w_des_{i}")
                    default_pb = w_tcfg.get("photo_boxes", [{}] * num_persons)
                    pb = default_pb[i] if i < len(default_pb) else {}
                    sc = st.slider("Zoom", 0.5, 3.0, float(pb.get("photo_scale", 1.0)), 0.01, key=f"w_zoom_{i}")
                    ox = st.slider("Move Left / Right", -500, 500, int(pb.get("photo_offset_x", 0)), 1, key=f"w_ox_{i}")
                    oy = st.slider("Move Up / Down", -500, 500, int(pb.get("photo_offset_y", 0)), 1, key=f"w_oy_{i}")
                    tp = st.slider("Visible Body Amount", 0.4, 1.0, float(pb.get("photo_top_percent", 1.0)), 0.01, key=f"w_tp_{i}")
                    people_inputs.append((up, nm, dg, sc, ox, oy, tp))

    with right:
        if template_key not in config.get("templates", {}):
            st.info("Select a valid template to preview.")
        elif not template_path_check.exists():
            st.info("Add the template image to see the preview.")
        else:
            any_photo = any(p[0] is not None for p in people_inputs)
            any_name = any(p[1].strip() for p in people_inputs)
            if not any_photo:
                st.info("Upload at least one photo to preview.")
            elif not any_name:
                st.warning("Enter at least one name.")
            else:
                w_result = render_welcome_preview(
                    people=people_inputs,
                    num_persons=num_persons,
                    config=config,
                )
                st.image(w_result, caption="Live Preview", use_container_width=True)
                w_bytes = BytesIO()
                w_result.save(w_bytes, format="PNG")
                w_bytes.seek(0)
                first_name = next((p[1].strip() for p in people_inputs if p[1].strip()), "")
                w_name_part = f"_{first_name.replace(' ', '_')}" if first_name else ""
                w_file = f"Welcome{w_name_part}_{num_persons}p.png"
                st.download_button(
                    "Download Welcome PNG",
                    data=w_bytes,
                    file_name=w_file,
                    mime="image/png",
                    use_container_width=True,
                    key="w_down",
                )
