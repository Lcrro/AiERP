# Compact single-container Frappe/ERPNext app (web+backend+ws+scheduler+workers).
# Keep base tag pinned — do not upgrade ERPNext in this stack.
FROM frappe/erpnext:v15.118.2

USER root
RUN apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log/supervisor \
    && chown -R frappe:frappe /var/log/supervisor

COPY --chown=frappe:frappe supervisord.conf /home/frappe/supervisord-compact.conf
COPY entrypoint.sh /usr/local/bin/compact-entrypoint.sh
COPY healthcheck.sh /usr/local/bin/compact-healthcheck.sh
RUN chmod 755 /usr/local/bin/compact-entrypoint.sh /usr/local/bin/compact-healthcheck.sh

USER frappe
WORKDIR /home/frappe/frappe-bench

ENV BACKEND=127.0.0.1:8000 \
    SOCKETIO=127.0.0.1:9000 \
    FRAPPE_SITE_NAME_HEADER='$host' \
    UPSTREAM_REAL_IP_ADDRESS=127.0.0.1 \
    UPSTREAM_REAL_IP_HEADER=X-Forwarded-For \
    UPSTREAM_REAL_IP_RECURSIVE=off \
    PROXY_READ_TIMEOUT=120 \
    CLIENT_MAX_BODY_SIZE=50m \
    GUNICORN_THREADS=4 \
    GUNICORN_WORKERS=2 \
    GUNICORN_TIMEOUT=120

EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/compact-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-n", "-c", "/home/frappe/supervisord-compact.conf"]
