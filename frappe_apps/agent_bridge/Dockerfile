FROM frappe/erpnext:v15.108.0

USER root

COPY . /home/frappe/frappe-bench/apps/agent_bridge

RUN chown -R frappe:frappe /home/frappe/frappe-bench/apps/agent_bridge \
    && /home/frappe/frappe-bench/env/bin/pip install --no-cache-dir -e /home/frappe/frappe-bench/apps/agent_bridge

USER frappe
