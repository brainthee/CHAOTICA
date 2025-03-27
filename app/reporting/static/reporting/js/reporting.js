/**
 * Main Reporting JavaScript
 * 
 * This file contains general JavaScript functionality for the reporting module
 * including functions used across multiple views.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize universal components
    initReportSearch();
    initFilterToggle();
    initConditionalFields();
    initTooltips();
    
    // Check if there are any specific page initializations needed
    if (document.getElementById('report-list')) {
        initReportList();
    }
    
    if (document.getElementById('report-preview')) {
        initReportPreview();
    }
});

/**
 * Initialize report search functionality
 */
function initReportSearch() {
    const searchInputs = document.querySelectorAll('.report-search');
    
    searchInputs.forEach(input => {
        input.addEventListener('keyup', function() {
            const searchText = this.value.toLowerCase();
            const listContainer = this.closest('.tab-pane') || document.body;
            const reportRows = listContainer.querySelectorAll('.report-row');
            
            reportRows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(searchText) ? '' : 'none';
            });
        });
    });
}

/**
 * Initialize filter toggle functionality
 */
function initFilterToggle() {
    const filterToggle = document.getElementById('filter-toggle');
    const filterPanel = document.getElementById('filter-panel');
    
    if (filterToggle && filterPanel) {
        filterToggle.addEventListener('click', function() {
            filterPanel.classList.toggle('show');
            
            // Update the toggle button text/icon
            const isExpanded = filterPanel.classList.contains('show');
            filterToggle.innerHTML = isExpanded 
                ? '<i class="fas fa-filter"></i> Hide Filters' 
                : '<i class="fas fa-filter"></i> Show Filters';
        });
    }
}

/**
 * Initialize conditional fields that depend on the value of other fields
 */
function initConditionalFields() {
    const conditionalFields = document.querySelectorAll('[data-condition]');
    
    conditionalFields.forEach(field => {
        const conditionField = field.getAttribute('data-condition');
        const conditionValue = field.getAttribute('data-condition-value');
        const controlField = document.querySelector(`[name="${conditionField}"]`);
        
        if (controlField) {
            // Set initial visibility
            toggleFieldVisibility(field, controlField, conditionValue);
            
            // Add change listener
            controlField.addEventListener('change', function() {
                toggleFieldVisibility(field, this, conditionValue);
            });
            
            // For radio buttons
            if (controlField.type === 'radio') {
                document.querySelectorAll(`[name="${conditionField}"]`).forEach(radio => {
                    radio.addEventListener('change', function() {
                        toggleFieldVisibility(field, this, conditionValue);
                    });
                });
            }
        }
    });
}

/**
 * Toggle visibility of a conditional field based on the control field's value
 */
function toggleFieldVisibility(field, controlField, conditionValue) {
    let currentValue;
    
    // Handle different field types
    if (controlField.type === 'checkbox') {
        currentValue = controlField.checked.toString();
    } else if (controlField.type === 'radio') {
        const checkedRadio = document.querySelector(`[name="${controlField.name}"]:checked`);
        currentValue = checkedRadio ? checkedRadio.value : '';
    } else {
        currentValue = controlField.value;
    }
    
    // Show/hide based on match
    field.style.display = (currentValue === conditionValue) ? '' : 'none';
}

/**
 * Initialize tooltips
 */
function initTooltips() {
    // Bootstrap 5 tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    if (typeof bootstrap !== 'undefined') {
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl)
        });
    }
}

/**
 * Initialize report list page functionality
 */
function initReportList() {
    // Handle tab persistence
    const reportTabs = document.getElementById('reportTabs');
    if (reportTabs) {
        // Restore active tab from localStorage if available
        const activeTab = localStorage.getItem('activeReportTab');
        if (activeTab) {
            const tab = document.querySelector(`[data-bs-target="${activeTab}"]`);
            if (tab) {
                new bootstrap.Tab(tab).show();
            }
        }
        
        // Save active tab when changed
        reportTabs.addEventListener('shown.bs.tab', function (e) {
            localStorage.setItem('activeReportTab', e.target.getAttribute('data-bs-target'));
        });
    }
}

/**
 * Initialize report preview functionality
 */
function initReportPreview() {
    const previewButton = document.getElementById('preview-report-btn');
    
    if (previewButton) {
        previewButton.addEventListener('click', function() {
            const form = document.getElementById('run-report-form');
            const formData = new FormData(form);
            
            // Show loading indicator
            document.getElementById('preview-loading').style.display = 'block';
            document.getElementById('preview-content').style.display = 'none';
            document.getElementById('preview-error').style.display = 'none';
            
            // Show modal
            const previewModal = new bootstrap.Modal(document.getElementById('previewModal'));
            previewModal.show();
            
            // Send AJAX request
            fetch(form.getAttribute('data-preview-url'), {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('preview-loading').style.display = 'none';
                
                if (data.error) {
                    // Show error
                    const errorElement = document.getElementById('preview-error');
                    errorElement.textContent = data.error;
                    errorElement.style.display = 'block';
                } else {
                    // Build preview table
                    buildPreviewTable(data);
                    document.getElementById('preview-content').style.display = 'block';
                }
            })
            .catch(error => {
                document.getElementById('preview-loading').style.display = 'none';
                document.getElementById('preview-error').style.display = 'block';
                console.error('Error fetching report preview:', error);
            });
        });
    }
}

/**
 * Build the preview table with report data
 */
function buildPreviewTable(data) {
    const tableHead = document.querySelector('#preview-table thead tr');
    const tableBody = document.querySelector('#preview-table tbody');
    
    tableHead.innerHTML = '';
    tableBody.innerHTML = '';
    
    if (!data.data || data.data.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="100" class="text-center py-4">No data to display</td></tr>';
        return;
    }
    
    // Add column headers
    const columns = Object.keys(data.data[0]);
    columns.forEach(column => {
        const th = document.createElement('th');
        th.textContent = column.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
        tableHead.appendChild(th);
    });
    
    // Add data rows
    data.data.forEach(row => {
        const tr = document.createElement('tr');
        
        columns.forEach(column => {
            const td = document.createElement('td');
            let cellValue = row[column] !== null ? row[column] : '';
            
            // Format dates if needed
            if (typeof cellValue === 'string' && cellValue.match(/^\d{4}-\d{2}-\d{2}T/)) {
                cellValue = new Date(cellValue).toLocaleString();
            }
            
            td.textContent = cellValue;
            tr.appendChild(td);
        });
        
        tableBody.appendChild(tr);
    });
}