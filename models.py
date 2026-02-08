"""Invidious-compatible response models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class Thumbnail(BaseModel):
    """Video thumbnail."""

    quality: str
    url: str
    width: Optional[int] = None
    height: Optional[int] = None


class AudioTrack(BaseModel):
    """Audio track metadata."""

    id: Optional[str] = None
    displayName: Optional[str] = None
    isDefault: bool = False


class FormatStream(BaseModel):
    """Muxed video+audio stream."""

    url: str
    itag: str
    type: str
    quality: str
    container: str
    resolution: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    encoding: Optional[str] = None
    size: Optional[str] = None
    fps: Optional[int] = None
    httpHeaders: Optional[dict] = None


class AdaptiveFormat(BaseModel):
    """Adaptive (video-only or audio-only) stream."""

    url: str
    itag: str
    type: str
    container: str
    resolution: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bitrate: Optional[str] = None
    clen: Optional[str] = None
    encoding: Optional[str] = None
    fps: Optional[int] = None
    audioTrack: Optional[AudioTrack] = None
    audioQuality: Optional[str] = None
    httpHeaders: Optional[dict] = None


class Caption(BaseModel):
    """Video caption/subtitle."""

    label: str
    languageCode: str
    url: str
    auto_generated: bool = False


class Storyboard(BaseModel):
    """Video storyboard/preview thumbnails."""

    url: str
    templateUrl: str
    width: int
    height: int
    count: int
    interval: int
    storyboardWidth: int
    storyboardHeight: int
    storyboardCount: int


class VideoResponse(BaseModel):
    """Full video details response (matches Invidious /api/v1/videos/{id})."""

    videoId: str
    title: str
    description: Optional[str] = None
    descriptionHtml: Optional[str] = None
    author: str
    authorId: str
    authorUrl: Optional[str] = None
    authorThumbnails: Optional[List[Thumbnail]] = None
    subCountText: Optional[str] = None
    lengthSeconds: int
    published: Optional[int] = None
    publishedText: Optional[str] = None
    viewCount: Optional[int] = None
    likeCount: Optional[int] = None
    videoThumbnails: List[Thumbnail] = Field(default_factory=list)
    liveNow: bool = False
    isUpcoming: bool = False
    premiereTimestamp: Optional[int] = None
    hlsUrl: Optional[str] = None
    dashUrl: Optional[str] = None
    formatStreams: List[FormatStream] = Field(default_factory=list)
    adaptiveFormats: List[AdaptiveFormat] = Field(default_factory=list)
    captions: List[Caption] = Field(default_factory=list)
    storyboards: List[Storyboard] = Field(default_factory=list)
    # Extended fields for external (non-YouTube) sources
    extractor: Optional[str] = None  # Site identifier (e.g., "vimeo", "twitter")
    originalUrl: Optional[str] = None  # Original URL for re-extraction on stream expiry
    # Recommended videos (only available when using Invidious proxy)
    recommendedVideos: Optional[List["VideoListItem"]] = None


class VideoListItem(BaseModel):
    """Video item in search/channel/playlist results."""

    type: str = "video"
    videoId: str
    title: str
    description: Optional[str] = None
    author: str
    authorId: str
    authorUrl: Optional[str] = None
    lengthSeconds: int
    published: Optional[int] = None
    publishedText: Optional[str] = None
    viewCount: Optional[int] = None
    viewCountText: Optional[str] = None
    likeCount: Optional[int] = None
    videoThumbnails: List[Thumbnail] = Field(default_factory=list)
    liveNow: bool = False
    isUpcoming: bool = False
    extractor: Optional[str] = None  # Site name (Vimeo, Dailymotion, etc.) for external videos
    videoUrl: Optional[str] = None  # Original video URL for external videos (for re-extraction)


class ChannelListItem(BaseModel):
    """Channel item in search results."""

    type: str = "channel"
    authorId: str
    author: str
    description: Optional[str] = None
    subCount: Optional[int] = None
    subCountText: Optional[str] = None
    videoCount: Optional[int] = None
    authorThumbnails: List[Thumbnail] = Field(default_factory=list)
    authorVerified: bool = False


class ChannelResponse(BaseModel):
    """Channel details response."""

    authorId: str
    author: str
    description: Optional[str] = None
    subCount: Optional[int] = None
    totalViews: Optional[int] = None
    authorThumbnails: List[Thumbnail] = Field(default_factory=list)
    authorBanners: List[Thumbnail] = Field(default_factory=list)
    authorVerified: bool = False


class ChannelMetadataRequest(BaseModel):
    """Request body for batch channel metadata endpoint."""

    channel_ids: List[str]


class ChannelVideosResponse(BaseModel):
    """Channel videos response (Invidious-compatible)."""

    videos: List[VideoListItem] = Field(default_factory=list)
    continuation: Optional[str] = None


class ChannelPlaylistsResponse(BaseModel):
    """Channel playlists response (Invidious-compatible)."""

    playlists: List["PlaylistListItem"] = Field(default_factory=list)
    continuation: Optional[str] = None


class ChannelShortsResponse(BaseModel):
    """Channel shorts response (Invidious-compatible)."""

    videos: List[VideoListItem] = Field(default_factory=list)
    continuation: Optional[str] = None


class ChannelStreamsResponse(BaseModel):
    """Channel past live streams response (Invidious-compatible)."""

    videos: List[VideoListItem] = Field(default_factory=list)
    continuation: Optional[str] = None


class ChannelSearchResponse(BaseModel):
    """Channel search results response (Invidious-compatible)."""

    videos: List[VideoListItem] = Field(default_factory=list)
    continuation: Optional[str] = None


class ChannelExtractResponse(BaseModel):
    """Generic channel extraction response for external (non-YouTube) sites."""

    author: str
    authorId: str
    authorUrl: str  # Channel URL for re-extraction
    extractor: str  # Site name (Vimeo, Dailymotion, TikTok, etc.)
    videos: List[VideoListItem] = Field(default_factory=list)
    continuation: Optional[str] = None  # Page number as string for next request


class PlaylistListItem(BaseModel):
    """Playlist item in search results."""

    type: str = "playlist"
    playlistId: str
    title: str
    author: Optional[str] = None
    authorId: Optional[str] = None
    videoCount: int = 0
    playlistThumbnail: Optional[str] = None
    videos: List[VideoListItem] = Field(default_factory=list)


class PlaylistResponse(BaseModel):
    """Playlist details response."""

    playlistId: str
    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    authorId: Optional[str] = None
    videoCount: int
    videos: List[VideoListItem] = Field(default_factory=list)
