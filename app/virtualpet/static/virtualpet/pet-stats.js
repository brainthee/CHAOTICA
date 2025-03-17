// pet-statistics.js
class PetStatistics {
    constructor(pet) {
        this.pet = pet;
        this.stats = {
            created: new Date(),
            totalFeeds: 0,
            totalPlays: 0,
            totalPets: 0,
            totalSleeps: 0,
            longestHappinessStreak: 0,
            currentHappinessStreak: 0,
            visitDays: [],
            lastVisit: null,
            pentestCompletions: 0, 
            highestHappiness: 80,
            lowestHappiness: 80,
            averageHappiness: 80
        };
        
        // Track login days
        this.trackVisit();
        
        // Load saved stats
        this.loadStats();
        
        // Set up happiness tracking
        this.startHappinessTracking();
    }
    
    trackVisit() {
        const today = new Date().toISOString().split('T')[0];
        if (!this.stats.visitDays.includes(today)) {
            this.stats.visitDays.push(today);
            
            // Check if consecutive day
            if (this.stats.lastVisit) {
                const lastVisitDate = new Date(this.stats.lastVisit);
                const yesterdayDate = new Date();
                yesterdayDate.setDate(yesterdayDate.getDate() - 1);
                const yesterday = yesterdayDate.toISOString().split('T')[0];
                
                if (this.stats.lastVisit === yesterday) {
                    this.pet.consecutiveVisitDays++;
                } else {
                    this.pet.consecutiveVisitDays = 1;
                }
            } else {
                this.pet.consecutiveVisitDays = 1;
            }
            
            this.stats.lastVisit = today;
            this.saveStats();
        }
    }
    
    incrementStat(stat) {
        if (this.stats[stat] !== undefined) {
            this.stats[stat]++;
            this.saveStats();
        }
        
        // Update pet counters
        if (stat === 'totalFeeds') {
            this.pet.feedCount = this.stats.totalFeeds;
        } else if (stat === 'totalPlays') {
            this.pet.playCount = this.stats.totalPlays;
        }
        
        this.pet.totalInteractions = 
            this.stats.totalFeeds + 
            this.stats.totalPlays + 
            this.stats.totalPets + 
            this.stats.totalSleeps;
    }
    
    recordPentestCompletion() {
        this.stats.pentestCompletions++;
        this.pet.pentestCompletions = this.stats.pentestCompletions;
        this.saveStats();
    }
    
    startHappinessTracking() {
        // Update happiness stats daily
        const checkHappiness = () => {
            // Update min/max values
            if (this.pet.happiness > this.stats.highestHappiness) {
                this.stats.highestHappiness = this.pet.happiness;
            }
            
            if (this.pet.happiness < this.stats.lowestHappiness) {
                this.stats.lowestHappiness = this.pet.happiness;
            }
            
            // Update average (simple moving average)
            this.stats.averageHappiness = (this.stats.averageHappiness * 9 + this.pet.happiness) / 10;
            
            // Update happiness streak
            this.updateHappinessStreak();
            
            this.saveStats();
        };
        
        // Check happiness every hour
        setInterval(checkHappiness, 60 * 60 * 1000);
        
        // Also check on initialization
        checkHappiness();
    }
    
    updateHappinessStreak() {
        if (this.pet.happiness >= 80) {
            this.stats.currentHappinessStreak++;
            if (this.stats.currentHappinessStreak > this.stats.longestHappinessStreak) {
                this.stats.longestHappinessStreak = this.stats.currentHappinessStreak;
            }
        } else {
            this.stats.currentHappinessStreak = 0;
        }
        this.saveStats();
    }
    
    saveStats() {
        localStorage.setItem('petStatistics', JSON.stringify(this.stats));
    }
    
