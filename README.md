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
