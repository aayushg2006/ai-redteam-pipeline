FROM python:3.13-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

# History is stored in /data (a named Docker volume, see docker-compose.yml)
ENV DATA_DIR=/data
RUN useradd -m dash && mkdir -p /data && chown dash /data
USER dash

EXPOSE 8090
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
