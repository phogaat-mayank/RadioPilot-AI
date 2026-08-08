#!/bin/sh
set -eu
: "${ICECAST_HOST:?ICECAST_HOST is required}"
: "${ICECAST_SOURCE_PASSWORD:?ICECAST_SOURCE_PASSWORD is required}"
envsubst '${STATION_NAME} ${ICECAST_HOST} ${ICECAST_PORT} ${ICECAST_MOUNT} ${ICECAST_SOURCE_USER} ${ICECAST_SOURCE_PASSWORD}' < /config/radiopilot.liq.template > /tmp/radiopilot.liq
exec liquidsoap /tmp/radiopilot.liq
