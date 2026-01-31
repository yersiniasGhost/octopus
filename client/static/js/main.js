/**
 * Energy Conservation Client Portal - Main JavaScript
 * Phase 1: Search and Profile Display
 */

// State
let currentUser = null;
let opportunities = [];
let conversationHistory = [];
let percentileChart = null;

// DOM Elements
const searchInput = document.getElementById('searchInput');
const searchResults = document.getElementById('searchResults');
const countySelect = document.getElementById('countySelect');
const participantsOnly = document.getElementById('participantsOnly');
const searchBtn = document.getElementById('searchBtn');
const profilePlaceholder = document.getElementById('profilePlaceholder');
const profileContent = document.getElementById('profileContent');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const opportunitiesList = document.getElementById('opportunitiesList');
const opportunitiesCount = document.getElementById('opportunitiesCount');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
});

function setupEventListeners() {
    // Search input with debounce
    let searchTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            if (searchInput.value.trim().length >= 2) {
                performSearch();
            } else {
                hideSearchResults();
            }
        }, 300);
    });

    // Search button click
    searchBtn.addEventListener('click', performSearch);

    // Enter key in search
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    // Click outside to close results
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-container')) {
            hideSearchResults();
        }
    });

    // Chat input auto-resize
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });

    // Send message
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

// Search Functions
async function performSearch() {
    const query = searchInput.value.trim();
    if (query.length < 2) return;

    const county = countySelect.value;
    const participantsOnlyChecked = participantsOnly.checked;

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                county: county,
                participants_only: participantsOnlyChecked
            })
        });

        const data = await response.json();

        if (data.success && data.results.length > 0) {
            displaySearchResults(data.results);
        } else {
            searchResults.innerHTML = '<div class="search-result-item">No results found</div>';
            searchResults.classList.add('active');
        }
    } catch (error) {
        console.error('Search error:', error);
        searchResults.innerHTML = '<div class="search-result-item">Error searching. Please try again.</div>';
        searchResults.classList.add('active');
    }
}

function displaySearchResults(results) {
    searchResults.innerHTML = results.map(user => `
        <div class="search-result-item" onclick="selectUser('${user.id}', '${user.county}')">
            <div class="name">
                ${escapeHtml(user.name)}
                ${user.is_participant ? '<span class="participant-badge">Participant</span>' : ''}
            </div>
            <div class="address">${escapeHtml(user.address)}</div>
        </div>
    `).join('');
    searchResults.classList.add('active');
}

function hideSearchResults() {
    searchResults.classList.remove('active');
}

// User Selection
async function selectUser(parcelId, county) {
    hideSearchResults();
    searchInput.value = '';

    // Show loading state
    profilePlaceholder.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Loading profile...</div>';
    profilePlaceholder.style.display = 'flex';
    profileContent.style.display = 'none';

    const url = `/api/user/${encodeURIComponent(parcelId)}?county=${encodeURIComponent(county)}`;
    console.log('Fetching URL:', url);  // Debug: see exact URL
    console.log('parcelId:', parcelId, 'county:', county);  // Debug: see values

    try {
        const response = await fetch(url);
        const data = await response.json();

        console.log('API response:', data);  // Debug logging

        if (data.success && data.profile) {
            currentUser = data.profile;
            try {
                displayProfile(data.profile);
                enableChat();
                resetConversation();
                startAdvisorConversation();
            } catch (displayError) {
                console.error('Display profile error:', displayError);
                profilePlaceholder.innerHTML = `
                    <i class="fas fa-exclamation-circle"></i>
                    <p>Error displaying profile: ${displayError.message}</p>
                `;
            }
        } else {
            console.error('API returned error:', data);
            profilePlaceholder.innerHTML = `
                <i class="fas fa-exclamation-circle"></i>
                <p>Error loading profile: ${data.error || 'Unknown error'}</p>
            `;
        }
    } catch (error) {
        console.error('Load profile error:', error);
        profilePlaceholder.innerHTML = `
            <i class="fas fa-exclamation-circle"></i>
            <p>Error loading profile: ${error.message}</p>
        `;
    }
}

