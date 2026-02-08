document.addEventListener('alpine:init', () => {
    Alpine.store('utils', {
        escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        formatTimeAgo(dateInput) {
            if (!dateInput) return '';

            let date;
            if (typeof dateInput === 'number') {
                // Unix timestamp (seconds)
                date = new Date(dateInput * 1000);
            } else {
                // ISO 8601 string - append Z if no timezone to treat as UTC
                let normalized = dateInput;
                if (!dateInput.endsWith('Z') && !dateInput.includes('+')) {
                    normalized = dateInput + 'Z';
                }
                date = new Date(normalized);
            }

            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);

            if (diffMins < 1) return 'just now';
            if (diffMins < 60) return `${diffMins}m ago`;
            if (diffHours < 24) return `${diffHours}h ago`;
            if (diffDays < 7) return `${diffDays}d ago`;
            return date.toLocaleDateString();
        }
    });
});
