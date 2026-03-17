/**
 * ChaosGames - LCARS-themed game menu triggered by Konami code
 * Star Trek LCARS (Library Computer Access/Retrieval System) interface
 */
window.ChaosGames = (function() {
    'use strict';

    var menuOverlay = null;
    var isOpen = false;

    // Game state tracking
    var gameStates = {
        holodeck: false,
        destroyer: false,
        blaster: false
    };

    function initMenu() {
        // Restore holodeck state
        if (localStorage.safetyProtocols === 'true') {
            gameStates.holodeck = true;
            document.documentElement.classList.add('holodeck');
        }

        // Restore destroyer state
        if (localStorage.chaosDestroyer === 'true' && window.DOMDestroyer) {
            gameStates.destroyer = true;
            window.DOMDestroyer.activate();
        }

        // Listen for Konami code
        onKonamiCode(function() {
            if (isOpen) {
                closeMenu();
            } else {
                openMenu();
            }
        });

        // Ctrl+Shift+D shortcut for DOM Destroyer
        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey && e.shiftKey && e.key === 'D') {
                e.preventDefault();
                toggleDestroyer();
            }
        });
    }

    function openMenu() {
        if (isOpen) return;
        isOpen = true;

        // Play holodeck audio
        try {
            var audio = document.createElement('audio');
            audio.setAttribute('src', window.CHAOS_AUDIO_URL || '');
            if (audio.src) audio.play().catch(function(){});
        } catch(e) {}

        createMenuDOM();

        // Animate in
        requestAnimationFrame(function() {
            if (menuOverlay) menuOverlay.classList.add('lcars-active');
        });
    }

    function closeMenu() {
        if (!isOpen) return;
        isOpen = false;
        if (menuOverlay) {
            menuOverlay.classList.remove('lcars-active');
            setTimeout(function() {
                if (menuOverlay && menuOverlay.parentNode) {
                    menuOverlay.parentNode.removeChild(menuOverlay);
                }
                menuOverlay = null;
            }, 300);
        }
    }

    function isOnSchedulerPage() {
        // Check for the actual game scripts, not just #calendar (which exists on dashboard, user detail, etc.)
        return !!(window.RageQuit || window.ScheduleBlaster);
    }

    function createMenuDOM() {
        if (menuOverlay) {
            menuOverlay.parentNode.removeChild(menuOverlay);
        }

        var onScheduler = isOnSchedulerPage();

        menuOverlay = document.createElement('div');
        menuOverlay.className = 'lcars-overlay';
        menuOverlay.innerHTML = buildLCARSHTML(onScheduler);
        document.body.appendChild(menuOverlay);

        // Close on backdrop click
        menuOverlay.addEventListener('click', function(e) {
            if (e.target === menuOverlay) closeMenu();
        });

        // Close on Escape
        var escHandler = function(e) {
            if (e.key === 'Escape' && isOpen) {
                closeMenu();
                document.removeEventListener('keydown', escHandler);
            }
        };
        document.addEventListener('keydown', escHandler);

        // Bind button actions
        bindMenuActions(menuOverlay, onScheduler);
    }

    function buildLCARSHTML(onScheduler) {
        var schedulerNote = !onScheduler
            ? '<span class="lcars-unavailable">REQUIRES SCHEDULING CONSOLE</span>'
            : '';

        return '' +
            '<div class="lcars-frame">' +
                // Top header bar
                '<div class="lcars-header">' +
                    '<div class="lcars-elbow lcars-elbow-tl lcars-bg-orange"></div>' +
                    '<div class="lcars-bar lcars-bg-orange">' +
                        '<span class="lcars-title">HOLODECK RECREATIONAL SUBROUTINES</span>' +
                    '</div>' +
                    '<div class="lcars-cap lcars-bg-lavender"></div>' +
                '</div>' +
                // Content area with sidebar
                '<div class="lcars-body">' +
                    // Left sidebar
                    '<div class="lcars-sidebar">' +
                        '<div class="lcars-sidebar-block lcars-bg-orange"></div>' +
                        '<div class="lcars-sidebar-block lcars-bg-tan"></div>' +
                        '<div class="lcars-sidebar-block lcars-bg-blue"></div>' +
                        '<div class="lcars-sidebar-block lcars-bg-lavender"></div>' +
                        '<div class="lcars-sidebar-block lcars-bg-tan" style="flex:1"></div>' +
                        '<div class="lcars-elbow lcars-elbow-bl lcars-bg-blue"></div>' +
                    '</div>' +
                    // Main content
                    '<div class="lcars-content">' +
                        '<div class="lcars-section-label">SYSTEM PROGRAMS</div>' +
                        buildMenuButton('holodeck', 'HOLODECK SAFETY PROTOCOLS', 'Toggle visual distortion field', 'lcars-bg-orange', true, gameStates.holodeck) +
                        buildMenuButton('destroyer', 'WEAPONS ARRAY', 'Target and destroy interface elements', 'lcars-bg-red', true, gameStates.destroyer) +
                        '<div class="lcars-divider"><div class="lcars-divider-line lcars-bg-tan"></div></div>' +
                        '<div class="lcars-section-label">TACTICAL SIMULATIONS ' + schedulerNote + '</div>' +
                        buildMenuButton('blaster', 'TACTICAL SIMULATION', 'Engage schedule invader defense protocol', 'lcars-bg-blue', onScheduler, false) +
                        buildMenuButton('ragequit', 'WARP CORE BREACH', 'Initiate controlled schedule detonation', 'lcars-bg-lavender', onScheduler, false) +
                        '<div class="lcars-footer-bar">' +
                            '<div class="lcars-bar lcars-bg-blue"></div>' +
                            '<div class="lcars-bar lcars-bg-tan"></div>' +
                            '<div class="lcars-bar lcars-bg-orange"></div>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>';
    }

    function buildMenuButton(id, label, desc, colorClass, enabled, active) {
        var stateText = '';
        if (id === 'holodeck' || id === 'destroyer') {
            stateText = '<span class="lcars-status ' + (active ? 'lcars-engaged' : '') + '">' +
                (active ? 'ENGAGED' : 'DISENGAGED') + '</span>';
        }
        var disabledClass = enabled ? '' : ' lcars-disabled';
        return '<button class="lcars-button' + disabledClass + '" data-game="' + id + '"' +
            (enabled ? '' : ' disabled') + '>' +
            '<div class="lcars-button-indicator ' + colorClass + '"></div>' +
            '<div class="lcars-button-content">' +
                '<div class="lcars-button-label">' + label + '</div>' +
                '<div class="lcars-button-desc">' + desc + '</div>' +
            '</div>' +
            stateText +
        '</button>';
    }

    function bindMenuActions(container) {
        var buttons = container.querySelectorAll('.lcars-button');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].addEventListener('click', function(e) {
                var btn = e.currentTarget;
                if (btn.disabled || btn.classList.contains('lcars-disabled')) return;
                var game = btn.getAttribute('data-game');
                handleGameAction(game);
            });
        }
    }

    function handleGameAction(game) {
        switch(game) {
            case 'holodeck':
                toggleHolodeck();
                refreshMenuState();
                break;
            case 'destroyer':
                toggleDestroyer();
                refreshMenuState();
                break;
            case 'blaster':
                if (window.ScheduleBlaster) {
                    closeMenu();
                    window.ScheduleBlaster.start();
                }
                break;
            case 'ragequit':
                if (window.RageQuit) {
                    closeMenu();
                    window.RageQuit.trigger();
                }
                break;
        }
    }

    function toggleHolodeck() {
        gameStates.holodeck = !gameStates.holodeck;
        if (gameStates.holodeck) {
            document.documentElement.classList.add('holodeck');
            localStorage.safetyProtocols = 'true';
        } else {
            document.documentElement.classList.remove('holodeck');
            localStorage.safetyProtocols = '';
        }
    }

    function toggleDestroyer() {
        gameStates.destroyer = !gameStates.destroyer;
        if (gameStates.destroyer) {
            localStorage.chaosDestroyer = 'true';
            if (window.DOMDestroyer) window.DOMDestroyer.activate();
        } else {
            localStorage.chaosDestroyer = '';
            if (window.DOMDestroyer) window.DOMDestroyer.deactivate();
        }
    }

    function refreshMenuState() {
        if (!menuOverlay) return;
        // Update status badges in-place
        var buttons = menuOverlay.querySelectorAll('.lcars-button');
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            var game = btn.getAttribute('data-game');
            var status = btn.querySelector('.lcars-status');
            if (!status) continue;

            var active = gameStates[game];
            if (active) {
                status.textContent = 'ENGAGED';
                status.classList.add('lcars-engaged');
            } else {
                status.textContent = 'DISENGAGED';
                status.classList.remove('lcars-engaged');
            }
        }
    }

    return {
        initMenu: initMenu,
        openMenu: openMenu,
        closeMenu: closeMenu,
        isOpen: function() { return isOpen; },
        getState: function(key) { return gameStates[key]; }
    };
})();
