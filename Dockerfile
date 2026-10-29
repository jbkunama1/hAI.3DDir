FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/jbkunama1/hAI.3DDir"
ENV PYTHONUNBUFFERED=1 SHARE_PATH=/share DATA_DIR=/data
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" python-multipart itsdangerous httpx
WORKDIR /srv
COPY app ./app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u;u.urlopen('http://localhost:8080/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
