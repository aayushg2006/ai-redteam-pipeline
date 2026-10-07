# Build context is the PROJECT ROOT (see docker-compose.yml) so the package keeps
# its name: /srv/guardrail  ->  `uvicorn guardrail.service:app`
#
# The model is NOT trained here. Jenkins trains it and runs the quality gate
# (guardrail.evaluate) first, and only then builds this image, so the image
# contains exactly the model version that passed the gate.
FROM python:3.13-slim

WORKDIR /srv

COPY guardrail/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY guardrail ./guardrail
# Fail the build early if nobody trained a model yet.
RUN test -f guardrail/models/latest.txt || (echo "Run python -m guardrail.train first" && exit 1)

RUN useradd -m app && chown -R app /srv
USER app

EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "guardrail.service:app", "--host", "0.0.0.0", "--port", "8001"]
