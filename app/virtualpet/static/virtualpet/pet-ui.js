// pet-ui.js - UI components and interactions for the virtual pet

class PetUI {
    constructor(pet) {
        this.pet = pet;
        this.menuExtended = false;
    }
    
    // Extend the pet menu with additional options
    extendPetMenu() {
        // If menu has already been extended, don't do it again
        if (this.menuExtended) return;
        
        // Get the menu element
        const menuElement = this.pet.menuElement;
        if (!menuElement) return;
        
        // Add a divider
        const divider = document.createElement('div');
        divider.style.width = '100%';
        divider.style.height = '1px';
        divider.style.backgroundColor = '#ddd';
        divider.style.margin = '5px 0';
        menuElement.appendChild(divider);
        
        // Add achievements button
        this.addMenuButton(menuElement, '🏆 Achievements', () => this.showAchievements());
        
        // Add customize button
        this.addMenuButton(menuElement, '✨ Customize', () => this.showCustomization());
        
        // Add stats button
        this.addMenuButton(menuElement, '📊 Statistics', () => this.showStatistics());
        
        // Add team ranking button (if server-side enabled)
        if (this.pet.options.syncWithServer) {
            this.addMenuButton(menuElement, '👥 Team Pets', () => this.showTeamRanking());
        }
        
        this.menuExtended = true;
    }
    
