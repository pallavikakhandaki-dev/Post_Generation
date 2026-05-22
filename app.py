import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

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


st.set_page_config(page_title="Poster Studio", page_icon="🖼️", layout="wide")
st.markdown("## Poster Studio")

config = load_config(CONFIG_PATH)
birthday_tab, anniversary_tab = st.tabs(["Birthday", "Anniversary"])

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
            st.image(result, caption="Live Preview", use_container_width=True)
            png_bytes = BytesIO()
            result.save(png_bytes, format="PNG")
            png_bytes.seek(0)
            file_name = f"{occasion}_{name.strip().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
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
            st.image(ann_result, caption="Live Preview", use_container_width=True)
            ann_bytes = BytesIO()
            ann_result.save(ann_bytes, format="PNG")
            ann_bytes.seek(0)
            ann_file = f"employee_anniversary_{ann_name.strip().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            st.download_button(
                "Download Anniversary PNG",
                data=ann_bytes,
                file_name=ann_file,
                mime="image/png",
                use_container_width=True,
                key="a_down",
            )
