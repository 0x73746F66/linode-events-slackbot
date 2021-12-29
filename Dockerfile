FROM docker.io/library/alpine:3.8
LABEL org.opencontainers.image.authors="Christopher Langton"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.source="https://gitlab.com/trivialsec/linode-events-slackbot"

ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /srv/app

WORKDIR /srv/app

COPY bin/entrypoint /entrypoint
RUN mkdir -p sqlite && \
        apk update -q && \
        apk -q --no-cache add python3 build-base linux-headers python3-dev sqlite && \
        python3 -m pip install -q --no-cache-dir --no-warn-script-location -U pip

COPY src .
COPY requirements.txt requirements.txt

RUN pip install -q --user -r requirements.txt
ENTRYPOINT ["/entrypoint"]
CMD ["/usr/bin/python3", "/srv/app/main.py"]
