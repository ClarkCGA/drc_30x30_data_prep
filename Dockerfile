
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    git curl unzip && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m geeuser

WORKDIR /home/geeuser
COPY --chown=geeuser . /home/geeuser/
RUN pip install --upgrade pip && pip install -r requirements.txt

USER geeuser

EXPOSE 8888

CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser"]