/**
 * Report Wizard Main Module
 * Handles the overall report builder wizard functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize step-specific components based on current wizard step
    initCurrentStep();
    
    // Initialize form validation
    initFormValidation();
    
    // Initialize conditional fields
    initConditionalFields();
});

/**
 * Initialize the appropriate component for the current wizard step
 */
function initCurrentStep() {
    const currentStep = document.querySelector('.multisteps-form__progress-btn.js-active');
    if (!currentStep) return;
    
    const stepTitle = currentStep.getAttribute('title');
    
    switch(stepTitle) {
        case 'Select Fields':
            // Check if the FieldSelector module is loaded
            if (typeof FieldSelector !== 'undefined' && typeof availableFieldsJson !== 'undefined') {
                const availableFields = typeof availableFieldsJson === 'string' ? 
                    JSON.parse(availableFieldsJson) : availableFieldsJson;
                    
                const selectedFields = typeof selectedFieldsJson === 'string' ? 
                    JSON.parse(selectedFieldsJson) : selectedFieldsJson;
                
                FieldSelector.init(availableFields, selectedFields);
                console.log("Field selector initialized via wizard.js");
            }
            break;
            
        case 'Define Filters':
            // Initialize filter builder if there's field data available
            if (typeof availableFieldsJson !== 'undefined' && typeof filtersJson !== 'undefined') {
                const fields = typeof availableFieldsJson === 'string' ? 
                    JSON.parse(availableFieldsJson) : availableFieldsJson;
                    
                const filters = typeof filtersJson === 'string' ? 
                    JSON.parse(filtersJson) : filtersJson;
                
                FilterBuilder.init(fields, filters);
            }
            break;
            
        case 'Define Sort Order':
            // Initialize sort builder if there's field data available
            if (typeof selectedFieldsJson !== 'undefined' && typeof sortOrderJson !== 'undefined') {
                const fields = typeof selectedFieldsJson === 'string' ? 
                    JSON.parse(selectedFieldsJson) : selectedFieldsJson;
                    
                const sortOrder = typeof sortOrderJson === 'string' ? 
                    JSON.parse(sortOrderJson) : sortOrderJson;
                
                SortBuilder.init(fields, sortOrder);
            }
            break;
            
        case 'Select Presentation':
            // Initialize presentation options
            initPresentationOptions();
            break;
    }
}

/**
 * Initialize form validation for the wizard
 */
function initFormValidation() {
    const form = document.getElementById('wizard-form');
    if (!form) return;
    
    form.addEventListener('submit', function(event) {
        // Check if form is valid
        if (!this.checkValidity()) {
            event.preventDefault();
            event.stopPropagation();
        }
        
        this.classList.add('was-validated');
    });
}

/**
 * Initialize conditional fields that should show/hide based on other field values
 */
function initConditionalFields() {
    const conditionalFields = document.querySelectorAll('.conditional-field');
    
    conditionalFields.forEach(field => {
        const conditionField = field.getAttribute('data-condition');
        const conditionValue = field.getAttribute('data-condition-value');
        
        if (conditionField && conditionValue) {
            const controlField = document.querySelector(`[name="${conditionField}"]`);
            
            if (controlField) {
                // Initial state
                updateConditionalField(controlField, field, conditionValue);
                
                // Add change listener
                controlField.addEventListener('change', function() {
                    updateConditionalField(this, field, conditionValue);
                });
            }
        }
    });
}

/**
 * Update conditional field visibility based on controlling field
 */
function updateConditionalField(controlField, conditionalField, requiredValue) {
    let fieldValue;
    
    // Handle different field types
    if (controlField.type === 'checkbox') {
        fieldValue = controlField.checked ? 'true' : 'false';
    } else if (controlField.type === 'radio') {
        // For radio buttons, find the checked one in the group
        const checkedRadio = document.querySelector(`[name="${controlField.name}"]:checked`);
        fieldValue = checkedRadio ? checkedRadio.value : '';
    } else {
        fieldValue = controlField.value;
    }
    
    // Show/hide based on value match
    if (fieldValue === requiredValue) {
        conditionalField.style.display = '';
    } else {
        conditionalField.style.display = 'none';
    }
}

/**
 * Initialize presentation options
 */
function initPresentationOptions() {
    const presentationType = document.querySelector('[name="presentation_type"]');
    const presentationOptions = document.querySelectorAll('.presentation-options');
    
    if (presentationType && presentationOptions.length) {
        // Initial state
        updatePresentationOptions();
        
        // Add change listener to presentation type
        const presentationRadios = document.querySelectorAll('[name="presentation_type"]');
        presentationRadios.forEach(radio => {
            radio.addEventListener('change', updatePresentationOptions);
        });
    }
}

/**
 * Update presentation options based on selected presentation type
 */
function updatePresentationOptions() {
    const selectedType = document.querySelector('[name="presentation_type"]:checked');
    const presentationOptions = document.querySelectorAll('.presentation-options');
    
    if (!selectedType) return;
    
    presentationOptions.forEach(option => {
        const forType = option.getAttribute('data-presentation');
        
        if (forType === selectedType.value) {
            option.style.display = '';
        } else {
            option.style.display = 'none';
        }
    });
}