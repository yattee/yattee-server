document.addEventListener('alpine:init', () => {
    Alpine.data('sitesManager', () => ({
        sites: [],
        loading: true,
        view: 'list',

        editingSiteId: null,
        selectedExtractor: '',
        customName: '',
        customPattern: '',
        proxyStreaming: true,
        credentials: [],
        credentialDropdownOpen: false,

        get isEditing() {
            return this.editingSiteId !== null;
        },

        get showCustomFields() {
            return this.selectedExtractor === 'custom';
        },

        get formTitle() {
            return this.isEditing ? 'Edit Site' : 'Add Site';
        },

        async init() {
            await this.loadSites();
        },

        async loadSites() {
            this.loading = true;
            try {
                this.sites = await Alpine.store('api').get('/sites');
            } catch (err) {
                console.error('Failed to load sites:', err);
            } finally {
                this.loading = false;
            }
        },

        async toggleSite(siteId, enabled) {
            try {
                await Alpine.store('api').put(`/sites/${siteId}`, { enabled });
                Alpine.store('toast').success(enabled ? 'Site enabled' : 'Site disabled');
            } catch (err) {
                await this.loadSites();
            }
        },

        async deleteSite(siteId) {
            if (!confirm('Delete this site and all its credentials?')) return;
            try {
                await Alpine.store('api').delete(`/sites/${siteId}`);
                Alpine.store('toast').success('Site deleted');
                await this.loadSites();
            } catch (err) {
                // Error handled by API store
            }
        },

        showAddForm() {
            this.resetForm();
            this.view = 'form';
        },

        async showEditForm(siteId) {
            try {
                const site = await Alpine.store('api').get(`/sites/${siteId}`);
                this.editingSiteId = siteId;

                const extractor = Alpine.store('app').getExtractorByPattern(site.extractor_pattern);
                if (extractor) {
                    this.selectedExtractor = extractor.id;
                } else {
                    this.selectedExtractor = 'custom';
                    this.customName = site.name;
                    this.customPattern = site.extractor_pattern;
                }

                this.proxyStreaming = site.proxy_streaming !== false;

                this.credentials = (site.credentials || []).map(c => ({
                    id: c.id,
                    credential_type: c.credential_type,
                    key: c.key,
                    value: '',
                    hasExisting: c.has_value
                }));

                this.view = 'form';
            } catch (err) {
                // Error handled by API store
            }
        },

        resetForm() {
            this.editingSiteId = null;
            this.selectedExtractor = '';
            this.customName = '';
            this.customPattern = '';
            this.proxyStreaming = true;
            this.proxyRecommended = false;
            this.credentials = [];
        },

        hideForm() {
            this.resetForm();
            this.view = 'list';
        },

        onExtractorChange() {
            if (this.selectedExtractor === 'custom') {
                this.proxyRecommended = false;
            } else if (this.selectedExtractor && !this.isEditing) {
                const extractor = Alpine.store('app').getExtractorById(this.selectedExtractor);
                if (extractor) {
                    if (extractor.suggested_credentials) {
                        this.credentials = extractor.suggested_credentials.map(type => ({
                            credential_type: type,
                            key: '',
                            value: ''
                        }));
                    }
                }
            }
        },

        addCredential(type) {
            const credType = Alpine.store('app').credentialTypes.find(t => t.value === type);
            this.credentials.push({
                credential_type: type,
                key: '',
                value: credType?.isFlag ? 'true' : ''
            });
            this.credentialDropdownOpen = false;
        },

        removeCredential(index) {
            this.credentials.splice(index, 1);
        },

        getCredentialType(value) {
            return Alpine.store('app').credentialTypes.find(t => t.value === value) || { label: value };
        },

        async saveSite() {
            let name, extractor_pattern;

            if (this.selectedExtractor === 'custom') {
                name = this.customName;
                extractor_pattern = this.customPattern;
                if (!name || !extractor_pattern) {
                    Alpine.store('toast').error('Name and extractor pattern are required');
                    return;
                }
            } else if (this.selectedExtractor) {
                const extractor = Alpine.store('app').getExtractorById(this.selectedExtractor);
                if (!extractor) {
                    Alpine.store('toast').error('Please select a valid site');
                    return;
                }
                name = extractor.name;
                extractor_pattern = extractor.pattern;
            } else {
                Alpine.store('toast').error('Please select a site');
                return;
            }

            try {
                if (this.editingSiteId) {
                    await this.updateSite(name, extractor_pattern);
                } else {
                    await this.createSite(name, extractor_pattern);
                }
                this.hideForm();
                await this.loadSites();
            } catch (err) {
                // Error handled by API store
            }
        },

        async createSite(name, extractor_pattern) {
            const credentials = this.credentials
                .filter(c => c.value)
                .map(c => ({
                    credential_type: c.credential_type,
                    key: c.key || null,
                    value: c.value
                }));

            await Alpine.store('api').post('/sites', {
                name,
                extractor_pattern,
                priority: 0,
                enabled: true,
                proxy_streaming: this.proxyStreaming,
                credentials
            });

            Alpine.store('toast').success('Site created');
        },

        async updateSite(name, extractor_pattern) {
            const siteId = this.editingSiteId;
            const api = Alpine.store('api');

            await api.put(`/sites/${siteId}`, {
                name,
                extractor_pattern,
                priority: 0,
                proxy_streaming: this.proxyStreaming
            });

            const site = await api.get(`/sites/${siteId}`);
            const keepIds = new Set();

            for (const cred of this.credentials) {
                if (cred.id && cred.hasExisting && !cred.value) {
                    keepIds.add(cred.id);
                }
            }

            for (const cred of site.credentials || []) {
                if (!keepIds.has(cred.id)) {
                    await api.delete(`/sites/${siteId}/credentials/${cred.id}`);
                }
            }

            for (const cred of this.credentials) {
                if (cred.value) {
                    await api.post(`/sites/${siteId}/credentials`, {
                        credential_type: cred.credential_type,
                        key: cred.key || null,
                        value: cred.value
                    });
                }
            }

            Alpine.store('toast').success('Site updated');
        }
    }));
});
