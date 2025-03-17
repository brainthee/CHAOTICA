// pet-integration.js
class PetIntegration {
    constructor(pet, options = {}) {
        this.pet = pet;
        this.options = {
            loginReward: true,
            taskCompletionReward: true,
            petProgressBar: true,
            syncWithServer: false,
            engagementTracking: true,
            ...options
        };
        
        // Initialize integration features
        if (this.options.loginReward) {
            this.addLoginReward();
        }
        
        if (this.options.taskCompletionReward) {
            this.addTaskCompletionReward();
        }
        
        if (this.options.petProgressBar) {
            this.addPetProgressBar();
        }
        
        if (this.options.engagementTracking) {
            this.setupEngagementTracking();
        }
        
        // Listen for penetration test completion events
        this.setupPentestTracking();
    }
    
    addLoginReward() {
        // Check if already rewarded today
        const today = new Date().toISOString().split('T')[0];
        const lastLoginReward = localStorage.getItem('lastPetLoginReward');
        
        if (lastLoginReward !== today) {
            // Add happiness and energy as a login reward
            this.pet.happiness = Math.min(100, this.pet.happiness + 10);
            this.pet.energy = Math.min(100, this.pet.energy + 20);
            
            // Save last reward date
            localStorage.setItem('lastPetLoginReward', today);
            
            // Show reward notification
            this.showNotification('Daily Login Reward!', `${this.pet.options.petName} is happy to see you today! (+10 Happiness, +20 Energy)`);
        }
    }
    
