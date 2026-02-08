"""Sites and credentials management endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import database
import encryption

from .deps import get_current_admin

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================


class CredentialCreate(BaseModel):
    credential_type: str
    key: Optional[str] = None
    value: str


class SiteCreate(BaseModel):
    name: str = Field(..., min_length=1)
    extractor_pattern: str = Field(..., min_length=1)
    enabled: bool = True
    priority: int = 0
    proxy_streaming: bool = True
    credentials: List[CredentialCreate] = []


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    extractor_pattern: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    proxy_streaming: Optional[bool] = None


class CredentialResponse(BaseModel):
    id: int
    credential_type: str
    key: Optional[str]
    has_value: bool
    is_encrypted: bool
    created_at: str


class SiteResponse(BaseModel):
    id: int
    name: str
    extractor_pattern: str
    enabled: bool
    priority: int
    proxy_streaming: bool = True
    credential_count: Optional[int] = None
    credentials: Optional[List[CredentialResponse]] = None
    created_at: str
    updated_at: str


class TestRequest(BaseModel):
    url: str


class TestResponse(BaseModel):
    success: bool
    message: str
    extractor: Optional[str] = None
    title: Optional[str] = None


# =============================================================================
# Site Credentials API
# =============================================================================


@router.get("/api/sites", response_model=List[SiteResponse])
async def list_sites(admin: dict = Depends(get_current_admin)):
    """List all configured sites."""
    sites = database.get_all_sites()
    return [
        SiteResponse(
            id=s["id"],
            name=s["name"],
            extractor_pattern=s["extractor_pattern"],
            enabled=bool(s["enabled"]),
            priority=s["priority"],
            credential_count=s["credential_count"],
            created_at=s["created_at"] or "",
            updated_at=s["updated_at"] or "",
        )
        for s in sites
    ]


@router.post("/api/sites", response_model=SiteResponse)
async def create_site(data: SiteCreate, admin: dict = Depends(get_current_admin)):
    """Create a new site configuration."""
    site_id = database.create_site(
        name=data.name,
        extractor_pattern=data.extractor_pattern,
        enabled=data.enabled,
        priority=data.priority,
        proxy_streaming=data.proxy_streaming,
    )

    # Add credentials
    for cred in data.credentials:
        is_encrypted = encryption.should_encrypt(cred.credential_type)
        value = encryption.encrypt(cred.value) if is_encrypted else cred.value
        database.add_credential(
            site_id=site_id, credential_type=cred.credential_type, key=cred.key, value=value, is_encrypted=is_encrypted
        )

    site = database.get_site(site_id)
    return _site_to_response(site)


@router.get("/api/sites/{site_id}", response_model=SiteResponse)
async def get_site(site_id: int, admin: dict = Depends(get_current_admin)):
    """Get a site with its credentials."""
    site = database.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return _site_to_response(site)


@router.put("/api/sites/{site_id}", response_model=SiteResponse)
async def update_site(site_id: int, data: SiteUpdate, admin: dict = Depends(get_current_admin)):
    """Update a site's configuration."""
    if not database.get_site(site_id):
        raise HTTPException(status_code=404, detail="Site not found")

    database.update_site(
        site_id,
        name=data.name,
        extractor_pattern=data.extractor_pattern,
        enabled=data.enabled,
        priority=data.priority,
        proxy_streaming=data.proxy_streaming,
    )

    site = database.get_site(site_id)
    return _site_to_response(site)


@router.delete("/api/sites/{site_id}")
async def delete_site(site_id: int, admin: dict = Depends(get_current_admin)):
    """Delete a site and its credentials."""
    if not database.delete_site(site_id):
        raise HTTPException(status_code=404, detail="Site not found")
    return {"success": True}


@router.post("/api/sites/{site_id}/credentials", response_model=CredentialResponse)
async def add_credential(site_id: int, data: CredentialCreate, admin: dict = Depends(get_current_admin)):
    """Add a credential to a site."""
    if not database.get_site(site_id):
        raise HTTPException(status_code=404, detail="Site not found")

    is_encrypted = encryption.should_encrypt(data.credential_type)
    value = encryption.encrypt(data.value) if is_encrypted else data.value

    cred_id = database.add_credential(
        site_id=site_id, credential_type=data.credential_type, key=data.key, value=value, is_encrypted=is_encrypted
    )

    cred = database.get_credential(cred_id)
    return CredentialResponse(
        id=cred["id"],
        credential_type=cred["credential_type"],
        key=cred["key"],
        has_value=True,
        is_encrypted=cred["is_encrypted"],
        created_at=cred["created_at"] or "",
    )


@router.delete("/api/sites/{site_id}/credentials/{credential_id}")
async def delete_credential(site_id: int, credential_id: int, admin: dict = Depends(get_current_admin)):
    """Delete a credential from a site."""
    cred = database.get_credential(credential_id)
    if not cred or cred["site_id"] != site_id:
        raise HTTPException(status_code=404, detail="Credential not found")

    database.delete_credential(credential_id)
    return {"success": True}


