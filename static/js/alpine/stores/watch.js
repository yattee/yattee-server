document.addEventListener('alpine:init', () => {
    Alpine.store('watch', {
        currentUser: null,
        extractionInfo: {},
        videoData: null,
        loading: false,
        loadingStep: '',
        error: null,
        autoplay: localStorage.getItem('watchAutoplay') !== 'false',

        toggleAutoplay() {
            this.autoplay = !this.autoplay;
            localStorage.setItem('watchAutoplay', this.autoplay);
        },

        get placeholderText() {
            if (this.extractionInfo.allow_all_sites) {
                return 'Paste any video URL (thousands of sites supported by yt-dlp)';
            }
            const sites = this.extractionInfo.enabled_sites;
            if (sites && sites.length > 0) {
                return `Paste a video URL (${sites.join(', ')})`;
            }
            return 'Paste a video URL';
        },

        async init() {
            try {
                // Fetch current user info
                const response = await fetch('/api/user/me', {
                    credentials: 'same-origin'
                });

                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }

                if (response.ok) {
                    const data = await response.json();
                    this.currentUser = data;
                    this.extractionInfo = data.extraction_info || {};
                }

                // Check for URL parameter to auto-load
                const params = new URLSearchParams(window.location.search);
                const url = params.get('url');
                if (url) {
                    await this.loadVideo(url);
                }
            } catch (err) {
                console.error('Watch init failed:', err);
            }
        },

        async loadVideo(url) {
            if (!url) return;

            // Prevent double-loading the same URL
            if (this._loadingUrl === url) {
                return;
            }
            this._loadingUrl = url;

            this.loading = true;
            this.error = null;
            this.videoData = null;
            this.loadingStep = 'Connecting to server...';

            try {
                this.loadingStep = 'Extracting video information...';

                const response = await fetch(`/api/v1/extract?url=${encodeURIComponent(url)}`, {
                    credentials: 'same-origin'
                });

                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Failed to extract video');
                }

                this.loadingStep = 'Loading player...';
                this.videoData = data;

                // Update URL for shareable link (without triggering reload)
                const newUrl = new URL(window.location);
                newUrl.searchParams.set('url', url);
                window.history.replaceState({}, '', newUrl);

                // Update page title
                if (data.title) {
                    document.title = `${data.title} - Watch - Yattee Server`;
                }

            } catch (err) {
                console.error('Video load failed:', err);
                this.error = err.message;
                this._loadingUrl = null;  // Allow retry on error
            } finally {
                this.loading = false;
                this.loadingStep = '';
            }
        }
    });
});
