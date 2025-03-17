// virtual-pet.js
class VirtualPet {
    constructor(options = {}) {
        // Default options
        this.options = {
            container: document.body,
            petName: 'Bitsy',
            initialState: 'idle',
            position: 'bottom-right',
            size: 'medium',
            ...options
        };
        
        // Pet states and properties
        this.state = this.options.initialState;
        this.happiness = 80;
        this.energy = 100;
        this.lastFed = new Date();
        this.lastInteraction = new Date();
        
        // Create pet element
        this.createPetElement();
        
        // Start animation and state loops
        this.startAnimationLoop();
        this.startStateLoop();
        
        // Load saved state if available
        this.loadState();
        
        // Add interaction listeners
        this.addEventListeners();
    }
    
    createPetElement() {
        // Create container
        this.container = document.createElement('div');
        this.container.className = `virtual-pet-container ${this.options.position}`;
        this.container.style.position = 'fixed';
        this.container.style.zIndex = '9999';
        
        // Set position based on options
        if (this.options.position === 'bottom-right') {
            this.container.style.bottom = '20px';
            this.container.style.right = '20px';
        } else if (this.options.position === 'bottom-left') {
            this.container.style.bottom = '20px';
            this.container.style.left = '20px';
        } else if (this.options.position === 'top-right') {
            this.container.style.top = '20px';
            this.container.style.right = '20px';
        } else if (this.options.position === 'top-left') {
            this.container.style.top = '20px';
            this.container.style.left = '20px';
        }
        
        // Create pet element
        this.petElement = document.createElement('div');
        this.petElement.className = `virtual-pet ${this.options.size}`;
        this.petElement.style.width = this.getSizeInPixels();
        this.petElement.style.height = this.getSizeInPixels();
        this.petElement.style.cursor = 'pointer';
        this.petElement.style.transition = 'all 0.3s ease';
        
        // Create SVG for the pet
        this.svgElement = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        this.svgElement.setAttribute('width', '100%');
        this.svgElement.setAttribute('height', '100%');
        this.svgElement.setAttribute('viewBox', '0 0 100 100');
        this.petElement.appendChild(this.svgElement);
        
        // Create status display
        this.statusElement = document.createElement('div');
        this.statusElement.className = 'virtual-pet-status';
        this.statusElement.style.fontSize = '12px';
        this.statusElement.style.textAlign = 'center';
        this.statusElement.style.marginTop = '5px';
        
        // Create interaction menu
        this.menuElement = document.createElement('div');
        this.menuElement.className = 'virtual-pet-menu';
        this.menuElement.style.display = 'none';
        this.menuElement.style.position = 'absolute';
        this.menuElement.style.bottom = '100%';
        this.menuElement.style.left = '50%';
        this.menuElement.style.transform = 'translateX(-50%)';
        this.menuElement.style.background = 'white';
        this.menuElement.style.borderRadius = '5px';
        this.menuElement.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        this.menuElement.style.padding = '5px';
        this.menuElement.style.marginBottom = '10px';
        
        // Add interaction buttons
        const interactions = [
            { name: 'Feed', icon: '🍔', action: () => this.feed() },
            { name: 'Play', icon: '🎮', action: () => this.play() },
            { name: 'Pet', icon: '👋', action: () => this.pet() },
            { name: 'Sleep', icon: '😴', action: () => this.sleep() }
        ];
        
        interactions.forEach(interaction => {
            const button = document.createElement('button');
            button.className = 'virtual-pet-action';
            button.style.margin = '3px';
            button.style.padding = '5px 10px';
            button.style.border = 'none';
            button.style.borderRadius = '3px';
            button.style.background = '#f0f0f0';
            button.style.cursor = 'pointer';
            button.textContent = `${interaction.icon} ${interaction.name}`;
            button.addEventListener('click', interaction.action);
            this.menuElement.appendChild(button);
        });
        
        // Append elements to DOM
        this.container.appendChild(this.petElement);
        this.container.appendChild(this.statusElement);
        this.container.appendChild(this.menuElement);
        this.options.container.appendChild(this.container);
        
        // Draw initial pet state
        this.updatePetAppearance();
    }
    
