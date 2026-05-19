import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

from src.generate_posts import fit_name_font, maybe_extract_subject, paste_photo


CONFIG_PATH = Path("config.json")


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_config(config_path: Path, config: dict) -> None:
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


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


st.set_page_config(page_title="Poster Studio", page_icon="🖼️", layout="wide")
st.markdown("## Poster Studio")
# st.caption("Simple HR workflow: upload photo, enter name, and download poster.")

config = load_config(CONFIG_PATH)
left, right = st.columns([1, 1.35], gap="large")
with left:
    uploaded = st.file_uploader("Upload employee photo", type=["png", "jpg", "jpeg", "webp"])
    name = st.text_input("Employee name", value="Ajinkya Jawalekar")

    occasion = "employee_birthday"
    st.text_input("Template", value=occasion, disabled=True)

    tcfg = config["templates"][occasion]
    default_photo_box = tcfg["photo_box"]
    default_name_box = tcfg["name_box"]
    scale = st.slider("Zoom", 0.6, 2.2, float(default_photo_box.get("photo_scale", 1.0)), 0.01)
    offset_x = st.slider("Move Left / Right", -700, 700, int(default_photo_box.get("photo_offset_x", 0)), 1)
    offset_y = st.slider("Move Up / Down", -700, 700, int(default_photo_box.get("photo_offset_y", 0)), 1)
    top_pct = st.slider("Visible Body Amount", 0.4, 1.0, float(default_photo_box.get("photo_top_percent", 1.0)), 0.01)
    with st.expander("Advanced: Name Position / Font"):
        n_x = st.slider("Name X", -500, 4000, int(default_name_box.get("x", 0)), 1)
        n_y = st.slider("Name Y", -500, 4000, int(default_name_box.get("y", 0)), 1)
        n_w = st.slider("Name Width", 100, 4000, int(default_name_box.get("width", 1000)), 1)
        n_h = st.slider("Name Height", 50, 2000, int(default_name_box.get("height", 200)), 1)
        n_max = st.slider("Name Max Font", 20, 300, int(tcfg.get("max_font_size", 72)), 1)
        n_min = st.slider("Name Min Font", 10, 220, int(tcfg.get("min_font_size", 32)), 1)
        n_color = st.color_picker("Name Color", tcfg.get("name_color", "#111111"))

    if st.button("Save Current Settings As Template Default", use_container_width=True):
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
        )
