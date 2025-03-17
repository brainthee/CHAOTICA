// pet-main.js - Main module for integrating all virtual pet features

// Import the core pet module and extensions
import VirtualPet from './virtual-pet.js';
import PetAchievements from './pet-achievements.js';
import PetCustomization from './pet-customisation.js';
import PetStatistics from './pet-stats.js';
import PetIntegration from './pet-integration.js';
import PetUI from './pet-ui.js';

/**
 * Create and initialize a virtual pet with all extended features
 * @param {Object} options - Configuration options for the pet
 * @returns {Object} - The fully configured pet instance with all extensions
 */
function createPet(options = {}) {
    // Create the base pet instance
    const pet = new VirtualPet(options);
    
    // Add extensions
    pet.achievements = new PetAchievements(pet);
    pet.customization = new PetCustomization(pet);
    pet.statistics = new PetStatistics(pet);
    pet.integration = new PetIntegration(pet, {
        // Configure integration options
        syncWithServer: options.syncWithServer || false,
        loginReward: options.loginReward !== false,
        taskCompletionReward: options.taskCompletionReward !== false,
        petProgressBar: options.petProgressBar !== false,
        engagementTracking: options.engagementTracking !== false
    });
    
    // Add UI functionality
    pet.ui = new PetUI(pet);
    
    // Extend the menu with additional options
    pet.ui.extendPetMenu();
    
    // Add security tips integration for pentesting app
    pet.integration.addSecurityTips();
    
    // Apply any saved customizations
    pet.customization.applyCustomization();
    
    // Initialize achievements
    pet.achievements.checkAchievements();
    
    return pet;
}

// Function to initialize the pet on page load
function initPet() {
    // Get user preferences from Django
    const petName = window.petConfig?.name || 'Bitsy';
    const petPosition = window.petConfig?.position || 'bottom-right';
    const petSize = window.petConfig?.size || 'medium';
    const petEnabled = window.petConfig?.enabled !== false;
    
    // Only create the pet if it's enabled
    if (petEnabled) {
        const pet = createPet({
            petName,
            position: petPosition,
            size: petSize,
            syncWithServer: window.petConfig?.syncWithServer || false
        });
        
        // Make the pet globally accessible for debugging
        window.petInstance = pet;
        
        return pet;
    }
    
    return null;
}

// Auto-initialize on page load if in browser environment
if (typeof window !== 'undefined') {
    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPet);
    } else {
        initPet();
    }
}

// Export functions for manual initialization
export { createPet, initPet };
export default createPet;