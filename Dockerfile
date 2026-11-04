FROM python:3.12-slim

# Logs shown at once, no .pyc files written in the container
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first: this layer is reused as long as requirements.txt does not change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY train.py .

# Not root: a flaw in the API would not give full control of the container.
# uid 1000 = usual first user of a Linux server, so it can write ./models through the volume.
RUN useradd --uid 1000 --no-create-home app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
