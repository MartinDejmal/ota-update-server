FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir . && mkdir -p /data/firmware /data/tmp && useradd --uid 10001 --create-home app && chown -R app:app /app /data
USER app
EXPOSE 8000
ENTRYPOINT ["ota-server"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
