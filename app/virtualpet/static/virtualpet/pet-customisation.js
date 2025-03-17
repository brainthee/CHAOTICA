// pet-customization.js
class PetCustomization {
    constructor(pet) {
        this.pet = pet;
        this.colors = {
            body: this.pet.options.bodyColor || '#98FB98',
            eyes: this.pet.options.eyesColor || '#000000',
            accessories: []
        };
        
        // Available accessories
        this.availableAccessories = [
            { id: 'hat', name: 'Hat', svg: '<path d="M30,40 L70,40 L65,20 L35,20 Z" fill="#ff0000" />' },
            { id: 'glasses', name: 'Glasses', svg: '<path d="M35,45 C35,40 40,40 40,45 C40,50 35,50 35,45 Z M60,45 C60,40 65,40 65,45 C65,50 60,50 60,45 Z M35,45 L60,45" fill="none" stroke="#000000" stroke-width="2" />' },
            { id: 'bow', name: 'Bow Tie', svg: '<path d="M45,60 L55,60 L50,65 Z" fill="#ff00ff" />' },
            { id: 'security', name: 'Security Badge', svg: '<rect x="43" y="60" width="14" height="18" rx="2" fill="#3366cc" /><rect x="46" y="64" width="8" height="6" fill="#ffffff" /><circle cx="50" cy="76" r="2" fill="#ffffff" />' }
        ];
        
        // Load saved customization
        this.loadCustomization();
    }
    
    setBodyColor(color) {
        this.colors.body = color;
        this.saveCustomization();
        this.pet.updatePetAppearance();
    }
    
    setEyesColor(color) {
        this.colors.eyes = color;
        this.saveCustomization();
        this.pet.updatePetAppearance();
    }
    
    addAccessory(accessoryId) {
        const accessory = this.availableAccessories.find(a => a.id === accessoryId);
        if (accessory && !this.hasAccessory(accessoryId)) {
            this.colors.accessories.push(accessoryId);
            this.saveCustomization();
            this.pet.updatePetAppearance();
        }
    }
    
    removeAccessory(accessoryId) {
        const index = this.colors.accessories.indexOf(accessoryId);
        if (index !== -1) {
            this.colors.accessories.splice(index, 1);
            this.saveCustomization();
            this.pet.updatePetAppearance();
        }
    }
    
    hasAccessory(accessoryId) {
        return this.colors.accessories.includes(accessoryId);
    }
    
    getAccessorySvg() {
        let svg = '';
        this.colors.accessories.forEach(accessoryId => {
            const accessory = this.availableAccessories.find(a => a.id === accessoryId);
            if (accessory) {
                svg += accessory.svg;
            }
        });
        return svg;
    }
    
    saveCustomization() {
        localStorage.setItem('petCustomization', JSON.stringify(this.colors));
    }
    
    loadCustomization() {
        const saved = localStorage.getItem('petCustomization');
        if (saved) {
            try {
                const savedColors = JSON.parse(saved);
                this.colors = {
                    ...this.colors,
                    ...savedColors
                };
            } catch (e) {
                console.error('Error loading pet customization:', e);
            }
        }
    }
    
