document.addEventListener('DOMContentLoaded', async () => {
    const authSection = document.getElementById('auth-section');
    const generatorSection = document.getElementById('generator-section');
    const resultSection = document.getElementById('result-section');
    const form = document.getElementById('playlist-form');
    
    // Check Auth Status
    try {
        const response = await fetch('/api/v1/me');
        if (response.ok) {
            const user = await response.json();
            showLoggedIn(user);
        } else {
            showLoggedOut();
        }
    } catch (e) {
        showLoggedOut();
    }

    function showLoggedOut() {
        authSection.innerHTML = `
            <a href="/login" class="spotify-btn" style="display:inline-block; padding: 12px 24px; text-decoration:none;">
                Login with Spotify
            </a>
        `;
    }

    function showLoggedIn(user) {
        const imgUrl = user.images && user.images.length > 0 ? user.images[0].url : 'https://i.scdn.co/image/ab6761610000e5eb55d39ab9c21d506aa52f7021';
        authSection.innerHTML = `
            <div class="user-profile">
                <img src="${imgUrl}" alt="Profile">
                <div class="user-info">
                    <span class="name">${user.display_name}</span>
                    <a href="/logout" class="logout">Log out</a>
                </div>
            </div>
        `;
        generatorSection.classList.remove('hidden');
    }

    // Form Submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const prompt = document.getElementById('prompt').value;
        const duration = document.getElementById('duration').value;
        const btnText = document.querySelector('.btn-text');
        const spinner = document.querySelector('.spinner');
        const generateBtn = document.getElementById('generate-btn');
        const statusMsg = document.getElementById('status-message');
        
        // UI Loading State
        btnText.classList.add('hidden');
        spinner.classList.remove('hidden');
        generateBtn.disabled = true;
        statusMsg.classList.remove('hidden');
        
        // Flashing status messages to keep user engaged
        const messages = [
            "Analyzing narrative arc...",
            "Summoning LLM candidate pool...",
            "Verifying tracks with Spotify...",
            "Solving 0-1 Knapsack for exact timing...",
            "Exporting to your Spotify library..."
        ];
        let msgIdx = 0;
        statusMsg.textContent = messages[0];
        const msgInterval = setInterval(() => {
            msgIdx = Math.min(msgIdx + 1, messages.length - 1);
            statusMsg.textContent = messages[msgIdx];
        }, 3000);

        try {
            const res = await fetch('/api/v1/playlists/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    prompt: prompt, 
                    target_duration_minutes: parseInt(duration) 
                })
            });

            const data = await res.json();
            
            clearInterval(msgInterval);
            
            if (res.ok) {
                // Show success
                generatorSection.classList.add('hidden');
                resultSection.classList.remove('hidden');
                
                document.getElementById('result-concept').textContent = `"${data.concept}"`;
                document.getElementById('result-tracks').textContent = data.track_count;
                
                const formatTime = (sec) => `${Math.floor(sec/60)}:${(sec%60).toString().padStart(2, '0')}`;
                document.getElementById('result-target').textContent = formatTime(data.target_duration_seconds);
                document.getElementById('result-actual').textContent = formatTime(data.total_duration_seconds);
                
                if (data.spotify_playlist_url) {
                    document.getElementById('spotify-link').href = data.spotify_playlist_url;
                    document.getElementById('spotify-link').classList.remove('hidden');
                } else {
                    document.getElementById('spotify-link').classList.add('hidden');
                    // Add a warning message if Spotify blocked the creation
                    const warning = document.createElement('p');
                    warning.style.color = '#ff9800';
                    warning.style.fontSize = '0.9rem';
                    warning.style.marginTop = '16px';
                    warning.textContent = "Spotify API blocked auto-export for your developer account. Your tracks are listed above!";
                    document.getElementById('result-section').insertBefore(warning, document.getElementById('spotify-link'));
                }
                
                // Render tracks
                const trackContainer = document.getElementById('track-list-container');
                trackContainer.innerHTML = '';
                if (data.tracks && data.tracks.length > 0) {
                    data.tracks.forEach(track => {
                        const div = document.createElement('div');
                        div.className = 'track-item';
                        div.innerHTML = `
                            <div class="track-info">
                                <span class="track-title">${track.title}</span>
                                <span class="track-artist">${track.artist}</span>
                            </div>
                            <span class="track-duration">${formatTime(track.duration_ms / 1000)}</span>
                        `;
                        trackContainer.appendChild(div);
                    });
                } else {
                    trackContainer.innerHTML = '<p>No tracks returned.</p>';
                }
            } else {
                alert(`Error: ${data.detail || 'Failed to generate'}`);
            }
        } catch (err) {
            clearInterval(msgInterval);
            alert('A network error occurred.');
            console.error(err);
        } finally {
            // Reset button
            btnText.classList.remove('hidden');
            spinner.classList.add('hidden');
            generateBtn.disabled = false;
            statusMsg.classList.add('hidden');
        }
    });

    document.getElementById('reset-btn').addEventListener('click', () => {
        resultSection.classList.add('hidden');
        generatorSection.classList.remove('hidden');
        form.reset();
    });
});
