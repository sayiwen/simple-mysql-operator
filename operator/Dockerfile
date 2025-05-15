FROM harbor.subat.cn/library/python@sha256:4fc77722db8bd186386ebfe056989b2ba1c8a602ef1c46ec461fa49a9bb4c667

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple

COPY src/ /app/src/

ENV PYTHONPATH=/app

CMD ["python", "src/main.py"] 