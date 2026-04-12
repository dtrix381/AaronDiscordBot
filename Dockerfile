FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

RUN python -m playwright install chromium

COPY . .

CMD ["python", "main.py"]