    addTaskCompletionReward() {
        // Watch for task completion notifications in the DOM
        // This will need to be customized based on your app's structure
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList' && mutation.addedNodes.length) {
                    const addedNodes = Array.from(mutation.addedNodes);
                    const completionNotice = addedNodes.find(node => 
                        node.textContent && 
                        (node.textContent.includes('completed') || 
                         node.textContent.includes('finished') ||
                         node.textContent.includes('done')));
                    
                    if (completionNotice) {
                        this.rewardTaskCompletion();
                    }
                }
            });
        });
        
        // Target notification area - adjust selector based on your app
        const taskContainer = document.querySelector('#task-container, .task-list, .notifications') || document.body;
        observer.observe(taskContainer, { childList: true, subtree: true });
        
        // Alternative: Hook into existing task completion functions
        if (window.markTaskComplete) {
            const originalHandler = window.markTaskComplete;
            window.markTaskComplete = (...args) => {
                // Call original handler
                const result = originalHandler(...args);
                
                // Add our reward
                this.rewardTaskCompletion();
                
                return result;
            };
        }
    }
    
    rewardTaskCompletion() {
        // Reward happiness for completing a task
        this.pet.happiness = Math.min(100, this.pet.happiness + 5);
        
        // Show reward notification
        this.showNotification('Task Completion Reward!', `${this.pet.options.petName} is proud of your progress! (+5 Happiness)`);
    }
    
    setupPentestTracking() {
        // Listen for pentest completion events
        // This is just an example and should be adapted to your app's actual events
        
        // Example 1: Watch for specific URL changes that might indicate completion
        let lastUrl = window.location.href;
        const urlChangeCallback = () => {
            const currentUrl = window.location.href;
            if (currentUrl !== lastUrl) {
                lastUrl = currentUrl;
                
                // Check if URL indicates completion of a pentest
                if (currentUrl.includes('/pentest/complete') || 
                    currentUrl.includes('/engagement/finished')) {
                    this.recordPentestCompletion();
                }
            }
        };
        
        // Check periodically for URL changes
        setInterval(urlChangeCallback, 500);
        
        // Example 2: Watch for DOM changes indicating completion
        const pentestObserver = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList' && mutation.addedNodes.length) {
                    const addedNodes = Array.from(mutation.addedNodes);
                    const completionElement = addedNodes.find(node => 
                        node.textContent && 
                        (node.textContent.includes('Pentest completed') || 
                         node.textContent.includes('Penetration test finished') ||
                         node.textContent.includes('Engagement closed')));
                    
                    if (completionElement) {
                        this.recordPentestCompletion();
                    }
                }
            });
        });
        
        // Target the typical areas where completion notices might appear
        const pentestContainer = document.querySelector('#pentest-container, .engagement-list, .dashboard') || document.body;
        pentestObserver.observe(pentestContainer, { childList: true, subtree: true });
        
        // Example 3: Override existing functions
        if (window.completePentest) {
            const originalHandler = window.completePentest;
            window.completePentest = (...args) => {
                // Call original handler
                const result = originalHandler(...args);
                
                // Record completion
                this.recordPentestCompletion();
                
                return result;
            };
        }
    }
    
    recordPentestCompletion() {
        // Give a bigger happiness boost for completing a pentest
        this.pet.happiness = Math.min(100, this.pet.happiness + 15);
        this.pet.energy = Math.min(100, this.pet.energy + 25);
        
        // Record the completion in statistics
        if (this.pet.statistics) {
            this.pet.statistics.recordPentestCompletion();
        }
        
        // Show special notification
        this.showNotification('Pentest Completed!', 
            `${this.pet.options.petName} is thrilled with your security work! (+15 Happiness, +25 Energy)`);
    }
    
    addPetProgressBar() {
        // Create a mini status bar that follows the pet
        const statusBar = document.createElement('div');
        statusBar.className = 'pet-status-bar';
        statusBar.style.position = 'absolute';
        statusBar.style.bottom = '-15px';
        statusBar.style.left = '0';
        statusBar.style.width = '100%';
        statusBar.style.height = '5px';
        statusBar.style.backgroundColor = '#ddd';
        statusBar.style.borderRadius = '2px';
        statusBar.style.overflow = 'hidden';
        
        // Happiness indicator
        const happinessBar = document.createElement('div');
        happinessBar.className = 'pet-happiness-bar';
        happinessBar.style.height = '2px';
        happinessBar.style.backgroundColor = '#4CAF50';
        happinessBar.style.width = `${this.pet.happiness}%`;
        happinessBar.style.position = 'absolute';
        happinessBar.style.top = '0';
        happinessBar.style.left = '0';
        statusBar.appendChild(happinessBar);
        
        // Energy indicator
        const energyBar = document.createElement('div');
        energyBar.className = 'pet-energy-bar';
        energyBar.style.height = '2px';
        energyBar.style.backgroundColor = '#2196F3';
        energyBar.style.width = `${this.pet.energy}%`;
        energyBar.style.position = 'absolute';
        energyBar.style.bottom = '0';
        energyBar.style.left = '0';
        statusBar.appendChild(energyBar);
        
        this.pet.container.appendChild(statusBar);
        
        // Update the status bar when pet stats change
        const updateStatusBar = () => {
            happinessBar.style.width = `${this.pet.happiness}%`;
            energyBar.style.width = `${this.pet.energy}%`;
            
            // Change colors based on values
            if (this.pet.happiness < 30) {
                happinessBar.style.backgroundColor = '#F44336'; // Red
            } else if (this.pet.happiness < 70) {
                happinessBar.style.backgroundColor = '#FF9800'; // Orange
            } else {
                happinessBar.style.backgroundColor = '#4CAF50'; // Green
            }
            
            if (this.pet.energy < 30) {
                energyBar.style.backgroundColor = '#F44336'; // Red
            } else if (this.pet.energy < 70) {
                energyBar.style.backgroundColor = '#FF9800'; // Orange
            } else {
                energyBar.style.backgroundColor = '#2196F3'; // Blue
            }
        };
        
        // Hook into pet state updates
        const originalUpdatePetState = this.pet.updatePetState;
        this.pet.updatePetState = () => {
            originalUpdatePetState.call(this.pet);
            updateStatusBar();
        };
        
        // Initial update
        updateStatusBar();
    }
    
    setupEngagementTracking() {
        // If pet happiness gets too low, remind user to interact
        const checkEngagement = () => {
            const hoursSinceLastInteraction = 
                (new Date() - new Date(this.pet.lastInteraction)) / (1000 * 60 * 60);
            
            if (hoursSinceLastInteraction > 24 && this.pet.happiness < 50) {
                this.showReminderNotification();
            }
        };
        
        // Check every hour
        setInterval(checkEngagement, 60 * 60 * 1000);
    }
    
    showReminderNotification() {
        // Don't show reminders too frequently
        const lastReminder = localStorage.getItem('lastPetReminder');
        const now = new Date().toISOString();
        
        if (!lastReminder || 
            (new Date(now) - new Date(lastReminder)) > (1000 * 60 * 60 * 12)) { // 12 hours
            
            // Create message based on happiness level
            let message = '';
            if (this.pet.happiness < 20) {
                message = `${this.pet.options.petName} is feeling very sad. Please take a moment to interact!`;
            } else if (this.pet.happiness < 40) {
                message = `${this.pet.options.petName} could use some attention when you have time.`;
            } else {
                message = `${this.pet.options.petName} would appreciate some playtime when you're free.`;
            }
            
            this.showNotification('Pet Reminder', message);
            localStorage.setItem('lastPetReminder', now);
        }
    }
    
    showNotification(title, message) {
        // Create notification
        const notification = document.createElement('div');
        notification.className = 'pet-notification';
        notification.innerHTML = `
            <div class="pet-notification-title">${title}</div>
            <div class="pet-notification-message">${message}</div>
        `;
        
        // Style notification
        notification.style.position = 'fixed';
        notification.style.bottom = '20px';
        notification.style.right = '20px';
        notification.style.backgroundColor = 'white';
        notification.style.border = '1px solid #ddd';
        notification.style.borderRadius = '5px';
        notification.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        notification.style.padding = '15px';
        notification.style.maxWidth = '300px';
        notification.style.zIndex = '10000';
        notification.style.transform = 'translateY(20px)';
        notification.style.opacity = '0';
        notification.style.transition = 'all 0.3s ease';
        
        notification.querySelector('.pet-notification-title').style.fontWeight = 'bold';
        notification.querySelector('.pet-notification-title').style.marginBottom = '5px';
        
        // Add to DOM
        document.body.appendChild(notification);
        
        // Animate in
        setTimeout(() => {
            notification.style.transform = 'translateY(0)';
            notification.style.opacity = '1';
        }, 10);
        
        // Add close button
        const closeButton = document.createElement('div');
        closeButton.innerHTML = '×';
        closeButton.style.position = 'absolute';
        closeButton.style.top = '5px';
        closeButton.style.right = '10px';
        closeButton.style.cursor = 'pointer';
        closeButton.style.fontSize = '16px';
        closeButton.style.color = '#999';
        closeButton.addEventListener('click', () => {
            notification.style.transform = 'translateY(20px)';
            notification.style.opacity = '0';
            setTimeout(() => notification.remove(), 300);
        });
        notification.appendChild(closeButton);
        
        // Remove after 5 seconds
        setTimeout(() => {
            notification.style.transform = 'translateY(20px)';
            notification.style.opacity = '0';
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }
    
    // Add Django CSRF token to requests
    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
               document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    }
    
    // Send pet stats to server (optional)
    syncWithServer() {
        if (!this.options.syncWithServer) return;
        
        const data = {
            pet_name: this.pet.options.petName,
            happiness: this.pet.happiness,
            energy: this.pet.energy,
            state: this.pet.state,
            last_fed: this.pet.lastFed.toISOString(),
            last_interaction: this.pet.lastInteraction.toISOString(),
            statistics: {
                total_feeds: this.pet.statistics ? this.pet.statistics.stats.totalFeeds : 0,
                total_plays: this.pet.statistics ? this.pet.statistics.stats.totalPlays : 0,
                total_pets: this.pet.statistics ? this.pet.statistics.stats.totalPets : 0,
                total_sleeps: this.pet.statistics ? this.pet.statistics.stats.totalSleeps : 0,
                phase_completions: this.pet.statistics ? this.pet.statistics.stats.pentestCompletions : 0,
            }
        };
        
        fetch('/api/pet/sync/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify(data)
        })
        .catch(error => {
            console.error('Error syncing pet data with server:', error);
        });
    }
    
    // Create server-side view for pets across the organization
    createTeamPetRankingTable() {
        const table = document.createElement('table');
        table.className = 'team-pet-ranking';
        table.style.width = '100%';
        table.style.borderCollapse = 'collapse';
        table.style.marginTop = '20px';
        
        // Create header
        const thead = document.createElement('thead');
        thead.innerHTML = `
            <tr>
                <th style="text-align: left; padding: 8px; border-bottom: 2px solid #ddd;">User</th>
                <th style="text-align: center; padding: 8px; border-bottom: 2px solid #ddd;">Pet Name</th>
                <th style="text-align: center; padding: 8px; border-bottom: 2px solid #ddd;">Happiness</th>
                <th style="text-align: center; padding: 8px; border-bottom: 2px solid #ddd;">Pentests</th>
                <th style="text-align: center; padding: 8px; border-bottom: 2px solid #ddd;">Age (days)</th>
            </tr>
        `;
        table.appendChild(thead);
        
        // Create body (will be populated from server-side data)
        const tbody = document.createElement('tbody');
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; padding: 20px;">Loading team data...</td>
            </tr>
        `;
        table.appendChild(tbody);
        
        // Load data from server
        this.loadTeamPetData(tbody);
        
        return table;
    }
    
    // Load team pet data from server
    loadTeamPetData(tableBody) {
        fetch('/api/pet/team/', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.pets && data.pets.length > 0) {
                // Sort pets by happiness level (descending)
                const sortedPets = data.pets.sort((a, b) => b.happiness - a.happiness);
                
                // Create table rows
                tableBody.innerHTML = sortedPets.map(pet => `
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">${pet.user_name}</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: center;">${pet.pet_name}</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: center;">
                            <div style="width: 100px; height: 10px; background-color: #eee; border-radius: 5px; margin: 0 auto; overflow: hidden;">
                                <div style="height: 100%; width: ${pet.happiness}%; background-color: ${
                                    pet.happiness < 30 ? '#F44336' : 
                                    pet.happiness < 70 ? '#FF9800' : '#4CAF50'
                                };"></div>
                            </div>
                            <span style="font-size: 12px;">${Math.round(pet.happiness)}%</span>
                        </td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: center;">${pet.phase_completions}</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: center;">${pet.age_days}</td>
                    </tr>
                `).join('');
            } else {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="5" style="text-align: center; padding: 20px;">No team pet data available</td>
                    </tr>
                `;
            }
        })
        .catch(error => {
            console.error('Error loading team pet data:', error);
            tableBody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; padding: 20px; color: #F44336;">
                        Error loading team data. Please try again later.
                    </td>
                </tr>
            `;
        });
    }
    
    // Add tooltips with security tips relevant to pentesting
    addSecurityTips() {
        // List of pentesting tips
        const securityTips = [
            "Remember to check for default credentials on all systems",
            "Always verify if file upload functionality allows for malicious files",
            "SQL injection is still one of the most common vulnerabilities",
            "Don't forget about Cross-Site Scripting (XSS) in your assessments",
            "Always check for sensitive data exposure in error messages",
            "Test applications for business logic flaws, not just technical vulnerabilities",
            "Broken access controls can lead to unauthorized data access",
            "Always verify that security headers are properly implemented",
            "Check if password policies are enforced on all entry points",
            "Don't forget about server-side request forgery (SSRF) vulnerabilities"
        ];
        
        // Create tip function
        const showRandomTip = () => {
            const randomTip = securityTips[Math.floor(Math.random() * securityTips.length)];
            this.showNotification('Security Tip', randomTip);
        };
        
        // Show tip when pet is clicked, occasionally
        const originalPetClick = this.pet.petElement.onclick;
        this.pet.petElement.onclick = (e) => {
            // Call original click handler
            if (originalPetClick) {
                originalPetClick.call(this.pet.petElement, e);
            }
            
            // Occasionally show a security tip (20% chance)
            if (Math.random() < 0.2) {
                showRandomTip();
            }
        };
        
        // Also add a tip button to the menu
        const menuElement = this.pet.menuElement;
        if (menuElement) {
            const tipButton = document.createElement('button');
            tipButton.className = 'virtual-pet-action';
            tipButton.style.margin = '3px';
            tipButton.style.padding = '5px 10px';
            tipButton.style.border = 'none';
            tipButton.style.borderRadius = '3px';
            tipButton.style.background = '#f0f0f0';
            tipButton.style.cursor = 'pointer';
            tipButton.textContent = '💡 Tip';
            tipButton.addEventListener('click', (e) => {
                e.stopPropagation();
                showRandomTip();
                menuElement.style.display = 'none';
            });
            
            menuElement.appendChild(tipButton);
        }
    }
}

// Export the PetIntegration class
export default PetIntegration;