    getSizeInPixels() {
        const sizes = {
            small: '40px',
            medium: '60px',
            large: '80px'
        };
        return sizes[this.options.size] || sizes.medium;
    }
    
    updatePetAppearance() {
        // Clear previous SVG content
        while (this.svgElement.firstChild) {
            this.svgElement.removeChild(this.svgElement.firstChild);
        }
        
        // Draw pet based on current state
        if (this.state === 'idle') {
            this.drawIdlePet();
        } else if (this.state === 'happy') {
            this.drawHappyPet();
        } else if (this.state === 'sleeping') {
            this.drawSleepingPet();
        } else if (this.state === 'eating') {
            this.drawEatingPet();
        } else if (this.state === 'playing') {
            this.drawPlayingPet();
        } else {
            this.drawIdlePet();
        }
        
        // Update status text
        this.updateStatusText();
    }
    
    drawIdlePet() {
        // Pet body
        const body = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        body.setAttribute('cx', '50');
        body.setAttribute('cy', '60');
        body.setAttribute('r', '30');
        body.setAttribute('fill', this.getBodyColor());
        this.svgElement.appendChild(body);
        
        // Eyes
        const leftEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        leftEye.setAttribute('cx', '40');
        leftEye.setAttribute('cy', '50');
        leftEye.setAttribute('r', '5');
        leftEye.setAttribute('fill', 'black');
        this.svgElement.appendChild(leftEye);
        
        const rightEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        rightEye.setAttribute('cx', '60');
        rightEye.setAttribute('cy', '50');
        rightEye.setAttribute('r', '5');
        rightEye.setAttribute('fill', 'black');
        this.svgElement.appendChild(rightEye);
        
        // Mouth
        const mouth = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        mouth.setAttribute('d', 'M40,70 Q50,75 60,70');
        mouth.setAttribute('stroke', 'black');
        mouth.setAttribute('stroke-width', '2');
        mouth.setAttribute('fill', 'none');
        this.svgElement.appendChild(mouth);
    }
    
    drawHappyPet() {
        // Pet body
        const body = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        body.setAttribute('cx', '50');
        body.setAttribute('cy', '60');
        body.setAttribute('r', '30');
        body.setAttribute('fill', this.getBodyColor());
        this.svgElement.appendChild(body);
        
        // Happy eyes
        const leftEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        leftEye.setAttribute('cx', '40');
        leftEye.setAttribute('cy', '50');
        leftEye.setAttribute('r', '5');
        leftEye.setAttribute('fill', 'black');
        this.svgElement.appendChild(leftEye);
        
        const rightEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        rightEye.setAttribute('cx', '60');
        rightEye.setAttribute('cy', '50');
        rightEye.setAttribute('r', '5');
        rightEye.setAttribute('fill', 'black');
        this.svgElement.appendChild(rightEye);
        
        // Big smile
        const mouth = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        mouth.setAttribute('d', 'M35,65 Q50,80 65,65');
        mouth.setAttribute('stroke', 'black');
        mouth.setAttribute('stroke-width', '2');
        mouth.setAttribute('fill', 'none');
        this.svgElement.appendChild(mouth);
    }
    
