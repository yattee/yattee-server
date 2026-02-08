document.addEventListener('alpine:init', () => {
    Alpine.data('settingsManager', () => ({
        loading: true,

        ytdlp_path: 'yt-dlp',
        ytdlp_timeout: 120,

        cache_video_ttl: 3600,
        cache_search_ttl: 900,
        cache_channel_ttl: 1800,
        cache_avatar_ttl: 86400,
        cache_extract_ttl: 900,

        invidious_enabled: true,
        invidious_instance: '',
        invidious_timeout: 10,
        invidious_max_retries: 3,
        invidious_retry_delay: 1.0,
        invidious_proxy_videos: true,
        invidious_proxy_channels: true,
        invidious_proxy_channel_tabs: true,
        invidious_proxy_playlists: true,
        invidious_proxy_captions: true,
        invidious_proxy_thumbnails: true,
        invidious_author_thumbnails: false,

        feed_fetch_interval: 1800,
        feed_fetch_interval_minutes: 30,
        feed_channel_delay: 2,
        feed_max_videos: 30,
        feed_video_max_age: 30,
        feed_ytdlp_use_flat_playlist: false,
        feed_fallback_ytdlp_on_414: false,
        feed_fallback_ytdlp_on_error: true,

        default_search_results: 20,
        max_search_results: 50,

        allow_all_sites_for_extraction: false,
        rate_limit_window: 60,
        rate_limit_max_failures: 5,
        proxy_download_max_age: 86400,
        proxy_download_max_age_hours: 24,
        dns_cache_ttl: 30,
        proxy_max_concurrent_downloads: 3,
        rate_limit_cleanup_interval: 300,
        rate_limit_cleanup_interval_minutes: 5,

        init() {
            // Load if we're on the settings tab on page load
            if (window.location.hash === '#settings') {
                this.loadSettings();
            }
        },

        async loadSettings() {
            this.loading = true;
            try {
                const settings = await Alpine.store('api').get('/settings');
                this.ytdlp_path = settings.ytdlp_path || 'yt-dlp';
                this.ytdlp_timeout = settings.ytdlp_timeout || 120;
                this.cache_video_ttl = settings.cache_video_ttl || 3600;
                this.cache_search_ttl = settings.cache_search_ttl || 900;
                this.cache_channel_ttl = settings.cache_channel_ttl || 1800;
                this.cache_avatar_ttl = settings.cache_avatar_ttl || 86400;
                this.cache_extract_ttl = settings.cache_extract_ttl || 900;
                this.invidious_enabled = settings.invidious_enabled !== false;
                this.invidious_instance = settings.invidious_instance || '';
                this.invidious_timeout = settings.invidious_timeout || 10;
                this.invidious_max_retries = settings.invidious_max_retries || 3;
                this.invidious_retry_delay = settings.invidious_retry_delay || 1.0;
                this.invidious_proxy_videos = settings.invidious_proxy_videos || false;
                this.invidious_proxy_channels = settings.invidious_proxy_channels !== false;
                this.invidious_proxy_channel_tabs = settings.invidious_proxy_channel_tabs !== false;
                this.invidious_proxy_playlists = settings.invidious_proxy_playlists !== false;
                this.invidious_proxy_captions = settings.invidious_proxy_captions || false;
                this.invidious_proxy_thumbnails = settings.invidious_proxy_thumbnails !== false;
                this.invidious_author_thumbnails = settings.invidious_author_thumbnails || false;
                this.feed_fetch_interval = settings.feed_fetch_interval || 1800;
                this.feed_fetch_interval_minutes = Math.round(this.feed_fetch_interval / 60);
                this.feed_channel_delay = settings.feed_channel_delay || 2;
                this.feed_max_videos = settings.feed_max_videos || 30;
                this.feed_video_max_age = settings.feed_video_max_age || 30;
                this.feed_ytdlp_use_flat_playlist = settings.feed_ytdlp_use_flat_playlist || false;
                this.feed_fallback_ytdlp_on_414 = settings.feed_fallback_ytdlp_on_414 || false;
                this.feed_fallback_ytdlp_on_error = settings.feed_fallback_ytdlp_on_error !== false;
                this.default_search_results = settings.default_search_results || 20;
                this.max_search_results = settings.max_search_results || 50;
                this.allow_all_sites_for_extraction = settings.allow_all_sites_for_extraction || false;
                this.rate_limit_window = settings.rate_limit_window || 60;
                this.rate_limit_max_failures = settings.rate_limit_max_failures || 5;
                this.proxy_download_max_age = settings.proxy_download_max_age || 86400;
                this.proxy_download_max_age_hours = Math.round(this.proxy_download_max_age / 3600);
                this.dns_cache_ttl = settings.dns_cache_ttl || 30;
                this.proxy_max_concurrent_downloads = settings.proxy_max_concurrent_downloads || 3;
                this.rate_limit_cleanup_interval = settings.rate_limit_cleanup_interval || 300;
                this.rate_limit_cleanup_interval_minutes = Math.round(this.rate_limit_cleanup_interval / 60);
            } catch (err) {
                console.error('Failed to load settings:', err);
            } finally {
                this.loading = false;
            }
        },

        async saveSettings() {
            try {
                const settings = {
                    ytdlp_path: this.ytdlp_path,
                    ytdlp_timeout: parseInt(this.ytdlp_timeout) || 120,
                    cache_video_ttl: parseInt(this.cache_video_ttl) || 3600,
                    cache_search_ttl: parseInt(this.cache_search_ttl) || 900,
                    cache_channel_ttl: parseInt(this.cache_channel_ttl) || 1800,
                    cache_avatar_ttl: parseInt(this.cache_avatar_ttl) || 86400,
                    cache_extract_ttl: parseInt(this.cache_extract_ttl) || 900,
                    invidious_enabled: this.invidious_enabled,
                    invidious_instance: this.invidious_instance || null,
                    invidious_timeout: parseInt(this.invidious_timeout) || 10,
                    invidious_max_retries: parseInt(this.invidious_max_retries) || 3,
                    invidious_retry_delay: parseFloat(this.invidious_retry_delay) || 1.0,
                    invidious_proxy_videos: this.invidious_proxy_videos,
                    invidious_proxy_channels: this.invidious_proxy_channels,
                    invidious_proxy_channel_tabs: this.invidious_proxy_channel_tabs,
                    invidious_proxy_playlists: this.invidious_proxy_playlists,
                    invidious_proxy_captions: this.invidious_proxy_captions,
                    invidious_proxy_thumbnails: this.invidious_proxy_thumbnails,
                    invidious_author_thumbnails: this.invidious_author_thumbnails,
                    feed_fetch_interval: (parseInt(this.feed_fetch_interval_minutes) || 30) * 60,
                    feed_channel_delay: parseInt(this.feed_channel_delay) || 2,
                    feed_max_videos: parseInt(this.feed_max_videos) || 30,
                    feed_video_max_age: parseInt(this.feed_video_max_age) || 30,
                    feed_ytdlp_use_flat_playlist: this.feed_ytdlp_use_flat_playlist,
                    feed_fallback_ytdlp_on_414: this.feed_fallback_ytdlp_on_414,
                    feed_fallback_ytdlp_on_error: this.feed_fallback_ytdlp_on_error,
                    default_search_results: parseInt(this.default_search_results) || 20,
                    max_search_results: parseInt(this.max_search_results) || 50,
                    allow_all_sites_for_extraction: this.allow_all_sites_for_extraction,
                    rate_limit_window: parseInt(this.rate_limit_window) || 60,
                    rate_limit_max_failures: parseInt(this.rate_limit_max_failures) || 5,
                    proxy_download_max_age: (parseInt(this.proxy_download_max_age_hours) || 24) * 3600,
                    dns_cache_ttl: parseInt(this.dns_cache_ttl) || 30,
                    proxy_max_concurrent_downloads: parseInt(this.proxy_max_concurrent_downloads) || 3,
                    rate_limit_cleanup_interval: (parseInt(this.rate_limit_cleanup_interval_minutes) || 5) * 60
                };

                await Alpine.store('api').put('/settings', settings);
                Alpine.store('toast').success('Settings saved successfully');
            } catch (err) {
                // Error handled by API store
            }
        }
    }));
});
