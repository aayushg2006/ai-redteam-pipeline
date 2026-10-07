# Build context is the PROJECT ROOT (see docker-compose.yml) so the package
# keeps its name: /srv/redteam -> `python -m redteam.runner`
FROM python:3.11-slim

WORKDIR /srv

COPY redteam/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY redteam ./redteam

RUN useradd -m rt && mkdir -p /srv/reports && chown rt /srv/reports
USER rt

ENV TARGET_URL=http://chatbot:8000 \
    REPORT_DIR=/srv/reports

# Default: run the attack suite. Override with `pytest redteam/tests` for unit tests.
CMD ["python", "-m", "redteam.runner"]