    renderCustomizationPanel() {
        const panel = document.createElement('div');
        panel.className = 'pet-customization-panel';
        panel.style.backgroundColor = 'white';
        panel.style.border = '1px solid #ddd';
        panel.style.borderRadius = '5px';
        panel.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        panel.style.padding = '15px';
        panel.style.width = '300px';
        
        // Add header
        const header = document.createElement('h3');
        header.textContent = 'Customize Your Pet';
        header.style.borderBottom = '1px solid #eee';
        header.style.paddingBottom = '10px';
        header.style.marginTop = '0';
        panel.appendChild(header);
        
        // Body color picker
        const bodyColorDiv = document.createElement('div');
        bodyColorDiv.style.marginBottom = '10px';
        
        const bodyColorLabel = document.createElement('label');
        bodyColorLabel.textContent = 'Body Color: ';
        bodyColorLabel.style.display = 'block';
        bodyColorLabel.style.marginBottom = '5px';
        
        const bodyColorInput = document.createElement('input');
        bodyColorInput.type = 'color';
        bodyColorInput.value = this.colors.body;
        bodyColorInput.style.width = '100%';
        bodyColorInput.addEventListener('input', () => {
            this.setBodyColor(bodyColorInput.value);
        });
        
        bodyColorDiv.appendChild(bodyColorLabel);
        bodyColorDiv.appendChild(bodyColorInput);
        panel.appendChild(bodyColorDiv);
        
        // Eye color picker
        const eyeColorDiv = document.createElement('div');
        eyeColorDiv.style.marginBottom = '15px';
        
        const eyeColorLabel = document.createElement('label');
        eyeColorLabel.textContent = 'Eye Color: ';
        eyeColorLabel.style.display = 'block';
        eyeColorLabel.style.marginBottom = '5px';
        
        const eyeColorInput = document.createElement('input');
        eyeColorInput.type = 'color';
        eyeColorInput.value = this.colors.eyes;
        eyeColorInput.style.width = '100%';
        eyeColorInput.addEventListener('input', () => {
            this.setEyesColor(eyeColorInput.value);
        });
        
        eyeColorDiv.appendChild(eyeColorLabel);
        eyeColorDiv.appendChild(eyeColorInput);
        panel.appendChild(eyeColorDiv);
        
        // Accessories
        const accessoriesDiv = document.createElement('div');
        
        const accessoriesLabel = document.createElement('label');
        accessoriesLabel.textContent = 'Accessories: ';
        accessoriesLabel.style.display = 'block';
        accessoriesLabel.style.marginBottom = '5px';
        
        accessoriesDiv.appendChild(accessoriesLabel);
        
        this.availableAccessories.forEach(accessory => {
            const accessoryDiv = document.createElement('div');
            accessoryDiv.style.display = 'flex';
            accessoryDiv.style.alignItems = 'center';
            accessoryDiv.style.marginBottom = '5px';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `accessory-${accessory.id}`;
            checkbox.checked = this.hasAccessory(accessory.id);
            checkbox.style.marginRight = '5px';
            checkbox.addEventListener('change', () => {
                if (checkbox.checked) {
                    this.addAccessory(accessory.id);
                } else {
                    this.removeAccessory(accessory.id);
                }
            });
            
            const label = document.createElement('label');
            label.htmlFor = `accessory-${accessory.id}`;
            label.textContent = accessory.name;
            
            accessoryDiv.appendChild(checkbox);
            accessoryDiv.appendChild(label);
            accessoriesDiv.appendChild(accessoryDiv);
        });
        
        panel.appendChild(accessoriesDiv);
        
        // Preview section
        const previewDiv = document.createElement('div');
        previewDiv.style.marginTop = '15px';
        previewDiv.style.textAlign = 'center';
        
        const previewLabel = document.createElement('label');
        previewLabel.textContent = 'Preview: ';
        previewLabel.style.display = 'block';
        previewLabel.style.marginBottom = '10px';
        
        const previewSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        previewSvg.setAttribute('width', '100');
        previewSvg.setAttribute('height', '100');
        previewSvg.setAttribute('viewBox', '0 0 100 100');
        
        // Draw pet with current customization
        const body = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        body.setAttribute('cx', '50');
        body.setAttribute('cy', '60');
        body.setAttribute('r', '30');
        body.setAttribute('fill', this.colors.body);
        previewSvg.appendChild(body);
        
        // Eyes
        const leftEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        leftEye.setAttribute('cx', '40');
        leftEye.setAttribute('cy', '50');
        leftEye.setAttribute('r', '5');
        leftEye.setAttribute('fill', this.colors.eyes);
        previewSvg.appendChild(leftEye);
        
        const rightEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        rightEye.setAttribute('cx', '60');
        rightEye.setAttribute('cy', '50');
        rightEye.setAttribute('r', '5');
        rightEye.setAttribute('fill', this.colors.eyes);
        previewSvg.appendChild(rightEye);
        
        // Mouth
        const mouth = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        mouth.setAttribute('d', 'M40,70 Q50,75 60,70');
        mouth.setAttribute('stroke', 'black');
        mouth.setAttribute('stroke-width', '2');
        mouth.setAttribute('fill', 'none');
        previewSvg.appendChild(mouth);
        
        // Add accessories (if any)
        if (this.colors.accessories.length > 0) {
            const accessoriesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            accessoriesGroup.innerHTML = this.getAccessorySvg();
            previewSvg.appendChild(accessoriesGroup);
        }
        
        previewDiv.appendChild(previewLabel);
        previewDiv.appendChild(previewSvg);
        panel.appendChild(previewDiv);
        
        // Save button
        const saveButton = document.createElement('button');
        saveButton.textContent = 'Apply Changes';
        saveButton.style.marginTop = '15px';
        saveButton.style.padding = '8px 15px';
        saveButton.style.backgroundColor = '#4CAF50';
        saveButton.style.color = 'white';
        saveButton.style.border = 'none';
        saveButton.style.borderRadius = '4px';
        saveButton.style.cursor = 'pointer';
        saveButton.style.width = '100%';
        saveButton.addEventListener('click', () => {
            this.saveCustomization();
            this.pet.updatePetAppearance();
            panel.remove();
        });
        
        panel.appendChild(saveButton);
        
        return panel;
    }
    
    // Apply customization to the pet's appearance
    applyCustomization() {
        // Called by the VirtualPet class to apply custom colors and accessories
        if (this.pet.svgElement) {
            // Update body color
            const bodyElements = this.pet.svgElement.querySelectorAll('circle[cx="50"][cy="60"]');
            bodyElements.forEach(el => {
                el.setAttribute('fill', this.colors.body);
            });
            
            // Update eye color
            const eyeElements = this.pet.svgElement.querySelectorAll('circle[cx="40"][cy="50"], circle[cx="60"][cy="50"]');
            eyeElements.forEach(el => {
                el.setAttribute('fill', this.colors.eyes);
            });
            
            // Add accessories
            const accessoriesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            accessoriesGroup.class = 'pet-accessories';
            accessoriesGroup.innerHTML = this.getAccessorySvg();
            this.pet.svgElement.appendChild(accessoriesGroup);
        }
    }
}

// Export the PetCustomization class
export default PetCustomization;