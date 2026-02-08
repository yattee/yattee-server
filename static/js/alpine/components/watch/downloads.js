document.addEventListener('alpine:init', () => {
    Alpine.data('downloadsPanel', () => ({
        expanded: false,

        get combinedFormats() {
            const data = Alpine.store('watch').videoData;
            if (!data?.formatStreams) return [];
            return data.formatStreams;
        },

        get videoOnlyFormats() {
            const data = Alpine.store('watch').videoData;
            if (!data?.adaptiveFormats) return [];
            return data.adaptiveFormats
                .filter(f => f.type && f.type.startsWith('video/'))
                .sort((a, b) => (b.height || 0) - (a.height || 0));
        },

        get audioOnlyFormats() {
            const data = Alpine.store('watch').videoData;
            if (!data?.adaptiveFormats) return [];
            return data.adaptiveFormats
                .filter(f => f.type && f.type.startsWith('audio/'))
                .sort((a, b) => {
                    const bitrateA = parseInt(a.bitrate) || 0;
                    const bitrateB = parseInt(b.bitrate) || 0;
                    return bitrateB - bitrateA;
                });
        },

        getFilename(format) {
            const data = Alpine.store('watch').videoData;
            const title = data?.title || 'video';
            const safeTitle = title.replace(/[/\\?%*:|"<>]/g, '-').substring(0, 100);
            const quality = format.resolution || format.quality || format.audioQuality || '';
            const ext = format.container || 'mp4';
            return `${safeTitle}${quality ? '_' + quality : ''}.${ext}`;
        },

        formatBytes(bytes) {
            if (!bytes) return '';
            const num = parseInt(bytes);
            if (isNaN(num)) return '';
            if (num >= 1073741824) {
                return (num / 1073741824).toFixed(1) + ' GB';
            }
            if (num >= 1048576) {
                return (num / 1048576).toFixed(1) + ' MB';
            }
            if (num >= 1024) {
                return (num / 1024).toFixed(1) + ' KB';
            }
            return num + ' B';
        }
    }));
});
