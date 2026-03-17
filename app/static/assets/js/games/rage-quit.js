/**
 * Rage Quit - Cathartic chain-reaction explosion of all schedule events
 * DOM-based physics animation with particle effects
 */
window.RageQuit = (function() {
    'use strict';

    var triggered = false;

    function trigger() {
        if (triggered) return;
        triggered = true;

        ChaosEngine.canvas.init();

        var events = document.querySelectorAll('.fc-event');
        if (!events.length) {
            triggered = false;
            return;
        }

        // Capture all element positions and colors before moving them
        var elements = [];
        for (var i = 0; i < events.length; i++) {
            var el = events[i];
            var rect = el.getBoundingClientRect();
            var bg = window.getComputedStyle(el).backgroundColor || '#FF9900';
            elements.push({
                el: el,
                rect: rect,
                color: ChaosEngine.util.rgbToHex(bg),
                centerX: rect.left + rect.width / 2,
                centerY: rect.top + rect.height / 2
            });
        }

        // Find center of all elements for chain reaction origin
        var avgX = 0, avgY = 0;
        for (var j = 0; j < elements.length; j++) {
            avgX += elements[j].centerX;
            avgY += elements[j].centerY;
        }
        avgX /= elements.length;
        avgY /= elements.length;

        // Sort by distance from center (center elements go first)
        elements.sort(function(a, b) {
            var distA = Math.hypot(a.centerX - avgX, a.centerY - avgY);
            var distB = Math.hypot(b.centerX - avgX, b.centerY - avgY);
            return distA - distB;
        });

        // Initial screen shake
        ChaosEngine.shake.trigger(15, 600);
        ChaosEngine.sound.explosion(1.5);

        // Chain reaction: stagger detonations from center outward
        var staggerMs = Math.max(20, Math.min(50, 2000 / elements.length));

        for (var k = 0; k < elements.length; k++) {
            (function(item, delay) {
                setTimeout(function() {
                    detonateElement(item);
                }, delay);
            })(elements[k], k * staggerMs);
        }

        // After all detonations, show "Feel better?" dialog
        var totalDuration = elements.length * staggerMs + 2000;
        setTimeout(function() {
            showEndDialog();
        }, totalDuration);
    }

    function detonateElement(item) {
        var el = item.el;
        var rect = item.rect;

        // Fix position to current location
        el.style.position = 'fixed';
        el.style.left = rect.left + 'px';
        el.style.top = rect.top + 'px';
        el.style.width = rect.width + 'px';
        el.style.height = rect.height + 'px';
        el.style.zIndex = '10000';
        el.style.margin = '0';

        // Particles at detonation point
        ChaosEngine.particles.emit(item.centerX, item.centerY, {
            count: 15,
            colors: [item.color, '#FF4444', '#FFAA00', '#FFD700'],
            speed: 250,
            lifetime: 0.8,
            size: 5,
            gravity: 200
        });

        // Sound with pitch variation
        ChaosEngine.sound.explosion(0.5 + Math.random() * 1.5);

        // Small screen shake per detonation
        ChaosEngine.shake.trigger(4, 100);

        // Apply physics-like CSS animation
        var dx = (Math.random() - 0.5) * 400;
        var launchVy = -100 - Math.random() * 300; // launch upward
        var fallDist = window.innerHeight + 200;
        var rotation = (Math.random() - 0.5) * 1440; // up to 2 full rotations

        // Force reflow before transition
        void el.offsetWidth;

        el.style.transition = 'transform 1.5s cubic-bezier(.2, -0.6, .7, 1.4), opacity 1.5s ease-out';
        el.style.transform = 'translateX(' + dx + 'px) translateY(' + fallDist + 'px) rotate(' + rotation + 'deg) scale(0.3)';
        el.style.opacity = '0';

        // Clean up after animation
        setTimeout(function() {
            el.style.display = 'none';
        }, 1600);
    }

    function showEndDialog() {
        var overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:100001;background:#0a0a1a;display:flex;align-items:center;justify-content:center;font-family:"Courier New","Lucida Console",monospace;';
        overlay.innerHTML =
            '<div style="text-align:center;max-width:500px;padding:40px;">' +
                '<h2 style="color:#CC99CC;font-family:monospace;letter-spacing:3px;margin-bottom:20px;">WARP CORE BREACH COMPLETE</h2>' +
                '<p style="font-family:monospace;color:#FF9900;margin-bottom:10px;">All schedule elements have been neutralized.</p>' +
                '<p style="font-family:monospace;color:#9999FF;margin-bottom:30px;">Feel better?</p>' +
                '<button class="lcars-button" style="display:inline-flex;justify-content:center;max-width:250px;margin:0 auto;">' +
                    '<div class="lcars-button-indicator lcars-bg-orange"></div>' +
                    '<div class="lcars-button-content">' +
                        '<div class="lcars-button-label">RESTORE SYSTEMS</div>' +
                    '</div>' +
                '</button>' +
            '</div>';
        document.body.appendChild(overlay);

        overlay.querySelector('.lcars-button').addEventListener('click', function() {
            location.reload();
        });
    }

    function reset() {
        triggered = false;
    }

    return {
        trigger: trigger,
        reset: reset,
        isTriggered: function() { return triggered; }
    };
})();
