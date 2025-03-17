// pet-achievements.js
class PetAchievements {
    constructor(pet) {
        this.pet = pet;
        this.achievements = [
            {
                id: 'first-feed',
                name: 'First Meal',
                description: 'Feed your pet for the first time',
                icon: '🍽️',
                unlocked: false,
                condition: () => this.pet.feedCount > 0
            },
            {
                id: 'well-fed',
                name: 'Well Fed',
                description: 'Feed your pet 10 times',
                icon: '🍗',
                unlocked: false,
                condition: () => this.pet.feedCount >= 10
            },
            {
                id: 'playful',
                name: 'Playful',
                description: 'Play with your pet 5 times',
                icon: '🎯',
                unlocked: false,
                condition: () => this.pet.playCount >= 5
            },
            {
                id: 'best-friends',
                name: 'Best Friends',
                description: 'Interact with your pet 20 times',
                icon: '👫',
                unlocked: false,
                condition: () => this.pet.totalInteractions >= 20
            },
            {
                id: 'loyal',
                name: 'Loyal Companion',
                description: 'Visit your pet for 5 consecutive days',
                icon: '📅',
                unlocked: false,
                condition: () => this.pet.consecutiveVisitDays >= 5
            },
            {
                id: 'pentest-helper',
                name: 'Security Companion',
                description: 'Complete 3 penetration test engagements with your pet',
                icon: '🔒',
                unlocked: false,
                condition: () => this.pet.pentestCompletions >= 3
            }
        ];
        
        // Load unlocked achievements from storage
        this.loadAchievements();
        
        // Check for achievements every 10 seconds
        setInterval(() => this.checkAchievements(), 10000);
    }
    
    checkAchievements() {
        let newlyUnlocked = false;
        
        this.achievements.forEach(achievement => {
            if (!achievement.unlocked && achievement.condition()) {
                achievement.unlocked = true;
                achievement.unlockedDate = new Date();
                newlyUnlocked = true;
                
                // Trigger notification
                this.notifyAchievementUnlocked(achievement);
            }
        });
        
        if (newlyUnlocked) {
            this.saveAchievements();
        }
    }
    
    notifyAchievementUnlocked(achievement) {
        // Create achievement notification
        const notification = document.createElement('div');
        notification.className = 'pet-achievement-notification';
        notification.innerHTML = `
            <div class="pet-achievement-icon">${achievement.icon}</div>
            <div class="pet-achievement-info">
                <div class="pet-achievement-title">Achievement Unlocked!</div>
                <div class="pet-achievement-name">${achievement.name}</div>
                <div class="pet-achievement-desc">${achievement.description}</div>
            </div>
        `;
        
        // Style the notification
        notification.style.position = 'fixed';
        notification.style.bottom = '100px';
        notification.style.right = '20px';
        notification.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
        notification.style.color = 'white';
        notification.style.padding = '15px';
        notification.style.borderRadius = '5px';
        notification.style.display = 'flex';
        notification.style.alignItems = 'center';
        notification.style.maxWidth = '300px';
        notification.style.transform = 'translateY(20px)';
        notification.style.opacity = '0';
        notification.style.transition = 'all 0.3s ease';
        notification.style.zIndex = '10000';
        
        // Style the icon
        notification.querySelector('.pet-achievement-icon').style.fontSize = '30px';
        notification.querySelector('.pet-achievement-icon').style.marginRight = '15px';
        
        // Style the title
        notification.querySelector('.pet-achievement-title').style.fontWeight = 'bold';
        notification.querySelector('.pet-achievement-title').style.marginBottom = '5px';
        
        // Add to DOM
        document.body.appendChild(notification);
        
        // Animate in
        setTimeout(() => {
            notification.style.transform = 'translateY(0)';
            notification.style.opacity = '1';
        }, 10);
        
        // Remove after 5 seconds
        setTimeout(() => {
            notification.style.transform = 'translateY(20px)';
            notification.style.opacity = '0';
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }
    
    getUnlockedAchievements() {
        return this.achievements.filter(a => a.unlocked);
    }
    
    saveAchievements() {
        localStorage.setItem('petAchievements', JSON.stringify(
            this.achievements.map(a => ({
                id: a.id,
                unlocked: a.unlocked,
                unlockedDate: a.unlockedDate
            }))
        ));
    }
    
    loadAchievements() {
        const saved = localStorage.getItem('petAchievements');
        if (saved) {
            try {
                const savedAchievements = JSON.parse(saved);
                savedAchievements.forEach(savedAchievement => {
                    const achievement = this.achievements.find(a => a.id === savedAchievement.id);
                    if (achievement) {
                        achievement.unlocked = savedAchievement.unlocked;
                        achievement.unlockedDate = savedAchievement.unlockedDate ? new Date(savedAchievement.unlockedDate) : null;
                    }
                });
            } catch (e) {
                console.error('Error loading pet achievements:', e);
            }
        }
    }
    
    renderAchievementsPanel() {
        const panel = document.createElement('div');
        panel.className = 'pet-achievements-panel';
        panel.style.backgroundColor = 'white';
        panel.style.border = '1px solid #ddd';
        panel.style.borderRadius = '5px';
        panel.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        panel.style.padding = '15px';
        panel.style.width = '300px';
        panel.style.maxHeight = '400px';
        panel.style.overflowY = 'auto';
        
        // Add header
        const header = document.createElement('h3');
        header.textContent = 'Pet Achievements';
        header.style.borderBottom = '1px solid #eee';
        header.style.paddingBottom = '10px';
        header.style.marginTop = '0';
        panel.appendChild(header);
        
        // Add achievements list
        const list = document.createElement('div');
        this.achievements.forEach(achievement => {
            const item = document.createElement('div');
            item.style.display = 'flex';
            item.style.alignItems = 'center';
            item.style.padding = '8px';
            item.style.borderBottom = '1px solid #eee';
            item.style.opacity = achievement.unlocked ? '1' : '0.5';
            
            const icon = document.createElement('div');
            icon.textContent = achievement.unlocked ? achievement.icon : '🔒';
            icon.style.fontSize = '24px';
            icon.style.marginRight = '10px';
            
            const info = document.createElement('div');
            const name = document.createElement('div');
            name.textContent = achievement.name;
            name.style.fontWeight = 'bold';
            
            const desc = document.createElement('div');
            desc.textContent = achievement.description;
            desc.style.fontSize = '12px';
            desc.style.color = '#666';
            
            info.appendChild(name);
            info.appendChild(desc);
            
            item.appendChild(icon);
            item.appendChild(info);
            list.appendChild(item);
        });
        
        panel.appendChild(list);
        return panel;
    }
}

// Export the PetAchievements class
export default PetAchievements;