/**
 * Filter Builder Module
 * Handles creation of filter conditions for reports
 */

const FilterBuilder = (function() {
    // Private variables
    let availableFieldsData = [];
    
    // Private functions
    function createFilterBuilderUI(container, fields, existingFilters) {
        // Store fields data for later use
        availableFieldsData = fields;
        
        // Create the filter builder components
        const builderContainer = document.createElement('div');
        builderContainer.className = 'filter-builder-container';
        
        // Filter groups container
        const groupsContainer = document.createElement('div');
        groupsContainer.className = 'filter-groups-container';
        groupsContainer.id = 'filter-groups';
        
        // Add initial group if none exist
        if (!existingFilters || existingFilters.length === 0) {
            addFilterGroup(groupsContainer);
        } else {
            // Add existing filter groups
            existingFilters.forEach(group => {
                addFilterGroup(groupsContainer, group);
            });
        }
        
        // Add group button
        const addGroupBtn = document.createElement('button');
        addGroupBtn.type = 'button';
        addGroupBtn.className = 'btn btn-sm btn-outline-primary mt-3';
        addGroupBtn.innerHTML = '<i class="fas fa-plus"></i> Add Filter Group';
        addGroupBtn.addEventListener('click', function() {
            addFilterGroup(groupsContainer);
        });
        
        builderContainer.appendChild(groupsContainer);
        builderContainer.appendChild(addGroupBtn);
        
        container.appendChild(builderContainer);
    }
    
    function addFilterGroup(container, existingGroup) {
        const groupId = 'filter-group-' + Date.now();
        
        const groupElement = document.createElement('div');
        groupElement.className = 'filter-group card mb-3';
        groupElement.id = groupId;
        
        const groupHeader = document.createElement('div');
        groupHeader.className = 'card-header d-flex justify-content-between align-items-center';
        
        const groupOperator = document.createElement('select');
        groupOperator.className = 'form-select form-select-sm w-auto group-operator';
        groupOperator.innerHTML = `
            <option value="AND" ${existingGroup && existingGroup.operator === 'AND' ? 'selected' : ''}>AND</option>
            <option value="OR" ${existingGroup && existingGroup.operator === 'OR' ? 'selected' : ''}>OR</option>
        `;
        
        const groupTitle = document.createElement('span');
        groupTitle.textContent = 'Filter Group';
        
        const deleteGroupBtn = document.createElement('button');
        deleteGroupBtn.type = 'button';
        deleteGroupBtn.className = 'btn btn-sm btn-outline-danger';
        deleteGroupBtn.innerHTML = '<i class="fas fa-trash"></i>';
        deleteGroupBtn.addEventListener('click', function() {
            if (document.querySelectorAll('.filter-group').length > 1) {
                groupElement.remove();
            } else {
                alert('You must have at least one filter group.');
            }
        });
        
        groupHeader.appendChild(groupTitle);
        groupHeader.appendChild(groupOperator);
        groupHeader.appendChild(deleteGroupBtn);
        
        const groupBody = document.createElement('div');
        groupBody.className = 'card-body';
        
        const conditionsContainer = document.createElement('div');
        conditionsContainer.className = 'filter-conditions-container';
        
        // Add existing conditions if any
        if (existingGroup && existingGroup.conditions) {
            existingGroup.conditions.forEach(condition => {
                addFilterCondition(conditionsContainer, condition);
            });
        } else {
            // Add an initial empty condition
            addFilterCondition(conditionsContainer);
        }
        
        // Add condition button
        const addConditionBtn = document.createElement('button');
        addConditionBtn.type = 'button';
        addConditionBtn.className = 'btn btn-sm btn-outline-secondary mt-2';
        addConditionBtn.innerHTML = '<i class="fas fa-plus"></i> Add Condition';
        addConditionBtn.addEventListener('click', function() {
            addFilterCondition(conditionsContainer);
        });
        
        groupBody.appendChild(conditionsContainer);
        groupBody.appendChild(addConditionBtn);
        
        groupElement.appendChild(groupHeader);
        groupElement.appendChild(groupBody);
        
        container.appendChild(groupElement);
    }
    
    function addFilterCondition(container, existingCondition) {
        const conditionId = 'filter-condition-' + Date.now();
        
        const conditionElement = document.createElement('div');
        conditionElement.className = 'filter-condition row mb-2';
        conditionElement.id = conditionId;
        
        // Field selector
        const fieldCol = document.createElement('div');
        fieldCol.className = 'col-md-4';
        
        const fieldSelect = document.createElement('select');
        fieldSelect.className = 'form-select form-select-sm field-select';
        
        // Populate fields from available fields data
        fieldSelect.innerHTML = '<option value="">Select Field</option>';
        availableFieldsData.forEach(field => {
            fieldSelect.innerHTML += `<option value="${field.name}" data-type="${field.type}">${field.label}</option>`;
        });
        
        // Add field change handler to update operators based on field type
        fieldSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            const fieldType = selectedOption.getAttribute('data-type');
            updateOperatorOptions(operatorSelect, fieldType);
            
            // Show/hide value input based on operator
            updateValueInput(valueCol, operatorSelect.value, fieldType);
        });
        
        // Operator selector
        const operatorCol = document.createElement('div');
        operatorCol.className = 'col-md-3';
        
        const operatorSelect = document.createElement('select');
        operatorSelect.className = 'form-select form-select-sm operator-select';
        
        // Default operators (will be updated based on field type)
        operatorSelect.innerHTML = `
            <option value="equals">Equals</option>
            <option value="not_equals">Not Equals</option>
            <option value="contains">Contains</option>
            <option value="starts_with">Starts With</option>
            <option value="ends_with">Ends With</option>
            <option value="greater_than">Greater Than</option>
            <option value="less_than">Less Than</option>
            <option value="is_null">Is Empty</option>
            <option value="is_not_null">Is Not Empty</option>
        `;
        
        // Add operator change handler to update value input
        operatorSelect.addEventListener('change', function() {
            const fieldType = getFieldTypeFromSelect(fieldSelect);
            updateValueInput(valueCol, this.value, fieldType);
        });
        
        // Value input
        const valueCol = document.createElement('div');
        valueCol.className = 'col-md-4';
        
        const valueInput = document.createElement('input');
        valueInput.type = 'text';
        valueInput.className = 'form-control form-control-sm value-input';
        valueInput.placeholder = 'Value';
        
        // Prompt checkbox
        const promptCheckbox = document.createElement('div');
        promptCheckbox.className = 'form-check mt-1';
        promptCheckbox.innerHTML = `
            <input class="form-check-input prompt-checkbox" type="checkbox" id="prompt-${conditionId}">
            <label class="form-check-label" for="prompt-${conditionId}">Prompt at runtime</label>
        `;
        
        // Prompt text input (hidden initially)
        const promptTextContainer = document.createElement('div');
        promptTextContainer.className = 'prompt-text-container mt-1 d-none';
        
        const promptInput = document.createElement('input');
        promptInput.type = 'text';
        promptInput.className = 'form-control form-control-sm prompt-text';
        promptInput.placeholder = 'Enter prompt text...';
        
        promptTextContainer.appendChild(promptInput);
        
        // Show/hide prompt text when checkbox changes
        promptCheckbox.querySelector('input').addEventListener('change', function() {
            if (this.checked) {
                promptTextContainer.classList.remove('d-none');
            } else {
                promptTextContainer.classList.add('d-none');
            }
        });
        
        valueCol.appendChild(valueInput);
        valueCol.appendChild(promptCheckbox);
        valueCol.appendChild(promptTextContainer);
        
        // Delete button
        const deleteCol = document.createElement('div');
        deleteCol.className = 'col-md-1';
        
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'btn btn-sm btn-outline-danger';
        deleteBtn.innerHTML = '<i class="fas fa-times"></i>';
        deleteBtn.addEventListener('click', function() {
            conditionElement.remove();
        });
        
        // Assemble the condition
        fieldCol.appendChild(fieldSelect);
        operatorCol.appendChild(operatorSelect);
        deleteCol.appendChild(deleteBtn);
        
        conditionElement.appendChild(fieldCol);
        conditionElement.appendChild(operatorCol);
        conditionElement.appendChild(valueCol);
        conditionElement.appendChild(deleteCol);
        
        // Set existing values if provided
        if (existingCondition) {
            fieldSelect.value = existingCondition.field || '';
            
            // Trigger field change to update operators
            const event = new Event('change');
            fieldSelect.dispatchEvent(event);
            
            operatorSelect.value = existingCondition.operator || '';
            valueInput.value = existingCondition.value || '';
            
            // Set prompt if available
            if (existingCondition.prompt) {
                promptCheckbox.querySelector('input').checked = true;
                promptInput.value = existingCondition.prompt;
                promptTextContainer.classList.remove('d-none');
            }
        }
        
        container.appendChild(conditionElement);
    }
    
    function updateOperatorOptions(operatorSelect, fieldType) {
        // Clear existing options
        operatorSelect.innerHTML = '';
        
        // Common operators for all types
        const commonOperators = [
            { value: 'equals', label: 'Equals' },
            { value: 'not_equals', label: 'Not Equals' },
            { value: 'is_null', label: 'Is Empty' },
            { value: 'is_not_null', label: 'Is Not Empty' }
        ];
        
        // Type-specific operators
        let typeOperators = [];
        
        switch(fieldType) {
            case 'string':
                typeOperators = [
                    { value: 'contains', label: 'Contains' },
                    { value: 'not_contains', label: 'Does Not Contain' },
                    { value: 'starts_with', label: 'Starts With' },
                    { value: 'ends_with', label: 'Ends With' }
                ];
                break;
                
            case 'number':
                typeOperators = [
                    { value: 'greater_than', label: 'Greater Than' },
                    { value: 'less_than', label: 'Less Than' },
                    { value: 'greater_than_or_equal', label: 'Greater Than or Equal' },
                    { value: 'less_than_or_equal', label: 'Less Than or Equal' }
                ];
                break;
                
            case 'date':
            case 'datetime':
                typeOperators = [
                    { value: 'greater_than', label: 'After' },
                    { value: 'less_than', label: 'Before' },
                    { value: 'greater_than_or_equal', label: 'On or After' },
                    { value: 'less_than_or_equal', label: 'On or Before' },
                    { value: 'between', label: 'Between' },
                    { value: 'today', label: 'Today' },
                    { value: 'yesterday', label: 'Yesterday' },
                    { value: 'this_week', label: 'This Week' },
                    { value: 'this_month', label: 'This Month' },
                    { value: 'this_year', label: 'This Year' }
                ];
                break;
                
            case 'boolean':
                typeOperators = [];  // Only use common operators for boolean
                break;
        }
        
        // Combine operators
        const operators = [...commonOperators, ...typeOperators];
        
        // Add options to select
        operators.forEach(op => {
            const option = document.createElement('option');
            option.value = op.value;
            option.textContent = op.label;
            operatorSelect.appendChild(option);
        });
    }
    
    function updateValueInput(valueCol, operator, fieldType) {
        // Get the value input
        const valueInput = valueCol.querySelector('.value-input');
        
        // Hide input for operators that don't need a value
        if (['is_null', 'is_not_null', 'today', 'yesterday', 'this_week', 'this_month', 'this_year'].includes(operator)) {
            valueInput.style.display = 'none';
        } else {
            valueInput.style.display = '';
            
            // Update input type based on field type
            switch(fieldType) {
                case 'date':
                    valueInput.type = 'date';
                    break;
                    
                case 'datetime':
                    valueInput.type = 'datetime-local';
                    break;
                    
                case 'number':
                    valueInput.type = 'number';
                    break;
                    
                case 'boolean':
                    // Replace input with select for boolean
                    if (valueInput.tagName !== 'SELECT') {
                        const boolSelect = document.createElement('select');
                        boolSelect.className = 'form-select form-select-sm value-input';
                        boolSelect.innerHTML = `
                            <option value="true">True</option>
                            <option value="false">False</option>
                        `;
                        valueInput.parentNode.replaceChild(boolSelect, valueInput);
                    }
                    break;
                    
                default:
                    valueInput.type = 'text';
            }
        }
    }
    
    function getFieldTypeFromSelect(fieldSelect) {
        const selectedOption = fieldSelect.options[fieldSelect.selectedIndex];
        return selectedOption ? selectedOption.getAttribute('data-type') : 'string';
    }
    
    function getFilterConditions() {
        const groups = [];
        
        // Get all filter groups
        document.querySelectorAll('.filter-group').forEach(groupElement => {
            const operator = groupElement.querySelector('.group-operator').value;
            const conditions = [];
            
            // Get all conditions in this group
            groupElement.querySelectorAll('.filter-condition').forEach(conditionElement => {
                const fieldSelect = conditionElement.querySelector('.field-select');
                const operatorSelect = conditionElement.querySelector('.operator-select');
                const valueInput = conditionElement.querySelector('.value-input');
                const promptCheckbox = conditionElement.querySelector('.prompt-checkbox');
                const promptText = conditionElement.querySelector('.prompt-text');
                
                // Skip incomplete conditions
                if (!fieldSelect.value) return;
                
                const condition = {
                    field: fieldSelect.value,
                    operator: operatorSelect.value,
                    value: valueInput ? valueInput.value : null
                };
                
                // Add prompt if checked
                if (promptCheckbox.checked && promptText.value) {
                    condition.prompt = promptText.value;
                    condition.prompt_id = 'prompt_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
                }
                
                conditions.push(condition);
            });
            
            // Only add group if it has conditions
            if (conditions.length > 0) {
                groups.push({
                    operator: operator,
                    conditions: conditions
                });
            }
        });
        
        return groups;
    }
    
    function setupFormSubmission() {
        // Handle form submission to include filters
        const form = document.getElementById('wizard-form');
        if (!form) return;
        
        form.addEventListener('submit', function(e) {
            // Get filter data from the builder
            const filterData = getFilterConditions();
            
            // Add it as a hidden field
            let input = form.querySelector('input[name="filter_data"]');
            if (!input) {
                input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'filter_data';
                form.appendChild(input);
            }
            
            input.value = JSON.stringify(filterData);
        });
    }
    
    // Public API
    return {
        init: function(fields, existingFilters) {
            const container = document.getElementById('filter-builder');
            if (!container) return;
            
            createFilterBuilderUI(container, fields, existingFilters);
            setupFormSubmission();
        }
    };
})();

// Initialize when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Filter builder initialization will be triggered from the main wizard.js
});