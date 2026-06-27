#!/bin/zsh
set -e
cd "$(dirname "$0")"
/opt/homebrew/bin/python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
cd backend
rm -f translator_engine.db
echo "Preparing built-in standards on backend startup..."
echo "Open http://127.0.0.1:8000/app/?v=19"
uvicorn app.main:app --reload
