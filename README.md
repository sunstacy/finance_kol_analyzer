# finance_kol_analyzer

Utilities for analyzing finance creator content.

## YouTube transcripts

This project uses [`youtube-transcript-api`](https://github.com/jdepoix/youtube-transcript-api)
to fetch YouTube captions. It is the best fit found in the current package/GitHub
search because it is actively maintained, widely used, supports manually created
and auto-generated captions, and does not require a YouTube API key or headless
browser.

```python
from finance_kol_analyzer import get_youtube_transcript, get_youtube_transcript_text

url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

snippets = get_youtube_transcript(url, languages=["en"])
# [{"text": "...", "start": 0.0, "duration": 3.2}, ...]

plain_text = get_youtube_transcript_text(url)
```

Supported inputs include normal `youtube.com/watch?v=...` links, `youtu.be`
short links, Shorts, Live, Embed, YouTube Music, YouTube nocookie embed URLs,
and bare 11-character video IDs.

The upstream library depends on YouTube's undocumented transcript endpoint. In
cloud environments YouTube may block requests from datacenter IPs; if that
happens, configure a `YouTubeTranscriptApi` instance with a proxy and pass it to
`get_youtube_transcript(..., api=your_api)`.

### When YouTube blocks the machine IP

If you see `RequestBlocked`, the code is running but YouTube is refusing the
request from that IP address. This is common in hosted/cloud environments. The
simplest fix is to run the same script from a local laptop or desktop network.
For cloud runs, configure a rotating residential proxy.

Generic proxy:

```bash
export YOUTUBE_TRANSCRIPT_PROXY="http://user:password@proxy-host:proxy-port"
python3 run_transcript.py
```

Or separate HTTP/HTTPS proxies:

```bash
export YOUTUBE_TRANSCRIPT_HTTP_PROXY="http://user:password@proxy-host:proxy-port"
export YOUTUBE_TRANSCRIPT_HTTPS_PROXY="http://user:password@proxy-host:proxy-port"
python3 run_transcript.py
```

Webshare residential proxy:

```bash
export YOUTUBE_TRANSCRIPT_WEBSHARE_USERNAME="your-webshare-username"
export YOUTUBE_TRANSCRIPT_WEBSHARE_PASSWORD="your-webshare-password"
export YOUTUBE_TRANSCRIPT_WEBSHARE_LOCATIONS="us"
python3 run_transcript.py
```

After these variables are set, normal calls such as
`get_youtube_transcript_text(url)` automatically use the proxy.
