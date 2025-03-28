/**
 * Report Builder JavaScript
 * This file contains common JavaScript functions used throughout the Report Builder.
 */

// Initialize any tooltips
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
      return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Handle favorite toggle
    const favoriteBtn = document.getElementById('favorite-toggle');
    if (favoriteBtn) {
      favoriteBtn.addEventListener('click', function(e) {
        e.preventDefault();
        
        const reportUuid = this.dataset.reportUuid;
        const isFavorite = this.dataset.isFavorite === 'true';
        
        // Send AJAX request to toggle favorite status
        fetch(this.href, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCsrfToken(),
            'Content-Type': 'application/json'
          },
          credentials: 'same-origin'
        })
        .then(response => response.json())
        .then(data => {
          if (data.status === 'success') {
            // Update button state
            this.dataset.isFavorite = data.is_favorite;
            
            // Update icon
            const icon = this.querySelector('i');
            if (data.is_favorite) {
              icon.classList.remove('far');
              icon.classList.add('fas');
              this.setAttribute('title', 'Remove from favorites');
              showToast('Report added to favorites');
            } else {
              icon.classList.remove('fas');
              icon.classList.add('far');
              this.setAttribute('title', 'Add to favorites');
              showToast('Report removed from favorites');
            }
            
            // Refresh tooltip
            bootstrap.Tooltip.getInstance(this).dispose();
            new bootstrap.Tooltip(this);
          }
        })
        .catch(error => {
          console.error('Error:', error);
          showToast('An error occurred while updating favorites', 'error');
        });
      });
    }
    
    // Handle report run form submission
    const runReportForm = document.getElementById('run-report-form');
    if (runReportForm) {
      runReportForm.addEventListener('submit', function(e) {
        // Show loading spinner
        const submitBtn = this.querySelector('button[type="submit"]');
        if (submitBtn) {
          const originalText = submitBtn.innerHTML;
          submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Running...';
          submitBtn.disabled = true;
          
          // Re-enable after some time in case the form doesn't submit
          setTimeout(() => {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
          }, 10000);
        }
      });
    }
  });
  
  /**
   * Get CSRF token from cookies
   * @returns {string} CSRF token
   */
  function getCsrfToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  
  /**
   * Show a toast message
   * @param {string} message - Message to display
   * @param {string} type - Type of toast (success, error, info, warning)
   */
  function showToast(message, type = 'success') {
    // Create toast container if it doesn't exist
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
      document.body.appendChild(toastContainer);
    }
    
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    // Create toast content
    toast.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">
          ${message}
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    `;
    
    // Add to container
    toastContainer.appendChild(toast);
    
    // Initialize and show toast
    const toastInstance = new bootstrap.Toast(toast, {
      delay: 5000
    });
    toastInstance.show();
    
    // Remove from DOM after hidden
    toast.addEventListener('hidden.bs.toast', function() {
      this.remove();
    });
  }
  
  /**
   * Format a value based on its type
   * @param {*} value - Value to format
   * @param {string} type - Type of value
   * @param {string} format - Format string (optional)
   * @returns {string} Formatted value
   */
  function formatValue(value, type, format) {
    if (value === null || value === undefined) {
      return '';
    }
    
    switch (type) {
      case 'date':
        return formatDate(value, format || 'yyyy-MM-dd');
      case 'datetime':
        return formatDate(value, format || 'yyyy-MM-dd HH:mm:ss');
      case 'number':
      case 'decimal':
        return formatNumber(value, format);
      case 'boolean':
        return value ? 'Yes' : 'No';
      default:
        return value.toString();
    }
  }
  
  /**
   * Format a date value
   * @param {string|Date} date - Date to format
   * @param {string} format - Format string
   * @returns {string} Formatted date
   */
  function formatDate(date, format) {
    if (!date) return '';
    
    const d = new Date(date);
    if (isNaN(d.getTime())) return date; // Invalid date
    
    // Simple formatter - replace with more sophisticated library if needed
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const seconds = String(d.getSeconds()).padStart(2, '0');
    
    return format
      .replace('yyyy', year)
      .replace('MM', month)
      .replace('dd', day)
      .replace('HH', hours)
      .replace('mm', minutes)
      .replace('ss', seconds);
  }
  
  /**
   * Format a number value
   * @param {number} number - Number to format
   * @param {string} format - Format string
   * @returns {string} Formatted number
   */
  function formatNumber(number, format) {
    if (typeof number !== 'number') {
      number = parseFloat(number);
      if (isNaN(number)) return '';
    }
    
    if (!format) {
      return number.toString();
    }
    
    // Simple approach - can be replaced with more sophisticated formatter
    if (format.includes('0.00')) {
      return number.toFixed(2);
    } else if (format.includes('0.0')) {
      return number.toFixed(1);
    } else if (format.includes('0,000')) {
      return number.toLocaleString();
    }
    
    return number.toString();
  }