// Profile Display
function displayProfile(profile) {
    profilePlaceholder.style.display = 'none';
    profileContent.style.display = 'block';

    // Basic info
    document.getElementById('profileName').textContent = profile.name;
    document.getElementById('profileAddress').textContent = profile.address;

    const badge = document.getElementById('participantBadge');
    if (profile.is_participant) {
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }

    // Demographics
    const demo = profile.demographic || {};
    document.getElementById('householdSize').textContent = demo.household_size || '-';
    document.getElementById('estimatedIncome').textContent = demo.estimated_income
        ? '$' + formatNumber(demo.estimated_income)
        : '-';

    // Home info
    const home = profile.home || {};
    document.getElementById('homeSqft').textContent = home.living_area_sqft
        ? formatNumber(home.living_area_sqft)
        : '-';
    document.getElementById('homeAge').textContent = home.age || '-';

    // Energy costs - show NA if gas data unavailable
    document.getElementById('electricCost').textContent = '$' + formatNumber(demo.annual_kwh_cost || 0);
    document.getElementById('gasCost').textContent = demo.gas_available
        ? '$' + formatNumber(demo.annual_gas_cost)
        : 'NA';
    document.getElementById('totalCost').textContent = '$' + formatNumber(demo.total_energy_cost || 0);

    // Energy burden
    const burden = demo.energy_burden_pct || 0;
    const burdenEl = document.getElementById('energyBurden');
    burdenEl.textContent = burden.toFixed(1) + '%';
    if (burden > 6) {
        burdenEl.classList.add('warning');
    } else {
        burdenEl.classList.remove('warning');
    }

    // Comparables - use actual averages; show NA and exclude gas if user has no gas data
    const comp = profile.comparables || {};
    const compElectric = comp.avg_kwh_cost || 0;
    const compGas = comp.avg_gas_cost || 0;
    // Only include gas in comparable total if user has gas data
    const compTotal = demo.gas_available ? (compElectric + compGas) : compElectric;
    document.getElementById('compElectric').textContent = '$' + formatNumber(compElectric);
    document.getElementById('compGas').textContent = demo.gas_available
        ? '$' + formatNumber(compGas)
        : 'NA';
    document.getElementById('compTotal').textContent = '$' + formatNumber(compTotal);

    // Potential savings
    document.getElementById('potentialSavings').textContent = '$' + formatNumber(comp.potential_savings || 0);

    // Energy percentile chart
    const percentile = profile.energy_percentile || 50;
    updatePercentileChart(percentile);
}

function updatePercentileChart(percentile) {
    const ctx = document.getElementById('percentileChart').getContext('2d');

    // Destroy existing chart
    if (percentileChart) {
        percentileChart.destroy();
    }

    // Determine color based on percentile
    let color;
    if (percentile <= 30) {
        color = '#4ecca3'; // Green - good
    } else if (percentile <= 70) {
        color = '#ff9800'; // Orange - average
    } else {
        color = '#ff6b6b'; // Red - high usage
    }

    // Create half-doughnut chart
    percentileChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [percentile, 100 - percentile],
                backgroundColor: [color, '#2d3748'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            circumference: 180,
            rotation: -90,
            cutout: '70%',
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            }
        }
    });

    // Update text
    document.getElementById('percentileValue').textContent = percentile + 'th';
    document.getElementById('percentileValue').style.color = color;
    document.getElementById('percentileLabel').textContent =
        `Uses more energy than ${percentile}% of similar homes`;
}

// Chat Functions
function enableChat() {
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.placeholder = 'Ask about energy savings...';
}

function disableChat() {
    chatInput.disabled = true;
    sendBtn.disabled = true;
    chatInput.placeholder = 'Select a user to start chatting...';
}

function resetConversation() {
    conversationHistory = [];
    opportunities = [];
    updateOpportunitiesDisplay();
}

function startAdvisorConversation() {
    // Clear previous messages except welcome
    chatMessages.innerHTML = '';

    // Add initial message from advisor
    const initialMessage = `Hello! I'm looking at the energy profile for **${currentUser.name}**.

I can see some interesting data here:
- Annual energy cost: **$${formatNumber(currentUser.demographic?.total_energy_cost || 0)}**
- Energy percentile: **${currentUser.energy_percentile || 'N/A'}th** (compared to similar homes)
${currentUser.comparables?.potential_savings > 0 ? `- Potential savings: **$${formatNumber(currentUser.comparables.potential_savings)}/year** if reduced to median` : ''}

Let me ask you a few questions to identify specific opportunities to save energy and money.

**Do you notice any comfort issues in your home?** For example, cold spots in winter, rooms that are hard to heat or cool, or drafts near windows and doors?`;

    addMessage(initialMessage, 'assistant');
}

