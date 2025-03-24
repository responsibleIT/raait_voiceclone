FROM python:3.9

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir flask

CMD ["python", "app.py"]