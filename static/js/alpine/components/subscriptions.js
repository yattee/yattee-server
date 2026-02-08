document.addEventListener('alpine:init', () => {
    Alpine.data('subscriptionsManager', () => ({
        subscriptions: [],
        loading: true,
        newChannelUrl: '',
        subscribing: false,

        init() {
            // Load if we're on the subscriptions tab on page load
            if (window.location.hash === '#subscriptions') {
                this.loadSubscriptions();
            }
        },

        async loadSubscriptions() {
            this.loading = true;
            try {
                this.subscriptions = await Alpine.store('api').get('/subscriptions');
            } catch (err) {
                console.error('Failed to load subscriptions:', err);
            } finally {
                this.loading = false;
            }
        },

        async unsubscribe(subscriptionId, channelName) {
            if (!confirm(`Unsubscribe from "${channelName}"?`)) return;
            try {
                await Alpine.store('api').delete(`/subscriptions/${subscriptionId}`);
                Alpine.store('toast').success('Unsubscribed');
                await this.loadSubscriptions();
            } catch (err) {
                // Error handled by API store
            }
        },

        async subscribeByUrl() {
            if (!this.newChannelUrl || this.subscribing) return;
            this.subscribing = true;
            try {
                await Alpine.store('api').post('/subscriptions/url', { url: this.newChannelUrl });
                Alpine.store('toast').success('Subscribed!');
                this.newChannelUrl = '';
                await this.loadSubscriptions();
            } catch (err) {
                // Error handled by API store
            } finally {
                this.subscribing = false;
            }
        },

        formatTimeAgo(dateString) {
            return Alpine.store('utils').formatTimeAgo(dateString);
        },

        escapeHtml(text) {
            return Alpine.store('utils').escapeHtml(text);
        }
    }));
});