async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message || !currentUser) return;

    // Add user message to chat
    addMessage(message, 'user');
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Disable input while waiting
    chatInput.disabled = true;
    sendBtn.disabled = true;

    // Show typing indicator
    showTypingIndicator();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                user_context: {
                    parcel_id: currentUser.parcel_id,
                    county: currentUser.county
                },
                conversation_history: conversationHistory
            })
        });

        const data = await response.json();
        hideTypingIndicator();

        if (data.success) {
            addMessage(data.response, 'assistant');

            // Update conversation history
            conversationHistory = data.conversation_history || conversationHistory;

            // Add any new opportunities
            if (data.opportunities_added && data.opportunities_added.length > 0) {
                data.opportunities_added.forEach(opp => addOpportunity(opp));
            }
        } else {
            addMessage('Sorry, I encountered an error. Please try again.', 'assistant');
        }
    } catch (error) {
        console.error('Chat error:', error);
        hideTypingIndicator();
        addMessage('Sorry, I encountered an error. Please try again.', 'assistant');
    }

    // Re-enable input
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.focus();
}

function addMessage(content, role) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    // Simple markdown-like formatting
    let formatted = escapeHtml(content)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');

    messageDiv.innerHTML = formatted;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Update history
    conversationHistory.push({ role, content });
}

function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'message assistant';
    indicator.id = 'typingIndicator';
    indicator.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
    chatMessages.appendChild(indicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

// Opportunities Functions
function addOpportunity(opp) {
    // Check for duplicates
    const exists = opportunities.some(o =>
        o.category === opp.category && o.description === opp.description
    );
    if (exists) return;

    opportunities.push(opp);
    updateOpportunitiesDisplay();
}

function updateOpportunitiesDisplay() {
    opportunitiesCount.textContent = opportunities.length;

    if (opportunities.length === 0) {
        opportunitiesList.innerHTML = `
            <div class="opportunities-empty">
                <i class="fas fa-lightbulb" style="font-size: 2rem; margin-bottom: 0.5rem; display: block; opacity: 0.5;"></i>
                <p>Energy-saving opportunities will appear here as we chat.</p>
            </div>
        `;
        return;
    }

    // Group by category
    const categories = {
        weatherization: { icon: 'fa-house-chimney', label: 'Weatherization', color: '#4CAF50', items: [] },
        hvac: { icon: 'fa-temperature-half', label: 'HVAC', color: '#2196F3', items: [] },
        appliances: { icon: 'fa-lightbulb', label: 'Appliances & Lighting', color: '#FF9800', items: [] },
        behavioral: { icon: 'fa-plug', label: 'Behavioral Changes', color: '#9C27B0', items: [] },
        programs: { icon: 'fa-dollar-sign', label: 'Programs & Rebates', color: '#F44336', items: [] }
    };

    opportunities.forEach(opp => {
        const cat = opp.category || 'behavioral';
        if (categories[cat]) {
            categories[cat].items.push(opp);
        }
    });

    let html = '';
    for (const [key, cat] of Object.entries(categories)) {
        if (cat.items.length === 0) continue;

        html += `
            <div class="opportunity-category">
                <div class="category-header">
                    <div class="category-icon" style="background-color: ${cat.color}20; color: ${cat.color};">
                        <i class="fas ${cat.icon}"></i>
                    </div>
                    <span style="color: ${cat.color};">${cat.label}</span>
                </div>
                ${cat.items.map(opp => `
                    <div class="opportunity-item priority-${opp.priority || 'medium'}">
                        <div class="opportunity-description">${escapeHtml(opp.description)}</div>
                        ${opp.estimated_savings ? `<div class="opportunity-savings">${escapeHtml(opp.estimated_savings)}</div>` : ''}
                        ${opp.contractor_type ? `<div class="opportunity-contractor"><i class="fas fa-user-hard-hat"></i> ${escapeHtml(opp.contractor_type)}</div>` : ''}
                        ${opp.program_name ? `<div class="opportunity-contractor"><i class="fas fa-hand-holding-dollar"></i> ${escapeHtml(opp.program_name)}</div>` : ''}
                    </div>
                `).join('')}
            </div>
        `;
    }

    opportunitiesList.innerHTML = html;
}

// Utility Functions
function formatNumber(num) {
    if (num === null || num === undefined) return '-';
    return Math.round(num).toLocaleString();
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
