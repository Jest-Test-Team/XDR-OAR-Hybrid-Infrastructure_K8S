FROM python:3.12-slim

WORKDIR /app

COPY main.py /app/main.py
COPY signatures.json /app/signatures.json

EXPOSE 9000

CMD ["python", "/app/main.py"]