    drawSleepingPet() {
        // Pet body
        const body = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        body.setAttribute('cx', '50');
        body.setAttribute('cy', '60');
        body.setAttribute('r', '30');
        body.setAttribute('fill', this.getBodyColor());
        this.svgElement.appendChild(body);
        
        // Closed eyes (X shape)
        const leftEyeX1 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        leftEyeX1.setAttribute('x1', '35');
        leftEyeX1.setAttribute('y1', '45');
        leftEyeX1.setAttribute('x2', '45');
        leftEyeX1.setAttribute('y2', '55');
        leftEyeX1.setAttribute('stroke', 'black');
        leftEyeX1.setAttribute('stroke-width', '2');
        this.svgElement.appendChild(leftEyeX1);
        
        const leftEyeX2 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        leftEyeX2.setAttribute('x1', '45');
        leftEyeX2.setAttribute('y1', '45');
        leftEyeX2.setAttribute('x2', '35');
        leftEyeX2.setAttribute('y2', '55');
        leftEyeX2.setAttribute('stroke', 'black');
        leftEyeX2.setAttribute('stroke-width', '2');
        this.svgElement.appendChild(leftEyeX2);
        
        const rightEyeX1 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        rightEyeX1.setAttribute('x1', '55');
        rightEyeX1.setAttribute('y1', '45');
        rightEyeX1.setAttribute('x2', '65');
        rightEyeX1.setAttribute('y2', '55');
        rightEyeX1.setAttribute('stroke', 'black');
        rightEyeX1.setAttribute('stroke-width', '2');
        this.svgElement.appendChild(rightEyeX1);
        
        const rightEyeX2 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        rightEyeX2.setAttribute('x1', '65');
        rightEyeX2.setAttribute('y1', '45');
        rightEyeX2.setAttribute('x2', '55');
        rightEyeX2.setAttribute('y2', '55');
        rightEyeX2.setAttribute('stroke', 'black');
        rightEyeX2.setAttribute('stroke-width', '2');
        this.svgElement.appendChild(rightEyeX2);
        
        // Zzz
        const zzzText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        zzzText.setAttribute('x', '75');
        zzzText.setAttribute('y', '40');
        zzzText.setAttribute('font-size', '15');
        zzzText.textContent = 'Zzz';
        this.svgElement.appendChild(zzzText);
    }
    
    drawEatingPet() {
        // Pet body
        const body = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        body.setAttribute('cx', '50');
        body.setAttribute('cy', '60');
        body.setAttribute('r', '30');
        body.setAttribute('fill', this.getBodyColor());
        this.svgElement.appendChild(body);
        
        // Eyes
        const leftEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        leftEye.setAttribute('cx', '40');
        leftEye.setAttribute('cy', '50');
        leftEye.setAttribute('r', '5');
        leftEye.setAttribute('fill', 'black');
        this.svgElement.appendChild(leftEye);
        
        const rightEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        rightEye.setAttribute('cx', '60');
        rightEye.setAttribute('cy', '50');
        rightEye.setAttribute('r', '5');
        rightEye.setAttribute('fill', 'black');
        this.svgElement.appendChild(rightEye);
        
        // Open mouth
        const mouth = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        mouth.setAttribute('cx', '50');
        mouth.setAttribute('cy', '70');
        mouth.setAttribute('r', '8');
        mouth.setAttribute('fill', 'black');
        this.svgElement.appendChild(mouth);
        
        // Food item
        const food = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        food.setAttribute('cx', '50');
        food.setAttribute('cy', '85');
        food.setAttribute('r', '5');
        food.setAttribute('fill', 'brown');
        this.svgElement.appendChild(food);
    }
    
    drawPlayingPet() {
        // Jumping pet body (slightly higher position)
        const body = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        body.setAttribute('cx', '50');
        body.setAttribute('cy', '50'); // Higher position
        body.setAttribute('r', '30');
        body.setAttribute('fill', this.getBodyColor());
        this.svgElement.appendChild(body);
        
        // Excited eyes
        const leftEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        leftEye.setAttribute('cx', '40');
        leftEye.setAttribute('cy', '40');
        leftEye.setAttribute('r', '5');
        leftEye.setAttribute('fill', 'black');
        this.svgElement.appendChild(leftEye);
        
        const rightEye = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        rightEye.setAttribute('cx', '60');
        rightEye.setAttribute('cy', '40');
        rightEye.setAttribute('r', '5');
        rightEye.setAttribute('fill', 'black');
        this.svgElement.appendChild(rightEye);
        
        // Smile
        const mouth = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        mouth.setAttribute('d', 'M40,55 Q50,65 60,55');
        mouth.setAttribute('stroke', 'black');
        mouth.setAttribute('stroke-width', '2');
        mouth.setAttribute('fill', 'none');
        this.svgElement.appendChild(mouth);
        
        // Ball
        const ball = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        ball.setAttribute('cx', '75');
        ball.setAttribute('cy', '85');
        ball.setAttribute('r', '8');
        ball.setAttribute('fill', 'red');
        this.svgElement.appendChild(ball);
    }
    
