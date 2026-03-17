/**
 * DOM Destroyer - Click to damage and destroy any element on the page
 * HP based on element size, visual damage progression, particle explosions
 */
window.DOMDestroyer = (function() {
    'use strict';

    var active = false;
    var clickHandler = null;
    var blockHandler = null;

    // Elements to never target
    var IGNORE_SELECTORS = [
        'html', 'body', '#chaos-canvas', '.lcars-overlay', '.lcars-overlay *',
        '.swal2-container', '.swal2-container *',
        // Allow navbar to be targeted but not the very top nav links (escape route)
        '#dualNav > .navbar-nav > .nav-item > .nav-link'
    ];

    var CRACK_SVG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100' viewBox='0 0 100 100'%3E%3Cpath d='M30 0 L35 25 L20 40 L35 50 L25 70 L40 85 L30 100' stroke='rgba(0,0,0,0.4)' stroke-width='2' fill='none'/%3E%3Cpath d='M70 0 L60 20 L75 35 L60 55 L70 70 L55 100' stroke='rgba(0,0,0,0.3)' stroke-width='1.5' fill='none'/%3E%3Cpath d='M50 30 L45 50 L55 65' stroke='rgba(0,0,0,0.25)' stroke-width='1' fill='none'/%3E%3C/svg%3E";

    function activate() {
        if (active) return;
        active = true;
        document.body.classList.add('chaos-crosshair');
        ChaosEngine.canvas.init();
        ChaosEngine.score.start('destroyer');

        clickHandler = function(e) {
            if (!active) return;
            var target = findTarget(e.target);
            if (!target) return;

            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            damageElement(target, e.clientX, e.clientY);
        };

        // Block mousedown/mouseup/dblclick to prevent text selection, focus, context menus
        blockHandler = function(e) {
            if (!active) return;
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
        };

        document.addEventListener('click', clickHandler, true);
        document.addEventListener('mousedown', blockHandler, true);
        document.addEventListener('mouseup', blockHandler, true);
        document.addEventListener('dblclick', blockHandler, true);
        document.addEventListener('contextmenu', blockHandler, true);
    }

    function deactivate() {
        if (!active) return;
        active = false;
        document.body.classList.remove('chaos-crosshair');
        if (clickHandler) {
            document.removeEventListener('click', clickHandler, true);
            clickHandler = null;
        }
        if (blockHandler) {
            document.removeEventListener('mousedown', blockHandler, true);
            document.removeEventListener('mouseup', blockHandler, true);
            document.removeEventListener('dblclick', blockHandler, true);
            document.removeEventListener('contextmenu', blockHandler, true);
            blockHandler = null;
        }
        ChaosEngine.score.saveHighScore();
        ChaosEngine.score.hide();
    }

    function findTarget(el) {
        // Walk up from event target to find a suitable element
        while (el && el !== document.body && el !== document.documentElement) {
            if (shouldIgnore(el)) return null;
            // Target elements with meaningful visual size
            if (el.offsetWidth >= 20 && el.offsetHeight >= 20) {
                return el;
            }
            el = el.parentElement;
        }
        return null;
    }

    function shouldIgnore(el) {
        for (var i = 0; i < IGNORE_SELECTORS.length; i++) {
            try {
                if (el.matches && el.matches(IGNORE_SELECTORS[i])) return true;
            } catch(e) {}
        }
        return false;
    }

    function getHP(el) {
        if (el.dataset.chaosHp !== undefined) {
            return parseInt(el.dataset.chaosHp, 10);
        }
        // Calculate HP based on element area
        var area = el.offsetWidth * el.offsetHeight;
        var hp = Math.max(1, Math.min(20, Math.ceil(area / 5000)));
        el.dataset.chaosHp = hp;
        el.dataset.chaosMaxHp = hp;
        return hp;
    }

    function damageElement(el, clickX, clickY) {
        var hp = getHP(el);
        hp--;
        el.dataset.chaosHp = hp;

        var maxHp = parseInt(el.dataset.chaosMaxHp, 10);
        var dmgPercent = (maxHp - hp) / maxHp;

        // Sound
        ChaosEngine.sound.hit();

        // Small particle burst at click point
        var bgColor = ChaosEngine.util.rgbToHex(ChaosEngine.util.getComputedBgColor(el));
        ChaosEngine.particles.emit(clickX, clickY, {
            count: 5,
            colors: [bgColor, '#FF4444', '#FFAA00'],
            speed: 100,
            lifetime: 0.4,
            size: 3
        });

        // Hit flash animation
        el.classList.remove('chaos-hit-flash');
        void el.offsetWidth; // force reflow
        el.classList.add('chaos-hit-flash');

        if (hp <= 0) {
            destroyElement(el, clickX, clickY, bgColor, maxHp);
        } else {
            applyDamageVisuals(el, dmgPercent);
        }
    }

    function applyDamageVisuals(el, dmgPercent) {
        // Progressive damage visualization
        if (dmgPercent >= 0.25) {
            el.style.boxShadow = 'inset 0 0 ' + (5 + dmgPercent * 15) + 'px rgba(255,0,0,' + (0.2 + dmgPercent * 0.3) + ')';
        }
        if (dmgPercent >= 0.5) {
            el.classList.add('chaos-cracked');
            el.style.backgroundImage = "url(\"" + CRACK_SVG + "\")";
            el.style.backgroundRepeat = 'repeat';
        }
        if (dmgPercent >= 0.75) {
            el.style.opacity = String(0.9 - dmgPercent * 0.3);
            var angle = (Math.random() - 0.5) * 4;
            el.style.transform = (el.style.transform || '') + ' rotate(' + angle + 'deg)';
        }
    }

    function destroyElement(el, clickX, clickY, bgColor, maxHp) {
        // Big explosion
        ChaosEngine.sound.explosion();
        ChaosEngine.particles.emit(clickX, clickY, {
            count: 25 + maxHp * 3,
            colors: [bgColor, '#FF4444', '#FFAA00', '#FFD700'],
            speed: 200,
            lifetime: 0.8,
            size: 5
        });

        // Score
        var points = maxHp * 50;
        ChaosEngine.score.add(points, clickX - 20, clickY - 20);

        // Screen shake proportional to element size
        var shakeIntensity = Math.min(15, 3 + maxHp);
        ChaosEngine.shake.trigger(shakeIntensity, 200);

        // Animate out
        el.style.transition = 'transform 0.25s ease-in, opacity 0.25s ease-in';
        el.style.transform = 'scale(0) rotate(' + (Math.random() > 0.5 ? 15 : -15) + 'deg)';
        el.style.opacity = '0';
        el.style.pointerEvents = 'none';

        setTimeout(function() {
            el.style.visibility = 'hidden';
            // Clean up classes
            el.classList.remove('chaos-cracked', 'chaos-hit-flash');
        }, 250);
    }

    return {
        activate: activate,
        deactivate: deactivate,
        isActive: function() { return active; }
    };
})();
