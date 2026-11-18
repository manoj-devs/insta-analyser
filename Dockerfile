FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*   # reads numbers from screenshots (Creator Income)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# rebuild warehouse.db from its compressed GitHub parts while the image is built (no-op when the full warehouse is already there)
RUN DATA_DIR=/app/data python -c "import app.config" && rm -f /app/data/processed/warehouse.db.gz.part*
ENV APP_ENV=production HOST=0.0.0.0 PORT=8000 DATA_DIR=/var/data
EXPOSE 8000
CMD ["python", "main.py"]
