"""Auto-provisioning from environment variables for automated deployments."""

import logging

import auth
import config
import database
import egress
import settings as settings_module

logger = logging.getLogger(__name__)


def apply_env_provisioning():
    """Apply provisioning from environment variables (runs once at startup).

    - ADMIN_USERNAME + ADMIN_PASSWORD: creates or updates admin user
    - INVIDIOUS_INSTANCE_URL: configures Invidious instance and enables proxy
    - YT_EGRESS_PROXY: configures HTTP/SOCKS proxy for YouTube-bound traffic
    - YT_IP_FAMILY: forces IP family (auto/ipv4/ipv6) for YouTube-bound traffic
    - YT_POT_ENABLED + YT_POT_PROVIDER_URL: configures the PO token provider
    """
    _provision_admin_user()
    _provision_invidious()
    _provision_egress_proxy()
    _provision_ip_family()
    _provision_pot()


def _provision_admin_user():
    """Create or update admin user from env vars."""
    username = config.ADMIN_USERNAME
    password = config.ADMIN_PASSWORD

    if not username or not password:
        return

    existing = database.get_user_by_username(username)
    if existing:
        database.update_user_password(existing["id"], auth.hash_password(password))
        database.update_user(existing["id"], is_admin=True)
        logger.info("ENV provisioning: updated admin user '%s'", username)
    else:
        database.create_admin(username, auth.hash_password(password))
        logger.info("ENV provisioning: created admin user '%s'", username)


def _provision_invidious():
    """Configure Invidious instance URL from env var."""
    url = config.INVIDIOUS_INSTANCE_URL
    if not url:
        return

    s = settings_module.load_settings()
    s.invidious_instance = url.rstrip("/")
    s.invidious_enabled = True
    settings_module.save_settings(s)
    logger.info("ENV provisioning: configured Invidious instance '%s'", url)


def _provision_egress_proxy():
    """Configure YouTube egress proxy from env var."""
    url = config.YT_EGRESS_PROXY
    if not url:
        return

    s = settings_module.load_settings()
    try:
        # Store the canonical form (credentials percent-encoded) so every
        # client — yt-dlp, InnerTube, relay — reads exactly the same value.
        s.yt_egress_proxy = egress.normalize_proxy_url(url)
    except egress.ProxyConfigError as e:
        # Keep the raw value: the runtime fails CLOSED with a clear error
        # instead of silently falling back to direct datacenter egress.
        s.yt_egress_proxy = url
        logger.error(
            "ENV provisioning: YT_EGRESS_PROXY is malformed (%s); YouTube requests will fail "
            "until it is fixed",
            e,
        )
    s.yt_egress_proxy_enabled = True
    settings_module.save_settings(s)
    logger.info("ENV provisioning: configured YT egress proxy %s", egress.redact_proxy_url(url))


def _provision_ip_family():
    """Configure forced IP family for YouTube egress from env var."""
    family = config.YT_IP_FAMILY
    if not family:
        return

    family = family.strip().lower()
    if family not in ("auto", "ipv4", "ipv6"):
        logger.warning("ENV provisioning: ignoring invalid YT_IP_FAMILY %r (use auto/ipv4/ipv6)", family)
        return

    s = settings_module.load_settings()
    s.yt_ip_family = family
    settings_module.save_settings(s)
    logger.info("ENV provisioning: configured YT IP family '%s'", family)


def _provision_pot():
    """Configure the PO token provider from env vars."""
    enabled = config.YT_POT_ENABLED
    url = config.YT_POT_PROVIDER_URL
    if enabled is None and url is None:
        return

    s = settings_module.load_settings()
    if enabled is not None:
        value = enabled.strip().lower()
        if value in ("true", "1", "yes"):
            s.yt_pot_enabled = True
        elif value in ("false", "0", "no"):
            s.yt_pot_enabled = False
        else:
            logger.warning("ENV provisioning: ignoring invalid YT_POT_ENABLED %r (use true/false)", enabled)
    if url is not None:
        s.yt_pot_provider_url = url.rstrip("/")
    settings_module.save_settings(s)
    logger.info(
        "ENV provisioning: configured POT provider (enabled=%s, url=%s)",
        s.yt_pot_enabled,
        s.yt_pot_provider_url or "bundled",
    )
