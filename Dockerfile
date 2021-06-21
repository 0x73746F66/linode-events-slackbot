FROM docker.io/library/alpine:3.8
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /srv/app
WORKDIR /srv/app
COPY src .
COPY requirements.txt requirements.txt

RUN mkdir -p sqlite && \
        adduser -HDS -u 1000 -h /srv/app app && \
        apk update -q && \
        apk -q --no-cache add python3 build-base linux-headers python3-dev sqlite && \
        python3 -m pip install -q --no-cache-dir --no-warn-script-location -U pip && \
        chown -R app: /srv/app 

USER app
RUN pip install -q --user -r requirements.txt

CMD ["python3", "main.py"]