    // Helper to add a button to the menu
    addMenuButton(menuElement, text, clickHandler) {
        const button = document.createElement('button');
        button.className = 'virtual-pet-action';
        button.style.margin = '3px';
        button.style.padding = '5px 10px';
        button.style.border = 'none';
        button.style.borderRadius = '3px';
        button.style.background = '#f0f0f0';
        button.style.cursor = 'pointer';
        button.style.width = '100%';
        button.style.textAlign = 'left';
        button.textContent = text;
        
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            menuElement.style.display = 'none';
            clickHandler();
        });
        
        menuElement.appendChild(button);
        return button;
    }
    
    // Show achievements panel
    showAchievements() {
        const achievementsPanel = this.pet.achievements.renderAchievementsPanel();
        document.body.appendChild(achievementsPanel);
        
        // Position panel near the pet
        this.positionPanel(achievementsPanel);
        
        // Add close button
        this.addCloseButton(achievementsPanel);
        
        // Close when clicking outside
        this.addOutsideClickHandler(achievementsPanel);
    }
    
    // Show customization panel
    showCustomization() {
        const customizationPanel = this.pet.customization.renderCustomizationPanel();
        document.body.appendChild(customizationPanel);
        
        // Position panel near the pet
        this.positionPanel(customizationPanel);
        
        // Close when clicking outside
        this.addOutsideClickHandler(customizationPanel);
    }
    
    // Show statistics panel
    showStatistics() {
        const statsPanel = this.pet.statistics.renderStatsPanel();
        document.body.appendChild(statsPanel);
        
        // Position panel near the pet
        this.positionPanel(statsPanel);
        
        // Add export button
        const exportButton = document.createElement('button');
        exportButton.textContent = 'Export Stats';
        exportButton.style.marginTop = '10px';
        exportButton.style.marginRight = '5px';
        exportButton.style.padding = '5px 10px';
        exportButton.style.border = 'none';
        exportButton.style.borderRadius = '3px';
        exportButton.style.backgroundColor = '#4CAF50';
        exportButton.style.color = 'white';
        exportButton.style.cursor = 'pointer';
        exportButton.addEventListener('click', () => this.pet.statistics.exportStatsCSV());
        statsPanel.appendChild(exportButton);
        
        // Add close button
        this.addCloseButton(statsPanel);
        
        // Close when clicking outside
        this.addOutsideClickHandler(statsPanel);
    }
    
    // Show team ranking panel
    showTeamRanking() {
        const teamPanel = document.createElement('div');
        teamPanel.className = 'pet-team-panel';
        teamPanel.style.backgroundColor = 'white';
        teamPanel.style.border = '1px solid #ddd';
        teamPanel.style.borderRadius = '5px';
        teamPanel.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        teamPanel.style.padding = '15px';
        teamPanel.style.width = '600px';
        teamPanel.style.maxHeight = '80vh';
        teamPanel.style.overflowY = 'auto';
        teamPanel.style.position = 'fixed';
        teamPanel.style.top = '50%';
        teamPanel.style.left = '50%';
        teamPanel.style.transform = 'translate(-50%, -50%)';
        teamPanel.style.zIndex = '10001';
        
        // Add header
        const header = document.createElement('h3');
        header.textContent = 'Team Pet Ranking';
        header.style.borderBottom = '1px solid #eee';
        header.style.paddingBottom = '10px';
        header.style.marginTop = '0';
        teamPanel.appendChild(header);
        
        // Add ranking table
        const rankingTable = this.pet.integration.createTeamPetRankingTable();
        teamPanel.appendChild(rankingTable);
        
        // Add close button
        const closeButton = document.createElement('button');
        closeButton.textContent = 'Close';
        closeButton.style.marginTop = '15px';
        closeButton.style.padding = '8px 15px';
        closeButton.style.border = 'none';
        closeButton.style.borderRadius = '4px';
        closeButton.style.backgroundColor = '#f0f0f0';
        closeButton.style.cursor = 'pointer';
        closeButton.addEventListener('click', () => teamPanel.remove());
        teamPanel.appendChild(closeButton);
        
        document.body.appendChild(teamPanel);
        
        // Add close icon in top right
        const closeIcon = document.createElement('div');
        closeIcon.innerHTML = '×';
        closeIcon.style.position = 'absolute';
        closeIcon.style.top = '10px';
        closeIcon.style.right = '15px';
        closeIcon.style.fontSize = '24px';
        closeIcon.style.cursor = 'pointer';
        closeIcon.style.color = '#999';
        closeIcon.addEventListener('click', () => teamPanel.remove());
        teamPanel.appendChild(closeIcon);
    }
    
    // Helper to position a panel near the pet
    positionPanel(panel) {
        const petRect = this.pet.container.getBoundingClientRect();
        panel.style.position = 'fixed';
        
        // Check if we should position to the left or right of the pet
        // based on available space
        const spaceOnRight = window.innerWidth - petRect.right;
        const spaceOnLeft = petRect.left;
        
        if (spaceOnRight > 320 || spaceOnRight > spaceOnLeft) {
            // Position to the right
            panel.style.top = `${petRect.top}px`;
            panel.style.left = `${petRect.right + 20}px`;
        } else {
            // Position to the left
            panel.style.top = `${petRect.top}px`;
            panel.style.left = `${petRect.left - panel.offsetWidth - 20}px`;
        }
        
        // Make sure panel is fully visible
        setTimeout(() => {
            const panelRect = panel.getBoundingClientRect();
            
            // Fix horizontal position if needed
            if (panelRect.right > window.innerWidth) {
                panel.style.left = `${window.innerWidth - panelRect.width - 10}px`;
            } else if (panelRect.left < 0) {
                panel.style.left = '10px';
            }
            
            // Fix vertical position if needed
            if (panelRect.bottom > window.innerHeight) {
                panel.style.top = `${window.innerHeight - panelRect.height - 10}px`;
            } else if (panelRect.top < 0) {
                panel.style.top = '10px';
            }
        }, 0);
    }
    
    // Helper to add a close button to a panel
    addCloseButton(panel) {
        const closeButton = document.createElement('button');
        closeButton.textContent = 'Close';
        closeButton.style.marginTop = '10px';
        closeButton.style.padding = '5px 10px';
        closeButton.style.border = 'none';
        closeButton.style.borderRadius = '3px';
        closeButton.style.backgroundColor = '#f0f0f0';
        closeButton.style.cursor = 'pointer';
        closeButton.style.width = '100%';
        closeButton.addEventListener('click', () => panel.remove());
        panel.appendChild(closeButton);
        
        return closeButton;
    }
    
    // Helper to add an outside click handler to close a panel
    addOutsideClickHandler(panel) {
        setTimeout(() => {
            const clickHandler = function(e) {
                if (!panel.contains(e.target) && e.target !== this.pet.petElement) {
                    panel.remove();
                    document.removeEventListener('click', clickHandler);
                }
            }.bind(this);
            
            document.addEventListener('click', clickHandler);
        }, 100);
    }
    
    // Create a modal dialog
    createModal(title, content, width = '400px') {
        // Create overlay
        const overlay = document.createElement('div');
        overlay.style.position = 'fixed';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '100%';
        overlay.style.height = '100%';
        overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
        overlay.style.zIndex = '10000';
        overlay.style.display = 'flex';
        overlay.style.justifyContent = 'center';
        overlay.style.alignItems = 'center';
        
        // Create modal container
        const modal = document.createElement('div');
        modal.style.backgroundColor = 'white';
        modal.style.borderRadius = '5px';
        modal.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.2)';
        modal.style.width = width;
        modal.style.maxWidth = '90%';
        modal.style.maxHeight = '90vh';
        modal.style.overflow = 'auto';
        modal.style.position = 'relative';
        
        // Add header
        const header = document.createElement('div');
        header.style.borderBottom = '1px solid #eee';
        header.style.padding = '15px';
        header.style.fontWeight = 'bold';
        header.style.fontSize = '18px';
        header.textContent = title;
        modal.appendChild(header);
        
        // Add content
        const contentContainer = document.createElement('div');
        contentContainer.style.padding = '15px';
        
        if (typeof content === 'string') {
            contentContainer.innerHTML = content;
        } else if (content instanceof HTMLElement) {
            contentContainer.appendChild(content);
        }
        
        modal.appendChild(contentContainer);
        
        // Add footer with close button
        const footer = document.createElement('div');
        footer.style.borderTop = '1px solid #eee';
        footer.style.padding = '10px 15px';
        footer.style.textAlign = 'right';
        
        const closeButton = document.createElement('button');
        closeButton.textContent = 'Close';
        closeButton.style.padding = '5px 15px';
        closeButton.style.border = 'none';
        closeButton.style.borderRadius = '3px';
        closeButton.style.backgroundColor = '#f0f0f0';
        closeButton.style.cursor = 'pointer';
        closeButton.addEventListener('click', () => overlay.remove());
        
        footer.appendChild(closeButton);
        modal.appendChild(footer);
        
        // Add close button in top right
        const closeIcon = document.createElement('div');
        closeIcon.innerHTML = '×';
        closeIcon.style.position = 'absolute';
        closeIcon.style.top = '10px';
        closeIcon.style.right = '15px';
        closeIcon.style.fontSize = '24px';
        closeIcon.style.cursor = 'pointer';
        closeIcon.style.color = '#999';
        closeIcon.addEventListener('click', () => overlay.remove());
        modal.appendChild(closeIcon);
        
        // Add to DOM
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        
        return { overlay, modal, contentContainer, closeButton };
    }
}

// Export the PetUI class
export default PetUI;