document.addEventListener('alpine:init', () => {
    Alpine.data('watchedChannelsManager', () => ({
        channels: [],
        loading: true,
        refreshing: false,

        init() {
            // Load if we're on the watched-channels tab on page load
            if (window.location.hash === '#watched-channels') {
                this.loadChannels();
            }
        },

        async loadChannels() {
            this.loading = true;
            try {
                this.channels = await Alpine.store('api').get('/watched-channels');
                this.sortChannels();
            } catch (err) {
                console.error('Failed to load watched channels:', err);
            } finally {
                this.loading = false;
            }
        },

        sortChannels() {
            // Sort by last_video_published (most recent first)
            // Channels without videos go to the bottom
            this.channels.sort((a, b) => {
                const aTime = a.last_video_published || 0;
                const bTime = b.last_video_published || 0;
                return bTime - aTime; // Descending order (newest first)
            });
        },

        async refreshAll() {
            this.refreshing = true;
            
            try {
                await Alpine.store('api').post('/watched-channels/refresh-all');
                
                // Show immediate feedback
                Alpine.store('toast').show('Refresh started for all channels', 'info');
                
                // Poll for updates (every 5 seconds for max 5 minutes = 60 attempts)
                await this.pollForUpdates();
                
                Alpine.store('toast').show('All channels refreshed', 'success');
            } catch (err) {
                console.error('Failed to refresh channels:', err);
                Alpine.store('toast').show('Failed to start refresh', 'error');
            } finally {
                this.refreshing = false;
            }
        },

        async pollForUpdates(maxAttempts = 60) {
            for (let i = 0; i < maxAttempts; i++) {
                await new Promise(resolve => setTimeout(resolve, 5000));
                
                try {
                    // Reload channel list to show updated timestamps, video counts, etc.
                    this.channels = await Alpine.store('api').get('/watched-channels');
                    this.sortChannels();
                } catch (err) {
                    console.error('Failed to reload channels:', err);
                }
            }
        },

        formatTimeAgo(dateString) {
            return Alpine.store('utils').formatTimeAgo(dateString);
        }
    }));
});
