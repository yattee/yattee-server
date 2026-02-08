document.addEventListener('alpine:init', () => {
    Alpine.data('watchPage', () => ({
        urlInput: '',

        init() {
            // Pre-fill URL input from query param
            const params = new URLSearchParams(window.location.search);
            const url = params.get('url');
            if (url) {
                this.urlInput = url;
            }
        },

        async loadVideo() {
            if (!this.urlInput) return;
            await Alpine.store('watch').loadVideo(this.urlInput);
        }
    }));
});
