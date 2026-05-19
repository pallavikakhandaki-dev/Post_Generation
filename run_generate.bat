@echo off
setlocal

if not exist .venv (
  py -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

python src\generate_posts.py --config config.json --input input\posts.csv

echo.
echo Done. Check output folder.
pause
