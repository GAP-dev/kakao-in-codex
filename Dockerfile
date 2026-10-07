FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends openssh-server tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash kakao && usermod --password '*' kakao
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bridge ./bridge
COPY sshd_config /etc/ssh/sshd_config
COPY container-entrypoint.sh /usr/local/bin/entrypoint
COPY kakao /usr/local/bin/kakao
COPY ssh-command.py /app/ssh-command.py
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint /usr/local/bin/kakao \
    && chmod 755 /usr/local/bin/entrypoint /usr/local/bin/kakao
ENV PYTHONPATH=/app TOKEN_FILE=/run/kakao/token LANG=C.UTF-8 PYTHONUNBUFFERED=1
EXPOSE 22
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint"]
