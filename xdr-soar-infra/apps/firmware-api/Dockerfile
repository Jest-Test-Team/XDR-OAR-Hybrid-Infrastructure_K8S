FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir pymongo==4.11.3

COPY main.py /app/main.py

EXPOSE 8081

CMD ["python", "/app/main.py"]
