FROM savonet/liquidsoap:v2.4.5
USER root
RUN apt-get update && apt-get install -y --no-install-recommends gettext-base && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
COPY radiopilot.liq.template /config/radiopilot.liq.template
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
