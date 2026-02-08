document.addEventListener('alpine:init', () => {
    Alpine.store('app', {
        currentUser: null,
        extractors: [],
        credentialTypes: [
            {
                value: 'cookies_file',
                label: 'Cookies (Netscape format)',
                description: 'Export using: <a href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank" class="text-primary hover:underline">Get cookies.txt LOCALLY</a> (Chrome), <a href="https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/" target="_blank" class="text-primary hover:underline">cookies.txt</a> (Firefox)',
                hasKey: false,
                isTextarea: true
            }
        ],

        async init() {
            try {
                this.currentUser = await Alpine.store('api').get('/user/me');
                this.extractors = await Alpine.store('api').get('/extractors');
            } catch (err) {
                console.error('App init failed:', err);
            }
        },

        getExtractorByPattern(pattern) {
            return this.extractors.find(e => e.pattern === pattern);
        },

        getExtractorById(id) {
            return this.extractors.find(e => e.id === id);
        }
    });
});
