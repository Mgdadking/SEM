FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=10000
EXPOSE 10000

CMD ["python", "monitor.py"]
```

**أنشئ ملف `.dockerignore`:**
```
__pycache__
*.pyc
*.log
*.png
.git
.env
venv/
