"""Auto-provisioning from environment variables for automated deployments."""

import logging

import auth
import config
import database
import settings as settings_module

logger = logging.getLogger(__name__)


def apply_env_provisioning():
    """Apply provisioning from environment variables (runs once at startup).

    - ADMIN_USERNAME + ADMIN_PASSWORD: creates or updates admin user
    - INVIDIOUS_INSTANCE_URL: configures Invidious instance and enables proxy
    """
    _provision_admin_user()
    _provision_invidious()


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
