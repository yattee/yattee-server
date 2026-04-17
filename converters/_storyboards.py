"""Convert yt-dlp storyboard format entries to Storyboard model objects."""

import re
from typing import List, Optional

from models import Storyboard


def convert_storyboards(formats: Optional[List[dict]]) -> List[Storyboard]:
    """Extract and convert storyboard data from yt-dlp format entries.

    yt-dlp returns storyboards as format entries with ext="mhtml" / vcodec="images".
    Each entry contains fragment URLs, grid dimensions, and thumbnail sizes.
    """
    if not formats:
        return []

    storyboards = []
    for fmt in formats:
        if fmt.get("ext") != "mhtml" and fmt.get("vcodec") != "images":
            continue

        fragments = fmt.get("fragments")
        columns = fmt.get("columns")
        rows = fmt.get("rows")
        width = fmt.get("width")
        height = fmt.get("height")

        if not fragments or not columns or not rows or not width or not height:
            continue

        first_url = fragments[0].get("url")
        if not first_url:
            continue

        # yt-dlp's fragments[i].duration is the span covered by that sheet
        # (columns*rows frames), not per-frame. The Invidious `interval` field
        # is milliseconds per thumbnail frame, so divide by the sheet size.
        frames_per_sheet = columns * rows
        duration = fragments[0].get("duration", 0)
        interval = int((duration * 1000) / frames_per_sheet) if frames_per_sheet else 0
        storyboard_count = len(fragments)
        count = frames_per_sheet * storyboard_count

        # Derive template URL: replace page number M0 with M$M
        template_url = re.sub(r"(/M)\d+(\.\w+)", r"\1$M\2", first_url)

        storyboards.append(
            Storyboard(
                url=first_url,
                templateUrl=template_url,
                width=width,
                height=height,
                count=count,
                interval=interval,
                storyboardWidth=columns,
                storyboardHeight=rows,
                storyboardCount=storyboard_count,
            )
        )

    # Sort by width ascending (lowest resolution first, matching Invidious ordering)
    storyboards.sort(key=lambda sb: sb.width)
    return storyboards