    loadStats() {
        const saved = localStorage.getItem('petStatistics');
        if (saved) {
            try {
                const savedStats = JSON.parse(saved);
                this.stats = {
                    ...this.stats,
                    ...savedStats
                };
                
                // Update pet counters from stats
                this.pet.feedCount = this.stats.totalFeeds;
                this.pet.playCount = this.stats.totalPlays;
                this.pet.pentestCompletions = this.stats.pentestCompletions || 0;
                this.pet.totalInteractions = 
                    this.stats.totalFeeds + 
                    this.stats.totalPlays + 
                    this.stats.totalPets + 
                    this.stats.totalSleeps;
                    
                // Ensure consecutive days is synced
                this.pet.consecutiveVisitDays = this.stats.visitDays.length > 0 ? 
                    this.getConsecutiveDays() : 0;
            } catch (e) {
                console.error('Error loading pet statistics:', e);
            }
        }
    }
    
    getConsecutiveDays() {
        if (!this.stats.visitDays.length) return 0;
        
        // Sort days by date
        const sortedDays = [...this.stats.visitDays].sort();
        
        // Get most recent visit
        const lastDay = sortedDays[sortedDays.length - 1];
        const lastDate = new Date(lastDay);
        
        let consecutiveDays = 1;
        let currentDate = new Date(lastDate);
        
        // Count backwards to find consecutive days
        for (let i = 1; i <= sortedDays.length; i++) {
            currentDate.setDate(currentDate.getDate() - 1);
            const prevDay = currentDate.toISOString().split('T')[0];
            
            if (sortedDays.includes(prevDay)) {
                consecutiveDays++;
            } else {
                break;
            }
        }
        
        return consecutiveDays;
    }
    
    getPetAge() {
        const created = new Date(this.stats.created);
        const now = new Date();
        const diffTime = Math.abs(now - created);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return diffDays;
    }
    
    getVisitCount() {
        return this.stats.visitDays.length;
    }
    
