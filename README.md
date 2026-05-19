---
title: birthday-poster-studio
emoji: 🎉
colorFrom: yellow
colorTo: gray
sdk: streamlit
sdk_version: 1.45.1
python_version: "3.10"
app_file: app.py
pinned: false
---


# Poster Studio (Employee / Manager Post Generator)

This project generates branded posters by placing:
- Employee photo
- Employee name
- Optional company logo

on pre-designed PNG templates.

It supports:
- Streamlit UI for HR team (`streamlit_app.py`)
- Batch CSV generation (`src/generate_posts.py`)

## Project Structure

- `streamlit_app.py`: Main UI app for non-technical users
- `src/generate_posts.py`: Batch generator script
- `config.json`: Template coordinates, font, color, and behavior
- `templates/`: Base template PNGs
- `assets/photos/`: Local photos (optional; UI also supports direct upload)
- `assets/logo/`: Optional template logos
- `requirements.txt`: Python dependencies
- `run_generate.bat`: Optional Windows batch runner for CSV mode

## 1. Local Setup (Windows)

Run in PowerShell from project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Run Streamlit UI (Recommended for HR)

```powershell
streamlit run streamlit_app.py
```

Then open:
- `http://localhost:8501`

UI flow:
1. Upload employee photo
2. Enter employee name
3. Select poster type (`Employee` / `Manager`)
4. Select template
5. Adjust sliders (zoom, move, name settings if needed)
6. Download final PNG

## 3. Run Batch CSV Generator (Optional)

```powershell
python src/generate_posts.py --config config.json --input input/posts.csv
```

Generated files are saved under:
- `output/<date>/...`

## CSV Format

`input/posts.csv`

```csv
occasion,employee_name,photo_path,date
employee_birthday,Ajinkya Jawalekar,assets/photos/Ajinkya Jawalekar.png,2026-05-19
manager_birthday,Akshay Deshmukh,assets/photos/Akshay_Deshmukh.png,2026-05-19
```

Fields:
- `occasion`: Must match a key inside `config.json -> templates`
- `employee_name`: Name text to render
- `photo_path`: Local path or image URL
- `date`: Output subfolder name

## 4. Change Name Font

Use template-specific font via `name_font_path` in `config.json`:

```json
"employee_birthday": {
  "name_font_path": "assets/fonts/Anton-Regular.ttf"
}
```

You can also use a Windows font directly:

```json
"name_font_path": "C:/Windows/Fonts/impact.ttf"
```

If font file is missing, default font is used.

## 5. Important Config Keys

In each template block (`config.json -> templates -> <template_key>`):
- `path`: Template PNG path
- `photo_box`: `x`, `y`, `width`, `height`, `photo_scale`, offsets
- `name_box`: Name text area
- `name_color`
- `max_font_size`, `min_font_size`
- `name_uppercase`
- `name_font_path` (optional per-template override)
- `logo_path`, `logo_box` (optional)

All coordinates are pixel-based.

## 6. Hugging Face Spaces Deployment

Current HF flow commonly uses Docker + Streamlit template.

1. Create Space on Hugging Face
2. Select `Docker`
3. Choose Streamlit starter/template
4. Push this project files (exclude local runtime folders)

Recommended `.gitignore`:

```gitignore
.venv/
__pycache__/
output/
.u2net/
node_modules/
*.pyc
```

## 7. Troubleshooting

- `No pyvenv.cfg file`
  - `.venv` is broken; recreate virtual environment.

- `WinError 10054` in Streamlit logs
  - Usually harmless socket disconnect on Windows; app still runs.

- Photo not found
  - Check `photo_path` spelling and file location.

- Font not matching
  - Set `name_font_path` for that specific template and restart app.
