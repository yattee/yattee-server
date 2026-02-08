document.addEventListener('alpine:init', () => {
    Alpine.store('tabs', {
        activeTab: 'sites',

        tabs: [
            { id: 'sites', label: 'Sites' },
            { id: 'users', label: 'Users' },
            { id: 'watched-channels', label: 'Channels' },
            { id: 'settings', label: 'Settings' }
        ],

        tabLabel(tabId) {
            return this.tabs.find(t => t.id === tabId)?.label ?? tabId;
        },

        updateTitle(tabId) {
            document.title = `${this.tabLabel(tabId)} - Yattee Server`;
        },

        init() {
            // Read initial tab from URL hash
            const hash = window.location.hash.slice(1);
            if (hash && this.tabs.some(t => t.id === hash)) {
                this.activeTab = hash;
                window.dispatchEvent(new CustomEvent('tab-changed', { detail: hash }));
            }
            this.updateTitle(this.activeTab);

            // Handle browser back/forward
            window.addEventListener('popstate', () => {
                const hash = window.location.hash.slice(1);
                if (hash && this.tabs.some(t => t.id === hash)) {
                    this.activeTab = hash;
                    this.updateTitle(hash);
                    window.dispatchEvent(new CustomEvent('tab-changed', { detail: hash }));
                }
            });
        },

        switchTab(tabId) {
            this.activeTab = tabId;
            this.updateTitle(tabId);
            window.location.hash = tabId;
            window.dispatchEvent(new CustomEvent('tab-changed', { detail: tabId }));
        },

        isActive(tabId) {
            return this.activeTab === tabId;
        }
    });
});
