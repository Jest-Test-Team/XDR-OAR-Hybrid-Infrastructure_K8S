FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir kafka-python==2.0.2

COPY main.py /app/main.py

EXPOSE 8085

CMD ["python", "/app/main.py"]