    getBodyColor() {
        if (this.happiness < 30) {
            return '#A3CFEC'; // Sad blue
        } else if (this.happiness > 80) {
            return '#FFD700'; // Happy gold
        } else {
            return '#98FB98'; // Default mint green
        }
    }
    
    updateStatusText() {
        let statusText = `${this.options.petName}`;
        let emoji = '';
        
        if (this.state === 'sleeping') {
            emoji = '😴';
        } else if (this.happiness < 30) {
            emoji = '😢';
        } else if (this.happiness < 60) {
            emoji = '😐';
        } else {
            emoji = '😊';
        }
        
        this.statusElement.textContent = `${statusText} ${emoji}`;
    }
    
    startAnimationLoop() {
        // Subtle animation to make pet feel alive
        let frameCount = 0;
        
        const animate = () => {
            frameCount++;
            
            // Slight bouncing movement when not sleeping
            if (this.state !== 'sleeping') {
                const bounce = Math.sin(frameCount / 15) * 2;
                this.petElement.style.transform = `translateY(${bounce}px)`;
            }
            
            // Occasionally blink or look around
            if (frameCount % 100 === 0 && this.state !== 'sleeping') {
                this.blink();
            }
            
            requestAnimationFrame(animate);
        };
        
        animate();
    }
    
    blink() {
        // Save current state
        const currentState = this.state;
        
        // Quickly change eyes to blink
        this.svgElement.querySelectorAll('circle[cx="40"][cy="50"], circle[cx="60"][cy="50"]').forEach(eye => {
            eye.setAttribute('ry', '1');
            eye.setAttribute('height', '1');
            
            setTimeout(() => {
                eye.setAttribute('ry', '5');
                eye.setAttribute('height', '5');
            }, 200);
        });
    }
    
    startStateLoop() {
        // Update pet state every 5 seconds
        setInterval(() => {
            this.updatePetState();
        }, 5000);
        
        // Save state every minute
        setInterval(() => {
            this.saveState();
        }, 60000);
    }
    
    updatePetState() {
        const now = new Date();
        const hoursSinceLastFed = (now - this.lastFed) / (1000 * 60 * 60);
        const hoursSinceLastInteraction = (now - this.lastInteraction) / (1000 * 60 * 60);
        
        // Decrease energy and happiness over time
        if (this.state !== 'sleeping') {
            this.energy = Math.max(0, this.energy - 2);
        } else {
            this.energy = Math.min(100, this.energy + 5);
        }
        
        if (hoursSinceLastFed > 1) {
            this.happiness = Math.max(0, this.happiness - 5);
        }
        
        if (hoursSinceLastInteraction > 0.5) {
            this.happiness = Math.max(0, this.happiness - 2);
        }
        
        // Auto-sleep if energy is very low
        if (this.energy < 20 && this.state !== 'sleeping') {
            this.sleep();
        }
        
        // Wake up if energy is full
        if (this.energy >= 100 && this.state === 'sleeping') {
            this.state = 'idle';
            this.updatePetAppearance();
        }
        
        // Return to idle after action states
        if (['eating', 'playing'].includes(this.state)) {
            const stateDuration = (now - this.lastInteraction) / 1000;
            if (stateDuration > 5) {
                this.state = 'idle';
                this.updatePetAppearance();
            }
        }
        
        // Update appearance based on new state variables
        this.updatePetAppearance();
    }
    
