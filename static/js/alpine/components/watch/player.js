document.addEventListener('alpine:init', () => {
    Alpine.data('videoPlayer', () => ({
        player: null,
        hls: null,
        qualities: [],
        audioTracks: [],
        selectedQuality: '',
        selectedAudio: '',
        playbackRate: '1',
        pipSupported: false,
        currentSource: null,
        _keyboardHandler: null,

        init() {
            this.pipSupported = 'pictureInPictureEnabled' in document;
            this._currentVideoId = null;

            // Watch for video data changes
            this.$watch('$store.watch.videoData', (data) => {
                if (data) {
                    // Check if this is the same video (prevent double-loading)
                    const videoId = data.videoId || data.id || data.title;
                    if (this._currentVideoId === videoId && this.player) {
                        return;
                    }
                    this._currentVideoId = videoId;

                    this.$nextTick(() => {
                        // Wait for next paint to ensure element is visible
                        requestAnimationFrame(() => {
                            requestAnimationFrame(() => {
                                this.initPlayer(data);
                            });
                        });
                    });
                }
            });

            // Keyboard shortcuts - bind handler for cleanup
            this._keyboardHandler = (e) => this.handleKeyboard(e);
            document.addEventListener('keydown', this._keyboardHandler);
        },

        destroy() {
            if (this._keyboardHandler) {
                document.removeEventListener('keydown', this._keyboardHandler);
            }
            this.detachHls();
            if (this.player) {
                this.player.dispose();
                this.player = null;
            }
        },

        initPlayer(data) {
            // Dispose existing player
            this.detachHls();
            if (this.player) {
                this.player.dispose();
                this.player = null;
            }

            const videoEl = this.$refs.videoElement;
            if (!videoEl) {
                return;
            }

            // Check if element is visible in DOM (not hidden by x-show)
            if (!videoEl.offsetParent) {
                // Element not visible yet, retry on next frame
                requestAnimationFrame(() => this.initPlayer(data));
                return;
            }

            // Parse available formats
            this.parseFormats(data);

            // Initialize Video.js
            this.player = videojs(videoEl, {
                controls: true,
                autoplay: false,
                preload: 'metadata',
                aspectRatio: '16:9',
                playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2],
                html5: {
                    vhs: {
                        overrideNative: true
                    },
                    nativeAudioTracks: false,
                    nativeVideoTracks: false
                }
            });

            // Set initial source
            this.setSource(data);

            // Handle errors
            this.player.on('error', () => {
                const error = this.player.error();
                console.error('[Player] Video playback error:', error);
            });

            this.player.on('ready', () => {
                if (Alpine.store('watch').autoplay) {
                    this.player.play();
                }
            });
        },

        parseFormats(data) {
            this.qualities = [];
            this.audioTracks = [];

            // Check for HLS first
            if (data.hlsUrl) {
                this.qualities.push({
                    itag: 'hls',
                    label: 'Auto (HLS)',
                    url: data.hlsUrl,
                    type: 'application/x-mpegURL',
                    isHls: true
                });
            }

            // Add muxed formats (formatStreams)
            if (data.formatStreams && data.formatStreams.length > 0) {
                data.formatStreams.forEach(f => {
                    const isHls = this.isHlsFormat(f);
                    // The same playlist as the hlsUrl entry above
                    if (isHls && data.hlsUrl) {
                        return;
                    }
                    const label = f.quality || f.resolution || 'Unknown';
                    this.qualities.push({
                        itag: f.itag,
                        // An HLS entry is a playlist, not a rendition. Its
                        // quality label describes only the master playlist.
                        label: isHls ? 'Auto (HLS)' : `${label} (${f.container})`,
                        url: f.url,
                        type: this.getMimeType(f),
                        container: f.container,
                        isHls: isHls
                    });
                });
            }

            // Add adaptive video formats with codec priority
            if (data.adaptiveFormats && data.adaptiveFormats.length > 0) {
                const videoFormats = data.adaptiveFormats
                    .filter(f => f.type && f.type.startsWith('video/'))
                    .sort((a, b) => {
                        // Sort by resolution (height) descending, then by codec priority
                        const heightA = a.height || 0;
                        const heightB = b.height || 0;
                        if (heightB !== heightA) return heightB - heightA;
                        return this.codecPriority(b.type) - this.codecPriority(a.type);
                    });

                // Group by resolution, prefer VP9/AV1
                const seenResolutions = new Set();
                videoFormats.forEach(f => {
                    const height = f.height || 0;
                    const resKey = `${height}p`;

                    // Check if browser supports this codec
                    if (!this.isTypeSupported(f.type)) return;

                    if (!seenResolutions.has(resKey) || this.codecPriority(f.type) > 1) {
                        seenResolutions.add(resKey);
                        const codecName = this.getCodecName(f.type);
                        const fpsLabel = f.fps > 30 ? ` ${f.fps}fps` : '';
                        this.qualities.push({
                            itag: f.itag,
                            label: `${f.resolution || resKey}${fpsLabel} (${codecName})`,
                            url: f.url,
                            type: f.type,
                            container: f.container,
                            height: height,
                            isAdaptive: true
                        });
                    }
                });

                // Get audio tracks
                const audioFormats = data.adaptiveFormats
                    .filter(f => f.type && f.type.startsWith('audio/'))
                    .sort((a, b) => {
                        // Sort by bitrate descending
                        const bitrateA = parseInt(a.bitrate) || 0;
                        const bitrateB = parseInt(b.bitrate) || 0;
                        return bitrateB - bitrateA;
                    });

                audioFormats.forEach(f => {
                    if (!this.isTypeSupported(f.type)) return;

                    const label = f.audioTrack?.displayName ||
                                  f.audioQuality ||
                                  (f.bitrate ? `${f.bitrate}` : 'Audio');
                    this.audioTracks.push({
                        itag: f.itag,
                        label: `${label} (${f.container})`,
                        url: f.url,
                        type: f.type
                    });
                });
            }

            // Set default selections
            if (this.qualities.length > 0) {
                // Prefer HLS: it carries the video and the audio together and
                // lets the player switch renditions. Then the best muxed format.
                const hlsFormat = this.qualities.find(q => q.isHls);
                const muxedFormat = this.qualities.find(q => !q.isAdaptive && !q.isHls);
                this.selectedQuality = hlsFormat?.itag || muxedFormat?.itag || this.qualities[0].itag;
            }

            if (this.audioTracks.length > 0) {
                this.selectedAudio = this.audioTracks[0].itag;
            }
        },

        isHlsFormat(format) {
            const type = (format.type || '').toLowerCase();
            return (
                format.container === 'hls' ||
                type.indexOf('mpegurl') !== -1 ||
                type.indexOf('m3u8') !== -1
            );
        },

        get isHlsSelected() {
            const quality = this.qualities.find(q => q.itag === this.selectedQuality);
            return !!(quality && quality.isHls);
        },

        codecPriority(type) {
            if (!type) return 0;
            if (type.includes('av01')) return 3;  // AV1
            if (type.includes('vp9') || type.includes('vp09')) return 2;  // VP9
            if (type.includes('avc1') || type.includes('h264')) return 1;  // H.264
            return 0;
        },

        getCodecName(type) {
            if (!type) return 'Unknown';
            if (type.includes('av01')) return 'AV1';
            if (type.includes('vp9') || type.includes('vp09')) return 'VP9';
            if (type.includes('avc1') || type.includes('h264')) return 'H.264';
            if (type.includes('opus')) return 'Opus';
            if (type.includes('mp4a')) return 'AAC';
            return type.split(';')[0].split('/')[1] || 'Unknown';
        },

        isTypeSupported(type) {
            if (!type) return false;
            if (typeof MediaSource === 'undefined') return true;  // Fallback
            try {
                return MediaSource.isTypeSupported(type);
            } catch {
                return true;  // Assume supported if check fails
            }
        },

        getMimeType(format) {
            if (format.type) return format.type.split(';')[0];
            const container = format.container?.toLowerCase() || '';
            if (container === 'mp4') return 'video/mp4';
            if (container === 'webm') return 'video/webm';
            if (container === 'hls' || container === 'm3u8') return 'application/x-mpegURL';
            return 'video/mp4';
        },

        setSource(data) {
            if (!this.player) return;

            let source = null;

            // Try HLS first
            if (data.hlsUrl) {
                source = {
                    src: data.hlsUrl,
                    type: 'application/x-mpegURL',
                    isHls: true
                };
            }
            // Try selected quality
            else if (this.selectedQuality) {
                const quality = this.qualities.find(q => q.itag === this.selectedQuality);
                if (quality) {
                    source = {
                        src: quality.url,
                        type: quality.type || 'video/mp4',
                        isHls: !!quality.isHls
                    };
                }
            }
            // Fallback to first format stream
            else if (data.formatStreams && data.formatStreams.length > 0) {
                const f = data.formatStreams[0];
                source = {
                    src: f.url,
                    type: this.getMimeType(f),
                    isHls: this.isHlsFormat(f)
                };
            }
            // Fallback to first adaptive format
            else if (data.adaptiveFormats && data.adaptiveFormats.length > 0) {
                const videoFormat = data.adaptiveFormats.find(f => f.type?.startsWith('video/'));
                if (videoFormat) {
                    source = {
                        src: videoFormat.url,
                        type: videoFormat.type,
                        isHls: false
                    };
                }
            }

            if (source) {
                this.applySource(source);

                // Set poster
                if (data.videoThumbnails && data.videoThumbnails.length > 0) {
                    const poster = data.videoThumbnails.find(t => t.quality === 'maxres') ||
                                   data.videoThumbnails.find(t => t.quality === 'high') ||
                                   data.videoThumbnails[0];
                    if (poster) {
                        this.player.poster(poster.url);
                    }
                }
            }
        },

        // HLS plays through hls.js, not through video.js's built-in VHS.
        // YouTube's media playlists carry no EXT-X-MAP init segment, which VHS
        // needs - it appends nothing and the player waits forever. hls.js plays
        // the same stream, alternate audio track included.
        applySource(source, restore) {
            this.currentSource = source;

            if (source.isHls && this.canUseHls()) {
                this.attachHls(source.src, restore);
                return;
            }

            this.detachHls();
            if (restore) {
                this.player.one('loadedmetadata', () => this.restorePlayback(restore));
            }
            this.player.src({
                src: source.src,
                type: source.type
            });
        },

        canUseHls() {
            return typeof Hls !== 'undefined' && Hls.isSupported();
        },

        attachHls(url, restore) {
            this.detachHls();
            const hls = new Hls({ enableWorker: true });
            this.hls = hls;
            hls.on(Hls.Events.ERROR, (event, data) => {
                console.error('[Player] HLS error:', data.type, data.details, 'fatal=' + data.fatal);
            });
            hls.on(Hls.Events.MANIFEST_PARSED, () => {
                this.useHlsLevels(hls.levels);
                if (!restore && Alpine.store('watch').autoplay) {
                    this.player.play();
                }
            });
            if (restore) {
                this.player.one('loadedmetadata', () => this.restorePlayback(restore));
            }
            hls.attachMedia(this.$refs.videoElement);
            hls.loadSource(url);
        },

        detachHls() {
            if (this.hls) {
                this.hls.destroy();
                this.hls = null;
            }
        },

        // While HLS is in use the menu lists the HLS levels. The DASH entries
        // carry no audio of their own, so picking one of those silences
        // playback; an HLS level switch keeps the audio track and the position.
        useHlsLevels(levels) {
            const previous = this.qualities.find(q => q.itag === this.selectedQuality);
            const wanted = previous && typeof previous.level === 'number' ? previous.level : -1;

            // The master playlist is ordered by bandwidth, which puts 144p in the
            // middle and the best renditions last. Show them largest first, like
            // the rest of the menu used to be, and keep the hls.js level index so
            // currentLevel still points at the right rendition. Same resolution
            // and codec twice (SDR/HDR, alternate audio groups) keeps the first,
            // which is the highest bitrate after the sort.
            const seen = new Set();
            const entries = [];
            levels
                .map((level, index) => ({ level: level, index: index, label: this.hlsLevelLabel(level) }))
                .sort((a, b) =>
                    (b.level.height || 0) - (a.level.height || 0) ||
                    (b.level.frameRate || 0) - (a.level.frameRate || 0) ||
                    (b.level.bitrate || 0) - (a.level.bitrate || 0)
                )
                .forEach(entry => {
                    if (seen.has(entry.label)) return;
                    seen.add(entry.label);
                    entries.push({ itag: `hls-${entry.index}`, label: entry.label, level: entry.index, isHls: true });
                });

            this.qualities = [{ itag: 'hls', label: 'Auto (HLS)', level: -1, isHls: true }].concat(entries);

            this.selectedQuality = wanted >= 0 && wanted < levels.length ? `hls-${wanted}` : 'hls';
            this.applyHlsLevel(this.selectedQuality === 'hls' ? -1 : wanted);
        },

        hlsLevelLabel(level) {
            const attrs = level.attrs || {};
            const height = level.height || (attrs.RESOLUTION ? parseInt(attrs.RESOLUTION.split('x')[1], 10) : 0);
            const fps = level.frameRate > 30 ? ` ${Math.round(level.frameRate)}fps` : '';
            const codec = this.getCodecName(attrs.CODECS || level.videoCodec || '');
            return `${height ? height + 'p' : 'Auto'}${fps} (${codec})`;
        },

        applyHlsLevel(level) {
            if (!this.hls) return;
            // -1 hands the choice back to hls.js's own adaptation
            this.hls.currentLevel = level >= 0 && level < this.hls.levels.length ? level : -1;
        },

        restorePlayback(restore) {
            this.player.currentTime(restore.time);
            if (restore.playing) {
                this.player.play();
            }
        },

        changeQuality() {
            if (!this.player || !this.selectedQuality) return;

            const quality = this.qualities.find(q => q.itag === this.selectedQuality);
            if (!quality) return;

            if (quality.isHls && this.hls) {
                this.applyHlsLevel(typeof quality.level === 'number' ? quality.level : -1);
                return;
            }

            this.applySource(
                {
                    src: quality.url,
                    type: quality.type || 'video/mp4',
                    isHls: !!quality.isHls
                },
                { time: this.player.currentTime(), playing: !this.player.paused() }
            );
        },

        changeAudio() {
            // Note: Separate audio track selection requires MSE/MediaSource
            // For now, this is a placeholder - full implementation would need
            // to handle audio/video muxing on the client side
            // Note: Full implementation would need audio/video muxing on the client side
        },

        changeSpeed() {
            if (this.player) {
                this.player.playbackRate(parseFloat(this.playbackRate));
            }
        },

        togglePip() {
            const videoEl = this.player?.el()?.querySelector('video');
            if (!videoEl) return;

            if (document.pictureInPictureElement) {
                document.exitPictureInPicture();
            } else if (videoEl.requestPictureInPicture) {
                videoEl.requestPictureInPicture();
            }
        },

        handleKeyboard(e) {
            if (!this.player) return;

            // Ignore if typing in input
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            switch (e.key.toLowerCase()) {
                case ' ':
                    e.preventDefault();
                    this.player.paused() ? this.player.play() : this.player.pause();
                    break;
                case 'arrowleft':
                    e.preventDefault();
                    this.player.currentTime(Math.max(0, this.player.currentTime() - 10));
                    break;
                case 'arrowright':
                    e.preventDefault();
                    this.player.currentTime(this.player.currentTime() + 10);
                    break;
                case 'arrowup':
                    e.preventDefault();
                    this.player.volume(Math.min(1, this.player.volume() + 0.1));
                    break;
                case 'arrowdown':
                    e.preventDefault();
                    this.player.volume(Math.max(0, this.player.volume() - 0.1));
                    break;
                case 'f':
                    e.preventDefault();
                    this.player.isFullscreen() ? this.player.exitFullscreen() : this.player.requestFullscreen();
                    break;
                case 'm':
                    e.preventDefault();
                    this.player.muted(!this.player.muted());
                    break;
            }
        }
    }));
});
