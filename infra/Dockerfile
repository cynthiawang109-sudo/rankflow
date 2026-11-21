FROM rankflow-stage4-local
RUN uv pip install --python /app/.venv/bin/python boto3==1.43.7
COPY infra/stage4_entry.py /app/stage4_entry.py
CMD ["/app/.venv/bin/python", "/app/stage4_entry.py"]
