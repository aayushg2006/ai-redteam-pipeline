# Build context is the PROJECT ROOT (see docker-compose.yml) so the package keeps
# its name: /srv/guardrail  ->  `uvicorn guardrail.service:app`
FROM python:3.11-slim

WORKDIR /srv

COPY guardrail/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY guardrail ./guardrail

# Train INSIDE the image so the model and the runtime use the same library
# versions, then run the quality gate. If evaluate fails (exit 1) the image
# build fails, so a bad model can never be deployed.
RUN python -m guardrail.make_dataset \
 && python -m guardrail.train \
 && python -m guardrail.evaluate

RUN useradd -m app && chown -R app /srv
USER app

EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "guardrail.service:app", "--host", "0.0.0.0", "--port", "8001"]