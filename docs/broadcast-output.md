# Broadcast output: Liquidsoap and Icecast

RadioPilot's AI agents do not access Liquidsoap. The API's `PlaybackController` maps a selected audio file into the shared `/media` volume and sends a queue command over the private Docker network. Liquidsoap encodes that audio as MP3 and publishes it to an Icecast-compatible server.

## Safe test mode

Keep `AUDIO_ENGINE=null` and do not start the `broadcast` profile. RadioPilot remains a full station-control simulation and cannot transmit audio.

## Enable an Icecast-compatible encoder target

Set these values in `.env` only after receiving them from the streaming provider or station engineer:

```env
AUDIO_ENGINE=liquidsoap
STATION_NAME=Your Station Name
ICECAST_HOST=encoder.provider.example
ICECAST_PORT=8000
ICECAST_MOUNT=/live.mp3
ICECAST_SOURCE_USER=source
ICECAST_SOURCE_PASSWORD=provided-by-your-streaming-provider
```

Start the stack with `docker compose --profile broadcast up --build`. The Liquidsoap control port is deliberately not published to the host or internet.

## Hardware transmitter chain

For FM transmission, feed the resulting Icecast stream into the station's licensed encoder/exciter or use a dedicated broadcast appliance supplied by the transmitter engineer. Do not expose the Liquidsoap control port or connect an unlicensed transmitter.
