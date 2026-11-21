FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements-server.txt /app/requirements-server.txt
RUN pip install --no-cache-dir -r requirements-server.txt \
    && useradd --uid 10001 --create-home lab
COPY --chown=10001:10001 src/devfest_security /app/src/devfest_security
USER 10001
CMD ["python", "-m", "devfest_security.server"]
