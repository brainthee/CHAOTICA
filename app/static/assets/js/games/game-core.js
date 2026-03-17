/**
 * ChaosEngine - Shared game engine for CHAOTICA easter egg games
 * Provides: canvas overlay, particle system, procedural sound, scoring, screen shake
 */
window.ChaosEngine = (function() {
    'use strict';

    // ─── Canvas Overlay ─────────────────────────────────────────────
    var canvas = null;
    var ctx = null;
    var animating = false;
    var animationId = null;
    var renderCallbacks = [];

    function initCanvas() {
        if (canvas) return canvas;
        canvas = document.createElement('canvas');
        canvas.id = 'chaos-canvas';
        canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:99998;pointer-events:none;';
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        document.body.appendChild(canvas);
        ctx = canvas.getContext('2d');

        window.addEventListener('resize', function() {
            if (canvas) {
                canvas.width = window.innerWidth;
                canvas.height = window.innerHeight;
            }
        });

        if (!animating) {
            animating = true;
            requestAnimationFrame(tick);
        }
        return canvas;
    }

    function destroyCanvas() {
        animating = false;
        if (animationId) cancelAnimationFrame(animationId);
        if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
        canvas = null;
        ctx = null;
        renderCallbacks = [];
    }

    function getCanvas() { return canvas; }
    function getCtx() { return ctx; }

    function addRenderCallback(fn) {
        renderCallbacks.push(fn);
    }
    function removeRenderCallback(fn) {
        renderCallbacks = renderCallbacks.filter(function(cb) { return cb !== fn; });
    }

    var lastTime = 0;
    function tick(timestamp) {
        if (!animating) return;
        var dt = lastTime ? (timestamp - lastTime) / 1000 : 0.016;
        lastTime = timestamp;
        if (dt > 0.1) dt = 0.016; // cap delta

        if (ctx) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            particles.update(dt);
            particles.draw(ctx);
            score._drawFloaters(ctx, dt);
            score._drawHUD(ctx);
            for (var i = 0; i < renderCallbacks.length; i++) {
                renderCallbacks[i](ctx, dt);
            }
        }
        animationId = requestAnimationFrame(tick);
    }

    // ─── Particle System ────────────────────────────────────────────
    var MAX_PARTICLES = 500;
    var particlePool = [];

    var particles = {
        emit: function(x, y, opts) {
            opts = opts || {};
            var count = opts.count || 15;
            var colors = opts.colors || ['#FF9900', '#FF4444', '#FFAA00'];
            var speed = opts.speed || 200;
            var gravity = opts.gravity !== undefined ? opts.gravity : 300;
            var lifetime = opts.lifetime || 1.0;
            var size = opts.size || 4;

            for (var i = 0; i < count; i++) {
                if (particlePool.length >= MAX_PARTICLES) break;
                var angle = Math.random() * Math.PI * 2;
                var vel = speed * (0.3 + Math.random() * 0.7);
                particlePool.push({
                    x: x + (Math.random() - 0.5) * 6,
                    y: y + (Math.random() - 0.5) * 6,
                    vx: Math.cos(angle) * vel,
                    vy: Math.sin(angle) * vel,
                    life: lifetime * (0.5 + Math.random() * 0.5),
                    maxLife: lifetime,
                    color: colors[Math.floor(Math.random() * colors.length)],
                    size: size * (0.5 + Math.random()),
                    rotation: Math.random() * 360,
                    rotSpeed: (Math.random() - 0.5) * 720,
                    gravity: gravity,
                    shape: opts.shape || 'rect'
                });
            }
        },

        update: function(dt) {
            for (var i = particlePool.length - 1; i >= 0; i--) {
                var p = particlePool[i];
                p.life -= dt;
                if (p.life <= 0) {
                    particlePool.splice(i, 1);
                    continue;
                }
                p.vy += p.gravity * dt;
                p.x += p.vx * dt;
                p.y += p.vy * dt;
                p.rotation += p.rotSpeed * dt;
            }
        },

        draw: function(ctx) {
            for (var i = 0; i < particlePool.length; i++) {
                var p = particlePool[i];
                var alpha = Math.max(0, p.life / p.maxLife);
                ctx.save();
                ctx.globalAlpha = alpha;
                ctx.translate(p.x, p.y);
                ctx.rotate(p.rotation * Math.PI / 180);
                ctx.fillStyle = p.color;
                if (p.shape === 'circle') {
                    ctx.beginPath();
                    ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
                    ctx.fill();
                } else if (p.shape === 'spark') {
                    ctx.fillRect(-p.size / 2, -1, p.size, 2);
                } else {
                    ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
                }
                ctx.restore();
            }
        },

        clear: function() {
            particlePool = [];
        },

        count: function() {
            return particlePool.length;
        }
    };

    // ─── Procedural Sound (Web Audio API) ───────────────────────────
    var audioCtx = null;

    function getAudioCtx() {
        if (!audioCtx) {
            try {
                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            } catch(e) {
                return null;
            }
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        return audioCtx;
    }

    var sound = {
        laser: function() {
            var ac = getAudioCtx();
            if (!ac) return;
            var osc = ac.createOscillator();
            var gain = ac.createGain();
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(600, ac.currentTime);
            osc.frequency.exponentialRampToValueAtTime(80, ac.currentTime + 0.1);
            gain.gain.setValueAtTime(0.15, ac.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.12);
            osc.connect(gain);
            gain.connect(ac.destination);
            osc.start(ac.currentTime);
            osc.stop(ac.currentTime + 0.12);
        },

        explosion: function(pitch) {
            var ac = getAudioCtx();
            if (!ac) return;
            pitch = pitch || 1;
            var bufferSize = ac.sampleRate * 0.3;
            var buffer = ac.createBuffer(1, bufferSize, ac.sampleRate);
            var data = buffer.getChannelData(0);
            for (var i = 0; i < bufferSize; i++) {
                data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / bufferSize, 2);
            }
            var noise = ac.createBufferSource();
            noise.buffer = buffer;
            var filter = ac.createBiquadFilter();
            filter.type = 'lowpass';
            filter.frequency.setValueAtTime(3000 * pitch, ac.currentTime);
            filter.frequency.exponentialRampToValueAtTime(100, ac.currentTime + 0.3);
            var gain = ac.createGain();
            gain.gain.setValueAtTime(0.3, ac.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.3);
            noise.connect(filter);
            filter.connect(gain);
            gain.connect(ac.destination);
            noise.start(ac.currentTime);
            noise.stop(ac.currentTime + 0.3);
        },

        hit: function() {
            var ac = getAudioCtx();
            if (!ac) return;
            var osc = ac.createOscillator();
            var gain = ac.createGain();
            osc.type = 'square';
            osc.frequency.setValueAtTime(150, ac.currentTime);
            osc.frequency.exponentialRampToValueAtTime(50, ac.currentTime + 0.06);
            gain.gain.setValueAtTime(0.2, ac.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.08);
            osc.connect(gain);
            gain.connect(ac.destination);
            osc.start(ac.currentTime);
            osc.stop(ac.currentTime + 0.08);
        },

        powerUp: function() {
            var ac = getAudioCtx();
            if (!ac) return;
            var osc = ac.createOscillator();
            var gain = ac.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(400, ac.currentTime);
            osc.frequency.exponentialRampToValueAtTime(800, ac.currentTime + 0.15);
            gain.gain.setValueAtTime(0.15, ac.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.2);
            osc.connect(gain);
            gain.connect(ac.destination);
            osc.start(ac.currentTime);
            osc.stop(ac.currentTime + 0.2);
        }
    };

    // ─── Score Manager ──────────────────────────────────────────────
    var floaters = [];
    var SCORES_KEY = 'chaosHighScores';

    var score = {
        _current: 0,
        _mode: '',
        _hudVisible: false,

        start: function(mode) {
            this._current = 0;
            this._mode = mode;
            this._hudVisible = true;
        },

        add: function(points, x, y) {
            this._current += points;
            if (x !== undefined && y !== undefined) {
                floaters.push({
                    text: '+' + points,
                    x: x,
                    y: y,
                    life: 1.0,
                    vy: -60
                });
            }
        },

        get: function() { return this._current; },

        getHighScore: function(mode) {
            try {
                var scores = JSON.parse(localStorage.getItem(SCORES_KEY) || '{}');
                return scores[mode || this._mode] || 0;
            } catch(e) { return 0; }
        },

        saveHighScore: function() {
            try {
                var scores = JSON.parse(localStorage.getItem(SCORES_KEY) || '{}');
                var mode = this._mode;
                if (this._current > (scores[mode] || 0)) {
                    scores[mode] = this._current;
                    localStorage.setItem(SCORES_KEY, JSON.stringify(scores));
                }
            } catch(e) {}
        },

        hide: function() {
            this._hudVisible = false;
        },

        _drawFloaters: function(ctx, dt) {
            for (var i = floaters.length - 1; i >= 0; i--) {
                var f = floaters[i];
                f.life -= dt;
                f.y += f.vy * dt;
                if (f.life <= 0) {
                    floaters.splice(i, 1);
                    continue;
                }
                ctx.save();
                ctx.globalAlpha = Math.max(0, f.life);
                ctx.font = 'bold 18px monospace';
                ctx.fillStyle = '#FFD700';
                ctx.strokeStyle = '#000';
                ctx.lineWidth = 2;
                ctx.strokeText(f.text, f.x, f.y);
                ctx.fillText(f.text, f.x, f.y);
                ctx.restore();
            }
        },

        _drawHUD: function(ctx) {
            if (!this._hudVisible) return;
            ctx.save();
            ctx.font = 'bold 16px monospace';
            ctx.textAlign = 'right';
            var x = ctx.canvas.width - 20;
            ctx.fillStyle = '#FF9900';
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 2;
            ctx.strokeText('SCORE: ' + this._current, x, 30);
            ctx.fillText('SCORE: ' + this._current, x, 30);
            var hi = this.getHighScore();
            if (hi > 0) {
                ctx.fillStyle = '#9999FF';
                ctx.strokeText('HIGH: ' + hi, x, 52);
                ctx.fillText('HIGH: ' + hi, x, 52);
            }
            ctx.restore();
        }
    };

    // ─── Screen Shake ───────────────────────────────────────────────
    var shakeTimer = null;

    var shake = {
        trigger: function(intensity, duration) {
            intensity = intensity || 10;
            duration = duration || 300;
            var start = Date.now();
            var body = document.body;
            var origTransform = body.style.transform || '';

            function doShake() {
                var elapsed = Date.now() - start;
                if (elapsed >= duration) {
                    body.style.transform = origTransform;
                    return;
                }
                var progress = elapsed / duration;
                var decay = 1 - progress;
                var dx = (Math.random() - 0.5) * 2 * intensity * decay;
                var dy = (Math.random() - 0.5) * 2 * intensity * decay;
                body.style.transform = 'translate3d(' + dx + 'px,' + dy + 'px,0)';
                shakeTimer = requestAnimationFrame(doShake);
            }
            doShake();
        }
    };

    // ─── Utilities ──────────────────────────────────────────────────
    function getElementCenter(el) {
        var r = el.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }

    function getElementRect(el) {
        return el.getBoundingClientRect();
    }

    function getComputedBgColor(el) {
        var bg = window.getComputedStyle(el).backgroundColor;
        if (!bg || bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') {
            return el.parentElement ? getComputedBgColor(el.parentElement) : '#888888';
        }
        return bg;
    }

    function rgbToHex(rgb) {
        if (rgb.charAt(0) === '#') return rgb;
        var match = rgb.match(/\d+/g);
        if (!match || match.length < 3) return '#888888';
        return '#' + match.slice(0, 3).map(function(n) {
            return ('0' + parseInt(n).toString(16)).slice(-2);
        }).join('');
    }

    // ─── Public API ─────────────────────────────────────────────────
    return {
        canvas: {
            init: initCanvas,
            destroy: destroyCanvas,
            get: getCanvas,
            getCtx: getCtx,
            addRenderCallback: addRenderCallback,
            removeRenderCallback: removeRenderCallback
        },
        particles: particles,
        sound: sound,
        score: score,
        shake: shake,
        util: {
            getElementCenter: getElementCenter,
            getElementRect: getElementRect,
            getComputedBgColor: getComputedBgColor,
            rgbToHex: rgbToHex
        }
    };
})();
