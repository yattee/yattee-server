document.addEventListener('alpine:init', () => {
    Alpine.data('testModal', () => ({
        open: false,
        siteId: null,
        testUrl: '',
        placeholder: 'Enter a video URL to test',
        testing: false,
        result: null,

        async openForSite(siteId) {
            this.siteId = siteId;
            this.testUrl = '';
            this.result = null;
            this.placeholder = 'Enter a video URL to test';

            try {
                const site = await Alpine.store('api').get(`/sites/${siteId}`);
                const extractor = Alpine.store('app').extractors.find(e =>
                    e.pattern === site.extractor_pattern || e.id === site.extractor_pattern
                );
                if (extractor?.example_url) {
                    this.placeholder = extractor.example_url;
                }
            } catch (err) {
                console.error('Failed to load site:', err);
            }

            this.open = true;
        },

        close() {
            this.open = false;
            this.siteId = null;
            this.testUrl = '';
            this.result = null;
        },

        async runTest() {
            if (!this.testUrl) {
                Alpine.store('toast').error('Please enter a URL');
                return;
            }

            this.testing = true;
            this.result = null;

            try {
                const result = await Alpine.store('api').post(`/sites/${this.siteId}/test`, {
                    url: this.testUrl
                });
                this.result = result;
            } catch (err) {
                this.result = { success: false, message: err.message };
            } finally {
                this.testing = false;
            }
        }
    }));
});