    renderStatsPanel() {
        const panel = document.createElement('div');
        panel.className = 'pet-stats-panel';
        panel.style.backgroundColor = 'white';
        panel.style.border = '1px solid #ddd';
        panel.style.borderRadius = '5px';
        panel.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        panel.style.padding = '15px';
        panel.style.width = '300px';
        
        // Add header
        const header = document.createElement('h3');
        header.textContent = `${this.pet.options.petName}'s Statistics`;
        header.style.borderBottom = '1px solid #eee';
        header.style.paddingBottom = '10px';
        header.style.marginTop = '0';
        panel.appendChild(header);
        
        // Create stats list
        const statsList = document.createElement('ul');
        statsList.style.listStyle = 'none';
        statsList.style.padding = '0';
        
        const addStat = (label, value) => {
            const li = document.createElement('li');
            li.style.padding = '5px 0';
            li.style.borderBottom = '1px solid #eee';
            li.style.display = 'flex';
            li.style.justifyContent = 'space-between';
            
            const labelSpan = document.createElement('span');
            labelSpan.textContent = label;
            
            const valueSpan = document.createElement('span');
            valueSpan.textContent = value;
            valueSpan.style.fontWeight = 'bold';
            
            li.appendChild(labelSpan);
            li.appendChild(valueSpan);
            statsList.appendChild(li);
        };
        
        // Basic stats
        addStat('Pet Age', `${this.getPetAge()} days`);
        addStat('Total Visits', this.getVisitCount());
        addStat('Consecutive Visit Days', this.pet.consecutiveVisitDays);
        
        // Interaction stats
        addStat('Times Fed', this.stats.totalFeeds);
        addStat('Times Played', this.stats.totalPlays);
        addStat('Times Petted', this.stats.totalPets);
        addStat('Times Put to Sleep', this.stats.totalSleeps);
        
        // Happiness stats
        addStat('Current Happiness', `${Math.round(this.pet.happiness)}%`);
        addStat('Current Energy', `${Math.round(this.pet.energy)}%`);
        addStat('Average Happiness', `${Math.round(this.stats.averageHappiness)}%`);
        addStat('Highest Happiness', `${Math.round(this.stats.highestHappiness)}%`);
        addStat('Happiness Streak', `${this.stats.currentHappinessStreak} days`);
        addStat('Longest Happiness Streak', `${this.stats.longestHappinessStreak} days`);
        
        // Work-related stats
        addStat('Pentest Completions', this.stats.pentestCompletions);
        
        panel.appendChild(statsList);
        
        // Add chart (simplified)
        const chartDiv = document.createElement('div');
        chartDiv.style.marginTop = '15px';
        chartDiv.style.height = '100px';
        chartDiv.style.border = '1px solid #eee';
        chartDiv.style.position = 'relative';
        chartDiv.style.overflow = 'hidden';
        
        // Simple happiness sparkline chart
        const sparkline = document.createElement('div');
        sparkline.style.position = 'absolute';
        sparkline.style.bottom = '0';
        sparkline.style.left = '0';
        sparkline.style.width = '100%';
        sparkline.style.height = '100%';
        sparkline.style.display = 'flex';
        sparkline.style.alignItems = 'flex-end';
        
        // Generate some sample data points based on min/max/avg happiness
        const dataPoints = 24;
        let prevValue = this.pet.happiness;
        
        for (let i = 0; i < dataPoints; i++) {
            const bar = document.createElement('div');
            bar.style.flex = '1';
            bar.style.marginRight = '1px';
            
            // Generate a realistic looking chart with values that trend towards the average
            const variance = Math.random() * 10 - 5;
            let value = Math.min(100, Math.max(0, 
                prevValue * 0.8 + this.stats.averageHappiness * 0.2 + variance));
            prevValue = value;
            
            bar.style.height = `${value}%`;
            bar.style.backgroundColor = value < 30 ? '#f44336' : 
                                          value < 70 ? '#ff9800' : '#4caf50';
            
            sparkline.appendChild(bar);
        }
        
        // Add a label
        const chartLabel = document.createElement('div');
        chartLabel.textContent = 'Happiness Trend (24h)';
        chartLabel.style.fontSize = '12px';
        chartLabel.style.marginBottom = '5px';
        
        chartDiv.appendChild(chartLabel);
        chartDiv.appendChild(sparkline);
        panel.appendChild(chartDiv);
        
        return panel;
    }
    
    // Generate CSV report of pet stats
    exportStatsCSV() {
        const headers = [
            'Stat', 'Value'
        ].join(',');
        
        const rows = [
            ['Pet Name', this.pet.options.petName],
            ['Created Date', this.stats.created],
            ['Age (Days)', this.getPetAge()],
            ['Total Visits', this.getVisitCount()],
            ['Consecutive Visit Days', this.pet.consecutiveVisitDays],
            ['Times Fed', this.stats.totalFeeds],
            ['Times Played', this.stats.totalPlays],
            ['Times Petted', this.stats.totalPets],
            ['Times Put to Sleep', this.stats.totalSleeps],
            ['Current Happiness', Math.round(this.pet.happiness)],
            ['Current Energy', Math.round(this.pet.energy)],
            ['Average Happiness', Math.round(this.stats.averageHappiness)],
            ['Highest Happiness', Math.round(this.stats.highestHappiness)],
            ['Lowest Happiness', Math.round(this.stats.lowestHappiness)],
            ['Current Happiness Streak', this.stats.currentHappinessStreak],
            ['Longest Happiness Streak', this.stats.longestHappinessStreak],
            ['Pentest Completions', this.stats.pentestCompletions]
        ].map(row => row.join(',')).join('\n');
        
        const csv = `${headers}\n${rows}`;
        
        // Create downloadable link
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.setAttribute('hidden', '');
        a.setAttribute('href', url);
        a.setAttribute('download', `${this.pet.options.petName}_stats_${new Date().toISOString().split('T')[0]}.csv`);
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
}

// Export the PetStatistics class
export default PetStatistics;