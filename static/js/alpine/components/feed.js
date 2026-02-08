document.addEventListener('alpine:init', () => {
    Alpine.data('feedManager', () => ({
        videos: [],
        loading: true,
        loadingMore: false,
        refreshing: false,
        total: 0,
        hasMore: false,
        offset: 0,
        perPage: 30,

        init() {
            if (window.location.hash === '#feed') {
                this.loadFeed();
            }
        },

        async loadFeed() {
            this.loading = true;
            this.offset = 0;
            try {
                const data = await Alpine.store('api').get(`/feed?limit=${this.perPage}&offset=0`);
                this.videos = data.videos;
                this.total = data.total;
                this.hasMore = data.has_more;
                this.offset = this.perPage;
            } catch (err) {
                console.error('Failed to load feed:', err);
            } finally {
                this.loading = false;
            }
        },

        async loadMore() {
            if (this.loadingMore || !this.hasMore) return;
            this.loadingMore = true;
            try {
                const data = await Alpine.store('api').get(`/feed?limit=${this.perPage}&offset=${this.offset}`);
                this.videos = [...this.videos, ...data.videos];
                this.hasMore = data.has_more;
                this.offset += this.perPage;
            } catch (err) {
                console.error('Failed to load more:', err);
            } finally {
                this.loadingMore = false;
            }
        },

        async refreshFeed() {
            if (this.refreshing) return;
            this.refreshing = true;
            try {
                await Alpine.store('api').post('/feed/refresh');
                Alpine.store('toast').success('Feed refreshed');
                await this.loadFeed();
            } catch (err) {
                // Error handled by API store
            } finally {
                this.refreshing = false;
            }
        },

        formatDuration(seconds) {
            if (!seconds) return '';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = seconds % 60;
            if (h > 0) {
                return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
            }
            return `${m}:${s.toString().padStart(2, '0')}`;
        },

        formatTimeAgo(timestamp) {
            if (!timestamp) return '';
            return Alpine.store('utils').formatTimeAgo(new Date(timestamp * 1000).toISOString());
        },

        formatViewCount(count) {
            if (!count) return '';
            if (count >= 1000000) {
                return (count / 1000000).toFixed(1) + 'M views';
            }
            if (count >= 1000) {
                return (count / 1000).toFixed(1) + 'K views';
            }
            return count + ' views';
        }
    }));
});
