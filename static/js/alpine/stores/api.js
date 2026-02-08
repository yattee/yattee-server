document.addEventListener('alpine:init', () => {
    Alpine.store('api', {
        baseUrl: '/api',

        async request(endpoint, options = {}) {
            try {
                const response = await fetch(`${this.baseUrl}${endpoint}`, {
                    headers: {
                        'Content-Type': 'application/json',
                        ...options.headers
                    },
                    credentials: 'same-origin',
                    ...options
                });

                if (response.status === 401) {
                    window.location.href = '/login';
                    throw new Error('Not authenticated');
                }

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Request failed');
                }

                return data;
            } catch (error) {
                if (error.message !== 'Not authenticated') {
                    Alpine.store('toast').error(error.message);
                }
                throw error;
            }
        },

        get(endpoint) {
            return this.request(endpoint);
        },

        post(endpoint, body) {
            return this.request(endpoint, {
                method: 'POST',
                body: JSON.stringify(body)
            });
        },

        put(endpoint, body) {
            return this.request(endpoint, {
                method: 'PUT',
                body: JSON.stringify(body)
            });
        },

        delete(endpoint) {
            return this.request(endpoint, { method: 'DELETE' });
        }
    });
});
