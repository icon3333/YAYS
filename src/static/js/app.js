        // Global state
        let channels = [];
        let channelNames = {};
        let channelStats = {};
        let isLoading = false;
        let pendingRemoval = null;
        let pendingAction = null;  // For storing the action to be confirmed
        let feedOffset = 0;
        let feedLimit = 25;

        // Load channels
        async function loadChannels() {
            try {
                // Load channels
                const response = await fetch('/api/channels');
                if (!response.ok) throw new Error('Failed to load');

                const data = await response.json();
                channels = data.channels || [];
                channelNames = data.names || {};

                // Load stats
                await loadChannelStats();

                renderChannels();

                // Load video feed
                await loadVideoFeed();

                // Populate channel filter
                populateChannelFilter();

            } catch (error) {
                showStatus('Failed to load channels', true);
            } finally {
                document.getElementById('loading').style.display = 'none';
            }
        }

        // Load channel statistics
        async function loadChannelStats() {
            try {
                const response = await fetch('/api/stats/channels');
                if (!response.ok) return;

                const data = await response.json();
                channelStats = data.channels || {};

            } catch (error) {
                console.error('Failed to load stats:', error);
            }
        }

        // Render channels with enhanced cards
        function renderChannels() {
            const container = document.getElementById('channels');
            const empty = document.getElementById('empty');
            const count = document.getElementById('count');

            count.textContent = channels.length;

            if (channels.length === 0) {
                empty.style.display = 'block';
                container.innerHTML = '';
                // Regenerate TOC after rendering
                setTimeout(() => generateTOC(), 50);
                return;
            }

            empty.style.display = 'none';
            container.innerHTML = '';

            channels.forEach(id => {
                const name = channelNames[id] || id;
                const showId = name !== id;
                const stats = channelStats[id] || { total_videos: 0, hours_saved: 0 };

                const div = document.createElement('div');
                div.className = 'channel-card';
                div.innerHTML = `
                    <div class="channel-card-header">
                        <div class="channel-name-section">
                            <div class="channel-name">${escapeHtml(name)}</div>
                            ${showId ? `<div class="channel-id">${escapeHtml(id)}</div>` : ''}
                        </div>
                        <div class="channel-stats">
                            <span class="channel-stat">
                                <span class="stat-icon">📊</span>
                                <span class="stat-value">${stats.total_videos || 0}</span>
                                <span class="stat-label">summaries</span>
                            </span>
                            <span class="stat-separator">•</span>
                            <span class="channel-stat">
                                <span class="stat-icon">⏱️</span>
                                <span class="stat-value">${stats.hours_saved || 0}</span>
                                <span class="stat-label">total hours</span>
                            </span>
                        </div>
                    </div>

                    <div class="channel-actions">
                        <button class="btn-secondary" onclick="viewChannelFeed('${escapeAttr(id)}')">
                            View Feed
                        </button>
                        <button class="btn-remove" onclick="promptRemove('${escapeAttr(id)}')">
                            Remove
                        </button>
                    </div>
                `;
                container.appendChild(div);
            });

            // Regenerate TOC after rendering
            setTimeout(() => generateTOC(), 50);
        }

        // HTML escape
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Attribute escape
        function escapeAttr(text) {
            return text.replace(/'/g, "\\\\'").replace(/"/g, '&quot;');
        }

        // Prompt removal
        function promptRemove(id) {
            pendingRemoval = id;
            const name = channelNames[id] || id;
            document.getElementById('modalMessage').textContent =
                `Are you sure you want to remove "${name}"?`;
            document.getElementById('modal').classList.add('show');
        }

        // Close modal
        function closeModal() {
            document.getElementById('modal').classList.remove('show');
            pendingRemoval = null;
            pendingAction = null;
        }

        // Confirm removal
        async function confirmRemove() {
            if (!pendingRemoval) return;

            channels = channels.filter(id => id !== pendingRemoval);
            delete channelNames[pendingRemoval];

            closeModal();
            await saveChannels();
            renderChannels();
        }



        // Generic modal prompt
        function showConfirmModal(title, message, confirmText, confirmCallback) {
            document.getElementById('modalTitle').textContent = title;
            document.getElementById('modalMessage').textContent = message;
            document.getElementById('modalConfirmBtn').textContent = confirmText;
            pendingAction = confirmCallback;

            // Update the confirm button onclick
            const confirmBtn = document.getElementById('modalConfirmBtn');
            confirmBtn.onclick = async function() {
                if (pendingAction) {
                    await pendingAction();
                    closeModal();
                }
            };

            document.getElementById('modal').classList.add('show');
        }

        // Risky deletion functions
        async function promptResetSettings() {
            showConfirmModal(
                '⚠️ Reset Settings',
                'This will reset all settings and AI prompt to defaults. Your channels and feed history will be preserved. This action cannot be undone. Are you sure?',
                'Reset Settings',
                confirmResetSettings
            );
        }

        async function confirmResetSettings() {
            try {
                const response = await fetch('/api/reset/settings', {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to reset settings');
                }

                const result = await response.json();

                // Show success message
                showSettingsStatus(result.message);

                // Reload the page to reflect changes
                setTimeout(() => location.reload(), 1500);
            } catch (error) {
                showSettingsStatus('Failed to reset settings: ' + error.message, true);
            }
        }

        async function promptResetYoutubeData() {
            showConfirmModal(
                '⚠️ Reset YouTube Data',
                'This will permanently delete all channels and feed history. Your settings and AI prompt will be preserved. This action cannot be undone. Are you sure?',
                'Reset YouTube Data',
                confirmResetYoutubeData
            );
        }

        async function confirmResetYoutubeData() {
            try {
                const response = await fetch('/api/reset/youtube-data', {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to reset YouTube data');
                }

                const result = await response.json();

                // Show success message
                showSettingsStatus(result.message);

                // Reload the page to reflect changes
                setTimeout(() => location.reload(), 1500);
            } catch (error) {
                showSettingsStatus('Failed to reset YouTube data: ' + error.message, true);
            }
        }

        async function promptResetFeedHistory() {
            showConfirmModal(
                '⚠️ Reset Feed History',
                'This will permanently delete all processed videos from your feed. Your channels and settings will be preserved. This action cannot be undone. Are you sure?',
                'Reset Feed History',
                confirmResetFeedHistory
            );
        }

        async function confirmResetFeedHistory() {
            try {
                const response = await fetch('/api/reset/feed-history', {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to reset feed history');
                }

                const result = await response.json();

                // Show success message
                showSettingsStatus(result.message);

                // Reload the feed
                feedOffset = 0;
                await loadVideoFeed();
            } catch (error) {
                showSettingsStatus('Failed to reset feed history: ' + error.message, true);
            }
        }

        async function promptResetCompleteApp() {
            showConfirmModal(
                '⚠️ Reset Complete App',
                'This will permanently delete ALL data including channels, feed history, and reset all settings and prompts to defaults. This action cannot be undone. Are you absolutely sure?',
                'Reset Everything',
                confirmResetCompleteApp
            );
        }

        async function confirmResetCompleteApp() {
            try {
                const response = await fetch('/api/reset/complete', {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to reset app');
                }

                const result = await response.json();

                // Show success message
                showSettingsStatus(result.message);

                // Reload the page to reflect changes
                setTimeout(() => location.reload(), 1500);
            } catch (error) {
                showSettingsStatus('Failed to reset app: ' + error.message, true);
            }
        }

        // Toggle Danger Zone visibility
        function toggleDangerZone() {
            const content = document.getElementById('dangerZoneContent');
            const toggle = document.getElementById('dangerZoneToggle');

            if (content.style.display === 'none') {
                content.style.display = 'block';
                toggle.textContent = '▼';
            } else {
                content.style.display = 'none';
                toggle.textContent = '▶';
            }
        }

        // Add channel
        async function addChannel() {
            if (isLoading) return;

            const idInput = document.getElementById('channelId');
            const nameInput = document.getElementById('channelName');
            const addBtn = document.getElementById('addBtn');

            const input = idInput.value.trim();
            const name = nameInput.value.trim();

            if (!input) {
                showStatus('Please enter a channel ID or URL', true);
                return;
            }

            // Get the actual channel ID by calling the fetch endpoint
            // This will handle URLs, @handles, and channel IDs
            isLoading = true;
            addBtn.disabled = true;
            addBtn.textContent = 'Resolving...';

            let channelId;
            let channelName;

            try {
                const response = await fetch(`/api/fetch-channel-name/${encodeURIComponent(input)}`);

                if (!response.ok) {
                    const error = await response.json();
                    showStatus(error.detail || 'Invalid channel', true);
                    isLoading = false;
                    addBtn.disabled = false;
                    addBtn.textContent = 'Add Channel';
                    return;
                }

                const data = await response.json();
                channelId = data.channel_id;
                channelName = name || data.channel_name;

                // Auto-fill the display name field if it was left empty
                if (!name && data.channel_name) {
                    nameInput.value = data.channel_name;
                }

            } catch (error) {
                showStatus('Failed to resolve channel: ' + error.message, true);
                isLoading = false;
                addBtn.disabled = false;
                addBtn.textContent = 'Add Channel';
                return;
            }

            // Check if already exists
            if (channels.includes(channelId)) {
                showStatus('Channel already exists', true);
                isLoading = false;
                addBtn.disabled = false;
                addBtn.textContent = 'Add Channel';
                return;
            }

            // Add
            addBtn.textContent = 'Adding...';

            channels.push(channelId);
            channelNames[channelId] = channelName;

            const saved = await saveChannels();

            // If save was successful, fetch initial videos
            if (saved) {
                addBtn.textContent = 'Fetching videos...';
                try {
                    const response = await fetch(`/api/channels/${encodeURIComponent(channelId)}/fetch-initial-videos`, {
                        method: 'POST'
                    });

                    if (response.ok) {
                        const result = await response.json();
                        showStatus(`Channel added! Fetched ${result.videos_fetched} recent videos.`, false);
                    } else {
                        showStatus('Channel added, but could not fetch initial videos', false);
                    }
                } catch (error) {
                    console.error('Error fetching initial videos:', error);
                    showStatus('Channel added, but could not fetch initial videos', false);
                }
            }

            idInput.value = '';
            nameInput.value = '';
            renderChannels();

            isLoading = false;
            addBtn.disabled = false;
            addBtn.textContent = 'Add Channel';
        }

        // Save channels
        async function saveChannels() {
            try {
                const response = await fetch('/api/channels', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ channels, names: channelNames })
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    console.error('Save failed:', response.status, errorData);
                    throw new Error(`Save failed: ${response.status}`);
                }

                const result = await response.json();
                console.log('Save successful:', result);
                showStatus('Saved successfully', false);
                return true;
            } catch (error) {
                console.error('Save error:', error);
                showStatus('Failed to save: ' + error.message, true);
                return false;
            }
        }

        // Show status
        function showStatus(msg, isError) {
            const status = document.getElementById('status');
            status.textContent = msg;
            status.className = isError ? 'status error show' : 'status show';
            setTimeout(() => status.classList.remove('show'), 3000);
        }

        // Video feed functions
        let feedRefreshInterval = null;

        async function loadVideoFeed(reset = false) {
            if (reset) {
                feedOffset = 0;
                document.getElementById('videoFeed').innerHTML = '';
            }

            try {
                const channelFilter = document.getElementById('feedChannelFilter').value;
                const sortOrder = document.getElementById('feedSortOrder').value;

                const params = new URLSearchParams({
                    limit: feedLimit,
                    offset: feedOffset,
                    order_by: sortOrder
                });

                if (channelFilter) {
                    params.append('channel_id', channelFilter);
                }

                const response = await fetch(`/api/videos/feed?${params}`);
                if (!response.ok) return;

                const data = await response.json();

                // Update count
                document.getElementById('feedCount').textContent = data.total;

                // Show/hide empty state
                if (data.total === 0) {
                    document.getElementById('feedEmpty').style.display = 'block';
                    document.getElementById('videoFeed').style.display = 'none';
                    document.getElementById('loadMoreBtn').style.display = 'none';
                    return;
                } else {
                    document.getElementById('feedEmpty').style.display = 'none';
                    document.getElementById('videoFeed').style.display = 'block';
                }

                // Check if any videos are processing
                const hasProcessingVideos = data.videos.some(v =>
                    v.processing_status === 'processing' || v.processing_status === 'pending'
                );

                // Start auto-refresh if videos are processing, stop otherwise
                if (hasProcessingVideos && !feedRefreshInterval) {
                    console.log('Starting auto-refresh (videos processing)');
                    feedRefreshInterval = setInterval(() => {
                        loadVideoFeed(true);
                    }, 5000); // Refresh every 5 seconds
                } else if (!hasProcessingVideos && feedRefreshInterval) {
                    console.log('Stopping auto-refresh (no videos processing)');
                    clearInterval(feedRefreshInterval);
                    feedRefreshInterval = null;
                }

                // Render videos
                const feedContainer = document.getElementById('videoFeed');
                data.videos.forEach(video => {
                    const div = document.createElement('div');
                    div.className = 'video-item';
                    div.innerHTML = `
                        <div class="video-header">
                            <div class="video-title" onclick="openYouTube('${escapeAttr(video.id)}')">
                                ${escapeHtml(video.title)}
                            </div>
                            <div class="video-actions">
                                ${renderVideoActions(video)}
                            </div>
                        </div>
                        <div class="video-meta">
                            <span class="video-channel">${escapeHtml(video.channel_name)}</span>
                            <span class="meta-separator">•</span>
                            <span class="video-date">${escapeHtml(video.upload_date_formatted)}</span>
                            <span class="meta-separator">•</span>
                            <span class="video-duration">${escapeHtml(video.duration_formatted)}</span>
                        </div>
                    `;
                    feedContainer.appendChild(div);
                });

                // Show/hide load more button
                if (data.has_more) {
                    const remaining = data.total - (feedOffset + feedLimit);
                    document.getElementById('remainingCount').textContent = remaining;
                    document.getElementById('loadMoreBtn').style.display = 'block';
                } else {
                    document.getElementById('loadMoreBtn').style.display = 'none';
                }

            } catch (error) {
                console.error('Failed to load video feed:', error);
            }
        }

        function loadMoreVideos() {
            feedOffset += feedLimit;
            loadVideoFeed(false);
        }

        function filterFeed() {
            loadVideoFeed(true);
        }

        function viewChannelFeed(channelId) {
            // Set filter to channel
            document.getElementById('feedChannelFilter').value = channelId;

            // Switch to feed tab
            showTab('feed');

            // Reload feed with filter
            filterFeed();
        }

        function populateChannelFilter() {
            const select = document.getElementById('feedChannelFilter');

            // Keep "All Channels" option
            select.innerHTML = '<option value="">All Channels</option>';

            // Add each channel
            channels.forEach(id => {
                const name = channelNames[id] || id;
                const option = document.createElement('option');
                option.value = id;
                option.textContent = name;
                select.appendChild(option);
            });
        }

        // Auto-fetch channel name
        let fetchTimeout = null;
        document.getElementById('channelId').addEventListener('input', async e => {
            const input = e.target.value.trim();

            // Clear previous timeout
            if (fetchTimeout) clearTimeout(fetchTimeout);

            // Check if input is empty or too short
            if (!input || input.length < 3) return;

            // Check if it looks like a valid channel ID, URL, or @handle
            const isChannelId = /UC[\w-]{22}/.test(input);
            const isUrl = /youtube\.com/.test(input);
            const isHandle = /^@[\w-]+$/.test(input);

            if (!isChannelId && !isUrl && !isHandle) return;

            const nameInput = document.getElementById('channelName');

            // Debounce: wait 500ms after user stops typing
            fetchTimeout = setTimeout(async () => {
                try {
                    nameInput.value = 'Fetching...';
                    nameInput.disabled = true;

                    const response = await fetch(`/api/fetch-channel-name/${encodeURIComponent(input)}`);

                    if (response.ok) {
                        const data = await response.json();
                        nameInput.value = data.channel_name;
                        showStatus(`Found: ${data.channel_name}`, false);
                    } else {
                        nameInput.value = '';
                        console.log('Could not fetch channel name');
                    }
                } catch (error) {
                    nameInput.value = '';
                    console.log('Error fetching channel name:', error);
                } finally {
                    nameInput.disabled = false;
                }
            }, 500);
        });

        // Keyboard shortcuts
        document.getElementById('channelId').addEventListener('keypress', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.getElementById('channelName').focus();
            }
        });

        document.getElementById('channelName').addEventListener('keypress', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addChannel();
            }
        });

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closeModal();
        });

        document.getElementById('modal').addEventListener('click', e => {
            if (e.target.id === 'modal') closeModal();
        });

        // Load on start
        loadChannels();

        // ============================================================================
        // TAB NAVIGATION
        // ============================================================================

        function showTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });

            // Remove active class from all buttons
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('active');
            });

            // Show selected tab
            document.getElementById(`tab-${tabName}`).classList.add('active');

            // Activate button (find the button by tab name if event not available)
            if (event && event.target) {
                event.target.classList.add('active');
            } else {
                // Find the button by searching for matching onclick
                const buttons = document.querySelectorAll('.tab-btn');
                buttons.forEach(btn => {
                    if (btn.getAttribute('onclick') === `showTab('${tabName}')`) {
                        btn.classList.add('active');
                    }
                });
            }

            // Load data for the tab
            if (tabName === 'feed') {
                loadVideoFeed(true);
            } else if (tabName === 'settings') {
                loadSettings();
            } else if (tabName === 'ai') {
                loadAITab();
            }

            // Generate TOC for the new tab (after content is visible)
            // Use setTimeout to ensure DOM is updated
            setTimeout(() => {
                generateTOC();
            }, 50);
        }

        // ============================================================================
        // SETTINGS TAB
        // ============================================================================

        let allSettings = {};

        // Toggle summary length input visibility based on checkbox
        function toggleSummaryLengthInput() {
            const checkbox = document.getElementById('USE_SUMMARY_LENGTH');
            const summaryLengthRow = document.getElementById('summaryLengthRow');

            if (checkbox && summaryLengthRow) {
                summaryLengthRow.style.display = checkbox.checked ? 'block' : 'none';
            }
        }

        async function loadOpenAIModels() {
            try {
                const response = await fetch('/api/openai/models');
                if (!response.ok) throw new Error('Failed to load models');

                const data = await response.json();
                const modelSelect = document.getElementById('OPENAI_MODEL');

                // Clear existing options
                modelSelect.innerHTML = '';

                // Filter to only show chat/text models (exclude image, audio, embedding, moderation, etc.)
                const textModels = data.models.filter(model => {
                    const id = model.id.toLowerCase();
                    return (
                        // Include GPT chat models
                        (id.startsWith('gpt-') && !id.includes('instruct')) ||
                        id.startsWith('o1') ||
                        id.startsWith('o3')
                    ) && (
                        // Exclude non-text models
                        !id.includes('dall-e') &&
                        !id.includes('whisper') &&
                        !id.includes('tts') &&
                        !id.includes('embedding') &&
                        !id.includes('moderation') &&
                        !id.includes('vision') &&
                        !id.includes('audio')
                    );
                });

                // Add filtered models to dropdown
                textModels.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model.id;
                    option.textContent = model.name;
                    modelSelect.appendChild(option);
                });

                console.log(`Loaded ${textModels.length} text models (filtered from ${data.models.length} total) from ${data.source}`);

            } catch (error) {
                console.error('Failed to load OpenAI models:', error);
                // Add default fallback options
                const modelSelect = document.getElementById('OPENAI_MODEL');
                modelSelect.innerHTML = `
                    <option value="gpt-4o">GPT-4o (Latest, Most Capable)</option>
                    <option value="gpt-4o-mini">GPT-4o Mini (Fast & Affordable)</option>
                    <option value="gpt-4-turbo">GPT-4 Turbo</option>
                    <option value="gpt-4">GPT-4</option>
                    <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                `;
            }
        }

        async function loadSettings() {
            try {
                // Load OpenAI models first
                await loadOpenAIModels();

                const response = await fetch('/api/settings');
                if (!response.ok) throw new Error('Failed to load settings');

                const data = await response.json();
                allSettings = data;

                // Populate .env settings
                for (const [key, info] of Object.entries(data.env)) {
                    const element = document.getElementById(key);

                    if (key === 'OPENAI_API_KEY' || key === 'SMTP_PASS') {
                        // For password fields, show placeholder if empty, otherwise show masked value
                        if (element) {
                            element.placeholder = info.masked || (key === 'OPENAI_API_KEY' ? 'sk-...' : '16-character app password');
                        }
                    } else if (element) {
                        if (info.type === 'enum') {
                            element.value = info.value || info.default;
                        } else {
                            element.value = info.value || info.default;
                        }
                    }
                }

                // Populate config settings
                const config = data.config;
                document.getElementById('SUMMARY_LENGTH').value = config.SUMMARY_LENGTH || '500';
                document.getElementById('USE_SUMMARY_LENGTH').checked = config.USE_SUMMARY_LENGTH === 'true';
                document.getElementById('SKIP_SHORTS').checked = config.SKIP_SHORTS === 'true';
                document.getElementById('MAX_VIDEOS_PER_CHANNEL').value = config.MAX_VIDEOS_PER_CHANNEL || '5';

                // Toggle summary length input visibility
                toggleSummaryLengthInput();

            } catch (error) {
                showSettingsStatus('Failed to load settings', true);
                console.error(error);
            }
        }

        function showSettingsStatus(msg, isError, autoHide = true) {
            const status = document.getElementById('settingsStatus');
            status.textContent = msg;
            status.className = isError ? 'status error show' : 'status show';
            if (autoHide) {
                setTimeout(() => status.classList.remove('show'), isError ? 5000 : 2000);
            }
        }

        function showAdvancedStatus(msg, isError) {
            const status = document.getElementById('advancedStatus');
            status.textContent = msg;
            status.className = isError ? 'status error show' : 'status show';
            setTimeout(() => status.classList.remove('show'), 5000);
        }

        async function saveAllSettings() {
            try {
                const settingsToSave = {};

                // Get all .env settings
                settingsToSave['TARGET_EMAIL'] = document.getElementById('TARGET_EMAIL').value;
                settingsToSave['SMTP_USER'] = document.getElementById('SMTP_USER').value;
                settingsToSave['LOG_LEVEL'] = document.getElementById('LOG_LEVEL').value;
                settingsToSave['CHECK_INTERVAL_HOURS'] = document.getElementById('CHECK_INTERVAL_HOURS').value;
                settingsToSave['MAX_PROCESSED_ENTRIES'] = document.getElementById('MAX_PROCESSED_ENTRIES').value;
                settingsToSave['SEND_EMAIL_SUMMARIES'] = document.getElementById('SEND_EMAIL_SUMMARIES').value;
                settingsToSave['OPENAI_MODEL'] = document.getElementById('OPENAI_MODEL').value;

                // Get password fields (only save if they have values)
                const openaiKey = document.getElementById('OPENAI_API_KEY').value;
                if (openaiKey) {
                    settingsToSave['OPENAI_API_KEY'] = openaiKey;
                }

                const smtpPass = document.getElementById('SMTP_PASS').value;
                if (smtpPass) {
                    settingsToSave['SMTP_PASS'] = smtpPass;
                }

                // Get config settings
                settingsToSave['SUMMARY_LENGTH'] = document.getElementById('SUMMARY_LENGTH').value;
                settingsToSave['USE_SUMMARY_LENGTH'] = document.getElementById('USE_SUMMARY_LENGTH').checked ? 'true' : 'false';
                settingsToSave['SKIP_SHORTS'] = document.getElementById('SKIP_SHORTS').checked ? 'true' : 'false';
                settingsToSave['MAX_VIDEOS_PER_CHANNEL'] = document.getElementById('MAX_VIDEOS_PER_CHANNEL').value;

                const response = await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ settings: settingsToSave })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail?.message || 'Failed to save');
                }

                const result = await response.json();

                showSettingsStatus('✅ Settings saved successfully', false);

                // Show restart notification after success message disappears
                if (result.restart_required) {
                    setTimeout(() => {
                        showRestartNotification();
                    }, 2000);
                }

            } catch (error) {
                showSettingsStatus(`❌ ${error.message}`, true);
                console.error(error);
            }
        }

        function showRestartNotification() {
            // Hide status message
            const status = document.getElementById('settingsStatus');
            status.classList.remove('show');

            // Show restart notification
            document.getElementById('restartNotification').style.display = 'flex';
        }

        // ============================================================================
        // CREDENTIAL TESTING
        // ============================================================================

        async function testOpenAIKey() {
            const resultDiv = document.getElementById('openai-test-result');
            resultDiv.innerHTML = '<div class="test-result">Testing...</div>';

            try {
                const apiKey = document.getElementById('OPENAI_API_KEY').value.trim();

                const response = await fetch('/api/settings/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        credential_type: 'openai',
                        test_value: apiKey || undefined
                    })
                });

                const result = await response.json();

                if (result.success) {
                    resultDiv.innerHTML = `<div class="test-result success">${result.message}</div>`;
                } else {
                    resultDiv.innerHTML = `<div class="test-result error">${result.message}</div>`;
                }

            } catch (error) {
                resultDiv.innerHTML = `<div class="test-result error">❌ Test failed: ${error.message}</div>`;
            }
        }

        async function testSmtpCredentials() {
            const resultDiv = document.getElementById('smtp-test-result');
            resultDiv.innerHTML = '<div class="test-result">Testing...</div>';

            try {
                const smtpUser = document.getElementById('SMTP_USER').value.trim();
                const smtpPass = document.getElementById('SMTP_PASS').value.trim();

                const response = await fetch('/api/settings/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        credential_type: 'smtp',
                        test_user: smtpUser || undefined,
                        test_pass: smtpPass || undefined
                    })
                });

                const result = await response.json();

                if (result.success) {
                    resultDiv.innerHTML = `<div class="test-result success">${result.message}</div>`;
                } else {
                    resultDiv.innerHTML = `<div class="test-result error">${result.message}</div>`;
                }

            } catch (error) {
                resultDiv.innerHTML = `<div class="test-result error">❌ Test failed: ${error.message}</div>`;
            }
        }

        // ============================================================================
        // RESTART APPLICATION
        // ============================================================================

        async function restartApplication() {
            const notification = document.getElementById('restartNotification');

            // Update notification text
            notification.innerHTML = 'Restarting... <button class="btn-restart-inline" disabled style="opacity: 0.6;">Restarting...</button>';

            try {
                const response = await fetch('/api/settings/restart', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const result = await response.json();

                if (result.success) {
                    notification.innerHTML = `✅ ${result.message} - Reloading page in 5 seconds...`;
                    // Only reload if restart was actually successful
                    setTimeout(() => {
                        window.location.reload();
                    }, 5000);
                } else {
                    notification.innerHTML = `❌ ${result.message} <button onclick="restartApplication()" class="btn-restart-inline">Try Again</button>`;
                }
            } catch (error) {
                // Server likely already restarted - this is expected
                console.log('Restart triggered, server restarting...');
                notification.innerHTML = `✅ Server restarting... Reloading page in 5 seconds...`;
                // Only reload after server restart
                setTimeout(() => {
                    window.location.reload();
                }, 5000);
            }
        }

        // ============================================================================
        // AI TAB (CREDENTIALS + PROMPT EDITOR)
        // ============================================================================

        let defaultPrompt = `You are summarizing a YouTube video. Create a concise summary that:
1. Captures the main points in 2-3 paragraphs
2. Highlights what's valuable or interesting
3. Mentions any actionable takeaways
4. Indicates who would benefit from watching

Keep the tone conversational and focus on value.

Title: {title}
Duration: {duration}
Transcript: {transcript}`;

        function showAIStatus(msg, isError) {
            const status = document.getElementById('aiStatus');
            status.textContent = msg;
            status.className = isError ? 'status error show' : 'status show';
            setTimeout(() => status.classList.remove('show'), 5000);
        }

        async function loadAITab() {
            // Load OpenAI models
            await loadOpenAIModels();

            // Load settings to populate AI credentials
            await loadSettings();

            // Load prompt
            await loadPrompt();
        }

        async function loadPrompt() {
            try {
                const response = await fetch('/api/settings/prompt');
                if (!response.ok) throw new Error('Failed to load prompt');

                const data = await response.json();
                document.getElementById('promptEditor').value = data.prompt || defaultPrompt;

            } catch (error) {
                showAIStatus('Failed to load prompt', true);
                console.error(error);
            }
        }

        async function savePrompt() {
            const prompt = document.getElementById('promptEditor').value.trim();

            if (!prompt) {
                showAIStatus('Prompt cannot be empty', true);
                return;
            }

            if (prompt.length < 10) {
                showAIStatus('Prompt is too short', true);
                return;
            }

            try {
                const response = await fetch('/api/settings/prompt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to save');
                }

                showAIStatus('✅ Prompt saved successfully', false);

            } catch (error) {
                showAIStatus(`❌ ${error.message}`, true);
                console.error(error);
            }
        }

        function resetPrompt() {
            if (confirm('Are you sure you want to reset the prompt to default?')) {
                document.getElementById('promptEditor').value = defaultPrompt;
                showAIStatus('Prompt reset to default. Click Save to apply.', false);
            }
        }

        async function saveAICredentials() {
            try {
                const settingsToSave = {};

                // Get OpenAI credentials
                settingsToSave['OPENAI_MODEL'] = document.getElementById('OPENAI_MODEL').value;

                // Get API key if changed
                const openaiKey = document.getElementById('OPENAI_API_KEY').value;
                if (openaiKey) {
                    settingsToSave['OPENAI_API_KEY'] = openaiKey;
                }

                const response = await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ settings: settingsToSave })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail?.message || 'Failed to save');
                }

                // Show success message in dedicated status box
                const status = document.getElementById('aiSettingsStatus');
                status.textContent = '✅ AI settings saved successfully';
                status.className = 'status show';
                setTimeout(() => status.classList.remove('show'), 3000);

                // Hide unsaved indicator
                document.getElementById('unsaved-ai-credentials').style.display = 'none';

            } catch (error) {
                // Show error message in dedicated status box
                const status = document.getElementById('aiSettingsStatus');
                status.textContent = `❌ ${error.message}`;
                status.className = 'status error show';
                setTimeout(() => status.classList.remove('show'), 5000);
                console.error(error);
            }
        }

        // Track all settings changes by section
        const trackableInputs = document.querySelectorAll('.trackable-input');
        trackableInputs.forEach(input => {
            const showIndicator = () => {
                const section = input.getAttribute('data-section');
                if (section === 'email') {
                    document.getElementById('unsaved-email').style.display = 'inline';
                } else if (section === 'app') {
                    document.getElementById('unsaved-app').style.display = 'inline';
                } else if (section === 'video') {
                    document.getElementById('unsaved-video').style.display = 'inline';
                } else if (section === 'ai-credentials') {
                    document.getElementById('unsaved-ai-credentials').style.display = 'inline';
                }
            };

            // Track both input and change events (input for text fields, change for select/checkbox)
            input.addEventListener('input', showIndicator);
            input.addEventListener('change', showIndicator);
        });

        // Hide all unsaved indicators when settings are saved
        const originalSaveAllSettings = saveAllSettings;
        saveAllSettings = async function() {
            await originalSaveAllSettings();
            document.getElementById('unsaved-email').style.display = 'none';
            document.getElementById('unsaved-app').style.display = 'none';
            document.getElementById('unsaved-video').style.display = 'none';
        };

        // ============================================================================
        // VIDEO FEED ENHANCEMENTS
        // ============================================================================

        function renderVideoActions(video) {
            const status = video.processing_status;

            if (status === 'success') {
                // Show Read Summary button + email status badge
                let html = `<button class="btn-read-summary" onclick="showSummary('${escapeAttr(video.id)}')">Read Summary</button>`;

                if (video.email_sent) {
                    html += `<span class="status-badge success" title="Email sent">Email</span>`;
                } else {
                    html += `<span class="status-badge warning" title="Email pending">Email Pending</span>`;
                }

                return html;
            } else if (status === 'pending' || status === 'processing') {
                return `<span class="status-badge processing">⏳ Processing...</span>`;
            } else if (status && status.startsWith('failed_')) {
                // Parse specific error type from status
                let errorType = 'Failed';
                const errorTitle = video.error_message || 'Processing failed';

                if (status === 'failed_transcript') {
                    errorType = 'Transcript';
                } else if (status === 'failed_ai') {
                    errorType = 'AI';
                } else if (status === 'failed_email') {
                    errorType = 'Email';
                }

                return `
                    <span class="status-badge error" title="${escapeAttr(errorTitle)}">${errorType}</span>
                    <button class="btn-retry" onclick="retryVideo('${escapeAttr(video.id)}')">Retry</button>
                `;
            }

            return '';
        }

        async function showSummary(videoId) {
            try {
                // Fetch video details with summary
                const response = await fetch(`/api/videos/${videoId}`);
                if (!response.ok) throw new Error('Failed to load summary');

                const video = await response.json();

                // Populate modal
                document.getElementById('summaryTitle').textContent = video.title;
                document.getElementById('summaryChannel').textContent = video.channel_name;
                document.getElementById('summaryDuration').textContent = video.duration_formatted || 'Unknown';
                document.getElementById('summaryViews').textContent = video.view_count_formatted || 'Unknown';
                document.getElementById('summaryUploadDate').textContent = video.upload_date_formatted || 'Unknown';
                document.getElementById('summaryText').textContent = video.summary_text || 'No summary available';
                document.getElementById('summaryYoutubeLink').href = `https://www.youtube.com/watch?v=${video.id}`;

                // Show modal
                document.getElementById('summaryModal').classList.add('show');

            } catch (error) {
                showStatus('Failed to load summary', true);
                console.error(error);
            }
        }

        function closeSummaryModal() {
            document.getElementById('summaryModal').classList.remove('show');
        }

        function openYouTube(videoId) {
            window.open(`https://www.youtube.com/watch?v=${videoId}`, '_blank');
        }

        async function retryVideo(videoId) {
            try {
                const response = await fetch(`/api/videos/${videoId}/retry`, {
                    method: 'POST'
                });

                if (response.ok) {
                    showStatus('Video queued for reprocessing. Auto-refreshing...', false);
                    // Reload feed immediately to show processing status
                    // Auto-refresh will continue updating every 5 seconds
                    setTimeout(() => loadVideoFeed(true), 1000);
                } else {
                    throw new Error('Failed to retry');
                }
            } catch (error) {
                showStatus('Failed to queue video for retry', true);
                console.error(error);
            }
        }

        async function checkNow() {
            const btn = event.target;
            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Checking...';

            try {
                const response = await fetch('/api/videos/process-now', {
                    method: 'POST'
                });

                if (response.ok) {
                    showStatus('Video check started! Auto-refreshing...', false);
                    // Reload feed to show any new processing videos
                    setTimeout(() => loadVideoFeed(true), 2000);
                } else {
                    throw new Error('Failed to start check');
                }
            } catch (error) {
                showStatus('Failed to start video check', true);
                console.error(error);
            } finally {
                setTimeout(() => {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }, 3000);
            }
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                closeModal();
                closeSummaryModal();
            }
        });

        // ============================================================================
        // IMPORT/EXPORT FUNCTIONS
        // ============================================================================

        // Global variable to store selected file for import
        let selectedImportFile = null;

        // Export Feed (JSON or CSV)
        async function exportFeed(format) {
            const btn = event.target.closest('button');
            const originalText = btn.innerHTML;

            try {
                btn.disabled = true;
                btn.innerHTML = '<div style="font-weight: bold;">Exporting...</div>';

                const response = await fetch(`/api/export/feed?format=${format}`);

                if (!response.ok) {
                    throw new Error(`Export failed: ${response.statusText}`);
                }

                // Trigger download
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;

                // Extract filename from Content-Disposition header
                const disposition = response.headers.get('Content-Disposition');
                const filenameMatch = disposition && disposition.match(/filename="(.+)"/);
                a.download = filenameMatch ? filenameMatch[1] : `yays_export.${format}`;

                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                showStatus('settingsStatus', `Export successful! File downloaded: ${a.download}`, 'success');

            } catch (error) {
                console.error('Export error:', error);
                showStatus('settingsStatus', `Export failed: ${error.message}`, 'error');
            } finally {
                setTimeout(() => {
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                }, 1000);
            }
        }

        // Export Complete Backup
        async function exportBackup() {
            const btn = event.target.closest('button');
            const originalText = btn.innerHTML;

            try {
                btn.disabled = true;
                btn.innerHTML = '<div style="font-weight: bold;">Exporting...</div>';

                const response = await fetch('/api/export/backup');

                if (!response.ok) {
                    throw new Error(`Export failed: ${response.statusText}`);
                }

                // Trigger download
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;

                const disposition = response.headers.get('Content-Disposition');
                const filenameMatch = disposition && disposition.match(/filename="(.+)"/);
                a.download = filenameMatch ? filenameMatch[1] : 'yays_full_backup.json';

                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                showStatus('settingsStatus', `Backup successful! File downloaded: ${a.download}`, 'success');

            } catch (error) {
                console.error('Export error:', error);
                showStatus('settingsStatus', `Export failed: ${error.message}`, 'error');
            } finally {
                setTimeout(() => {
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                }, 1000);
            }
        }

        // Setup drag-and-drop for import
        const dropzone = document.getElementById('importDropzone');

        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        // Highlight dropzone on drag over
        ['dragenter', 'dragover'].forEach(eventName => {
            dropzone.addEventListener(eventName, () => {
                dropzone.style.borderColor = 'rgba(255, 255, 255, 0.8)';
                dropzone.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, () => {
                dropzone.style.borderColor = 'rgba(255, 255, 255, 0.3)';
                dropzone.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
            }, false);
        });

        // Handle dropped files
        dropzone.addEventListener('drop', handleFileDrop, false);

        function handleFileDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;

            if (files.length > 0) {
                handleFile(files[0]);
            }
        }

        // Handle file selection from file picker
        function handleFileSelect(e) {
            const files = e.target.files;
            if (files.length > 0) {
                handleFile(files[0]);
            }
        }

        // Handle file (common logic for drag-and-drop and file picker)
        async function handleFile(file) {
            // Check file type
            if (!file.name.endsWith('.json')) {
                showStatus('settingsStatus', 'Invalid file type. Please select a JSON file.', 'error');
                return;
            }

            // Store file
            selectedImportFile = file;

            // Update UI - show filename
            document.getElementById('dropzoneDefault').style.display = 'none';
            document.getElementById('dropzoneFile').style.display = 'block';
            document.getElementById('dropzoneFileName').textContent = `📄 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
            document.getElementById('dropzoneValidating').textContent = 'Validating...';
            document.getElementById('dropzoneValidating').style.color = '#888';

            // Show import buttons container
            document.getElementById('importButtonsContainer').style.display = 'flex';

            // Validate file
            await validateImportFile(file);
        }

        // Validate import file
        async function validateImportFile(file) {
            try {
                // Create FormData
                const formData = new FormData();
                formData.append('file', file);

                const response = await fetch('/api/import/validate', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (result.valid) {
                    // Show success
                    document.getElementById('dropzoneValidating').textContent = '✓ Valid file, ready to import';
                    document.getElementById('dropzoneValidating').style.color = '#4ade80';

                    // Show preview
                    renderValidationPreview(result);

                    // Enable import button
                    document.getElementById('importButton').disabled = false;
                    document.getElementById('importButton').style.backgroundColor = '#16a34a';

                } else {
                    // Show error
                    document.getElementById('dropzoneValidating').textContent = '✗ Validation failed';
                    document.getElementById('dropzoneValidating').style.color = '#ef4444';

                    // Show errors
                    renderValidationErrors(result);

                    // Disable import button
                    document.getElementById('importButton').disabled = true;
                    document.getElementById('importButton').style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
                }

            } catch (error) {
                console.error('Validation error:', error);
                document.getElementById('dropzoneValidating').textContent = '✗ Validation error';
                document.getElementById('dropzoneValidating').style.color = '#ef4444';
                showStatus('settingsStatus', `Validation failed: ${error.message}`, 'error');
            }
        }

        // Render validation preview (success)
        function renderValidationPreview(result) {
            const preview = result.preview;
            const previewDiv = document.getElementById('validationPreview');
            const contentDiv = document.getElementById('validationContent');

            let html = '<div style="color: #4ade80; margin-bottom: 8px;">✓ Valid file format</div>';

            if (result.warnings.length > 0) {
                html += '<div style="color: #fbbf24; margin-bottom: 8px;">';
                result.warnings.forEach(warning => {
                    html += `⚠ ${warning}<br>`;
                });
                html += '</div>';
            }

            html += '<div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1);">';
            html += '<div style="font-weight: bold; margin-bottom: 8px;">Changes to apply:</div>';
            html += `<div>• Channels: Add ${preview.channels_new} new (${preview.channels_existing} existing)</div>`;
            html += `<div>• Videos: Add ${preview.videos_new} new (${preview.videos_duplicate} skipped)</div>`;

            if (preview.settings_changed > 0) {
                html += `<div>• Settings: Replace ${preview.settings_changed} values</div>`;
                if (preview.settings_details.length > 0) {
                    html += '<div style="font-size: 12px; color: #888; margin-left: 16px; margin-top: 4px;">';
                    preview.settings_details.forEach(detail => {
                        html += `${detail}<br>`;
                    });
                    html += '</div>';
                }
            } else {
                html += '<div>• Settings: No changes</div>';
            }

            html += `<div style="margin-top: 8px; font-size: 12px; color: #888;">Total size: ${preview.total_size_mb} MB</div>`;
            html += '</div>';

            contentDiv.innerHTML = html;
            previewDiv.style.display = 'block';
        }

        // Render validation errors
        function renderValidationErrors(result) {
            const previewDiv = document.getElementById('validationPreview');
            const contentDiv = document.getElementById('validationContent');

            let html = '<div style="color: #ef4444; margin-bottom: 12px; font-weight: bold;">Validation Failed</div>';
            html += '<div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 12px;">';

            if (result.errors.length > 0) {
                result.errors.forEach(error => {
                    html += `<div style="color: #ef4444; margin-bottom: 4px;">✗ ${error}</div>`;
                });
            }

            if (result.warnings.length > 0) {
                html += '<div style="margin-top: 12px;">';
                result.warnings.forEach(warning => {
                    html += `<div style="color: #fbbf24; margin-bottom: 4px;">⚠ ${warning}</div>`;
                });
                html += '</div>';
            }

            html += '<div style="margin-top: 12px; color: #888;">Please fix errors and try again.</div>';
            html += '</div>';

            contentDiv.innerHTML = html;
            previewDiv.style.display = 'block';
        }

        // Execute import
        async function executeImport() {
            if (!selectedImportFile) {
                showStatus('settingsStatus', 'No file selected', 'error');
                return;
            }

            const btn = document.getElementById('importButton');
            const originalText = btn.textContent;

            try {
                btn.disabled = true;
                btn.textContent = 'Importing...';

                // Create FormData
                const formData = new FormData();
                formData.append('file', selectedImportFile);

                const response = await fetch('/api/import/execute', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (result.success) {
                    const message = `Import successful! Added ${result.channels_added} channels, ${result.videos_added} videos, updated ${result.settings_updated} settings.`;
                    showStatus('settingsStatus', message, 'success');

                    // Reset import UI
                    cancelImport();

                    // Refresh data
                    await loadChannels();
                    await refreshFeed();

                    // Refresh settings to show updated values immediately
                    if (result.settings_updated > 0) {
                        await loadSettings();
                        await loadPrompt();  // Refresh AI prompt template if updated
                    }

                } else {
                    const errors = result.errors.join('; ');
                    showStatus('settingsStatus', `Import failed: ${errors}`, 'error');
                }

            } catch (error) {
                console.error('Import error:', error);
                showStatus('settingsStatus', `Import failed: ${error.message}`, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }

        // Cancel import
        function cancelImport() {
            selectedImportFile = null;

            // Reset dropzone
            document.getElementById('dropzoneDefault').style.display = 'block';
            document.getElementById('dropzoneFile').style.display = 'none';

            // Hide preview
            document.getElementById('validationPreview').style.display = 'none';

            // Hide import buttons container
            document.getElementById('importButtonsContainer').style.display = 'none';

            // Disable import button
            document.getElementById('importButton').disabled = true;
            document.getElementById('importButton').style.backgroundColor = 'rgba(255, 255, 255, 0.1)';

            // Clear file input
            document.getElementById('importFileInput').value = '';
        }

        // ============================================================================
        // TABLE OF CONTENTS (TOC) NAVIGATION
        // ============================================================================

        // Global state for TOC
        let tocObserver = null;
        let currentActiveSection = null;

        // Generate TOC for the current active tab
        function generateTOC() {
            // Find the currently active tab
            const activeTab = document.querySelector('.tab-content.active');
            if (!activeTab) {
                hideTOC();
                return;
            }

            // Find all h3 elements within .settings-section
            const sections = activeTab.querySelectorAll('.settings-section h3');

            // Apply threshold: only show TOC if 2 or more sections exist
            if (sections.length < 2) {
                hideTOC();
                return;
            }

            // Extract section data
            const tocItems = [];
            sections.forEach((heading, index) => {
                // Extract text and remove emojis
                const rawText = heading.textContent || heading.innerText;
                const text = rawText.replace(/[\u{1F300}-\u{1F9FF}]/gu, '').replace(/[^\x00-\x7F]/g, '').trim();

                // Generate unique ID
                const baseId = text.toLowerCase()
                    .replace(/\s+/g, '-')
                    .replace(/[^a-z0-9-]/g, '')
                    .replace(/-+/g, '-')
                    .replace(/^-|-$/g, '');

                // Handle empty or duplicate IDs
                const id = baseId || `section-${index}`;
                const uniqueId = `section-${id}`;

                // Add ID to the section's parent (.settings-section)
                const section = heading.closest('.settings-section');
                if (section) {
                    section.id = uniqueId;
                }

                tocItems.push({ id: uniqueId, text: text || `Section ${index + 1}` });
            });

            // Render TOC
            renderTOC(tocItems);

            // Initialize scroll-spy
            initScrollSpy();

            // Show TOC
            showTOC();
        }

        // Render TOC HTML for both desktop and mobile
        function renderTOC(items) {
            // Render desktop TOC
            const tocList = document.getElementById('tocList');
            tocList.innerHTML = '';

            items.forEach((item, index) => {
                const li = document.createElement('li');
                li.className = 'toc-item';
                if (index === 0) li.classList.add('active'); // First item active by default

                const link = document.createElement('a');
                link.href = `#${item.id}`;
                link.className = 'toc-link';
                link.textContent = item.text;
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    scrollToSection(item.id);
                });

                li.appendChild(link);
                tocList.appendChild(li);
            });

            // Render mobile TOC (same structure)
            const tocListMobile = document.getElementById('tocListMobile');
            tocListMobile.innerHTML = '';

            items.forEach((item, index) => {
                const li = document.createElement('li');
                li.className = 'toc-item';
                if (index === 0) li.classList.add('active');

                const link = document.createElement('a');
                link.href = `#${item.id}`;
                link.className = 'toc-link';
                link.textContent = item.text;
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    scrollToSection(item.id);
                    closeMobileTOC(); // Close drawer after navigation
                });

                li.appendChild(link);
                tocListMobile.appendChild(li);
            });
        }

        // Initialize scroll-spy with Intersection Observer
        function initScrollSpy() {
            // Clean up existing observer
            if (tocObserver) {
                tocObserver.disconnect();
            }

            // Find all sections with IDs starting with "section-"
            const sections = document.querySelectorAll('.settings-section[id^="section-"]');

            if (sections.length === 0) return;

            // Create Intersection Observer
            tocObserver = new IntersectionObserver(
                (entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting && entry.intersectionRatio > 0) {
                            setActiveSection(entry.target.id);
                        }
                    });
                },
                {
                    root: null, // viewport
                    rootMargin: '-20% 0px -75% 0px', // Top 20% of viewport
                    threshold: 0
                }
            );

            // Observe all sections
            sections.forEach(section => {
                tocObserver.observe(section);
            });
        }

        // Set active section in TOC
        function setActiveSection(sectionId) {
            if (currentActiveSection === sectionId) return;
            currentActiveSection = sectionId;

            // Update desktop TOC
            document.querySelectorAll('#tocList .toc-item').forEach(item => {
                item.classList.remove('active');
            });

            const activeLink = document.querySelector(`#tocList .toc-link[href="#${sectionId}"]`);
            if (activeLink) {
                activeLink.closest('.toc-item').classList.add('active');
            }

            // Update mobile TOC
            document.querySelectorAll('#tocListMobile .toc-item').forEach(item => {
                item.classList.remove('active');
            });

            const activeLinkMobile = document.querySelector(`#tocListMobile .toc-link[href="#${sectionId}"]`);
            if (activeLinkMobile) {
                activeLinkMobile.closest('.toc-item').classList.add('active');
            }
        }

        // Scroll to section (instant, no smooth animation)
        function scrollToSection(sectionId) {
            const section = document.getElementById(sectionId);
            if (!section) return;

            // Instant scroll
            section.scrollIntoView({
                behavior: 'auto',
                block: 'start'
            });

            // Update active state immediately
            setActiveSection(sectionId);
        }

        // Show TOC
        function showTOC() {
            const tocContainer = document.getElementById('tocContainer');
            tocContainer.classList.add('show');
            document.getElementById('tocToggle').classList.add('show');

            // Dynamically position TOC to align with first section
            const activeTab = document.querySelector('.tab-content.active');
            if (activeTab) {
                const firstSection = activeTab.querySelector('.settings-section');
                if (firstSection) {
                    const rect = firstSection.getBoundingClientRect();
                    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                    const absoluteTop = rect.top + scrollTop;
                    tocContainer.style.top = `${rect.top}px`;
                }
            }
        }

        // Hide TOC
        function hideTOC() {
            document.getElementById('tocContainer').classList.remove('show');
            document.getElementById('tocToggle').classList.remove('show');

            // Clean up observer
            if (tocObserver) {
                tocObserver.disconnect();
                tocObserver = null;
            }

            // Reset state
            currentActiveSection = null;
        }

        // Mobile TOC toggle handlers
        function openMobileTOC() {
            document.getElementById('tocDrawer').classList.add('open');
            document.getElementById('tocBackdrop').classList.add('show');
        }

        function closeMobileTOC() {
            document.getElementById('tocDrawer').classList.remove('open');
            document.getElementById('tocBackdrop').classList.remove('show');
        }

        // Event listeners for mobile TOC
        document.getElementById('tocToggle').addEventListener('click', openMobileTOC);
        document.getElementById('tocDrawerClose').addEventListener('click', closeMobileTOC);
        document.getElementById('tocBackdrop').addEventListener('click', closeMobileTOC);

        // Close mobile TOC on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeMobileTOC();
            }
        });