    addEventListeners() {
        // Toggle menu on pet click
        this.petElement.addEventListener('click', () => {
            if (this.menuElement.style.display === 'none') {
                this.menuElement.style.display = 'block';
            } else {
                this.menuElement.style.display = 'none';
            }
            
            this.lastInteraction = new Date();
        });
        
        // Close menu when clicking elsewhere
        document.addEventListener('click', (e) => {
            if (!this.container.contains(e.target)) {
                this.menuElement.style.display = 'none';
            }
        });
        
        // Pet movement - allow dragging pet to new position
        let isDragging = false;
        let offsetX, offsetY;
        
        this.petElement.addEventListener('mousedown', (e) => {
            isDragging = true;
            offsetX = e.clientX - this.container.getBoundingClientRect().left;
            offsetY = e.clientY - this.container.getBoundingClientRect().top;
            this.container.style.cursor = 'grabbing';
            e.preventDefault();
        });
        
        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                this.container.style.left = (e.clientX - offsetX) + 'px';
                this.container.style.top = (e.clientY - offsetY) + 'px';
                this.container.style.right = 'auto';
                this.container.style.bottom = 'auto';
            }
        });
        
        document.addEventListener('mouseup', () => {
            isDragging = false;
            this.container.style.cursor = 'grab';
            this.savePosition();
        });
    }
    
    feed() {
        this.state = 'eating';
        this.lastFed = new Date();
        this.lastInteraction = new Date();
        this.happiness = Math.min(100, this.happiness + 10);
        this.energy = Math.min(100, this.energy + 20);
        this.menuElement.style.display = 'none';
        this.updatePetAppearance();
        
        // Return to idle after 3 seconds
        setTimeout(() => {
            if (this.state === 'eating') {
                this.state = 'idle';
                this.updatePetAppearance();
            }
        }, 3000);
    }
    
    play() {
        this.state = 'playing';
        this.lastInteraction = new Date();
        this.happiness = Math.min(100, this.happiness + 15);
        this.energy = Math.max(0, this.energy - 15);
        this.menuElement.style.display = 'none';
        this.updatePetAppearance();
        
        // Return to idle after 3 seconds
        setTimeout(() => {
            if (this.state === 'playing') {
                this.state = 'idle';
                this.updatePetAppearance();
            }
        }, 3000);
    }
    
    pet() {
        this.state = 'happy';
        this.lastInteraction = new Date();
        this.happiness = Math.min(100, this.happiness + 5);
        this.menuElement.style.display = 'none';
        this.updatePetAppearance();
        
        // Return to idle after 2 seconds
        setTimeout(() => {
            if (this.state === 'happy') {
                this.state = 'idle';
                this.updatePetAppearance();
            }
        }, 2000);
    }
    
    sleep() {
        this.state = 'sleeping';
        this.lastInteraction = new Date();
        this.menuElement.style.display = 'none';
        this.updatePetAppearance();
    }
    
    saveState() {
        const state = {
            happiness: this.happiness,
            energy: this.energy,
            lastFed: this.lastFed.toISOString(),
            lastInteraction: this.lastInteraction.toISOString(),
            state: this.state,
            position: {
                left: this.container.style.left,
                top: this.container.style.top,
                right: this.container.style.right,
                bottom: this.container.style.bottom
            }
        };
        
        localStorage.setItem('virtualPetState', JSON.stringify(state));
    }
    
    savePosition() {
        const position = {
            left: this.container.style.left,
            top: this.container.style.top,
            right: this.container.style.right,
            bottom: this.container.style.bottom
        };
        
        localStorage.setItem('virtualPetPosition', JSON.stringify(position));
    }
    
    loadState() {
        const savedState = localStorage.getItem('virtualPetState');
        const savedPosition = localStorage.getItem('virtualPetPosition');
        
        if (savedState) {
            try {
                const state = JSON.parse(savedState);
                this.happiness = state.happiness;
                this.energy = state.energy;
                this.lastFed = new Date(state.lastFed);
                this.lastInteraction = new Date(state.lastInteraction);
                this.state = state.state;
            } catch (e) {
                console.error('Error loading pet state:', e);
            }
        }
        
        if (savedPosition) {
            try {
                const position = JSON.parse(savedPosition);
                this.container.style.left = position.left || '';
                this.container.style.top = position.top || '';
                this.container.style.right = position.right || '';
                this.container.style.bottom = position.bottom || '';
            } catch (e) {
                console.error('Error loading pet position:', e);
            }
        }
    }
};
export default VirtualPet;