document.addEventListener('alpine:init', () => {
    Alpine.data('videoInfo', () => ({
        descriptionExpanded: false,

        formatNumber(num) {
            if (!num) return '0';
            if (num >= 1000000) {
                return (num / 1000000).toFixed(1) + 'M';
            }
            if (num >= 1000) {
                return (num / 1000).toFixed(1) + 'K';
            }
            return num.toLocaleString();
        },

        formatDuration(seconds) {
            if (!seconds) return '';
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = seconds % 60;

            if (hours > 0) {
                return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
            }
            return `${minutes}:${secs.toString().padStart(2, '0')}`;
        },

        formatDescription(text) {
            if (!text) return '';
            // If it's already HTML, return as-is
            if (text.includes('<')) return text;
            // Otherwise, escape and convert URLs to links
            return this.escapeHtml(text)
                .replace(
                    /(https?:\/\/[^\s<]+)/g,
                    '<a href="$1" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline">$1</a>'
                );
        },

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    }));
});