@router.post("/api/sites/{site_id}/test", response_model=TestResponse)
async def test_site_credentials(site_id: int, data: TestRequest, admin: dict = Depends(get_current_admin)):
    """Test site credentials by extracting a URL."""
    from ytdlp_wrapper import YtDlpError, extract_url, is_safe_url, is_valid_url

    site = database.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Validate URL format
    if not is_valid_url(data.url):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    # SSRF prevention - block requests to private/internal networks
    if not is_safe_url(data.url):
        raise HTTPException(status_code=403, detail="URL targets restricted network resources")

    try:
        # The extract_url function will automatically use credentials
        # once we modify ytdlp_wrapper.py
        info = await extract_url(data.url, use_cache=False)
        return TestResponse(
            success=True, message="Extraction successful", extractor=info.get("extractor"), title=info.get("title")
        )
    except YtDlpError as e:
        return TestResponse(success=False, message=str(e))
    except (ValueError, KeyError, TypeError, OSError) as e:
        return TestResponse(success=False, message=f"Error: {str(e)}")


# Popular sites that commonly need credentials
POPULAR_SITES = [
    {
        "id": "youtube",
        "name": "YouTube",
        "pattern": "youtube",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    },
    {
        "id": "tiktok",
        "name": "TikTok",
        "pattern": "tiktok",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.tiktok.com/@user/video/123",
    },
    {
        "id": "twitter",
        "name": "Twitter/X",
        "pattern": "twitter",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": False,
        "example_url": "https://twitter.com/user/status/123",
    },
    {
        "id": "instagram",
        "name": "Instagram",
        "pattern": "instagram",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": False,
        "example_url": "https://www.instagram.com/p/ABC123/",
    },
    {
        "id": "facebook",
        "name": "Facebook",
        "pattern": "facebook",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.facebook.com/watch?v=123",
    },
    {
        "id": "twitch",
        "name": "Twitch",
        "pattern": "twitch",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.twitch.tv/videos/123",
    },
    {
        "id": "vimeo",
        "name": "Vimeo",
        "pattern": "vimeo",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": False,
        "example_url": "https://vimeo.com/123456789",
    },
    {
        "id": "dailymotion",
        "name": "Dailymotion",
        "pattern": "dailymotion",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": False,
        "example_url": "https://www.dailymotion.com/video/x123abc",
    },
    {
        "id": "reddit",
        "name": "Reddit",
        "pattern": "reddit",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": False,
        "example_url": "https://www.reddit.com/r/videos/comments/abc123/",
    },
    {
        "id": "soundcloud",
        "name": "SoundCloud",
        "pattern": "soundcloud",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": False,
        "example_url": "https://soundcloud.com/artist/track",
    },
    {
        "id": "spotify",
        "name": "Spotify",
        "pattern": "spotify",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://open.spotify.com/track/abc123",
    },
    {
        "id": "bilibili",
        "name": "Bilibili",
        "pattern": "bilibili",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.bilibili.com/video/BV1xx411c7mD",
    },
    {
        "id": "niconico",
        "name": "Niconico",
        "pattern": "niconico",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.nicovideo.jp/watch/sm12345678",
    },
    {
        "id": "crunchyroll",
        "name": "Crunchyroll",
        "pattern": "crunchyroll",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.crunchyroll.com/watch/ABC123",
    },
    {
        "id": "funimation",
        "name": "Funimation",
        "pattern": "funimation",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.funimation.com/shows/show-name/episode",
    },
    {
        "id": "patreon",
        "name": "Patreon",
        "pattern": "patreon",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": False,
        "example_url": "https://www.patreon.com/posts/123456",
    },
    {
        "id": "nebula",
        "name": "Nebula",
        "pattern": "nebula",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://nebula.tv/videos/creator-video-title",
    },
    {
        "id": "dropout",
        "name": "Dropout",
        "pattern": "dropout",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.dropout.tv/videos/video-title",
    },
    {
        "id": "floatplane",
        "name": "Floatplane",
        "pattern": "floatplane",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.floatplane.com/post/abc123",
    },
    {
        "id": "curiositystream",
        "name": "CuriosityStream",
        "pattern": "curiositystream",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://curiositystream.com/video/123",
    },
    {
        "id": "lynda",
        "name": "LinkedIn Learning",
        "pattern": "lynda",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.linkedin.com/learning/course-name/lesson",
    },
    {
        "id": "udemy",
        "name": "Udemy",
        "pattern": "udemy",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.udemy.com/course/course-name/learn/lecture/123",
    },
    {
        "id": "skillshare",
        "name": "Skillshare",
        "pattern": "skillshare",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": True,
        "example_url": "https://www.skillshare.com/classes/class-name/123",
    },
    {
        "id": "pornhub",
        "name": "Pornhub",
        "pattern": "pornhub",
        "suggested_credentials": ["cookies_file"],
        "proxy_recommended": False,
        "example_url": "https://www.pornhub.com/view_video.php?viewkey=abc123",
    },
]


@router.get("/api/extractors")
async def list_extractors(admin: dict = Depends(get_current_admin)):
    """List popular sites for the site selector dropdown."""
    return POPULAR_SITES


# =============================================================================
# Helper Functions
# =============================================================================


def _site_to_response(site: dict) -> SiteResponse:
    """Convert database site dict to SiteResponse."""
    credentials = None
    if "credentials" in site:
        credentials = [
            CredentialResponse(
                id=c["id"],
                credential_type=c["credential_type"],
                key=c["key"],
                has_value=bool(c.get("value")),
                is_encrypted=bool(c["is_encrypted"]),
                created_at=c["created_at"] or "",
            )
            for c in site["credentials"]
        ]

    return SiteResponse(
        id=site["id"],
        name=site["name"],
        extractor_pattern=site["extractor_pattern"],
        enabled=bool(site["enabled"]),
        priority=site["priority"],
        proxy_streaming=bool(site.get("proxy_streaming", True)),
        credentials=credentials,
        created_at=site["created_at"] or "",
        updated_at=site["updated_at"] or "",
    )
