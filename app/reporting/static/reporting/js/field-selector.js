/**
 * Field Selector Module
 * Handles selection of data fields (columns) for reports
 */

const FieldSelector = (function() {
    // Private variables and functions
    function createFieldSelectorUI(container, availableFields, selectedFields) {
        // Create the main layout
        const layout = document.createElement('div');
        layout.className = 'field-selector-layout';
        
        // Available fields panel
        const availablePanel = document.createElement('div');
        availablePanel.className = 'available-fields-panel';
        
        const availableHeader = document.createElement('h5');
        availableHeader.textContent = 'Available Fields';
        availablePanel.appendChild(availableHeader);
        
        const availableSearch = document.createElement('input');
        availableSearch.type = 'text';
        availableSearch.className = 'form-control form-control-sm mb-2';
        availableSearch.placeholder = 'Search fields...';
        availableSearch.addEventListener('input', function() {
            filterAvailableFields(this.value);
        });
        availablePanel.appendChild(availableSearch);
        
        const availableFieldsList = document.createElement('div');
        availableFieldsList.className = 'available-fields-list';
        
        // Populate available fields
        availableFields.forEach(group => {
            const groupElement = document.createElement('div');
            groupElement.className = 'field-group';
            
            const groupHeader = document.createElement('div');
            groupHeader.className = 'field-group-header';
            groupHeader.innerHTML = `<i class="fas fa-folder"></i> ${group.name}`;
            groupHeader.addEventListener('click', function() {
                this.parentElement.classList.toggle('expanded');
            });
            groupElement.appendChild(groupHeader);
            
            const fieldsList = document.createElement('div');
            fieldsList.className = 'fields-list';
            
            group.fields.forEach(field => {
                const fieldItem = document.createElement('div');
                fieldItem.className = 'field-item';
                fieldItem.dataset.fieldId = `${field.name}:${field.type}`;
                fieldItem.dataset.fieldName = field.name;
                fieldItem.dataset.fieldType = field.type;
                fieldItem.dataset.fieldTitle = field.verbose_name;
                fieldItem.innerHTML = `
                    <span class="field-name">${field.verbose_name}</span>
                    <span class="field-type badge bg-secondary">${field.type}</span>
                    <button type="button" class="btn-add"><i class="fas fa-plus"></i></button>
                `;
                fieldItem.querySelector('.btn-add').addEventListener('click', function() {
                    addFieldToSelection(field);
                });
                
                // Add tooltip with help text if available
                if (field.help_text) {
                    fieldItem.setAttribute('title', field.help_text);
                    // Initialize tooltip (Bootstrap 5)
                    new bootstrap.Tooltip(fieldItem);
                }
                
                fieldsList.appendChild(fieldItem);
            });
            
            groupElement.appendChild(fieldsList);
            availableFieldsList.appendChild(groupElement);
        });
        
        availablePanel.appendChild(availableFieldsList);
        
        // Selected fields panel
        const selectedPanel = document.createElement('div');
        selectedPanel.className = 'selected-fields-panel';
        
        const selectedHeader = document.createElement('h5');
        selectedHeader.textContent = 'Selected Fields';
        selectedPanel.appendChild(selectedHeader);
        
        const selectedFieldsList = document.createElement('div');
        selectedFieldsList.className = 'selected-fields-list';
        selectedFieldsList.id = 'selected-fields-list';
        
        // Make the selected fields list sortable
        selectedPanel.appendChild(selectedFieldsList);
        
        // Add buttons between panels
        const buttonsPanel = document.createElement('div');
        buttonsPanel.className = 'field-selector-buttons';
        
        const addAllBtn = document.createElement('button');
        addAllBtn.type = 'button';
        addAllBtn.className = 'btn btn-sm btn-outline-primary';
        addAllBtn.innerHTML = '<i class="fas fa-angle-double-right"></i>';
        addAllBtn.title = 'Add all fields';
        addAllBtn.addEventListener('click', addAllFields);
        
        const removeAllBtn = document.createElement('button');
        removeAllBtn.type = 'button';
        removeAllBtn.className = 'btn btn-sm btn-outline-danger';
        removeAllBtn.innerHTML = '<i class="fas fa-angle-double-left"></i>';
        removeAllBtn.title = 'Remove all fields';
        removeAllBtn.addEventListener('click', removeAllFields);
        
        buttonsPanel.appendChild(addAllBtn);
        buttonsPanel.appendChild(removeAllBtn);
        
        // Assemble the layout
        layout.appendChild(availablePanel);
        layout.appendChild(buttonsPanel);
        layout.appendChild(selectedPanel);
        
        container.appendChild(layout);
        
        // Initialize with any pre-selected fields
        if (selectedFields && selectedFields.length) {
            selectedFields.forEach(fieldId => {
                // Find the field in available fields
                availableFields.forEach(group => {
                    group.fields.forEach(field => {
                        if (`${field.name}:${field.type}` === fieldId) {
                            addFieldToSelection(field);
                        }
                    });
                });
            });
        }
        
        // Make the selected fields sortable
        initSortable();
    }

    function addFieldToSelection(field) {
        const selectedList = document.getElementById('selected-fields-list');
        
        // Check if field is already selected
        const existingField = document.querySelector(`.selected-field-item[data-field-id="${field.name}:${field.type}"]`);
        if (existingField) return;
        
        const fieldItem = document.createElement('div');
        fieldItem.className = 'selected-field-item';
        fieldItem.dataset.fieldId = `${field.name}:${field.type}`;
        fieldItem.dataset.fieldName = field.name;
        fieldItem.dataset.fieldType = field.type;
        fieldItem.innerHTML = `
            <div class="drag-handle"><i class="fas fa-grip-vertical"></i></div>
            <span class="field-name">${field.verbose_name}</span>
            <span class="field-type badge bg-secondary">${field.type}</span>
            <button type="button" class="btn-remove"><i class="fas fa-times"></i></button>
        `;
        
        fieldItem.querySelector('.btn-remove').addEventListener('click', function() {
            fieldItem.remove();
        });
        
        selectedList.appendChild(fieldItem);
    }

    function addAllFields() {
        const visibleFields = document.querySelectorAll('.field-item:not(.hidden)');
        visibleFields.forEach(fieldItem => {
            const fieldName = fieldItem.dataset.fieldName;
            const fieldType = fieldItem.dataset.fieldType;
            const fieldTitle = fieldItem.dataset.fieldTitle;
            
            addFieldToSelection({
                name: fieldName,
                type: fieldType,
                verbose_name: fieldTitle
            });
        });
    }

    function removeAllFields() {
        if (confirm('Are you sure you want to remove all selected fields?')) {
            const selectedList = document.getElementById('selected-fields-list');
            selectedList.innerHTML = '';
        }
    }

    function filterAvailableFields(searchText) {
        const fieldItems = document.querySelectorAll('.field-item');
        const searchLower = searchText.toLowerCase();
        
        fieldItems.forEach(item => {
            const fieldName = item.dataset.fieldName.toLowerCase();
            const fieldTitle = item.dataset.fieldTitle.toLowerCase();
            
            if (fieldName.includes(searchLower) || fieldTitle.includes(searchLower)) {
                item.classList.remove('hidden');
            } else {
                item.classList.add('hidden');
            }
        });
        
        // Show/hide groups based on whether they have visible fields
        const fieldGroups = document.querySelectorAll('.field-group');
        fieldGroups.forEach(group => {
            const hasVisibleFields = group.querySelectorAll('.field-item:not(.hidden)').length > 0;
            if (hasVisibleFields) {
                group.classList.remove('hidden');
                group.classList.add('expanded');
            } else {
                group.classList.add('hidden');
            }
        });
    }

    function initSortable() {
        // Initialize sortable list for selected fields (using Sortable.js if available)
        if (typeof Sortable !== 'undefined') {
            Sortable.create(document.getElementById('selected-fields-list'), {
                handle: '.drag-handle',
                animation: 150
            });
        }
    }

    function setupFormSubmission() {
        // Handle form submission to include selected fields
        const form = document.getElementById('wizard-form');
        if (!form) return;
        
        form.addEventListener('submit', function(e) {
            // Get all selected fields
            const selectedItems = document.querySelectorAll('.selected-field-item');
            
            // Clear any existing hidden fields
            const existingFields = form.querySelectorAll('input[name="selected_fields"]');
            existingFields.forEach(field => field.remove());
            
            // Add a hidden field for each selected field
            selectedItems.forEach(item => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'selected_fields';
                input.value = item.dataset.fieldId;
                form.appendChild(input);
            });
        });
    }

    // Public API
    return {
        init: function(availableFields, selectedFields) {
            const container = document.getElementById('field-selector');
            if (!container) return;
            
            createFieldSelectorUI(container, availableFields, selectedFields);
            setupFormSubmission();
        }
    };
})();

// Initialize when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Field selector initialization will be triggered from the main wizard.js
});