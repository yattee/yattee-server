"""Caption conversion."""

from typing import List, Optional

import tokens as token_utils
from models import Caption


def convert_captions(
    subtitles: Optional[dict],
    automatic_captions: Optional[dict],
    video_id: str,
    base_url: str = "",
    user_id: Optional[int] = None,
) -> List[Caption]:
    """Convert yt-dlp subtitles to Invidious captions.

    Args:
        subtitles: Manual captions from yt-dlp
        automatic_captions: Auto-generated captions from yt-dlp
        video_id: Video ID for proxy URL construction
        base_url: Base URL for proxy endpoints
        user_id: User ID for generating caption tokens (if basic auth enabled)
    """
    captions = []

    # Generate token if user_id is provided (basic auth enabled)
    caption_token = None
    if user_id is not None and base_url and video_id:
        caption_token = token_utils.generate_stream_token(user_id, video_id)

    def is_fetchable_auto_caption(formats: List[dict]) -> bool:
        """Check if this is an original auto-caption (not a translation target).

        YouTube's automatic_captions from yt-dlp contains two types:
        - Original auto-caption: URL has lang=X but NO tlang parameter
        - Auto-translation targets: URL has lang=X AND tlang=Y (translation target)

        Auto-translations are generated on-demand by YouTube's player and while
        yt-dlp lists them, our caption endpoint cannot fetch them reliably.

        We detect this by checking if any format URL contains 'tlang=' parameter.
        """
        for f in formats:
            url = f.get("url", "")
            # If ANY format URL has tlang= parameter, this is a translation target
            if "tlang=" in url:
                return False
        return True

    def process_subtitles(subs: Optional[dict], auto_generated: bool):
        if not subs:
            return
        for lang_code, formats in subs.items():
            if not formats:
                continue

            # Skip unfetchable auto-translation targets
            # These are generated on-demand by YouTube and cannot be downloaded
            if auto_generated and not is_fetchable_auto_caption(formats):
                continue

            # Get language name
            label = formats[0].get("name", lang_code)
            if auto_generated:
                label = f"{label} (auto-generated)"

            # Build proxy URL
            proxy_url = f"{base_url}/api/v1/captions/{video_id}/content?lang={lang_code}"
            if auto_generated:
                proxy_url += "&auto=true"
            if caption_token:
                proxy_url += f"&token={caption_token}"

            captions.append(Caption(label=label, languageCode=lang_code, url=proxy_url, auto_generated=auto_generated))

    # Process manual captions first
    process_subtitles(subtitles, auto_generated=False)

    # Then auto-generated captions
    process_subtitles(automatic_captions, auto_generated=True)

    return captions
