/**
 * Sort Builder Module
 * Handles defining the sort order for reports
 */

const SortBuilder = (function() {
    // Private functions
    function createSortBuilderUI(container, selectedFields, existingSortOrder) {
        // Create the sort builder elements
        const sortBuilderContainer = document.createElement('div');
        sortBuilderContainer.className = 'sort-builder-container';
        
        // Available fields panel
        const availableFieldsPanel = document.createElement('div');
        availableFieldsPanel.className = 'card mb-3';
        
        const availableFieldsHeader = document.createElement('div');
        availableFieldsHeader.className = 'card-header';
        availableFieldsHeader.innerHTML = '<h5 class="mb-0">Available Fields</h5>';
        
        const availableFieldsList = document.createElement('div');
        availableFieldsList.className = 'card-body';
        availableFieldsList.id = 'available-sort-fields';
        
        // Add fields to the available list
        selectedFields.forEach(field => {
            // Skip fields already in the sort order
            if (existingSortOrder && existingSortOrder.some(sort => sort.field === field.name)) {
                return;
            }
            
            const fieldItem = createFieldItem(field);
            availableFieldsList.appendChild(fieldItem);
        });
        
        availableFieldsPanel.appendChild(availableFieldsHeader);
        availableFieldsPanel.appendChild(availableFieldsList);
        
        // Sort order panel
        const sortOrderPanel = document.createElement('div');
        sortOrderPanel.className = 'card';
        
        const sortOrderHeader = document.createElement('div');
        sortOrderHeader.className = 'card-header';
        sortOrderHeader.innerHTML = '<h5 class="mb-0">Sort Order</h5>';
        
        const sortOrderList = document.createElement('div');
        sortOrderList.className = 'card-body';
        sortOrderList.id = 'sort-order-list';
        
        // Instructions when empty
        const emptyMessage = document.createElement('p');
        emptyMessage.className = 'text-muted empty-sort-message';
        emptyMessage.textContent = 'Drag fields here to define the sort order.';
        sortOrderList.appendChild(emptyMessage);
        
        // Add existing sort order if any
        if (existingSortOrder && existingSortOrder.length > 0) {
            emptyMessage.style.display = 'none';
            
            existingSortOrder.forEach(sortItem => {
                // Find the corresponding field
                const field = selectedFields.find(f => f.name === sortItem.field);
                if (field) {
                    const sortFieldItem = createSortOrderItem(field, sortItem.direction);
                    sortOrderList.appendChild(sortFieldItem);
                }
            });
        }
        
        sortOrderPanel.appendChild(sortOrderHeader);
        sortOrderPanel.appendChild(sortOrderList);
        
        // Add both panels to the container
        sortBuilderContainer.appendChild(availableFieldsPanel);
        sortBuilderContainer.appendChild(sortOrderPanel);
        container.appendChild(sortBuilderContainer);
        
        // Initialize drag and drop
        initDragAndDrop();
    }
    
    function createFieldItem(field) {
        const fieldItem = document.createElement('div');
        fieldItem.className = 'field-item draggable';
        fieldItem.dataset.fieldName = field.name;
        fieldItem.dataset.fieldTitle = field.verbose_name || field.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        fieldItem.draggable = true;
        
        fieldItem.innerHTML = `
            <i class="fas fa-grip-vertical drag-handle"></i>
            <span class="field-name">${fieldItem.dataset.fieldTitle}</span>
        `;
        
        return fieldItem;
    }
    
    function createSortOrderItem(field, direction = 'asc') {
        const sortItem = document.createElement('div');
        sortItem.className = 'sort-order-item';
        sortItem.dataset.fieldName = field.name;
        sortItem.dataset.fieldTitle = field.verbose_name || field.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        
        sortItem.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <i class="fas fa-grip-vertical drag-handle"></i>
                    <span class="field-name">${sortItem.dataset.fieldTitle}</span>
                </div>
                <div class="sort-controls">
                    <div class="btn-group btn-group-sm">
                        <button type="button" class="btn btn-outline-secondary sort-asc ${direction === 'asc' ? 'active' : ''}" title="Sort Ascending">
                            <i class="fas fa-sort-up"></i>
                        </button>
                        <button type="button" class="btn btn-outline-secondary sort-desc ${direction === 'desc' ? 'active' : ''}" title="Sort Descending">
                            <i class="fas fa-sort-down"></i>
                        </button>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-danger remove-sort" title="Remove">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `;
        
        // Add event listeners for sort direction buttons
        sortItem.querySelector('.sort-asc').addEventListener('click', function() {
            this.classList.add('active');
            sortItem.querySelector('.sort-desc').classList.remove('active');
        });
        
        sortItem.querySelector('.sort-desc').addEventListener('click', function() {
            this.classList.add('active');
            sortItem.querySelector('.sort-asc').classList.remove('active');
        });
        
        // Add event listener for remove button
        sortItem.querySelector('.remove-sort').addEventListener('click', function() {
            removeFromSortOrder(sortItem);
        });
        
        return sortItem;
    }
    
    function initDragAndDrop() {
        // Get elements
        const availableFields = document.querySelectorAll('#available-sort-fields .draggable');
        const sortOrderList = document.getElementById('sort-order-list');
        
        // Make sort order list sortable
        if (typeof Sortable !== 'undefined') {
            Sortable.create(sortOrderList, {
                group: 'sort-fields',
                animation: 150,
                handle: '.drag-handle',
                onAdd: function(evt) {
                    // Convert field item to sort order item
                    const field = {
                        name: evt.item.dataset.fieldName,
                        verbose_name: evt.item.dataset.fieldTitle
                    };
                    
                    const sortItem = createSortOrderItem(field);
                    sortOrderList.replaceChild(sortItem, evt.item);
                    
                    // Hide empty message
                    const emptyMessage = sortOrderList.querySelector('.empty-sort-message');
                    if (emptyMessage) {
                        emptyMessage.style.display = 'none';
                    }
                }
            });
        }
        
        // Make available fields draggable
        if (typeof Sortable !== 'undefined') {
            Sortable.create(document.getElementById('available-sort-fields'), {
                group: {
                    name: 'sort-fields',
                    pull: 'clone',
                    put: false
                },
                animation: 150,
                handle: '.drag-handle',
                sort: false
            });
        }
    }
    
    function removeFromSortOrder(sortItem) {
        const sortOrderList = document.getElementById('sort-order-list');
        sortOrderList.removeChild(sortItem);
        
        // Show empty message if no more items
        if (sortOrderList.querySelectorAll('.sort-order-item').length === 0) {
            const emptyMessage = sortOrderList.querySelector('.empty-sort-message');
            if (emptyMessage) {
                emptyMessage.style.display = '';
            }
        }
    }
    
    function getSortOrder() {
        const sortItems = document.querySelectorAll('#sort-order-list .sort-order-item');
        const sortOrder = [];
        
        sortItems.forEach(item => {
            sortOrder.push({
                field: item.dataset.fieldName,
                direction: item.querySelector('.sort-asc').classList.contains('active') ? 'asc' : 'desc'
            });
        });
        
        return sortOrder;
    }
    
    function setupFormSubmission() {
        // Handle form submission to include sort order
        const form = document.getElementById('wizard-form');
        if (!form) return;
        
        form.addEventListener('submit', function(e) {
            // Get sort order data
            const sortOrderData = getSortOrder();
            
            // Add it as a hidden field
            let input = form.querySelector('input[name="sort_data"]');
            if (!input) {
                input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'sort_data';
                form.appendChild(input);
            }
            
            input.value = JSON.stringify(sortOrderData);
        });
    }
    
    // Public API
    return {
        init: function(selectedFields, existingSortOrder) {
            const container = document.getElementById('sort-order-builder');
            if (!container) return;
            
            createSortBuilderUI(container, selectedFields, existingSortOrder);
            setupFormSubmission();
        }
    };
})();

// Initialize when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Sort builder initialization will be triggered from the main wizard.js
});